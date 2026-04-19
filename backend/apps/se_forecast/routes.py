"""
SE Forecast — Flask Blueprint.
Four views mirroring the SF forecast reports for the Digital Sales (Self Service) team.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from salesforce import sf

log = logging.getLogger(__name__)

se_forecast_bp = Blueprint("se_forecast", __name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

_LOCAL_DEV  = os.environ.get("LOCAL_DEV") == "1"
_ICAV_FIELD = "Comms_Segment_Combined_iACV__c"

# ---------------------------------------------------------------------------
# Quarter helpers
# ---------------------------------------------------------------------------

_QS = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}
_QE = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def _current_quarter() -> tuple[str, str, str, str]:
    today = date.today()
    q = (today.month - 1) // 3 + 1
    y = today.year
    start = f"{y}-{_QS[q]}"
    end   = f"{y}-{_QE[q]}"
    key   = f"{y}_Q{q}"
    label = f"Q{q} {y}"
    return start, end, key, label


def _next_quarter(q: int, y: int) -> tuple[int, int]:
    return (1, y + 1) if q == 4 else (q + 1, y)


def _two_quarter_range() -> tuple[str, str, str, str, str, str]:
    """Returns start/end/key/label for current quarter, plus end/key/label for next quarter."""
    today = date.today()
    q = (today.month - 1) // 3 + 1
    y = today.year
    nq, ny = _next_quarter(q, y)
    start      = f"{y}-{_QS[q]}"
    end_cur    = f"{y}-{_QE[q]}"
    end_next   = f"{ny}-{_QE[nq]}"
    key        = f"{y}_Q{q}_{ny}_Q{nq}"
    label_cur  = f"Q{q} {y}"
    label_next = f"Q{nq} {ny}"
    return start, end_cur, end_next, key, label_cur, label_next


# ---------------------------------------------------------------------------
# DSR team filters — mirrors scorecard
# ---------------------------------------------------------------------------

# SE filter: Self Service SEs only
_SE_FILTER = (
    "Technical_Lead__r.UserRole.Name = 'SE - Self Service'"
    " AND Technical_Lead__r.Title LIKE '%Engineer%'"
)

# DSR opp filter (AE/DSR owner side) — same logic as scorecard
_DSR_OPP_FILTER = (
    "(FY_16_Owner_Team__c LIKE 'DSR%'"
    " OR (Owner.UserRole.Name LIKE '%DSR%'"
    " AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')))"
)

# Expansion: owner role or FY16 contains Expansion
_IS_EXPANSION = "(Owner.UserRole.Name LIKE '%Expansion%' OR FY_16_Owner_Team__c LIKE '%Expansion%')"
_NOT_EXPANSION = "(NOT Owner.UserRole.Name LIKE '%Expansion%') AND (NOT FY_16_Owner_Team__c LIKE '%Expansion%')"


# ---------------------------------------------------------------------------
# SOQL builders
# ---------------------------------------------------------------------------

def _soql_assigned(start: str, end: str) -> str:
    """All open DSR opps with an SE assigned — activation + expansion, all stages."""
    return (
        f"SELECT Id, Name, CloseDate, StageName, ForecastCategoryName,"
        f" Presales_Stage__c, {_ICAV_FIELD},"
        f" eARR_post_Launch__c, Incremental_ACV__c, Current_eARR__c,"
        f" NextStep, LastActivityDate,"
        f" Technical_Lead__r.Name, Technical_Lead__r.UserRole.Name,"
        f" Owner.Name, Owner.UserRole.Name,"
        f" AccountId, Account.Name, Account.Website, Account.SE_Notes__c,"
        f" Sales_Engineer_Notes__c, SE_Notes_History__c,"
        f" FY_16_Owner_Team__c"
        f" FROM Opportunity"
        f" WHERE StageName NOT IN ('Closed Won', 'Closed Lost')"
        f" AND ForecastCategoryName != 'Omitted'"
        f" AND {_DSR_OPP_FILTER}"
        f" AND {_SE_FILTER}"
        f" AND Technical_Lead__c != null"
        f" AND {_ICAV_FIELD} >= 30000"
        f" AND CloseDate >= {start}"
        f" AND CloseDate <= {end}"
        f" AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')"
        f" ORDER BY {_ICAV_FIELD} DESC NULLS LAST"
        f" LIMIT 500"
    )


def _soql_unassigned(start: str, end: str) -> str:
    """Open DSR opps with no SE assigned, iACV >= 30K."""
    return (
        f"SELECT Id, Name, CloseDate, StageName, ForecastCategoryName,"
        f" Presales_Stage__c, {_ICAV_FIELD},"
        f" eARR_post_Launch__c,"
        f" Owner.Name, Owner.UserRole.Name,"
        f" Account.Name,"
        f" NextStep, LastActivityDate,"
        f" Renegotiated_Deal_SE_Involved__c,"
        f" FY_16_Owner_Team__c"
        f" FROM Opportunity"
        f" WHERE StageName NOT IN ('Closed Won', 'Closed Lost')"
        f" AND ForecastCategoryName != 'Omitted'"
        f" AND {_DSR_OPP_FILTER}"
        f" AND Technical_Lead__c = null"
        f" AND {_ICAV_FIELD} >= 30000"
        f" AND CloseDate >= {start}"
        f" AND CloseDate <= {end}"
        f" AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')"
        f" AND Renegotiated_Deal_SE_Involved__c != 'No'"
        f" ORDER BY {_ICAV_FIELD} DESC NULLS LAST"
        f" LIMIT 200"
    )


# ---------------------------------------------------------------------------
# Record transformers
# ---------------------------------------------------------------------------

def _is_expansion(opp: dict) -> bool:
    role = ((opp.get("Owner") or {}).get("UserRole") or {}).get("Name") or ""
    fy16 = (opp.get("FY_16_Owner_Team__c") or "")
    return "Expansion" in role or "Expansion" in fy16


def _icav(opp: dict) -> int:
    try:
        return int(float(opp.get(_ICAV_FIELD) or 0))
    except (TypeError, ValueError):
        return 0


def _earr(opp: dict) -> int:
    try:
        return int(float(opp.get("eARR_post_Launch__c") or 0))
    except (TypeError, ValueError):
        return 0


def _fmt_opp(opp: dict) -> dict:
    tl    = opp.get("Technical_Lead__r") or {}
    owner = opp.get("Owner") or {}
    acct  = opp.get("Account") or {}
    oid   = opp.get("Id") or ""

    presales     = (opp.get("Presales_Stage__c") or "").strip()
    forecast_cat = (opp.get("ForecastCategoryName") or "").strip()
    is_tw        = presales == "4 - Technical Win Achieved"
    expansion    = _is_expansion(opp)

    mismatch = _check_mismatch(forecast_cat, presales)

    return {
        "id":              oid,
        "name":            (opp.get("Name") or "").strip(),
        "account":         (acct.get("Name") or "").strip(),
        "account_id":      (opp.get("AccountId") or "").strip(),
        "account_website": (acct.get("Website") or "").strip(),
        "account_notes":   (acct.get("SE_Notes__c") or "").strip(),
        "se_name":         (tl.get("Name") or "").strip(),
        "ae_name":         (owner.get("Name") or "").strip(),
        "ae_role":         ((owner.get("UserRole") or {}).get("Name") or "").strip(),
        "stage":           (opp.get("StageName") or "").strip(),
        "presales":        presales,
        "presales_short":  presales.replace(r"^\d+ - ", "").strip() if presales else "",
        "forecast_cat":    forecast_cat,
        "close_date":      opp.get("CloseDate") or "",
        "icav":            _icav(opp),
        "earr":            _earr(opp),
        "current_earr":    int(float(opp.get("Current_eARR__c") or 0)),
        "incremental_acv": int(float(opp.get("Incremental_ACV__c") or 0)),
        "next_step":       (opp.get("NextStep") or "").strip(),
        "last_activity":   opp.get("LastActivityDate") or "",
        "se_notes":        (opp.get("Sales_Engineer_Notes__c") or "").strip(),
        "se_history":      (opp.get("SE_Notes_History__c") or "").strip(),
        "is_tw":           is_tw,
        "is_expansion":    expansion,
        "mismatch":        mismatch,
    }


def _fmt_unassigned(opp: dict) -> dict:
    owner = opp.get("Owner") or {}
    acct  = opp.get("Account") or {}
    return {
        "id":           opp.get("Id") or "",
        "name":         (opp.get("Name") or "").strip(),
        "account":      (acct.get("Name") or "").strip(),
        "ae_name":      (owner.get("Name") or "").strip(),
        "stage":        (opp.get("StageName") or "").strip(),
        "presales":     (opp.get("Presales_Stage__c") or "").strip(),
        "forecast_cat": (opp.get("ForecastCategoryName") or "").strip(),
        "close_date":   opp.get("CloseDate") or "",
        "icav":         _icav(opp),
        "earr":         _earr(opp),
        "next_step":    (opp.get("NextStep") or "").strip(),
        "last_activity": opp.get("LastActivityDate") or "",
        "se_involved":  (opp.get("Renegotiated_Deal_SE_Involved__c") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Mismatch rules
# ---------------------------------------------------------------------------

_MISMATCH_RULES = {
    "Pipeline":    {"allowed": {"1 - Qualified"}},
    "Best Case":   {"allowed": {"2 - Discovery", "3 - Technical Evaluation"}},
    "Most Likely": {"allowed": {"3 - Technical Evaluation", "4 - Technical Win Achieved"}},
    "Commit":      {"allowed": {"4 - Technical Win Achieved"}},
}

_STAGE_LABEL = {
    "1 - Qualified":             "Qualified",
    "2 - Discovery":             "Discovery",
    "3 - Technical Evaluation":  "Technical Evaluation",
    "4 - Technical Win Achieved": "Technical Win",
}


def _check_mismatch(forecast_cat: str, presales: str) -> str | None:
    if not presales:
        return "No Presales Stage set"
    rule = _MISMATCH_RULES.get(forecast_cat)
    if not rule:
        return None
    if presales not in rule["allowed"]:
        allowed = " or ".join(_STAGE_LABEL.get(s, s) for s in sorted(rule["allowed"]))
        return f"{forecast_cat} expects {allowed}"
    return None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_TTL = 300  # 5 min


def _cache_path(period_key: str) -> Path:
    return OUTPUT_DIR / f"sf_forecast_dsr_{period_key}.json"


def _is_fresh(period_key: str) -> bool:
    if _LOCAL_DEV:
        return False
    p = _cache_path(period_key)
    return p.exists() and (time.time() - p.stat().st_mtime) < _CACHE_TTL


def _load_cache(period_key: str) -> dict | None:
    p = _cache_path(period_key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(period_key: str, data: dict):
    if _LOCAL_DEV:
        return
    p   = _cache_path(period_key)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(p)


# ---------------------------------------------------------------------------
# Data fetch & build
# ---------------------------------------------------------------------------

def _fetch(period_key: str, start: str, end: str) -> tuple[dict | None, str | None]:
    if _is_fresh(period_key):
        cached = _load_cache(period_key)
        if cached:
            return cached, None

    if not sf.configured:
        stale = _load_cache(period_key)
        if stale:
            return stale, None
        return None, "Salesforce is not configured."

    try:
        assigned_opps   = sf.query(_soql_assigned(start, end), timeout=60)
        unassigned_opps = sf.query(_soql_unassigned(start, end), timeout=60)
    except Exception as e:
        stale = _load_cache(period_key)
        if stale:
            log.warning("SF error, serving stale: %s", e)
            return stale, None
        return None, f"Salesforce query failed: {e}"

    formatted   = [_fmt_opp(o) for o in (assigned_opps or [])]
    unassigned  = [_fmt_unassigned(o) for o in (unassigned_opps or [])]

    # Split assigned into views
    no_tw_act   = [d for d in formatted if not d["is_tw"] and not d["is_expansion"]]
    no_tw_exp   = [d for d in formatted if not d["is_tw"] and d["is_expansion"]]
    tw_open     = [d for d in formatted if d["is_tw"]]

    # Group no_tw_act by SE
    act_by_se   = _group_by_se(no_tw_act)
    exp_by_se   = _group_by_se(no_tw_exp)

    data = {
        "act_by_se":  act_by_se,
        "exp_by_se":  exp_by_se,
        "tw_open":    tw_open,
        "unassigned": unassigned,
        "summary":    _build_summary(formatted, unassigned),
    }
    _save_cache(period_key, data)
    return data, None


def _group_by_se(deals: list) -> list:
    """Group deals by SE name, sorted by total iACV desc."""
    by_se: dict[str, dict] = {}
    for d in deals:
        se = d["se_name"] or "Unassigned"
        if se not in by_se:
            by_se[se] = {"se_name": se, "total_icav": 0, "total_earr": 0, "deals": []}
        by_se[se]["deals"].append(d)
        by_se[se]["total_icav"] += d["icav"]
        by_se[se]["total_earr"] += d["earr"]
    groups = sorted(by_se.values(), key=lambda x: x["total_icav"], reverse=True)
    # sort deals within each group by iACV desc
    for g in groups:
        g["deals"].sort(key=lambda d: d["icav"], reverse=True)
    return groups


def _build_summary(assigned: list, unassigned: list) -> dict:
    total_icav      = sum(d["icav"] for d in assigned)
    tw_icav         = sum(d["icav"] for d in assigned if d["is_tw"])
    no_tw_icav      = sum(d["icav"] for d in assigned if not d["is_tw"])
    mismatch_deals  = [d for d in assigned if d["mismatch"]]
    mismatch_icav   = sum(d["icav"] for d in mismatch_deals)

    by_cat: dict[str, dict] = {}
    for d in assigned:
        cat = d["forecast_cat"] or "Omitted"
        if cat not in by_cat:
            by_cat[cat] = {"icav": 0, "count": 0, "mismatch_icav": 0, "mismatch_count": 0}
        by_cat[cat]["icav"]  += d["icav"]
        by_cat[cat]["count"] += 1
        if d["mismatch"]:
            by_cat[cat]["mismatch_icav"]  += d["icav"]
            by_cat[cat]["mismatch_count"] += 1

    return {
        "total_deals":      len(assigned),
        "total_icav":       total_icav,
        "tw_icav":          tw_icav,
        "tw_count":         sum(1 for d in assigned if d["is_tw"]),
        "no_tw_icav":       no_tw_icav,
        "no_tw_count":      sum(1 for d in assigned if not d["is_tw"]),
        "mismatch_count":   len(mismatch_deals),
        "mismatch_icav":    mismatch_icav,
        "mismatch_pct":     round(mismatch_icav / total_icav * 100) if total_icav else 0,
        "unassigned_count": len(unassigned),
        "unassigned_icav":  sum(d["icav"] for d in unassigned),
        "by_cat":           by_cat,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@se_forecast_bp.route("/api/se-forecast/pipeline")
def api_pipeline():
    start, end_cur, end_next, period_key, label_cur, label_next = _two_quarter_range()
    data, err = _fetch(period_key, start, end_next)
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

    # Verify caller is the Technical Lead on this opportunity
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


# ---------------------------------------------------------------------------
# Account enrichment — scrape website + Bedrock LLM classification
# ---------------------------------------------------------------------------

import re as _re

_BEDROCK_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_AWS_REGION    = os.environ.get("REGION", "us-west-2")


def _fetch_website_text(url: str) -> str:
    import requests as _req
    from bs4 import BeautifulSoup
    if not url.startswith("http"):
        url = "https://" + url
    try:
        resp = _req.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return " ".join(soup.get_text(" ", strip=True).split())[:8000]
    except Exception as e:
        log.warning("Website fetch failed for %s: %s", url, e)
        return ""


_LLM_SYSTEM = """You are a B2B business analyst. Given a company name and optional website excerpt, output a JSON object with:
- "business_model": one short sentence (max 15 words)
- "category": one of ["Lead Generation", "Lead Management", "Marketing / Advertising", "E-commerce", "SaaS / Software", "Financial Services", "Healthcare", "Logistics / Operations", "Media / Content", "Other"]
- "is_lead_gen_or_marketing": true if the category is Lead Generation, Lead Management, or Marketing / Advertising, else false
- "tags": array of 1-3 short descriptive tags (e.g. "performance marketing", "affiliate network", "lead routing")

Respond with ONLY valid JSON. No explanation."""


def _classify_with_bedrock(account_name: str, website_text: str) -> dict:
    import boto3
    client = boto3.client("bedrock-runtime", region_name=_AWS_REGION)
    prompt = f"Company: {account_name}\n\nWebsite excerpt:\n{website_text[:6000]}" if website_text else f"Company: {account_name}"
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "system": _LLM_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    })
    try:
        resp = client.invoke_model(modelId=_BEDROCK_MODEL, body=body, contentType="application/json", accept="application/json")
        raw = json.loads(resp["body"].read())["content"][0]["text"].strip()
        # Strip any markdown fences
        raw = _re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=_re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        log.warning("Bedrock classify failed: %s", e)
        return {"business_model": "Could not determine", "category": "Other", "is_lead_gen_or_marketing": False, "tags": []}


@se_forecast_bp.route("/api/se-forecast/enrich", methods=["POST"])
def api_enrich():
    if not session.get("user_email"):
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    account_name    = (body.get("account_name") or "").strip()[:200]
    account_website = (body.get("account_website") or "").strip()[:200]
    if not account_name:
        return jsonify({"error": "account_name required"}), 400

    website_text = _fetch_website_text(account_website) if account_website else ""
    result = _classify_with_bedrock(account_name, website_text)
    result["account_name"] = account_name
    result["website"]      = account_website
    return jsonify(result)


_DEAL_SUMMARY_SYSTEM = """You are a sales intelligence assistant. Given an opportunity's notes, next steps, and context, output a JSON object with exactly these fields:

- "next_steps": 1-2 sentences summarizing the immediate next actions and most recent SE activity
- "next_meeting_date": ISO date (YYYY-MM-DD) of the next scheduled call or meeting after today, or null if none found
- "next_meeting_label": short human-readable label (e.g. "POC review May 14", "Executive QBR Jun 3"), or null if none found
- "confidence": one of ["High", "Medium", "Low"] — confidence this deal closes by the close date
- "confidence_reason": one short sentence (max 15 words) explaining the confidence level

Respond with ONLY valid JSON. No explanation, no markdown."""


def _summarize_with_bedrock(opp_name: str, close_date: str, se_notes: str, se_history: str, next_step: str, last_activity: str) -> dict:
    import boto3, json as _json
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = f"""Opportunity: {opp_name}
Close date: {close_date}
Today: {today}

AE Next Step: {next_step or 'Not set'}
Last Activity: {last_activity or 'Unknown'}

SE Notes:
{se_notes or 'No SE notes'}

SE History:
{se_history or 'No SE history'}"""

    client = boto3.client("bedrock-runtime", region_name=_AWS_REGION)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "system": _DEAL_SUMMARY_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = client.invoke_model(modelId=_BEDROCK_MODEL, body=_json.dumps(body))
        raw = _json.loads(resp["body"].read())["content"][0]["text"].strip()
        raw = _re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=_re.MULTILINE).strip()
        log.info("Bedrock summarize raw: %s", raw[:300])
        return _json.loads(raw)
    except Exception as e:
        log.warning("Bedrock summarize failed: %s", e)
        return {"next_steps": "Could not summarize", "next_meeting_date": None, "next_meeting_label": None, "confidence": "Low", "confidence_reason": "Summarization failed"}


@se_forecast_bp.route("/api/se-forecast/summarize", methods=["POST"])
def api_summarize():
    if not session.get("user_email"):
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    opp_id       = (body.get("id") or "").strip()[:50]
    opp_name     = (body.get("name") or "").strip()[:200]
    close_date   = (body.get("close_date") or "").strip()[:20]
    se_notes     = (body.get("se_notes") or "").strip()[:4000]
    se_history   = (body.get("se_history") or "").strip()[:4000]
    next_step    = (body.get("next_step") or "").strip()[:500]
    last_activity = (body.get("last_activity") or "").strip()[:30]
    if not opp_id:
        return jsonify({"error": "id required"}), 400

    result = _summarize_with_bedrock(opp_name, close_date, se_notes, se_history, next_step, last_activity)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Chat context — auto-discovered by app.py via CHAT_APP_ID + get_chat_context
# ---------------------------------------------------------------------------

CHAT_APP_ID = "se-forecast"

_SOQL_SCHEMA = """
Salesforce Opportunity fields available:
  Id, Name, CloseDate, StageName, ForecastCategoryName, Amount, Type
  Comms_Segment_Combined_iACV__c  (iACV — primary revenue metric)
  eARR_post_launch_No_Decimal__c, eARR_post_Launch__c  (eARR)
  Incremental_ACV__c, Current_eARR__c
  FY_16_Owner_Team__c
  Presales_Stage__c               ('4 - Technical Win Achieved' = TW)
  Technical_Lead__r.Name, Technical_Lead__r.Email, Technical_Lead__r.UserRole.Name
  Owner.Name, Owner.UserRole.Name
  Account.Name, Account.Owner.Name, Account.Website, Account.SE_Notes__c
  SE_Notes__c, SE_Notes_History__c, Sales_Engineer_Notes__c
  NextStep, LastActivityDate, RecordType.Name
  Renegotiated_Deal_SE_Involved__c
Standard date literals: TODAY, THIS_QUARTER, LAST_QUARTER, THIS_YEAR, LAST_N_DAYS:n
Limit results to 50 rows unless more are needed.
"""

_SYSTEM = (
    "You are an AI assistant embedded in the SE Forecast dashboard for the "
    "Twilio Digital Sales (Self Service) team. "
    "You have access to pre-loaded pipeline data (open opportunities for the current and next quarter) "
    f"and a run_soql tool to query Salesforce directly for additional detail.\n\n"
    f"{_SOQL_SCHEMA}\n"
    "Answer concisely. Format currency with $ and K/M suffixes. "
    "When using run_soql, scope queries to the DSR/Self Service team using the filters already "
    "present in the context (FY_16_Owner_Team__c LIKE 'DSR%' etc.)."
)


def get_chat_context(body: dict) -> tuple[str, str]:
    """Return (system_prompt, context) for the global /api/chat endpoint."""
    start, _end_cur, end_next, period_key, label_cur, label_next = _two_quarter_range()
    data, err = _fetch(period_key, start, end_next)
    if err or not data:
        return _SYSTEM, ""

    summary = data.get("summary", {})
    lines = [
        f"SE Forecast — Digital Sales (Self Service) team",
        f"Period: {label_cur} / {label_next}",
        f"Total assigned deals: {summary.get('total_deals', 0)} | Total iACV: ${summary.get('total_icav', 0):,}",
        f"Technical Wins: {summary.get('tw_count', 0)} (${summary.get('tw_icav', 0):,})",
        f"No-TW pipeline: {summary.get('no_tw_count', 0)} (${summary.get('no_tw_icav', 0):,})",
        f"Mismatches: {summary.get('mismatch_count', 0)} (${summary.get('mismatch_icav', 0):,})",
        f"Unassigned: {summary.get('unassigned_count', 0)} (${summary.get('unassigned_icav', 0):,})",
        "",
        "--- Activation deals by SE ---",
    ]

    for group in data.get("act_by_se", []):
        lines.append(f"SE: {group['se_name']} | iACV: ${group['total_icav']:,} | {len(group['deals'])} deals")
        for d in group["deals"][:10]:
            tw = "[TW]" if d["is_tw"] else ""
            mm = f"[MISMATCH:{d['mismatch']}]" if d["mismatch"] else ""
            lines.append(
                f"  {d['name']} | acct:{d['account']} | stage:{d['stage']} | fc:{d['forecast_cat']} "
                f"| presales:{d['presales']} | iACV:${d['icav']:,} | close:{d['close_date']} "
                f"| AE:{d['ae_name']} {tw}{mm}"
            )

    lines.append("")
    lines.append("--- Expansion deals by SE ---")
    for group in data.get("exp_by_se", []):
        lines.append(f"SE: {group['se_name']} | iACV: ${group['total_icav']:,} | {len(group['deals'])} deals")
        for d in group["deals"][:5]:
            lines.append(
                f"  {d['name']} | acct:{d['account']} | stage:{d['stage']} | fc:{d['forecast_cat']} "
                f"| iACV:${d['icav']:,} | close:{d['close_date']}"
            )

    lines.append("")
    lines.append("--- Technical Wins (open) ---")
    for d in data.get("tw_open", [])[:20]:
        lines.append(
            f"  {d['name']} | acct:{d['account']} | SE:{d['se_name']} | iACV:${d['icav']:,} | close:{d['close_date']}"
        )

    lines.append("")
    lines.append("--- Unassigned deals ---")
    for d in data.get("unassigned", [])[:10]:
        lines.append(
            f"  {d['name']} | acct:{d['account']} | iACV:${d['icav']:,} | close:{d['close_date']} | AE:{d['ae_name']}"
        )

    return _SYSTEM, "\n".join(lines)
