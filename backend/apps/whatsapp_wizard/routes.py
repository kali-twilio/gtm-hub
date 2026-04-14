"""
WhatsApp Wizard — Flask Blueprint
Ported from Laravel/Livewire by Andre Vieira (avieira-twilio/whatsapp-wizard).

Wizard steps:
  1. Connect Twilio account (SID + Auth Token)
  2. Meta Embedded Signup (WABA via Facebook OAuth)
  3. Phone number registration (pick + register a Twilio number)
  4. Business profile + first message template

Admin endpoints (sf_access == 'full') let managers see all users' progress.
"""
from __future__ import annotations

import json
import logging
import os
import re

import requests as http
from flask import Blueprint, jsonify, request, session, current_app

from .db import (
    init_db,
    get_account, upsert_account,
    get_step, get_steps, upsert_step,
    get_senders, upsert_sender,
    get_profile, upsert_profile,
    get_templates, insert_template,
    all_users_summary,
    encrypt_token, decrypt_token,
)

log = logging.getLogger(__name__)

bp = Blueprint("whatsapp_wizard", __name__, url_prefix="/api/whatsapp-wizard")

# Initialise DB tables on first import
init_db()

_local_dev = os.environ.get("LOCAL_DEV") == "1"

STEP_LABELS = {
    1: "Connect Twilio Account",
    2: "Link WhatsApp Business Account",
    3: "Register Phone Number",
    4: "Business Profile & Template",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _email() -> str:
    return session["user_email"]


def _secret() -> str:
    return current_app.secret_key


def _is_admin() -> bool:
    return session.get("sf_access", "full") == "full"


def _twilio_client(account_sid: str, auth_token: str):
    """Return a minimal Twilio REST helper (avoids hard dependency on twilio SDK)."""
    try:
        from twilio.rest import Client
        return Client(account_sid, auth_token)
    except ImportError:
        return None


def _validate_twilio(sid: str, token: str) -> tuple[bool, str | None]:
    """Return (valid, friendly_name)."""
    client = _twilio_client(sid, token)
    if client is None:
        # Twilio SDK not installed — can still validate via REST
        r = http.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
            auth=(sid, token), timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("status") in ("active", "suspended"), data.get("friendly_name")
        return False, None
    try:
        acct = client.api.v2010.account.fetch()
        ok = acct.status in ("active", "suspended")
        return ok, acct.friendly_name if ok else None
    except Exception:
        return False, None


def _list_phone_numbers(sid: str, token: str) -> list[dict]:
    client = _twilio_client(sid, token)
    if client:
        try:
            nums = client.incoming_phone_numbers.list(limit=50)
            return [{"sid": n.sid, "phone_number": n.phone_number,
                     "friendly_name": n.friendly_name} for n in nums]
        except Exception:
            pass
    # Fallback: REST
    r = http.get(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
        auth=(sid, token), params={"PageSize": 50}, timeout=15,
    )
    if r.ok:
        return [{"sid": n["sid"], "phone_number": n["phone_number"],
                 "friendly_name": n["friendly_name"]}
                for n in r.json().get("incoming_phone_numbers", [])]
    return []


def _register_whatsapp(sid: str, token: str, phone_sid: str,
                       waba_id: str, phone_number_id: str) -> dict:
    client = _twilio_client(sid, token)
    if client:
        try:
            resp = client.request("POST",
                "https://messaging.twilio.com/v1/Channels/WhatsApp/Senders",
                {"PhoneNumberSid": phone_sid, "WabaId": waba_id,
                 "PhoneNumberId": phone_number_id})
            content = resp.get_content()
            return content if isinstance(content, dict) else {"raw": str(content)}
        except Exception as e:
            return {"error": str(e)}
    r = http.post(
        "https://messaging.twilio.com/v1/Channels/WhatsApp/Senders",
        auth=(sid, token),
        data={"PhoneNumberSid": phone_sid, "WabaId": waba_id,
              "PhoneNumberId": phone_number_id},
        timeout=20,
    )
    return r.json() if r.ok else {"error": r.text}


def _create_template(sid: str, token: str, name: str, body: str, language: str) -> dict:
    """Create a WhatsApp message template via Twilio Content API."""
    payload = {
        "friendly_name": name,
        "language": language,
        "variables": {"1": "placeholder"},
        "types": {"twilio/text": {"body": body}},
    }
    r = http.post(
        "https://content.twilio.com/v1/Content",
        auth=(sid, token),
        json=payload,
        timeout=20,
    )
    if r.ok:
        data = r.json()
        return {"sid": data.get("sid"),
                "status": data.get("approval_requests", {}).get("status", "pending")}
    return {"error": r.text}


def _update_business_profile(sid: str, token: str, phone_number: str, data: dict) -> dict:
    payload = {k: v for k, v in {
        "PhoneNumber": phone_number,
        "DisplayName": data.get("display_name"),
        "Description": data.get("description"),
        "Address": data.get("address"),
        "LogoUrl": data.get("logo_url"),
    }.items() if v}
    r = http.post(
        "https://messaging.twilio.com/v1/Channels/WhatsApp/BusinessProfiles",
        auth=(sid, token), data=payload, timeout=20,
    )
    return r.json() if r.ok else {"error": r.text}


def _exchange_meta_token(code: str) -> dict:
    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")
    graph_version = os.environ.get("META_GRAPH_VERSION", "v21.0")
    base = f"https://graph.facebook.com/{graph_version}"

    # 1. Exchange code for short-lived token
    r = http.get(f"{base}/oauth/access_token", params={
        "client_id": app_id, "client_secret": app_secret, "code": code,
    }, timeout=15)
    if not r.ok:
        return {"error": r.json().get("error", {}).get("message", r.text)}
    user_token = r.json()["access_token"]

    # 2. Extend to long-lived token
    r = http.get(f"{base}/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": user_token,
    }, timeout=15)
    if not r.ok:
        return {"error": r.json().get("error", {}).get("message", r.text)}
    long_token = r.json()["access_token"]

    # 3. Find WABA from token debug info
    r = http.get(f"{base}/debug_token", params={
        "input_token": long_token,
        "access_token": f"{app_id}|{app_secret}",
    }, timeout=15)
    if not r.ok:
        return {"error": "Could not inspect token"}
    scopes = r.json().get("data", {}).get("granular_scopes", [])
    waba_scope = next((s for s in scopes if s.get("scope") == "whatsapp_business_management"), None)
    waba_id = (waba_scope or {}).get("target_ids", [None])[0]
    if not waba_id:
        return {"error": "No WhatsApp Business Account found in token."}

    # 4. Get phone number ID from WABA
    r = http.get(f"{base}/{waba_id}/phone_numbers",
                 params={"access_token": long_token}, timeout=15)
    phone_number_id = None
    if r.ok:
        phone_number_id = (r.json().get("data") or [{}])[0].get("id")

    return {"waba_id": waba_id, "phone_number_id": phone_number_id,
            "access_token": long_token}


# ── Status ────────────────────────────────────────────────────────────────────

@bp.get("/status")
def wizard_status():
    email = _email()
    steps = get_steps(email)
    account = get_account(email)
    senders = get_senders(email)
    profile = get_profile(email)
    templates = get_templates(email)

    completed = [n for n, s in steps.items() if s["status"] == "complete"]
    # First incomplete step (1-4), or 4 if all done
    current = next((i for i in range(1, 5) if i not in completed), 4)

    return jsonify({
        "current_step": current,
        "completed_steps": completed,
        "account": {"sid": account["account_sid"],
                    "friendly_name": account["friendly_name"]} if account else None,
        "senders": senders,
        "profile": profile,
        "templates": templates,
        "meta_app_id": os.environ.get("META_APP_ID", ""),
        "meta_config_id": os.environ.get("META_CONFIG_ID", ""),
        "dev_bypass": _local_dev,
    })


# ── Step 1: Connect Twilio account ────────────────────────────────────────────

@bp.post("/step/1")
def step1_connect():
    body = request.get_json(force=True) or {}
    sid = (body.get("account_sid") or "").strip()
    token = (body.get("auth_token") or "").strip()

    if not sid.startswith("AC") or len(token) < 32:
        return jsonify({"error": "Invalid Account SID or Auth Token format."}), 422

    valid, name = _validate_twilio(sid, token)
    if not valid:
        return jsonify({"error": "Could not validate these credentials. Check your Account SID and Auth Token."}), 422

    email = _email()
    upsert_account(email, sid, encrypt_token(token, _secret()), name)
    upsert_step(email, 1, "complete")
    return jsonify({"friendly_name": name})


# ── Step 2: Meta Embedded Signup ─────────────────────────────────────────────

@bp.post("/step/2/meta-callback")
def step2_meta_callback():
    body = request.get_json(force=True) or {}
    code = (body.get("code") or "").strip()
    if not code:
        return jsonify({"error": "Missing OAuth code."}), 422

    result = _exchange_meta_token(code)
    if "error" in result:
        return jsonify({"error": result["error"]}), 422

    email = _email()
    upsert_step(email, 2, "complete", {
        "waba_id": result["waba_id"],
        "phone_number_id": result["phone_number_id"],
        "access_token_enc": encrypt_token(result["access_token"], _secret()),
    })
    return jsonify({"waba_id": result["waba_id"]})


@bp.post("/step/2/bypass")
def step2_bypass():
    if not _local_dev:
        return jsonify({"error": "Not available"}), 404
    email = _email()
    upsert_step(email, 2, "complete", {
        "waba_id": "sandbox-waba-dev",
        "phone_number_id": "sandbox-phone-id-dev",
        "sandbox": True,
    })
    return jsonify({"waba_id": "sandbox-waba-dev"})


# ── Step 3: Phone number registration ────────────────────────────────────────

@bp.get("/step/3/numbers")
def step3_numbers():
    email = _email()
    account = get_account(email)
    if not account:
        return jsonify({"error": "No Twilio account connected. Complete step 1 first."}), 422
    token = decrypt_token(account["auth_token_enc"], _secret())
    numbers = _list_phone_numbers(account["account_sid"], token)
    return jsonify({"numbers": numbers})


@bp.post("/step/3/register")
def step3_register():
    body = request.get_json(force=True) or {}
    selected_sid = (body.get("phone_sid") or "").strip()
    if not selected_sid:
        return jsonify({"error": "No phone number selected."}), 422

    email = _email()
    account = get_account(email)
    step2 = get_step(email, 2)
    if not account or not step2:
        return jsonify({"error": "Please complete previous steps first."}), 422

    token = decrypt_token(account["auth_token_enc"], _secret())
    numbers = _list_phone_numbers(account["account_sid"], token)
    num_data = next((n for n in numbers if n["sid"] == selected_sid), None)
    if not num_data:
        return jsonify({"error": "Selected number not found."}), 422

    waba_id = step2["metadata"].get("waba_id")
    phone_number_id = step2["metadata"].get("phone_number_id")
    is_sandbox = waba_id in ("sandbox-waba-dev", None)

    if not is_sandbox:
        result = _register_whatsapp(
            account["account_sid"], token, selected_sid, waba_id, phone_number_id
        )
        if "error" in result:
            return jsonify({"error": result["error"]}), 422

    upsert_sender(email, num_data["phone_number"], selected_sid, waba_id or "", "active")
    upsert_step(email, 3, "complete", {"phone_number": num_data["phone_number"]})
    return jsonify({"phone_number": num_data["phone_number"]})


@bp.post("/step/3/bypass")
def step3_bypass():
    if not _local_dev:
        return jsonify({"error": "Not available"}), 404
    sandbox_number = os.environ.get("TWILIO_WHATSAPP_SANDBOX_NUMBER", "+14155238886")
    email = _email()
    upsert_sender(email, sandbox_number, "sandbox", "sandbox-waba-dev", "sandbox")
    upsert_step(email, 3, "complete", {"phone_number": sandbox_number, "sandbox": True})
    return jsonify({"phone_number": sandbox_number})


# ── Step 4: Business profile + template ──────────────────────────────────────

@bp.post("/step/4/profile")
def step4_profile():
    body = request.get_json(force=True) or {}
    display_name = (body.get("display_name") or "").strip()
    if not display_name:
        return jsonify({"error": "Display name is required."}), 422

    email = _email()
    account = get_account(email)
    senders = get_senders(email)
    step2 = get_step(email, 2)

    upsert_profile(
        email,
        display_name,
        (body.get("description") or "").strip(),
        body.get("logo_url") or None,
        (body.get("address") or "").strip(),
    )

    is_sandbox = not step2 or step2["metadata"].get("waba_id") == "sandbox-waba-dev"
    if account and senders and not is_sandbox:
        token = decrypt_token(account["auth_token_enc"], _secret())
        _update_business_profile(account["account_sid"], token, senders[0]["phone_number"], {
            "display_name": display_name,
            "description": body.get("description"),
            "address": body.get("address"),
            "logo_url": body.get("logo_url"),
        })

    _check_step4_completion(email)
    return jsonify({"ok": True})


@bp.post("/step/4/template")
def step4_template():
    body = request.get_json(force=True) or {}
    name = (body.get("name") or "").strip().lower()
    tmpl_body = (body.get("body") or "").strip()
    category = body.get("category", "UTILITY")
    language = body.get("language", "en_US")

    if not name or not re.fullmatch(r"[a-z0-9_]+", name):
        return jsonify({"error": "Template name must be lowercase letters, numbers, and underscores only."}), 422
    if not tmpl_body:
        return jsonify({"error": "Template body is required."}), 422
    if category not in ("MARKETING", "UTILITY", "AUTHENTICATION"):
        return jsonify({"error": "Invalid category."}), 422

    email = _email()
    account = get_account(email)
    step2 = get_step(email, 2)
    is_sandbox = not step2 or step2["metadata"].get("waba_id") == "sandbox-waba-dev"

    twilio_sid = None
    status = "pending"

    if account and not is_sandbox:
        token = decrypt_token(account["auth_token_enc"], _secret())
        result = _create_template(account["account_sid"], token, name, tmpl_body, language)
        if "error" in result:
            return jsonify({"error": result["error"]}), 422
        twilio_sid = result.get("sid")
        status = result.get("status", "pending")

    insert_template(email, name, category, language, tmpl_body, status, twilio_sid)
    _check_step4_completion(email)
    return jsonify({"ok": True, "status": status})


def _check_step4_completion(email: str) -> None:
    profile = get_profile(email)
    templates = get_templates(email)
    if profile and templates:
        upsert_step(email, 4, "complete")


# ── Admin ─────────────────────────────────────────────────────────────────────

@bp.get("/admin/clients")
def admin_clients():
    if not _is_admin():
        return jsonify({"error": "Access denied"}), 403
    return jsonify({"clients": all_users_summary()})


@bp.get("/admin/clients/<path:client_email>")
def admin_client_detail(client_email: str):
    if not _is_admin():
        return jsonify({"error": "Access denied"}), 403
    steps = get_steps(client_email)
    account = get_account(client_email)
    senders = get_senders(client_email)
    templates = get_templates(client_email)
    profile = get_profile(client_email)
    return jsonify({
        "email": client_email,
        "account": {"sid": account["account_sid"],
                    "friendly_name": account["friendly_name"]} if account else None,
        "steps": {str(k): {"status": v["status"], "completed_at": v["completed_at"]}
                  for k, v in steps.items()},
        "senders": senders,
        "templates": templates,
        "profile": profile,
    })


# ── enrich_me ─────────────────────────────────────────────────────────────────

def enrich_me(email: str) -> dict:
    """Expose wizard completion count on /api/me."""
    steps = get_steps(email)
    completed = sum(1 for s in steps.values() if s["status"] == "complete")
    return {"ww_completed_steps": completed}
