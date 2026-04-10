#!/usr/bin/env python3
"""
SE Scorecard Web App
--------------------
Google OAuth login restricted to @twilio.com accounts.
Accepts a Google Sheets URL or CSV upload.

Usage:
  pip install -r requirements.txt
  python app.py               # dev (uses password fallback)
  gunicorn -b 0.0.0.0:5000 app:app   # production
"""

import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

from flask import Flask, request, render_template, send_file, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix
from google_auth_oauthlib.flow import Flow
import requests as http

sys.path.insert(0, str(Path(__file__).parent))
import se_analysis
import se_rankings

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)  # trust nginx X-Forwarded-Proto only

# Secure session cookies — HTTPS only in production, relaxed locally
_local_dev = os.environ.get("LOCAL_DEV") == "1"
if _local_dev:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # allow HTTP OAuth on localhost
app.config.update(
    SESSION_COOKIE_SECURE=not _local_dev,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
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


# ── Auth helpers ──────────────────────────────────────────────────────────────

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

def match_email(email):
    """Returns the email used for SE matching. SIMULATE_EMAIL overrides in LOCAL_DEV."""
    if _local_dev:
        return os.environ.get("SIMULATE_EMAIL", email)
    return email


def email_to_se_name(email, ses):
    """
    Best-effort match of a Twilio email to an SE's full name.

    Handles common Twilio email patterns:
      first.last@  → kali.jones    matches "Kali Jones"
      flast@       → ybabenko      matches "Yuriy Babenko"
                     cchin         matches "Connor Chin"
                     bbennettday   matches "Ben Bennett-Day"  (hyphens stripped)
                     jichang       matches "CJ Chang"         (unique last name fallback)
    """
    local = email.split("@")[0].lower()

    def norm(s):
        # strip punctuation so bennett-day == bennettday
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
        # Pass 1: prefix matches start of first name AND normalized last name matches
        for split in range(1, len(local)):
            prefix, suffix = local[:split], local[split:]
            for se in ses:
                fn, ln = names(se)
                if norm(ln) == norm(suffix) and fn.startswith(prefix):
                    return se["name"]

        # Pass 2: last-name-only fallback when the last name is unique in the dataset
        # (handles jichang → "CJ Chang" where display name doesn't match email prefix)
        for split in range(1, len(local)):
            suffix = local[split:]
            matches = [se for se in ses if norm(names(se)[1]) == norm(suffix)]
            if len(matches) == 1:
                return matches[0]["name"]

        # Pass 3: whole local part as first name
        for se in ses:
            fn, _ = names(se)
            if fn == local:
                return se["name"]

    return None


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login")
def login():
    if authenticated():
        return redirect(url_for("index"))
    return render_template("login.html", error=request.args.get("error"))

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
        return redirect(url_for("login", error="Invalid auth state. Please try again."))
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
            return redirect(url_for("login", error=f"Access restricted to @{ALLOWED_DOMAIN} accounts."))
        session["user_email"] = email
    except Exception:
        return redirect(url_for("login", error="Sign-in failed. Please try again."))
    # Send matched SEs straight to their own stats page
    data_path = OUTPUT_DIR / "se_data.json"
    if data_path.exists():
        import json as _json
        ses = _json.loads(data_path.read_text(encoding="utf-8"))
        if email_to_se_name(match_email(email), ses):
            return redirect(url_for("se_profile"))
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── CSV resolution ────────────────────────────────────────────────────────────

def sheets_to_csv_url(url):
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not match:
        return None
    sheet_id = match.group(1)
    gid_match = re.search(r"gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

def get_csv_path():
    sheet_url = request.form.get("sheet_url", "").strip()
    f = request.files.get("csv_file")

    if sheet_url:
        csv_url = sheets_to_csv_url(sheet_url)
        if not csv_url:
            raise ValueError("That doesn't look like a valid Google Sheets URL.")
        try:
            with urllib.request.urlopen(csv_url, timeout=15) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ValueError("Sheet is private — share it as 'Anyone with the link can view'.")
            raise ValueError(f"Could not fetch sheet (HTTP {e.code}).")
        except Exception as e:
            raise ValueError(f"Could not fetch sheet: {e}")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(data)
            return tmp.name

    if f and f.filename:
        if Path(f.filename).suffix.lower() not in ALLOWED:
            raise ValueError("Only .csv files are supported.")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            f.save(tmp.name)
            return tmp.name

    # Fall back to last-used CSV if available
    last = OUTPUT_DIR / "last_data.csv"
    if last.exists():
        return str(last)

    raise ValueError("Please paste a Google Sheets URL or upload a CSV file.")


# ── App routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not authenticated():
        return redirect(url_for("login"))
    import json
    email = session.get("user_email", "")
    data_path = OUTPUT_DIR / "se_data.json"
    has_data = data_path.exists()
    if has_data:
        ses = json.loads(data_path.read_text(encoding="utf-8"))
        if email_to_se_name(match_email(email), ses):
            return redirect(url_for("se_profile"))
    return render_template(
        "index.html",
        error=request.args.get("error"),
        user_email=email,
        has_data=has_data,
    )


@app.route("/generate", methods=["POST"])
def generate():
    if not authenticated():
        return redirect(url_for("login"))
    try:
        csv_path = get_csv_path()
    except ValueError as e:
        return redirect(url_for("index", error=str(e)))

    try:
        import shutil
        # Always regenerate everything
        ses    = se_analysis.load_ses(csv_path)
        ranked = se_analysis.rank_ses(ses)
        se_analysis.generate_html(ranked, ses, output_path=str(OUTPUT_DIR / "se_report.html"))

        ses_r    = se_rankings.load(csv_path)
        ranked_r = se_rankings.rank(ses_r)
        html     = se_rankings.generate(ranked_r)
        (OUTPUT_DIR / "se_rankings.html").write_text(html, encoding="utf-8")

        # Save as default for future runs
        last = OUTPUT_DIR / "last_data.csv"
        if csv_path != str(last):
            shutil.copy2(csv_path, last)
    except Exception as e:
        return redirect(url_for("index", error=f"Failed to generate report: {e}"))
    finally:
        last = str(OUTPUT_DIR / "last_data.csv")
        if csv_path != last:
            Path(csv_path).unlink(missing_ok=True)

    return redirect(url_for("index"))

@app.route("/report/<name>")
def view_report(name):
    if not authenticated():
        return redirect(url_for("login"))
    # SE users can't access the full reports — send them to their own stats
    import json as _j
    _dp = OUTPUT_DIR / "se_data.json"
    if _dp.exists():
        _ses = _j.loads(_dp.read_text(encoding="utf-8"))
        if email_to_se_name(match_email(session.get("user_email", "")), _ses):
            return redirect(url_for("se_profile"))
    if name not in ("se_report", "se_rankings"):
        return "Not found", 404
    path = OUTPUT_DIR / f"{name}.html"
    if not path.exists():
        return redirect(url_for("index",
                                error="No report found. Paste a sheet URL or upload a CSV."))
    back_btn = (
        '<div style="position:fixed;top:14px;left:16px;z-index:9999">'
        '<a href="/" style="background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);'
        'color:#d1d5db;text-decoration:none;padding:7px 14px;border-radius:8px;'
        'font-size:12px;font-family:ui-sans-serif,system-ui,sans-serif">← Back</a></div>'
    )
    content = path.read_text(encoding="utf-8")
    content = re.sub(r'(<body[^>]*>)', r'\1' + back_btn, content, count=1)
    return content


@app.route("/report/se")
def se_profile():
    if not authenticated():
        return redirect(url_for("login"))
    import json
    data_path = OUTPUT_DIR / "se_data.json"
    if not data_path.exists():
        return redirect(url_for("index",
                                error="No analysis report found. Generate the SE Analysis report first."))
    ses = json.loads(data_path.read_text(encoding="utf-8"))
    email = session.get("user_email", "")
    own_name = email_to_se_name(match_email(email), ses)
    selected = request.args.get("name", "") or own_name or ""
    se = next((s for s in ses if s["name"] == selected), None)
    return render_template("se_profile.html",
                           ses=ses, selected=selected, se=se,
                           user_email=email,
                           is_own_profile=bool(own_name))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
