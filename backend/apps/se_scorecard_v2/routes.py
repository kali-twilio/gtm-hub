"""
SE Scorecard V2 — Flask Blueprint. Routes only; all business logic is in scorecard.py.
"""
from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request, session

from salesforce import sf
from . import scorecard as logic
from suggestions import get_firestore as _get_firestore, masked_email as _masked, display_author as _display_author
from suggestions import FIRESTORE_COLLECTION as _FIRESTORE_COLLECTION, SUGGESTIONS_MAX as _SUGGESTIONS_MAX
from chat import run_chat as _run_chat

log = logging.getLogger(__name__)

se_scorecard_v2_bp = Blueprint("se_scorecard_v2", __name__)

TEAMS         = logic.TEAMS  # re-exported; app.py does `from apps.se_scorecard_v2.routes import TEAMS`
_DEFAULT_TEAM = logic.DEFAULT_TEAM


# ---------------------------------------------------------------------------
# Platform hook — called by app.py /api/me
# ---------------------------------------------------------------------------

def enrich_me(email: str) -> dict:
    from flask import session
    out: dict = {
        "sf_access":       session.get("sf_access", "full"),
        "sf_role_name":    session.get("sf_role_name"),
        "sf_display_name": session.get("sf_display_name"),
        "sf_title":        session.get("sf_title"),
        "sf_department":   session.get("sf_department"),
        "sf_manager":      session.get("sf_manager"),
        "sf_division":     session.get("sf_division"),
        "sf_subteam":      session.get("sf_subteam"),
    }
    from pathlib import Path
    OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
    for team_key in TEAMS:
        for p in OUTPUT_DIR.glob(f"sf_se_data_{team_key}_*.json"):
            try:
                raw    = json.loads(p.read_text(encoding="utf-8"))
                cached = raw.get("ses", raw) if isinstance(raw, dict) else raw
            except Exception:
                continue
            se_name = logic.email_to_se_name(email, cached)
            if se_name:
                out.update({"sf_is_se": True, "sf_se_name": se_name, "sf_team": team_key})
                return out
    out.update({"sf_is_se": False, "sf_se_name": None, "sf_team": session.get("sf_team")})
    return out


def _get_data(team_key, period_key, icav_min=0, subteam_key=""):
    return logic.get_data(TEAMS, team_key, period_key, icav_min, subteam_key)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@se_scorecard_v2_bp.route("/api/se-scorecard-v2/teams")
def api_teams():
    return jsonify([
        {
            "key":         k,
            "label":       v["label"],
            "description": v["description"],
            "criteria":    v.get("criteria", []),
            "subteams":    [{"key": s["key"], "label": s["label"]} for s in v.get("subteams", [])],
        }
        for k, v in TEAMS.items()
    ])


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/periods")
def api_periods():
    return jsonify(logic.available_periods())


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/data/ses")
def api_ses():
    team_key   = request.args.get("team", _DEFAULT_TEAM)
    period_key = request.args.get("period", logic.default_period())
    icav_min, err = logic.parse_icav_min(request.args.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key = request.args.get("subteam", "")
    ses, err, *_ = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": err}), 503
    team_medians = logic.compute_team_medians(ses)
    se_name      = logic.email_to_se_name(session.get("user_email", ""), ses)
    if se_name:
        ses = [s for s in ses if s["name"] == se_name]
    team_motion = TEAMS[team_key].get("motion", "dsr") if team_key in TEAMS else "dsr"
    return jsonify({"ses": [{**s, "team_motion": team_motion, "team_medians": team_medians} for s in ses], "sf_instance_url": sf.instance_url})


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/data/report")
def api_report():
    team_key   = request.args.get("team", _DEFAULT_TEAM)
    period_key = request.args.get("period", logic.default_period())
    icav_min, err = logic.parse_icav_min(request.args.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key = request.args.get("subteam", "")
    ses_list, err, team_total_icav, act_total_icav, exp_total_icav, all_owner_opps = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": err}), 503
    if logic.email_to_se_name(session.get("user_email", ""), ses_list):
        return jsonify({"error": "Access denied"}), 403

    team       = TEAMS[team_key]
    subteam    = next((s for s in team.get("subteams", []) if s["key"] == subteam_key), None) if subteam_key else None
    team_label = f"{team['label']} · {subteam['label']}" if subteam else team["label"]
    period     = logic.period_info(period_key)
    total      = len(ses_list)

    unique_owners  = {o["owner"] for s in ses_list for o in s.get("tw_opps_detail", []) if o.get("owner")}
    ae_dsr_count   = len(unique_owners)
    ae_to_se_ratio = round(ae_dsr_count / total, 1) if total > 0 else 0
    act_sorted     = sorted(ses_list, key=lambda x: x["act_icav"], reverse=True)
    exp_sorted     = sorted(ses_list, key=lambda x: x["exp_icav"], reverse=True)
    deal_sorted    = [s for s in sorted(ses_list, key=lambda x: x["largest_deal_value"], reverse=True) if s["largest_deal_value"] > 0]

    cache_key_trend = f"{team_key}_{subteam_key}" if subteam_key else team_key
    is_fy           = "_FY" in period_key
    comparable      = [p for p in logic.available_periods() if (("_FY" in p["key"]) == is_fy) and p["key"] != period_key]

    def _exp_snapshot(ses, p_label, p_key, is_current):
        return {
            "period": p_label, "period_key": p_key, "is_current": is_current,
            "team_exp_icav":   sum(s.get("exp_icav", 0) for s in ses),
            "team_exp_wins":   sum(s.get("exp_wins", 0) for s in ses),
            "team_influenced": sum(s.get("exp_icav", 0) + s.get("non_tw_exp_icav", 0) for s in ses),
            "ses": {s["name"]: {"exp_icav": s.get("exp_icav", 0), "influenced": s.get("exp_icav", 0) + s.get("non_tw_exp_icav", 0)} for s in ses},
        }

    exp_trend = [_exp_snapshot(ses_list, period["label"], period_key, True)]
    for p in comparable[:3]:
        prior, *_ = logic.load_cached(cache_key_trend, p["key"], 0)
        if prior:
            exp_trend.append(_exp_snapshot(prior, p["label"], p["key"], False))
    exp_trend.reverse()

    se_icav         = sum(s["total_icav"] for s in ses_list)
    se_act_icav     = sum(s["act_icav"]   for s in ses_list)
    se_exp_icav     = sum(s["exp_icav"]   for s in ses_list)
    se_icav_pct     = round(se_icav     / team_total_icav * 100) if team_total_icav else None
    se_act_icav_pct = round(se_act_icav / act_total_icav  * 100) if act_total_icav  else None
    se_exp_icav_pct = round(se_exp_icav / exp_total_icav  * 100) if exp_total_icav  else None

    return jsonify({
        "ranked": ses_list, "total": total, "icav_min": icav_min,
        "team_icav": se_icav, "team_earr": sum(s.get("total_earr", 0) for s in ses_list),
        "team_wins": sum(s["act_wins"] + s["exp_wins"] for s in ses_list),
        "team_arr":  sum(s.get("exp_arr_total", 0) for s in ses_list),
        "team_total_icav": team_total_icav, "act_total_icav": act_total_icav, "exp_total_icav": exp_total_icav,
        "se_icav_pct": se_icav_pct, "se_act_icav_pct": se_act_icav_pct, "se_exp_icav_pct": se_exp_icav_pct,
        "act_sorted": act_sorted, "exp_sorted": exp_sorted, "pipe_sorted": [], "deal_sorted": deal_sorted,
        "max_act": act_sorted[0]["act_icav"] if act_sorted else 1,
        "max_exp": max((s["exp_icav"] for s in exp_sorted), default=1) or 1,
        "max_fut": 1, "max_act_icav": max(s["act_icav"] for s in ses_list) or 1,
        "max_exp_icav": max(s["exp_icav"] for s in ses_list) or 1,
        "trends":          sorted(logic.collect_team_trends(ses_list, team.get("motion", "dsr")), key=lambda x: x[0]),
        "recommendations": logic.generate_recommendations(ses_list, team.get("motion", "dsr")),
        "ae_engagement":   logic.compute_ae_engagement(ses_list, all_owner_opps or []),
        "exp_trend": exp_trend, "quarter": period["label"], "team_label": team_label,
        "motion": team.get("motion", "dsr"), "sf_instance_url": sf.instance_url,
        "ae_dsr_count": ae_dsr_count, "ae_to_se_ratio": ae_to_se_ratio,
    })


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/chat", methods=["POST"])
def api_chat():
    body       = request.get_json(silent=True) or {}
    message    = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > 2000:
        return jsonify({"error": "message too long (max 2000 chars)"}), 400

    team_key   = body.get("team", _DEFAULT_TEAM)
    period_key = body.get("period", logic.default_period())
    icav_min, err = logic.parse_icav_min(body.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key = body.get("subteam", "") or ""
    if subteam_key == "none":
        subteam_key = ""

    ses, err, *_ = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": f"Could not load data: {err}"}), 503
    if not ses:
        return jsonify({"answer": "No SE data is available for the selected team and period."}), 200

    context     = logic.build_chat_context(ses, team_key, period_key, TEAMS)
    team_info   = TEAMS.get(team_key, {})
    period_info = logic.period_info(period_key)
    system_prompt = (
        "You are an AI assistant embedded in the Twilio SE Scorecard dashboard. "
        "You have access to pre-loaded SE performance data and a run_soql tool to query Salesforce directly.\n\n"
        f"Current context: team={team_info.get('label', team_key)}, period={period_info['label']} "
        f"(CloseDate {period_info['start']} to {period_info['end']})\n"
        f"Team SE filter: {team_info.get('soql_filter','')}\n"
        f"Team opp scope filter: {team_info.get('team_total_filter','')}\n\n"
        f"{logic.SF_SCHEMA_HINT}\n"
        "Answer questions clearly and concisely. Format numbers with $ and K/M suffixes. "
        "Always apply both the team SE filter AND the team opp scope filter when calling run_soql. "
        "Use the metric definitions above to explain how any number shown on the scorecard was calculated."
    )
    return jsonify(_run_chat(system_prompt, context, message))


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/data/rankings")
def api_rankings():
    team_key   = request.args.get("team", _DEFAULT_TEAM)
    period_key = request.args.get("period", logic.default_period())
    icav_min, err = logic.parse_icav_min(request.args.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key       = request.args.get("subteam", "")
    ses_list, err, *_ = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": err}), 503
    if logic.email_to_se_name(session.get("user_email", ""), ses_list):
        return jsonify({"error": "Access denied"}), 403

    team       = TEAMS[team_key]
    subteam    = next((s for s in team.get("subteams", []) if s["key"] == subteam_key), None) if subteam_key else None
    team_label = f"{team['label']} · {subteam['label']}" if subteam else team["label"]
    period     = logic.period_info(period_key)
    total      = len(ses_list)
    TIER_CFG   = {
        "Elite":   {"color": "#FFB800", "bg": "#1a1200", "label": "🐐 GOAT TIER"},
        "Strong":  {"color": "#3B82F6", "bg": "#0a1628", "label": "🔥 ON FIRE"},
        "Steady":  {"color": "#10B981", "bg": "#071a12", "label": "😤 GRINDING"},
        "Develop": {"color": "#EF4444", "bg": "#1a0a0a", "label": "💀 SEND HELP"},
    }
    max_a = max((s["act_icav"] for s in ses_list), default=0) or 1
    max_e = max((s["exp_icav"] for s in ses_list), default=0) or 1
    return jsonify({
        "ranked": [{**s,
            "_cfg":   TIER_CFG.get(s.get("tier", "Steady"), TIER_CFG["Steady"]),
            "_tier":  s.get("tier", "Steady"),
            "_aw":    round(s["act_icav"] / max_a * 100),
            "_ew":    round(s["exp_icav"] / max_e * 100),
            "_fw":    0,
            "_roast": s.get("roast", "Getting it done. 📋"),
            "total":  s["total_icav"],
            "future": 0,
        } for s in ses_list],
        "total": total, "team_total": sum(s["total_icav"] for s in ses_list),
        "quarter": period["label"], "team_label": team_label,
        "motion": team.get("motion", "dsr"),
    })
