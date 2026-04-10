#!/usr/bin/env python3
"""
SE Scorecard Web App
--------------------
Accepts a Google Sheets URL or CSV upload, generates full report and/or power rankings.

Usage:
  pip install flask gunicorn
  python app.py               # dev
  gunicorn -b 0.0.0.0:5000 app:app   # production
"""

import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

from flask import Flask, request, render_template, send_file, redirect, url_for, session

sys.path.insert(0, str(Path(__file__).parent))
import se_analysis
import se_rankings

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "se-scorecard-secret")

PASSWORD = "SE"

BASE       = Path(__file__).parent
OUTPUT_DIR = BASE / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED = {".csv"}


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

    raise ValueError("Please paste a Google Sheets URL or upload a CSV file.")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == PASSWORD:
            session["auth"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Incorrect password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def index():
    if not session.get("auth"):
        return redirect(url_for("login"))
    return render_template(
        "index.html",
        error=request.args.get("error"),
        report_exists=(OUTPUT_DIR / "se_report.html").exists(),
        rankings_exists=(OUTPUT_DIR / "se_rankings.html").exists(),
    )


@app.route("/generate", methods=["POST"])
def generate():
    if not session.get("auth"):
        return redirect(url_for("login"))
    report_type = request.form.get("report_type")

    try:
        csv_path = get_csv_path()
    except ValueError as e:
        return redirect(url_for("index", error=str(e)))

    try:
        if report_type == "analysis":
            ses    = se_analysis.load_ses(csv_path)
            ranked = se_analysis.rank_ses(ses)
            se_analysis.generate_html(ranked, ses,
                                      output_path=str(OUTPUT_DIR / "se_report.html"))
        elif report_type == "rankings":
            ses_r    = se_rankings.load(csv_path)
            ranked_r = se_rankings.rank(ses_r)
            html     = se_rankings.generate(ranked_r)
            (OUTPUT_DIR / "se_rankings.html").write_text(html, encoding="utf-8")
    except Exception as e:
        return redirect(url_for("index", error=f"Failed to generate report: {e}"))
    finally:
        Path(csv_path).unlink(missing_ok=True)

    if report_type == "rankings":
        return redirect(url_for("view_report", name="se_rankings"))
    return redirect(url_for("view_report", name="se_report"))


@app.route("/report/<name>")
def view_report(name):
    if not session.get("auth"):
        return redirect(url_for("login"))
    if name not in ("se_report", "se_rankings"):
        return "Not found", 404
    path = OUTPUT_DIR / f"{name}.html"
    if not path.exists():
        return redirect(url_for("index",
                                error="No report found. Paste a sheet URL or upload a CSV."))
    return send_file(path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
