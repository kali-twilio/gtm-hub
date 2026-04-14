from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests as http
from flask import Blueprint, jsonify, request, session

bp = Blueprint("whatsapp_wizard", __name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

_DEV_BYPASS       = os.environ.get("WHATSAPP_DEV_BYPASS", "").lower() in ("1", "true")
_SANDBOX_NUMBER   = os.environ.get("TWILIO_WHATSAPP_SANDBOX_NUMBER", "+14155238886")
_META_APP_ID      = os.environ.get("META_APP_ID", "")
_META_APP_SECRET  = os.environ.get("META_APP_SECRET", "")
_META_GRAPH_VER   = os.environ.get("META_GRAPH_VERSION", "v21.0")
_META_CONFIG_ID   = os.environ.get("META_CONFIG_ID", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_path(email: str) -> Path:
    key = re.sub(r"[^a-z0-9]", "_", email.lower())
    return OUTPUT_DIR / f"ww_{key}.json"


def _load_state(email: str) -> dict:
    p = _state_path(email)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "steps": {
            "1": {"status": "pending", "data": {}},
            "2": {"status": "pending", "data": {}},
            "3": {"status": "pending", "data": {}},
            "4": {"status": "pending", "data": {}},
        },
        "twilio": {},
    }


def _save_state(email: str, state: dict) -> None:
    p = _state_path(email)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(p)


def _current_step(state: dict) -> int:
    """Return the lowest incomplete step (1–4), or 5 if all done."""
    for n in range(1, 5):
        if state["steps"][str(n)]["status"] != "complete":
            return n
    return 5


# ---------------------------------------------------------------------------
# GET /api/whatsapp-wizard/state
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/state")
def get_state():
    email = session.get("user_email", "")
    state = _load_state(email)
    return jsonify({
        "current_step":  _current_step(state),
        "steps":         state["steps"],
        "dev_bypass":    _DEV_BYPASS,
        "sandbox_number": _SANDBOX_NUMBER,
        "meta_app_id":   _META_APP_ID,
        "meta_config_id": _META_CONFIG_ID,
    })


# ---------------------------------------------------------------------------
# POST /api/whatsapp-wizard/step1  — Connect Twilio Account
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/step1", methods=["POST"])
def step1():
    email = session.get("user_email", "")
    body  = request.get_json(silent=True) or {}
    sid   = (body.get("account_sid") or "").strip()
    token = (body.get("auth_token")  or "").strip()

    if not sid.startswith("AC") or len(token) < 32:
        return jsonify({"error": "Invalid Account SID or Auth Token format."}), 400

    # Validate via Twilio REST API
    try:
        r = http.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
            auth=(sid, token),
            timeout=10,
        )
    except Exception as exc:
        return jsonify({"error": f"Network error: {exc}"}), 502

    if r.status_code == 401:
        return jsonify({"error": "Invalid credentials — check your Account SID and Auth Token."}), 400
    if not r.ok:
        return jsonify({"error": f"Twilio returned {r.status_code}."}), 400

    data          = r.json()
    friendly_name = data.get("friendly_name", sid)

    state = _load_state(email)
    state["twilio"] = {"account_sid": sid, "auth_token": token, "friendly_name": friendly_name}
    state["steps"]["1"] = {
        "status": "complete",
        "data":   {"friendly_name": friendly_name, "account_sid": sid},
        "completed_at": int(time.time()),
    }
    _save_state(email, state)
    return jsonify({"friendly_name": friendly_name})


# ---------------------------------------------------------------------------
# POST /api/whatsapp-wizard/step2/bypass  — Dev bypass for Meta
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/step2/bypass", methods=["POST"])
def step2_bypass():
    if not _DEV_BYPASS:
        return jsonify({"error": "Dev bypass is not enabled."}), 403

    email = session.get("user_email", "")
    state = _load_state(email)

    if state["steps"]["1"]["status"] != "complete":
        return jsonify({"error": "Complete step 1 first."}), 400

    state["steps"]["2"] = {
        "status": "complete",
        "data": {
            "waba_id":         "sandbox-waba-dev",
            "phone_number_id": "sandbox-phone-id-dev",
            "sandbox":         True,
        },
        "completed_at": int(time.time()),
    }
    _save_state(email, state)
    return jsonify({"waba_id": "sandbox-waba-dev", "sandbox": True})


# ---------------------------------------------------------------------------
# POST /api/whatsapp-wizard/step2/callback  — Meta Embedded Signup (production)
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/step2/callback", methods=["POST"])
def step2_callback():
    email = session.get("user_email", "")
    body  = request.get_json(silent=True) or {}
    code  = (body.get("code") or "").strip()

    if not code:
        return jsonify({"error": "Missing code."}), 400
    if not _META_APP_ID or not _META_APP_SECRET:
        return jsonify({"error": "Meta app not configured on server."}), 500

    try:
        # 1. Exchange code for short-lived token
        r1 = http.get(
            f"https://graph.facebook.com/{_META_GRAPH_VER}/oauth/access_token",
            params={"client_id": _META_APP_ID, "client_secret": _META_APP_SECRET, "code": code},
            timeout=10,
        )
        r1.raise_for_status()
        user_token = r1.json()["access_token"]

        # 2. Exchange for long-lived token
        r2 = http.get(
            f"https://graph.facebook.com/{_META_GRAPH_VER}/oauth/access_token",
            params={
                "grant_type":        "fb_exchange_token",
                "client_id":         _META_APP_ID,
                "client_secret":     _META_APP_SECRET,
                "fb_exchange_token": user_token,
            },
            timeout=10,
        )
        r2.raise_for_status()
        long_token = r2.json()["access_token"]

        # 3. Debug token to get WABA ID
        r3 = http.get(
            f"https://graph.facebook.com/{_META_GRAPH_VER}/debug_token",
            params={
                "input_token":  long_token,
                "access_token": f"{_META_APP_ID}|{_META_APP_SECRET}",
            },
            timeout=10,
        )
        r3.raise_for_status()
        debug = r3.json()
        granular = debug.get("data", {}).get("granular_scopes", [])
        waba_scope = next((s for s in granular if s.get("scope") == "whatsapp_business_management"), None)
        waba_id = (waba_scope or {}).get("target_ids", [None])[0]

        if not waba_id:
            return jsonify({"error": "No WhatsApp Business Account found in token scopes."}), 400

        # 4. Get phone number IDs for WABA
        r4 = http.get(
            f"https://graph.facebook.com/{_META_GRAPH_VER}/{waba_id}/phone_numbers",
            params={"access_token": long_token},
            timeout=10,
        )
        r4.raise_for_status()
        phones         = r4.json().get("data", [])
        phone_number_id = phones[0]["id"] if phones else None

    except Exception as exc:
        return jsonify({"error": f"Meta API error: {exc}"}), 502

    state = _load_state(email)
    state["steps"]["2"] = {
        "status": "complete",
        "data": {
            "waba_id":         waba_id,
            "phone_number_id": phone_number_id,
            "access_token":    long_token,
            "sandbox":         False,
        },
        "completed_at": int(time.time()),
    }
    _save_state(email, state)
    return jsonify({"waba_id": waba_id, "phone_number_id": phone_number_id})


# ---------------------------------------------------------------------------
# GET /api/whatsapp-wizard/step3/numbers  — List ISV's phone numbers
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/step3/numbers")
def step3_numbers():
    email = session.get("user_email", "")
    state = _load_state(email)

    twilio = state.get("twilio", {})
    sid    = twilio.get("account_sid", "")
    token  = twilio.get("auth_token",  "")

    if not sid or not token:
        return jsonify({"error": "No Twilio account connected. Complete step 1 first."}), 400

    try:
        r = http.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
            auth=(sid, token),
            params={"PageSize": 50},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as exc:
        return jsonify({"error": f"Twilio error: {exc}"}), 502

    numbers = [
        {
            "sid":           n["sid"],
            "phone_number":  n["phone_number"],
            "friendly_name": n["friendly_name"],
        }
        for n in r.json().get("incoming_phone_numbers", [])
    ]
    return jsonify({"numbers": numbers})


# ---------------------------------------------------------------------------
# POST /api/whatsapp-wizard/step3/sandbox  — Use Twilio sandbox number
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/step3/sandbox", methods=["POST"])
def step3_sandbox():
    if not _DEV_BYPASS:
        return jsonify({"error": "Dev bypass is not enabled."}), 403

    email = session.get("user_email", "")
    state = _load_state(email)

    if state["steps"]["2"]["status"] != "complete":
        return jsonify({"error": "Complete step 2 first."}), 400

    state["steps"]["3"] = {
        "status": "complete",
        "data":   {"phone_number": _SANDBOX_NUMBER, "sandbox": True},
        "completed_at": int(time.time()),
    }
    _save_state(email, state)
    return jsonify({"phone_number": _SANDBOX_NUMBER, "sandbox": True})


# ---------------------------------------------------------------------------
# POST /api/whatsapp-wizard/step3/register  — Register WhatsApp sender
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/step3/register", methods=["POST"])
def step3_register():
    email = session.get("user_email", "")
    body  = request.get_json(silent=True) or {}
    state = _load_state(email)

    selected_sid  = (body.get("phone_number_sid") or "").strip()
    selected_num  = (body.get("phone_number")     or "").strip()

    if not selected_sid:
        return jsonify({"error": "No phone number selected."}), 400

    step2_data = state["steps"]["2"].get("data", {})
    waba_id    = step2_data.get("waba_id")
    ph_id      = step2_data.get("phone_number_id")
    is_sandbox = waba_id == "sandbox-waba-dev"

    if not is_sandbox:
        twilio = state.get("twilio", {})
        sid    = twilio.get("account_sid", "")
        token  = twilio.get("auth_token",  "")

        try:
            r = http.post(
                "https://messaging.twilio.com/v1/Channels/WhatsApp/Senders",
                auth=(sid, token),
                data={
                    "PhoneNumberSid": selected_sid,
                    "WabaId":         waba_id,
                    "PhoneNumberId":  ph_id,
                },
                timeout=15,
            )
            if not r.ok:
                err = r.json().get("message", r.text)
                return jsonify({"error": err}), 400
        except Exception as exc:
            return jsonify({"error": f"Twilio error: {exc}"}), 502

    state["steps"]["3"] = {
        "status": "complete",
        "data":   {"phone_number": selected_num, "phone_number_sid": selected_sid, "sandbox": is_sandbox},
        "completed_at": int(time.time()),
    }
    _save_state(email, state)
    return jsonify({"phone_number": selected_num})


# ---------------------------------------------------------------------------
# POST /api/whatsapp-wizard/step4/profile  — Save business profile
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/step4/profile", methods=["POST"])
def step4_profile():
    email = session.get("user_email", "")
    body  = request.get_json(silent=True) or {}
    state = _load_state(email)

    display_name = (body.get("display_name") or "").strip()
    description  = (body.get("description")  or "").strip()
    address      = (body.get("address")      or "").strip()

    if not display_name:
        return jsonify({"error": "Display name is required."}), 400

    step2_data = state["steps"]["2"].get("data", {})
    step3_data = state["steps"]["3"].get("data", {})
    is_sandbox = step2_data.get("waba_id") == "sandbox-waba-dev"

    if not is_sandbox:
        twilio = state.get("twilio", {})
        sid    = twilio.get("account_sid", "")
        token  = twilio.get("auth_token",  "")
        phone  = step3_data.get("phone_number", "")

        try:
            payload = {"PhoneNumber": phone, "DisplayName": display_name}
            if description:
                payload["Description"] = description
            if address:
                payload["Address"] = address

            r = http.post(
                "https://messaging.twilio.com/v1/Channels/WhatsApp/BusinessProfiles",
                auth=(sid, token),
                data=payload,
                timeout=15,
            )
            if not r.ok:
                err = r.json().get("message", r.text)
                return jsonify({"error": err}), 400
        except Exception as exc:
            return jsonify({"error": f"Twilio error: {exc}"}), 502

    # Merge profile into step 4 data
    step4 = state["steps"]["4"]
    existing = step4.get("data", {})
    existing["profile"] = {
        "display_name": display_name,
        "description":  description,
        "address":      address,
        "saved":        True,
    }
    step4["data"] = existing
    if existing.get("profile", {}).get("saved") and existing.get("template", {}).get("saved"):
        step4["status"]       = "complete"
        step4["completed_at"] = int(time.time())
    state["steps"]["4"] = step4
    _save_state(email, state)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# POST /api/whatsapp-wizard/step4/template  — Create message template
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/step4/template", methods=["POST"])
def step4_template():
    email = session.get("user_email", "")
    body  = request.get_json(silent=True) or {}
    state = _load_state(email)

    name     = (body.get("name")     or "").strip().lower()
    category = (body.get("category") or "UTILITY").strip().upper()
    language = (body.get("language") or "en_US").strip()
    tmpl_body = (body.get("body")    or "").strip()

    if not name or not tmpl_body:
        return jsonify({"error": "Template name and body are required."}), 400
    if not re.match(r"^[a-z0-9_]+$", name):
        return jsonify({"error": "Template name must be lowercase letters, numbers, and underscores only."}), 400

    step2_data = state["steps"]["2"].get("data", {})
    is_sandbox = step2_data.get("waba_id") == "sandbox-waba-dev"

    twilio_sid    = None
    meta_status   = "pending"

    if not is_sandbox:
        twilio = state.get("twilio", {})
        sid    = twilio.get("account_sid", "")
        token  = twilio.get("auth_token",  "")

        try:
            payload = {
                "friendly_name": name,
                "language":      language,
                "variables":     json.dumps({"1": "placeholder"}),
                "types":         json.dumps({
                    "twilio/text": {"body": tmpl_body},
                }),
            }
            r = http.post(
                "https://content.twilio.com/v1/Content",
                auth=(sid, token),
                json=payload,
                timeout=15,
            )
            if not r.ok:
                err = r.json().get("message", r.text)
                return jsonify({"error": err}), 400

            result     = r.json()
            twilio_sid = result.get("sid")
            meta_status = (result.get("approval_requests") or {}).get("status", "pending")
        except Exception as exc:
            return jsonify({"error": f"Twilio error: {exc}"}), 502

    step4 = state["steps"]["4"]
    existing = step4.get("data", {})
    existing["template"] = {
        "name":        name,
        "category":    category,
        "language":    language,
        "body":        tmpl_body,
        "twilio_sid":  twilio_sid,
        "meta_status": meta_status,
        "saved":       True,
    }
    step4["data"] = existing
    if existing.get("profile", {}).get("saved") and existing.get("template", {}).get("saved"):
        step4["status"]       = "complete"
        step4["completed_at"] = int(time.time())
    state["steps"]["4"] = step4
    _save_state(email, state)
    return jsonify({"twilio_sid": twilio_sid, "meta_status": meta_status})


# ---------------------------------------------------------------------------
# POST /api/whatsapp-wizard/reset  — Reset state (dev only)
# ---------------------------------------------------------------------------

@bp.route("/api/whatsapp-wizard/reset", methods=["POST"])
def reset():
    if not _DEV_BYPASS:
        return jsonify({"error": "Only available in dev mode."}), 403
    email = session.get("user_email", "")
    p = _state_path(email)
    if p.exists():
        p.unlink()
    return jsonify({"ok": True})
