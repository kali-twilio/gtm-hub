"""
SE Forecast — Flask Blueprint. Routes only; all business logic is in forecast_logic.py.
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request, session

from salesforce import sf
from . import forecast_logic as logic

log = logging.getLogger(__name__)

se_forecast_bp = Blueprint("se_forecast", __name__)

# ---------------------------------------------------------------------------
# Chat context — auto-discovered by app.py via CHAT_APP_ID + get_chat_context
# ---------------------------------------------------------------------------

CHAT_APP_ID = "se-forecast"


def get_chat_context(body: dict) -> tuple[str, str]:
    return logic.build_chat_context(body)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@se_forecast_bp.route("/api/se-forecast/pipeline")
def api_pipeline():
    start, end_cur, end_next, period_key, label_cur, label_next = logic.two_quarter_range()
    data, err = logic.fetch_pipeline(period_key, start, end_next)
    if err:
        return jsonify({"error": err}), 503

    return jsonify({
        **data,
        "period_label":    label_cur,
        "period_next":     label_next,
        "quarter_end_cur": end_cur,
        "sf_instance_url": sf.instance_url,
    })


@se_forecast_bp.route("/api/se-forecast/se-notes/<opp_id>", methods=["POST"])
def api_save_se_notes(opp_id: str):
    email = session.get("user_email", "")
    if not email:
        return jsonify({"error": "Unauthorized"}), 401
    if session.get("sf_role_name") != "SE - Self Service":
        return jsonify({"error": "Forbidden"}), 403
    if not opp_id or len(opp_id) > 50:
        return jsonify({"error": "Invalid opp_id"}), 400
    body = request.get_json(silent=True) or {}
    notes = (body.get("se_notes") or "").strip()
    if len(notes) > 32000:
        return jsonify({"error": "Notes too long"}), 400

    try:
        records = sf.query(
            f"SELECT Id, Technical_Lead__r.Email FROM Opportunity WHERE Id = '{opp_id}' LIMIT 1"
        )
    except Exception as e:
        log.error("SF ownership check failed: %s", e)
        return jsonify({"error": "Could not verify ownership"}), 503

    if not records:
        return jsonify({"error": "Opportunity not found"}), 404
    tl = (records[0].get("Technical_Lead__r") or {})
    tl_email = (tl.get("Email") or "").lower()
    if tl_email != email.lower():
        return jsonify({"error": "Forbidden — you are not the Technical Lead on this opportunity"}), 403

    try:
        sf.patch(
            f"/services/data/v59.0/sobjects/Opportunity/{opp_id}",
            {"Sales_Engineer_Notes__c": notes},
        )
    except Exception as e:
        log.error("SF SE notes update failed: %s", e)
        return jsonify({"error": "Failed to save"}), 503

    return jsonify({"se_notes": notes})


@se_forecast_bp.route("/api/se-forecast/notes/<opp_id>", methods=["POST"])
def api_save_note(opp_id: str):
    email = session.get("user_email", "")
    if not email:
        return jsonify({"error": "Unauthorized"}), 401
    if session.get("sf_role_name") != "SE FLM - Self Service":
        return jsonify({"error": "Forbidden"}), 403
    if not opp_id or len(opp_id) > 50:
        return jsonify({"error": "Invalid opp_id"}), 400
    body = request.get_json(silent=True) or {}
    note = (body.get("note") or "").strip()
    if len(note) > 32000:
        return jsonify({"error": "Note too long"}), 400

    try:
        records = sf.query(
            f"SELECT AccountId FROM Opportunity WHERE Id = '{opp_id}' LIMIT 1"
        )
    except Exception as e:
        log.error("SF account lookup failed: %s", e)
        return jsonify({"error": "Could not look up account"}), 503

    if not records:
        return jsonify({"error": "Opportunity not found"}), 404
    account_id = records[0].get("AccountId")
    if not account_id:
        return jsonify({"error": "No account linked to this opportunity"}), 400

    try:
        sf.patch(
            f"/services/data/v59.0/sobjects/Account/{account_id}",
            {"SE_Notes__c": note},
        )
        return jsonify({"note": note})
    except Exception as e:
        log.error("SF account notes update failed: %s", e)
        return jsonify({"error": "Failed to save"}), 503


@se_forecast_bp.route("/api/se-forecast/enrich", methods=["POST"])
def api_enrich():
    if not session.get("user_email"):
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    account_name    = (body.get("account_name") or "").strip()[:200]
    account_website = (body.get("account_website") or "").strip()[:200]
    if not account_name:
        return jsonify({"error": "account_name required"}), 400

    website_text = logic.fetch_website_text(account_website) if account_website else ""
    result = logic.classify_with_bedrock(account_name, website_text)
    result["account_name"] = account_name
    result["website"]      = account_website
    return jsonify(result)


@se_forecast_bp.route("/api/se-forecast/summarize", methods=["POST"])
def api_summarize():
    if not session.get("user_email"):
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    opp_id        = (body.get("id") or "").strip()[:50]
    opp_name      = (body.get("name") or "").strip()[:200]
    close_date    = (body.get("close_date") or "").strip()[:20]
    se_notes      = (body.get("se_notes") or "").strip()[:4000]
    se_history    = (body.get("se_history") or "").strip()[:4000]
    next_step     = (body.get("next_step") or "").strip()[:500]
    last_activity = (body.get("last_activity") or "").strip()[:30]
    if not opp_id:
        return jsonify({"error": "id required"}), 400

    result = logic.summarize_with_bedrock(opp_name, close_date, se_notes, se_history, next_step, last_activity)
    return jsonify(result)
