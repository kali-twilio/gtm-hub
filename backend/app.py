#!/usr/bin/env python3
"""
GTM Hub — Platform API
----------------------
Handles auth (Google OAuth) and the /api/me endpoint.
App-specific routes are registered as Blueprints from apps/.

Usage:
  python app.py                                    # dev
  gunicorn -b 0.0.0.0:5001 -w 2 app:app           # production
"""

import os
import logging

from flask import Flask, request, jsonify, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix
from google_auth_oauthlib.flow import Flow
import requests as http

from apps.scorecard.routes import scorecard_bp, get_se_info

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
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
)

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
ALLOWED_DOMAIN       = "twilio.com"
SCOPES               = ["openid", "https://www.googleapis.com/auth/userinfo.email"]

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.")

# ── Register app blueprints ───────────────────────────────────────────────────

app.register_blueprint(scorecard_bp)

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

# ── Platform API ──────────────────────────────────────────────────────────────

@app.route("/api/me")
def api_me():
    email = session.get("user_email", "")
    if not email:
        return jsonify({"email": None}), 200
    return jsonify({"email": email, **get_se_info(email)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
