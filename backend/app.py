#!/usr/bin/env python3
"""
GTM Hub — Platform API
----------------------
Handles auth (Google OAuth), /api/me, and /api/apps.
App blueprints are auto-discovered from apps/ — no manual registration needed.

To add a new app:
  1. Create backend/apps/<name>/manifest.json
  2. Create backend/apps/<name>/routes.py with a Blueprint named <name>_bp
  3. Optionally expose enrich_me(email) -> dict to add fields to /api/me

Usage:
  python app.py                          # dev
  gunicorn -b 0.0.0.0:5001 -w 2 app:app # production
"""

from __future__ import annotations
import os
import sys
import json
import logging
import importlib
import inspect
import time
from collections import defaultdict
from pathlib import Path
from flask import Blueprint

from flask import Flask, request, jsonify, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix
from google_auth_oauthlib.flow import Flow
import requests as http
from salesforce import sf

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

# ── Salesforce role → access helpers ─────────────────────────────────────────

def _sf_access_level(role_name: str) -> str:
    """
    'full'          — SE managers (FLM/SLM) and all non-SE roles.
    'se_restricted' — Individual SE contributors (role starts with 'SE -').
    """
    if role_name.startswith(("SE FLM", "SE SLM")):
        return "full"
    if role_name.startswith("SE -"):
        return "se_restricted"
    return "full"

def _sf_role_to_team(role_name: str) -> str | None:
    """Map an IC SE's UserRole to a scorecard team key."""
    r = role_name.lower()
    if "self service" in r: return "digital_sales"
    if "dorg"         in r: return "dorg"
    if "namer"        in r: return "namer"
    if "emea"         in r: return "emea"
    if "apj"          in r: return "apj"
    if "latam"        in r: return "latam"
    return None

def _sf_role_to_subteam(role_name: str) -> str | None:
    """Map an IC SE's UserRole to a scorecard subteam key using the TEAMS config."""
    import re as _re
    try:
        from apps.se_scorecard_v2.routes import TEAMS
        for team in TEAMS.values():
            for subteam in team.get("subteams", []):
                roles = _re.findall(r"'([^']+)'", subteam["soql_filter"])
                if role_name in roles:
                    return subteam["key"]
    except Exception:
        pass
    return None

def _enrich_session_from_sf(email: str) -> None:
    """
    Optionally enrich the session with Salesforce profile data.
    This is best-effort: if Salesforce is not configured, or the user has no
    SF account, the session gets sf_access='full' and all SF fields remain null.
    Apps must not assume SF data is present — use session.get() with defaults.
    """
    sf_user = sf.get_user_by_email(email)
    if not sf_user:
        session.setdefault("sf_access", "full")
        return
    role_name = (sf_user.get("UserRole") or {}).get("Name") or ""
    access    = _sf_access_level(role_name)
    session["sf_access"]       = access
    session["sf_role_name"]    = role_name
    session["sf_display_name"] = sf_user.get("Name")
    session["sf_title"]        = sf_user.get("Title")
    session["sf_department"]   = sf_user.get("Department")
    session["sf_manager"]      = (sf_user.get("Manager") or {}).get("Name")
    session["sf_division"]     = sf_user.get("Division")
    session["sf_user_id"]      = sf_user.get("Id")
    session["sf_team"]         = _sf_role_to_team(role_name) if access == "se_restricted" else None
    session["sf_subteam"]      = _sf_role_to_subteam(role_name) if access == "se_restricted" else None
    log.info("SF profile loaded for %s: role=%r access=%s subteam=%s",
             email, role_name, access, session["sf_subteam"])

# ─────────────────────────────────────────────────────────────────────────────

APPS_DIR = Path(__file__).parent / "apps"

# Add backend root to path so apps/ is importable without __init__.py files
sys.path.insert(0, str(Path(__file__).parent))

# Routes the platform exposes publicly (no login required)
_PUBLIC_ROUTES = {"/auth", "/oauth2callback", "/logout", "/simulate", "/api/me", "/api/se-scorecard-v2/sms"}

# ── Rate limiting (in-memory, per IP) ────────────────────────────────────────
_rl_store: dict[str, list[float]] = defaultdict(list)
_RL_LIMIT  = 120  # max requests
_RL_WINDOW = 60   # per N seconds

def _rate_limited(ip: str) -> bool:
    """Returns True if this IP has exceeded the rate limit."""
    now = time.monotonic()
    cutoff = now - _RL_WINDOW
    ts = _rl_store[ip]
    while ts and ts[0] < cutoff:
        ts.pop(0)
    if len(ts) >= _RL_LIMIT:
        return True
    ts.append(now)
    return False

# ── Auto-discover app blueprints ──────────────────────────────────────────────
# Drop a routes.py in apps/<name>/ with any Blueprint and it registers itself.
# Optionally expose enrich_me(email) -> dict to add fields to /api/me.

_me_enrichers: list = []


def _load_app_env(app_dir: Path) -> None:
    """Load per-app .env file into os.environ (local dev convenience).
    In production, vars come from the systemd EnvironmentFile instead."""
    env_file = app_dir / ".env"
    if not env_file.exists():
        return
    with env_file.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:   # don't override values already set
                os.environ[key] = val
    log.info("Loaded env: %s/.env", app_dir.name)


for _app_dir in sorted(APPS_DIR.iterdir()):
    if not _app_dir.is_dir() or not (_app_dir / "routes.py").exists():
        continue
    _load_app_env(_app_dir)
    _mod = importlib.import_module(f"apps.{_app_dir.name}.routes")
    # Find any Blueprint in the module — no naming convention required
    _blueprints = [obj for _, obj in inspect.getmembers(_mod)
                   if isinstance(obj, Blueprint)]
    for _bp in _blueprints:
        app.register_blueprint(_bp)
        log.info("Registered blueprint: %s (%s)", _app_dir.name, _bp.name)
    if hasattr(_mod, "enrich_me"):
        _me_enrichers.append(_mod.enrich_me)

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
        redirect_uri=(url_for("oauth2callback", _external=True) if _local_dev
                      else f"{_frontend_url}/oauth2callback"),
    )

@app.before_request
def enforce_auth():
    """
    Platform-level auth gate. All /api/* routes require a valid session
    unless explicitly listed in _PUBLIC_ROUTES. App builders never need
    to implement their own auth checks.
    """
    if request.path in _PUBLIC_ROUTES:
        return

    if not request.path.startswith("/api/"):
        return

    # CSRF: reject API requests whose Origin doesn't match this app.
    # Browsers always send Origin on cross-origin requests; same-origin
    # requests either omit it or send the correct value.
    origin = request.headers.get("Origin")
    if origin and _frontend_url and origin.rstrip("/") != _frontend_url.rstrip("/"):
        return jsonify({"error": "Forbidden"}), 403

    # Auth
    if not session.get("user_email"):
        return jsonify({"error": "Unauthorized"}), 401

    # Rate limit (per authenticated user email, falls back to IP)
    key = session.get("user_email") or request.remote_addr or "unknown"
    if _rate_limited(key):
        return jsonify({"error": "Too many requests"}), 429

    # Role-based access control for individual SE contributors
    if session.get("sf_access") == "se_restricted":
        p = request.path
        allowed_team = session.get("sf_team")
        # Power rankings are manager-only
        if p == "/api/se-scorecard-v2/data/rankings":
            return jsonify({"error": "Access denied"}), 403
        # Report and SE list: allow only for the SE's own team
        if p in ("/api/se-scorecard-v2/data/report", "/api/se-scorecard-v2/data/ses"):
            requested = request.args.get("team", "")
            if not requested:
                return jsonify({"error": "team parameter required"}), 400
            if allowed_team and requested != allowed_team:
                return jsonify({"error": "Access denied"}), 403

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
        _enrich_session_from_sf(email)
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
        session.clear()
        session["user_email"] = email
        _enrich_session_from_sf(email)
    # Send restricted SEs straight to their personal stats page
    if session.get("sf_access") == "se_restricted":
        return redirect(f"{_frontend_url}/se-scorecard-v2/me")
    return redirect(f"{_frontend_url}/")

# ── Platform API ──────────────────────────────────────────────────────────────

@app.route("/api/me")
def api_me():
    email = session.get("user_email", "")
    if not email:
        return jsonify({"email": None}), 200
    data: dict = {"email": email}
    for enrich in _me_enrichers:
        data.update(enrich(email))
    return jsonify(data)

@app.route("/api/apps")
def api_apps():
    """Returns all registered app manifests, ordered by status (live first)."""
    manifests = []
    for app_dir in sorted(APPS_DIR.iterdir()):
        manifest_path = app_dir / "manifest.json"
        if app_dir.is_dir() and not app_dir.name.startswith("_") and manifest_path.exists():
            manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
    manifests.sort(key=lambda m: (m.get("status") != "live", m.get("order", 999), m.get("name", "")))
    return jsonify(manifests)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
