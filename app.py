#!/usr/bin/env python3
"""
SE Scorecard API
----------------
Pure JSON API backend. All UI is served by the SvelteKit frontend.

Usage:
  python app.py               # dev
  gunicorn -b 0.0.0.0:5001 app:app   # production
"""

import os
import re
import sys
import json
import logging
import tempfile
import urllib.request
from pathlib import Path

from flask import Flask, request, jsonify, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix
from google_auth_oauthlib.flow import Flow
import requests as http

sys.path.insert(0, str(Path(__file__).parent))
import se_analysis

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

_local_dev    = os.environ.get("LOCAL_DEV") == "1"
_frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173" if _local_dev else "")

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    if _local_dev:
        _secret_key = "dev-insecure-key-do-not-use-in-production"
        log.warning("SECRET_KEY not set — using insecure dev key. Never run this in production.")
    else:
        raise RuntimeError("SECRET_KEY must be set in production.")
app.secret_key = _secret_key

if _local_dev:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
app.config.update(
    SESSION_COOKIE_SECURE=not _local_dev,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB upload limit
)

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
ALLOWED_DOMAIN       = "twilio.com"
SCOPES               = ["openid", "https://www.googleapis.com/auth/userinfo.email"]

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.")

BASE       = Path(__file__).parent
OUTPUT_DIR = BASE / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED = {".csv"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_flow():
    return Flow.from_client_config(
        {"web": {
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
        }},
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True),
    )

def authenticated():
    return bool(session.get("user_email"))

def email_to_se_name(email, ses):
    local = email.split("@")[0].lower()

    def norm(s):
        return re.sub(r'[^a-z0-9]', '', s)

    def names(se):
        parts = se["name"].lower().split()
        return (parts[0] if parts else ""), (parts[-1] if len(parts) > 1 else "")

    if "." in local:
        parts = local.split(".")
        first_part, last_part = parts[0], parts[-1]
        for se in ses:
            fn, ln = names(se)
            if fn == first_part and norm(ln) == norm(last_part):
                return se["name"]
        for se in ses:
            fn, _ = names(se)
            if fn == first_part:
                return se["name"]
    else:
        for split in range(1, len(local)):
            prefix, suffix = local[:split], local[split:]
            for se in ses:
                fn, ln = names(se)
                if norm(ln) == norm(suffix) and fn.startswith(prefix):
                    return se["name"]
        for split in range(1, len(local)):
            suffix = local[split:]
            matches = [se for se in ses if norm(names(se)[1]) == norm(suffix)]
            if len(matches) == 1:
                return matches[0]["name"]
        for se in ses:
            fn, _ = names(se)
            if fn == local:
                return se["name"]

    return None

@app.after_request
def security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "img-src 'self' data:; "
        "frame-ancestors 'none'"
    )
    if not _local_dev:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/auth")
def auth():
    flow = build_flow()
    auth_url, state = flow.authorization_url(prompt="select_account")
    session["oauth_state"] = state
    try:
        session["code_verifier"] = flow.code_verifier
    except Exception:
        pass
    return redirect(auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    if request.args.get("state") != session.pop("oauth_state", None):
        return redirect(f"{_frontend_url}/?error=Invalid+auth+state")
    try:
        flow = build_flow()
        cv = session.pop("code_verifier", None)
        if cv:
            flow.code_verifier = cv
        flow.fetch_token(authorization_response=request.url)
        resp = http.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {flow.credentials.token}"},
            timeout=10,
        )
        email = resp.json().get("email", "")
        if not email.endswith(f"@{ALLOWED_DOMAIN}"):
            return redirect(f"{_frontend_url}/?error=Access+restricted+to+%40{ALLOWED_DOMAIN}+accounts")
        session["user_email"] = email
    except Exception:
        return redirect(f"{_frontend_url}/?error=Sign-in+failed")
    return redirect(f"{_frontend_url}/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(f"{_frontend_url}/")

@app.route("/simulate")
def simulate():
    if not _local_dev:
        return "Not available", 404
    email = request.args.get("email", "")
    if email:
        session["user_email"] = email
    return redirect(f"{_frontend_url}/")


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/me")
def api_me():
    email = session.get("user_email", "")
    if not email:
        return jsonify({"email": None}), 200

    data_path = OUTPUT_DIR / "se_data.json"
    has_data = data_path.exists()
    se_name = None
    if has_data:
        ses = json.loads(data_path.read_text(encoding="utf-8"))
        se_name = email_to_se_name(email, ses)

    return jsonify({
        "email":    email,
        "is_se":    se_name is not None,
        "se_name":  se_name,
        "has_data": has_data,
    })

@app.route("/api/generate", methods=["POST"])
def api_generate():
    if not authenticated():
        return jsonify({"ok": False, "error": "Not authenticated"}), 401

    # Resolve CSV path
    sheet_url = request.form.get("sheet_url", "").strip()
    f = request.files.get("csv_file")
    csv_path = None

    try:
        if sheet_url:
            match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
            if not match:
                return jsonify({"ok": False, "error": "Invalid Google Sheets URL"}), 400
            sheet_id = match.group(1)
            gid_match = re.search(r"gid=(\d+)", sheet_url)
            gid = gid_match.group(1) if gid_match else "0"
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
            try:
                with urllib.request.urlopen(csv_url, timeout=15) as resp:
                    data = resp.read()
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    return jsonify({"ok": False, "error": "Sheet is private — share as 'Anyone with the link can view'"}), 400
                return jsonify({"ok": False, "error": f"Could not fetch sheet (HTTP {e.code})"}), 400
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp.write(data)
                csv_path = tmp.name

        elif f and f.filename:
            if Path(f.filename).suffix.lower() not in ALLOWED:
                return jsonify({"ok": False, "error": "Only .csv files are supported"}), 400
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                f.save(tmp.name)
                csv_path = tmp.name
        else:
            last = OUTPUT_DIR / "last_data.csv"
            if last.exists():
                csv_path = str(last)
            else:
                return jsonify({"ok": False, "error": "No data provided"}), 400

        import shutil
        ses    = se_analysis.load_ses(csv_path)
        ranked = se_analysis.rank_ses(ses)
        se_analysis.save_data(ranked, str(OUTPUT_DIR))

        last = OUTPUT_DIR / "last_data.csv"
        if csv_path != str(last):
            shutil.copy2(csv_path, last)

        return jsonify({"ok": True})

    except Exception as e:
        log.exception("Error in /api/generate")
        return jsonify({"ok": False, "error": "Failed to process data. Check server logs."}), 500
    finally:
        last = str(OUTPUT_DIR / "last_data.csv")
        if csv_path and csv_path != last:
            Path(csv_path).unlink(missing_ok=True)

@app.route("/api/data/ses")
def api_ses():
    if not authenticated():
        return jsonify([]), 401
    data_path = OUTPUT_DIR / "se_data.json"
    if not data_path.exists():
        return jsonify([]), 404
    ses = json.loads(data_path.read_text(encoding="utf-8"))
    # SE users only get their own record
    se_name = email_to_se_name(session.get("user_email", ""), ses)
    if se_name:
        ses = [s for s in ses if s["name"] == se_name]
    return jsonify(ses)

@app.route("/api/data/report")
def api_report():
    if not authenticated():
        return jsonify({}), 401
    # Block SE users from seeing full report
    data_path = OUTPUT_DIR / "se_data.json"
    if data_path.exists():
        ses = json.loads(data_path.read_text(encoding="utf-8"))
        if email_to_se_name(session.get("user_email", ""), ses):
            return jsonify({"error": "Access denied"}), 403

    if not data_path.exists():
        return jsonify({}), 404

    ses_list = json.loads(data_path.read_text(encoding="utf-8"))
    total = len(ses_list)
    team_icav  = sum(s["total_icav"] for s in ses_list)
    avg_owl    = round(sum(s["owl_pct"] for s in ses_list) / total) if total else 0
    act_sorted  = sorted(ses_list, key=lambda x: x["act_icav"], reverse=True)
    exp_sorted  = sorted(ses_list, key=lambda x: x["exp_icav"], reverse=True)
    pipe_sorted = sorted(ses_list, key=lambda x: x["future_emails"], reverse=True)
    deal_sorted = [s for s in sorted(ses_list, key=lambda x: x["largest_deal_value"], reverse=True)
                   if s["largest_deal_value"] > 0]
    max_act      = act_sorted[0]["act_icav"]  if act_sorted  else 1
    max_exp      = max((s["exp_icav"] for s in exp_sorted), default=1) or 1
    max_fut      = pipe_sorted[0]["future_emails"] if pipe_sorted and pipe_sorted[0]["future_emails"] else 1
    max_act_icav = max(s["act_icav"] for s in ses_list) or 1
    max_exp_icav = max(s["exp_icav"] for s in ses_list) or 1

    ranked = ses_list  # already sorted by rank in se_data.json

    return jsonify({
        "ranked": ranked,
        "total": total,
        "team_icav": team_icav,
        "avg_owl": avg_owl,
        "act_sorted": act_sorted,
        "exp_sorted": exp_sorted,
        "pipe_sorted": pipe_sorted,
        "deal_sorted": deal_sorted,
        "max_act": max_act,
        "max_exp": max_exp,
        "max_fut": max_fut,
        "max_act_icav": max_act_icav,
        "max_exp_icav": max_exp_icav,
        "trends": sorted(se_analysis.collect_team_trends(ses_list), key=lambda x: x[0]),
    })

@app.route("/api/data/rankings")
def api_rankings():
    if not authenticated():
        return jsonify({}), 401
    data_path = OUTPUT_DIR / "se_data.json"
    if data_path.exists():
        ses = json.loads(data_path.read_text(encoding="utf-8"))
        if email_to_se_name(session.get("user_email", ""), ses):
            return jsonify({"error": "Access denied"}), 403
    data_path = OUTPUT_DIR / "se_data.json"
    if not data_path.exists():
        return jsonify({}), 404

    ses_list = json.loads(data_path.read_text(encoding="utf-8"))
    total      = len(ses_list)
    team_total = sum(s["total_icav"] for s in ses_list)
    team_owl   = round(sum(s["owl_pct"] for s in ses_list) / total) if total else 0

    TIER_CFG = {
        "Elite":   {"color": "#FFB800", "bg": "#1a1200", "label": "🐐 GOAT TIER"},
        "Strong":  {"color": "#3B82F6", "bg": "#0a1628", "label": "🔥 ON FIRE"},
        "Steady":  {"color": "#10B981", "bg": "#071a12", "label": "😤 GRINDING"},
        "Develop": {"color": "#EF4444", "bg": "#1a0a0a", "label": "💀 SEND HELP"},
    }

    max_a = max(s["act_icav"]  for s in ses_list) or 1
    max_e = max(s["exp_icav"]  for s in ses_list) or 1
    max_f = max(s["future_emails"] for s in ses_list) or 1

    ranked_out = []
    for s in ses_list:
        t   = s.get("tier", "Steady")
        cfg = TIER_CFG.get(t, TIER_CFG["Steady"])
        ranked_out.append({**s,
            "_cfg":    cfg,
            "_tier":   t,
            "_aw":     round(s["act_icav"] / max_a * 100),
            "_ew":     round(s["exp_icav"] / max_e * 100),
            "_fw":     round(s["future_emails"] / max_f * 100),
            "_roast":  s.get("roast", "Getting it done. 📋"),
            "total":   s["total_icav"],
            "owl":     s["owl_pct"],
            "future":  s["future_emails"],
        })

    return jsonify({
        "ranked":     ranked_out,
        "total":      total,
        "team_total": team_total,
        "team_owl":   team_owl,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
