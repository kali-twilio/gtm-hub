import re
import json
import logging
import shutil
import tempfile
import urllib.request
from pathlib import Path

from flask import Blueprint, request, jsonify, session

from . import se_analysis

log = logging.getLogger(__name__)

scorecard_bp = Blueprint("scorecard", __name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED = {".csv"}


def _authenticated():
    return bool(session.get("user_email"))


def email_to_se_name(email: str, ses: list) -> str | None:
    """Match a @twilio.com email to an SE name in the dataset."""
    local = email.split("@")[0].lower()

    def norm(s):
        return re.sub(r"[^a-z0-9]", "", s)

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


def get_se_info(email: str) -> dict:
    """Return SE metadata for /api/me. Called by the platform layer."""
    data_path = OUTPUT_DIR / "se_data.json"
    has_data = data_path.exists()
    se_name = None
    if has_data:
        ses = json.loads(data_path.read_text(encoding="utf-8"))
        se_name = email_to_se_name(email, ses)
    return {"is_se": se_name is not None, "se_name": se_name, "has_data": has_data}


def _load_ses():
    data_path = OUTPUT_DIR / "se_data.json"
    if not data_path.exists():
        return None
    return json.loads(data_path.read_text(encoding="utf-8"))


@scorecard_bp.route("/api/generate", methods=["POST"])
def api_generate():
    if not _authenticated():
        return jsonify({"ok": False, "error": "Not authenticated"}), 401

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
                    data = resp.read(10 * 1024 * 1024 + 1)
                if len(data) > 10 * 1024 * 1024:
                    return jsonify({"ok": False, "error": "Sheet is too large (max 10 MB)"}), 400
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

        ses = se_analysis.load_ses(csv_path)
        ranked = se_analysis.rank_ses(ses)
        se_analysis.save_data(ranked, str(OUTPUT_DIR))

        last = OUTPUT_DIR / "last_data.csv"
        if csv_path != str(last):
            shutil.copy2(csv_path, last)

        return jsonify({"ok": True})

    except Exception:
        log.exception("Error in /api/generate")
        return jsonify({"ok": False, "error": "Failed to process data. Check server logs."}), 500
    finally:
        last = str(OUTPUT_DIR / "last_data.csv")
        if csv_path and csv_path != last:
            Path(csv_path).unlink(missing_ok=True)


@scorecard_bp.route("/api/data/ses")
def api_ses():
    if not _authenticated():
        return jsonify([]), 401
    ses = _load_ses()
    if ses is None:
        return jsonify([]), 404
    # SE users only get their own record
    se_name = email_to_se_name(session.get("user_email", ""), ses)
    if se_name:
        ses = [s for s in ses if s["name"] == se_name]
    return jsonify(ses)


@scorecard_bp.route("/api/data/report")
def api_report():
    if not _authenticated():
        return jsonify({}), 401
    ses_list = _load_ses()
    if ses_list is None:
        return jsonify({}), 404
    # Block SE users
    if email_to_se_name(session.get("user_email", ""), ses_list):
        return jsonify({"error": "Access denied"}), 403

    total = len(ses_list)
    act_sorted  = sorted(ses_list, key=lambda x: x["act_icav"], reverse=True)
    exp_sorted  = sorted(ses_list, key=lambda x: x["exp_icav"], reverse=True)
    pipe_sorted = sorted(ses_list, key=lambda x: x["future_emails"], reverse=True)
    deal_sorted = [s for s in sorted(ses_list, key=lambda x: x["largest_deal_value"], reverse=True)
                   if s["largest_deal_value"] > 0]

    return jsonify({
        "ranked":     ses_list,
        "total":      total,
        "team_icav":  sum(s["total_icav"] for s in ses_list),
        "avg_owl":    round(sum(s["owl_pct"] for s in ses_list) / total) if total else 0,
        "act_sorted": act_sorted,
        "exp_sorted": exp_sorted,
        "pipe_sorted": pipe_sorted,
        "deal_sorted": deal_sorted,
        "max_act":     act_sorted[0]["act_icav"] if act_sorted else 1,
        "max_exp":     max((s["exp_icav"] for s in exp_sorted), default=1) or 1,
        "max_fut":     pipe_sorted[0]["future_emails"] if pipe_sorted and pipe_sorted[0]["future_emails"] else 1,
        "max_act_icav": max(s["act_icav"] for s in ses_list) or 1,
        "max_exp_icav": max(s["exp_icav"] for s in ses_list) or 1,
        "trends":      sorted(se_analysis.collect_team_trends(ses_list), key=lambda x: x[0]),
    })


@scorecard_bp.route("/api/data/rankings")
def api_rankings():
    if not _authenticated():
        return jsonify({}), 401
    ses_list = _load_ses()
    if ses_list is None:
        return jsonify({}), 404
    # Block SE users
    if email_to_se_name(session.get("user_email", ""), ses_list):
        return jsonify({"error": "Access denied"}), 403

    total = len(ses_list)
    TIER_CFG = {
        "Elite":   {"color": "#FFB800", "bg": "#1a1200", "label": "🐐 GOAT TIER"},
        "Strong":  {"color": "#3B82F6", "bg": "#0a1628", "label": "🔥 ON FIRE"},
        "Steady":  {"color": "#10B981", "bg": "#071a12", "label": "😤 GRINDING"},
        "Develop": {"color": "#EF4444", "bg": "#1a0a0a", "label": "💀 SEND HELP"},
    }
    max_a = max(s["act_icav"]       for s in ses_list) or 1
    max_e = max(s["exp_icav"]       for s in ses_list) or 1
    max_f = max(s["future_emails"]  for s in ses_list) or 1

    ranked_out = []
    for s in ses_list:
        t = s.get("tier", "Steady")
        ranked_out.append({**s,
            "_cfg":  TIER_CFG.get(t, TIER_CFG["Steady"]),
            "_tier": t,
            "_aw":   round(s["act_icav"] / max_a * 100),
            "_ew":   round(s["exp_icav"] / max_e * 100),
            "_fw":   round(s["future_emails"] / max_f * 100),
            "_roast": s.get("roast", "Getting it done. 📋"),
            "total": s["total_icav"],
            "owl":   s["owl_pct"],
            "future": s["future_emails"],
        })

    return jsonify({
        "ranked":     ranked_out,
        "total":      total,
        "team_total": sum(s["total_icav"] for s in ses_list),
        "team_owl":   round(sum(s["owl_pct"] for s in ses_list) / total) if total else 0,
    })
