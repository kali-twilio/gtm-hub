"""Twilio SMS/WhatsApp webhook Blueprint — shared across all apps."""
from __future__ import annotations
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import requests as http_requests
from flask import Blueprint, Response, request

from suggestions import (
    get_firestore,
    display_author,
    FIRESTORE_COLLECTION,
    FIRESTORE_SMS_PENDING,
    SUGGESTIONS_MAX,
)

log = logging.getLogger(__name__)

sms_bp = Blueprint("sms", __name__)

_TWILIO_ACCOUNT_SID  = os.environ.get("TWILIO_ACCOUNT_SID")
_TWILIO_AUTH_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN")
_TWILIO_PHONE_NUMBER = "+18446990268"

_SMS_RL_LIMIT  = 100
_SMS_RL_WINDOW = 3600
_sms_rl_store: dict[str, list[float]] = {}

_SMS_CONFIRM_TTL = 300


# ── Firestore pending-state helpers ──────────────────────────────────────────

def _sms_pending_get(db, key: str) -> dict | None:
    doc = db.collection(FIRESTORE_SMS_PENDING).document(key).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    if time.time() > data.get("expires_at", 0):
        db.collection(FIRESTORE_SMS_PENDING).document(key).delete()
        return None
    return data


def _sms_pending_set(db, key: str, data: dict):
    data["expires_at"] = time.time() + _SMS_CONFIRM_TTL
    db.collection(FIRESTORE_SMS_PENDING).document(key).set(data)


def _sms_pending_delete(db, key: str):
    db.collection(FIRESTORE_SMS_PENDING).document(key).delete()


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _sms_rate_limited(phone: str) -> bool:
    now    = time.monotonic()
    cutoff = now - _SMS_RL_WINDOW
    ts     = _sms_rl_store.setdefault(phone, [])
    while ts and ts[0] < cutoff:
        ts.pop(0)
    if len(ts) >= _SMS_RL_LIMIT:
        return True
    ts.append(now)
    return False


# ── Twilio Lookup ─────────────────────────────────────────────────────────────

def _lookup_phone(phone: str) -> dict:
    result = {"caller_name": None, "is_mobile": True}
    if not (_TWILIO_ACCOUNT_SID and _TWILIO_AUTH_TOKEN):
        return result
    try:
        resp = http_requests.get(
            f"https://lookups.twilio.com/v2/PhoneNumbers/{phone}",
            params={"Fields": "caller_name,line_type_intelligence"},
            auth=(_TWILIO_ACCOUNT_SID, _TWILIO_AUTH_TOKEN),
            timeout=5,
        )
        if resp.ok:
            data = resp.json()
            name = (data.get("caller_name") or {}).get("caller_name")
            if name and name.strip():
                result["caller_name"] = name.strip().title()
            line_type = (data.get("line_type_intelligence") or {}).get("type", "")
            if line_type and line_type not in ("mobile", "prepaid", ""):
                result["is_mobile"] = False
                log.info("Lookup: %s is line_type=%s — rejecting", phone, line_type)
    except Exception as e:
        log.warning("Twilio Lookup failed for %s: %s", phone, e)
    return result


# ── TwiML helpers ─────────────────────────────────────────────────────────────

def _twiml_reply(message: str) -> Response:
    import xml.sax.saxutils as saxutils
    safe  = saxutils.escape(message)
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'
    return Response(twiml, mimetype="text/xml")


def _twiml_empty() -> Response:
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', mimetype="text/xml")


# ── Webhook route ─────────────────────────────────────────────────────────────

@sms_bp.route("/api/sms", methods=["POST"])
def api_sms_webhook():
    """Twilio SMS/WhatsApp webhook — command interface for suggestions.

    Commands (case-insensitive):
      LIST             — receive all suggestions with authors
      DELETE <n>       — delete one of your own suggestions by list index
      DELETE ALL       — delete all of your suggestions
      <anything else>  — saved as a new suggestion

    Security:
      1. HMAC-SHA1 signature validation
      2. Mobile-only via Lookup line_type_intelligence (blocks landlines/VoIP)
      3. Per-phone rate limiting (SMS pump protection)
    """
    _local_dev = os.environ.get("LOCAL_DEV") == "1"

    # ── 1. Signature validation ───────────────────────────────────────────────
    if _TWILIO_AUTH_TOKEN and not _local_dev:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(_TWILIO_AUTH_TOKEN)
        _frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
        url = f"{_frontend}/api/sms"
        sig = request.headers.get("X-Twilio-Signature", "")
        log.info("Twilio sig check — url=%s sig=%s", url, sig[:16] if sig else "missing")
        if not validator.validate(url, request.form, sig):
            log.warning("Twilio signature validation failed — url=%s", url)
            return "Forbidden", 403

    raw_from = request.form.get("From", "").strip()
    body     = request.form.get("Body", "").strip()

    if not raw_from or not body:
        return _twiml_reply("No message body received.")

    is_whatsapp = raw_from.lower().startswith("whatsapp:")
    from_number = raw_from[len("whatsapp:"):] if is_whatsapp else raw_from
    channel     = "whatsapp" if is_whatsapp else "sms"
    pending_key = f"{channel}:{from_number}"

    # ── 2. Rate limiting ──────────────────────────────────────────────────────
    if _sms_rate_limited(from_number):
        log.warning("%s rate limit exceeded for %s", channel, from_number)
        return _twiml_reply("You've sent too many messages. Please wait an hour before trying again.")

    # ── 3. Lookup: verify mobile number + get caller name ────────────────────
    lookup = ({"caller_name": None, "is_mobile": True} if (is_whatsapp or _local_dev)
              else _lookup_phone(from_number))
    if not lookup["is_mobile"]:
        log.info("SMS from non-mobile %s — ignoring silently", from_number)
        return _twiml_empty()

    db = get_firestore()
    if db is None:
        log.error("Firestore unavailable for SMS from %s", from_number)
        return _twiml_reply("Sorry, storage is unavailable right now. Please try again later.")

    cmd = body.strip().upper()

    def _load_all_docs():
        return list(db.collection(FIRESTORE_COLLECTION)
                      .order_by("created_at", direction="DESCENDING").stream())

    def _format_list(docs):
        if not docs:
            return "No suggestions yet."
        lines = []
        for i, doc in enumerate(docs, 1):
            s      = doc.to_dict()
            author = display_author(s)
            text   = s.get("text", "")[:60]
            suffix = "..." if len(s.get("text", "")) > 60 else ""
            mine   = " *" if s.get("phone") == from_number else ""
            lines.append(f"{i}. [{author}]{mine} {text}{suffix}")
        return "\n".join(lines)

    def _save_suggestion(text, caller_name, app_id):
        all_docs = _load_all_docs()
        if len(all_docs) >= SUGGESTIONS_MAX:
            return None, "Sorry, we've reached our suggestion limit. Thank you for your interest!"
        doc_id     = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        doc = {"phone": from_number, "text": text, "source": channel, "created_at": created_at}
        if caller_name:
            doc["caller_name"] = caller_name
        if app_id:
            doc["app"] = app_id
        db.collection(FIRESTORE_COLLECTION).document(doc_id).set(doc)
        log.info("SMS suggestion saved from %s app=%s", from_number, app_id)
        updated = _load_all_docs()
        reply = "Saved! Here are all suggestions (* = yours). Reply DELETE 1,2 to remove yours:\n\n" + _format_list(updated)
        return reply, None

    import importlib as _il
    try:
        _app_mod  = _il.import_module("app")
        _live_apps = _app_mod._get_live_apps()
    except Exception:
        _live_apps = [
            {"id": "gtm-hub",         "name": "GTM Hub"},
            {"id": "se-scorecard-v2", "name": "SE Scorecard V2"},
            {"id": "se-forecast",     "name": "SE Forecast"},
        ]

    def _app_menu():
        lines = ["Which app is your feedback for? Reply with a number:"]
        for i, a in enumerate(_live_apps, 1):
            lines.append(f"{i}. {a['name']}")
        return "\n".join(lines)

    # ── Multi-step flow ───────────────────────────────────────────────────────
    state = _sms_pending_get(db, pending_key)
    if state is not None:
        if state["stage"] == "confirm_app":
            caller_name  = state["caller_name"]
            pending_text = state["pending_text"]
            try:
                choice = int(body.strip()) - 1
                if choice < 0 or choice >= len(_live_apps):
                    raise ValueError
            except (ValueError, TypeError):
                return _twiml_reply(_app_menu())
            selected_app  = _live_apps[choice]["id"]
            selected_name = _live_apps[choice]["name"]
            preview = pending_text[:80] + ("..." if len(pending_text) > 80 else "")
            _sms_pending_set(db, pending_key, {
                "stage":         "confirm",
                "caller_name":   caller_name,
                "pending_text":  pending_text,
                "selected_app":  selected_app,
                "selected_name": selected_name,
            })
            return _twiml_reply(f'Save to {selected_name}?\n\n"{preview}"\n\nReply Y to confirm or N to cancel.')
        elif state["stage"] == "confirm":
            caller_name   = state["caller_name"]
            pending_text  = state["pending_text"]
            selected_app  = state["selected_app"]
            selected_name = state["selected_name"]
            answer = body.strip().upper()
            if answer in ("Y", "YES"):
                _sms_pending_delete(db, pending_key)
                try:
                    reply, err = _save_suggestion(pending_text, caller_name, selected_app)
                    if err:
                        return _twiml_reply(err)
                    return _twiml_reply(reply)
                except Exception as e:
                    log.error("Firestore SMS save failed: %s", e)
                    return _twiml_reply("Sorry, something went wrong. Please try again.")
            elif answer in ("N", "NO"):
                _sms_pending_delete(db, pending_key)
                return _twiml_reply("Cancelled. Send a new message any time to leave feedback.")
            else:
                preview = pending_text[:80] + ("..." if len(pending_text) > 80 else "")
                return _twiml_reply(f'Reply Y to confirm or N to cancel.\n\n"{preview}"')

    # ── DELETE ────────────────────────────────────────────────────────────────
    if cmd.startswith("DELETE"):
        arg = body.strip()[6:].strip()
        try:
            docs = _load_all_docs()
            if arg.upper() == "ALL":
                mine = [d for d in docs if d.to_dict().get("phone") == from_number]
                if not mine:
                    return _twiml_reply("You have no suggestions to delete.")
                for d in mine:
                    db.collection(FIRESTORE_COLLECTION).document(d.id).delete()
                log.info("SMS DELETE ALL: removed %d for %s", len(mine), from_number)
                updated = _load_all_docs()
                reply = f"Deleted all {len(mine)} of your suggestion{'s' if len(mine) != 1 else ''}.\n\n" + _format_list(updated)
                return _twiml_reply(reply)

            try:
                indices = [int(x.strip()) - 1 for x in arg.split(",") if x.strip()]
                if not indices:
                    raise ValueError
            except ValueError:
                return _twiml_reply("Usage: DELETE 1  or  DELETE 1,2,3  or  DELETE ALL")

            errors, deleted = [], []
            for idx in sorted(set(indices)):
                if idx < 0 or idx >= len(docs):
                    errors.append(f"#{idx+1} doesn't exist")
                    continue
                d = docs[idx]
                if d.to_dict().get("phone") != from_number:
                    errors.append(f"#{idx+1} isn't yours")
                    continue
                db.collection(FIRESTORE_COLLECTION).document(d.id).delete()
                deleted.append(idx + 1)

            log.info("SMS DELETE %s by %s — deleted=%s errors=%s", arg, from_number, deleted, errors)
            parts = []
            if deleted:
                parts.append(f"Deleted #{', #'.join(str(n) for n in deleted)}.")
            if errors:
                parts.append("Skipped: " + "; ".join(errors) + ".")
            updated = _load_all_docs()
            return _twiml_reply(" ".join(parts) + "\n\n" + _format_list(updated))

        except Exception as e:
            log.error("Firestore delete (SMS) failed: %s", e)
            return _twiml_reply("Failed to delete suggestion.")

    # ── SUBMIT (default) ──────────────────────────────────────────────────────
    if len(body) > 1000:
        return _twiml_reply("Your message is too long (max 1000 characters). Please shorten it and try again.")

    _sms_pending_set(db, pending_key, {
        "stage":        "confirm_app",
        "caller_name":  lookup["caller_name"],
        "pending_text": body,
    })
    return _twiml_reply(_app_menu())
