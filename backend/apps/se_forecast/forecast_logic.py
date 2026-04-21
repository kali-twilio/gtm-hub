"""
SE Forecast — business logic, SOQL builders, data transformers, cache, and OpenAI integrations.
All non-route logic lives here; routes.py imports from this module.
"""
from __future__ import annotations

import json
import logging
import os
import re as _re
import time
from datetime import date, datetime, timezone
from pathlib import Path

from salesforce import sf

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

_LOCAL_DEV  = os.environ.get("LOCAL_DEV") == "1"
_ICAV_FIELD = "Comms_Segment_Combined_iACV__c"

# ---------------------------------------------------------------------------
# Quarter helpers
# ---------------------------------------------------------------------------

_QS = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}
_QE = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def current_quarter() -> tuple[str, str, str, str]:
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


def two_quarter_range() -> tuple[str, str, str, str, str, str]:
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
# DSR team filters
# ---------------------------------------------------------------------------

_SE_FILTER = (
    "Technical_Lead__r.UserRole.Name = 'SE - Self Service'"
    " AND Technical_Lead__r.Title LIKE '%Engineer%'"
)

_DSR_OPP_FILTER = (
    "(FY_16_Owner_Team__c LIKE 'DSR%'"
    " OR (Owner.UserRole.Name LIKE '%DSR%'"
    " AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')))"
)

_IS_EXPANSION  = "(Owner.UserRole.Name LIKE '%Expansion%' OR FY_16_Owner_Team__c LIKE '%Expansion%')"
_NOT_EXPANSION = "(NOT Owner.UserRole.Name LIKE '%Expansion%') AND (NOT FY_16_Owner_Team__c LIKE '%Expansion%')"


# ---------------------------------------------------------------------------
# SOQL builders
# ---------------------------------------------------------------------------

def soql_assigned(start: str, end: str) -> str:
    return (
        f"SELECT Id, Name, CloseDate, StageName, ForecastCategoryName,"
        f" Presales_Stage__c, {_ICAV_FIELD},"
        f" eARR_post_Launch__c, Incremental_ACV__c, Current_eARR__c,"
        f" NextStep, LastActivityDate,"
        f" Technical_Lead__r.Name, Technical_Lead__r.UserRole.Name,"
        f" Owner.Name, Owner.UserRole.Name,"
        f" AccountId, Account.Name, Account.Website, Account.SE_Notes__c, Account.BillingCountry,"
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


def soql_ps_engagement(opp_ids: list[str]) -> str:
    id_list = ", ".join(f"'{oid}'" for oid in opp_ids)
    return (
        f"SELECT Opportunity__c, Assigned_To__r.Name"
        f" FROM Demo_Engineering_Request__c"
        f" WHERE Opportunity__c IN ({id_list})"
        f" AND Assigned_To__c != null"
    )


def soql_unassigned(start: str, end: str) -> str:
    return (
        f"SELECT Id, Name, CloseDate, StageName, ForecastCategoryName,"
        f" Presales_Stage__c, {_ICAV_FIELD},"
        f" eARR_post_Launch__c,"
        f" Owner.Name, Owner.UserRole.Name,"
        f" Account.Name, Account.BillingCountry,"
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

def is_expansion(opp: dict) -> bool:
    role = ((opp.get("Owner") or {}).get("UserRole") or {}).get("Name") or ""
    fy16 = (opp.get("FY_16_Owner_Team__c") or "")
    return "Expansion" in role or "Expansion" in fy16


def _parse_int_field(opp: dict, field: str) -> int:
    try:
        return int(float(opp.get(field) or 0))
    except (TypeError, ValueError):
        return 0


def _icav(opp: dict) -> int:
    return _parse_int_field(opp, _ICAV_FIELD)


def _earr(opp: dict) -> int:
    return _parse_int_field(opp, "eARR_post_Launch__c")


_MISMATCH_RULES = {
    "Pipeline":    {"allowed": {"1 - Qualified"}},
    "Best Case":   {"allowed": {"2 - Discovery", "3 - Technical Evaluation"}},
    "Most Likely": {"allowed": {"3 - Technical Evaluation", "4 - Technical Win Achieved"}},
    "Commit":      {"allowed": {"4 - Technical Win Achieved"}},
}

_STAGE_LABEL = {
    "1 - Qualified":              "Qualified",
    "2 - Discovery":              "Discovery",
    "3 - Technical Evaluation":   "Technical Evaluation",
    "4 - Technical Win Achieved": "Technical Win",
}


def check_mismatch(forecast_cat: str, presales: str) -> str | None:
    if not presales:
        return "No Presales Stage set"
    rule = _MISMATCH_RULES.get(forecast_cat)
    if not rule:
        return None
    if presales not in rule["allowed"]:
        allowed = " or ".join(_STAGE_LABEL.get(s, s) for s in sorted(rule["allowed"]))
        return f"{forecast_cat} expects {allowed}"
    return None


def fmt_opp(opp: dict) -> dict:
    tl    = opp.get("Technical_Lead__r") or {}
    owner = opp.get("Owner") or {}
    acct  = opp.get("Account") or {}
    oid   = opp.get("Id") or ""

    presales     = (opp.get("Presales_Stage__c") or "").strip()
    forecast_cat = (opp.get("ForecastCategoryName") or "").strip()
    is_tw        = presales == "4 - Technical Win Achieved"
    expansion    = is_expansion(opp)

    mismatch = check_mismatch(forecast_cat, presales)

    return {
        "id":              oid,
        "name":            (opp.get("Name") or "").strip(),
        "account":         (acct.get("Name") or "").strip(),
        "account_id":      (opp.get("AccountId") or "").strip(),
        "account_website": (acct.get("Website") or "").strip(),
        "account_notes":   (acct.get("SE_Notes__c") or "").strip(),
        "account_country": (acct.get("BillingCountry") or "").strip(),
        "se_name":         (tl.get("Name") or "").strip(),
        "ae_name":         (owner.get("Name") or "").strip(),
        "ae_role":         ((owner.get("UserRole") or {}).get("Name") or "").strip(),
        "stage":           (opp.get("StageName") or "").strip(),
        "presales":        presales,
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


def fmt_unassigned(opp: dict) -> dict:
    owner = opp.get("Owner") or {}
    acct  = opp.get("Account") or {}
    return {
        "id":           opp.get("Id") or "",
        "name":         (opp.get("Name") or "").strip(),
        "account":         (acct.get("Name") or "").strip(),
        "account_country": (acct.get("BillingCountry") or "").strip(),
        "ae_name":         (owner.get("Name") or "").strip(),
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
# Cache
# ---------------------------------------------------------------------------

_CACHE_TTL = 300  # 5 min


def cache_path(period_key: str) -> Path:
    return OUTPUT_DIR / f"sf_forecast_dsr_{period_key}.json"


def is_fresh(period_key: str) -> bool:
    if _LOCAL_DEV:
        return False
    p = cache_path(period_key)
    return p.exists() and (time.time() - p.stat().st_mtime) < _CACHE_TTL


def load_cache(period_key: str) -> dict | None:
    p = cache_path(period_key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cache(period_key: str, data: dict):
    if _LOCAL_DEV:
        return
    p   = cache_path(period_key)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(p)


# ---------------------------------------------------------------------------
# Data fetch & build
# ---------------------------------------------------------------------------

def group_by_se(deals: list) -> list:
    by_se: dict[str, dict] = {}
    for d in deals:
        se = d["se_name"] or "Unassigned"
        if se not in by_se:
            by_se[se] = {"se_name": se, "total_icav": 0, "total_earr": 0, "deals": []}
        by_se[se]["deals"].append(d)
        by_se[se]["total_icav"] += d["icav"]
        by_se[se]["total_earr"] += d["earr"]
    groups = sorted(by_se.values(), key=lambda x: x["total_icav"], reverse=True)
    for g in groups:
        g["deals"].sort(key=lambda d: d["icav"], reverse=True)
    return groups


def build_summary(assigned: list, unassigned: list) -> dict:
    total_icav     = sum(d["icav"] for d in assigned)
    tw_icav        = sum(d["icav"] for d in assigned if d["is_tw"])
    no_tw_icav     = sum(d["icav"] for d in assigned if not d["is_tw"])
    mismatch_deals = [d for d in assigned if d["mismatch"]]
    mismatch_icav  = sum(d["icav"] for d in mismatch_deals)

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


def fetch_pipeline(period_key: str, start: str, end: str) -> tuple[dict | None, str | None]:
    if is_fresh(period_key):
        cached = load_cache(period_key)
        if cached:
            return cached, None

    if not sf.configured:
        stale = load_cache(period_key)
        if stale:
            return stale, None
        return None, "Salesforce is not configured."

    try:
        assigned_opps   = sf.query(soql_assigned(start, end), timeout=60)
        unassigned_opps = sf.query(soql_unassigned(start, end), timeout=60)
    except Exception as e:
        stale = load_cache(period_key)
        if stale:
            log.warning("SF error, serving stale: %s", e)
            return stale, None
        return None, f"Salesforce query failed: {e}"

    formatted  = [fmt_opp(o) for o in (assigned_opps or [])]
    unassigned = [fmt_unassigned(o) for o in (unassigned_opps or [])]

    opp_ids = [d["id"] for d in formatted if d["id"]]
    ps_by_opp: dict[str, list[str]] = {}
    if opp_ids:
        try:
            der_records = sf.query(soql_ps_engagement(opp_ids), timeout=30) or []
            for rec in der_records:
                oid     = rec.get("Opportunity__c") or ""
                ps_name = ((rec.get("Assigned_To__r") or {}).get("Name") or "").strip()
                if oid and ps_name:
                    ps_by_opp.setdefault(oid, [])
                    if ps_name not in ps_by_opp[oid]:
                        ps_by_opp[oid].append(ps_name)
        except Exception as e:
            log.warning("PS engagement query failed (non-fatal): %s", e)

    for d in formatted:
        d["ps_names"] = ps_by_opp.get(d["id"], [])

    no_tw_act, no_tw_exp, tw_open = [], [], []
    for d in formatted:
        if d["is_tw"]:
            tw_open.append(d)
        elif d["is_expansion"]:
            no_tw_exp.append(d)
        else:
            no_tw_act.append(d)

    data = {
        "act_by_se":  group_by_se(no_tw_act),
        "exp_by_se":  group_by_se(no_tw_exp),
        "tw_open":    tw_open,
        "unassigned": unassigned,
        "summary":    build_summary(formatted, unassigned),
    }
    save_cache(period_key, data)
    return data, None


# ---------------------------------------------------------------------------
# OpenAI — account enrichment
# ---------------------------------------------------------------------------

_OPENAI_MODEL = "gpt-4o"


def _strip_json_fences(raw: str) -> str:
    return _re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=_re.MULTILINE).strip()


def fetch_website_text(url: str) -> str:
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


def classify_account(account_name: str, website_text: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = f"Company: {account_name}\n\nWebsite excerpt:\n{website_text[:6000]}" if website_text else f"Company: {account_name}"
    try:
        resp = client.chat.completions.create(
            model=_OPENAI_MODEL,
            max_tokens=256,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        raw = _strip_json_fences(resp.choices[0].message.content.strip())
        return json.loads(raw)
    except Exception as e:
        log.warning("OpenAI classify failed: %s", e)
        return {"business_model": "Could not determine", "category": "Other", "is_lead_gen_or_marketing": False, "tags": []}


# ---------------------------------------------------------------------------
# OpenAI — deal summarization
# ---------------------------------------------------------------------------

_DEAL_SUMMARY_SYSTEM = """You are a sales intelligence assistant. Given an opportunity's notes, next steps, and context, output a JSON object with exactly these fields:

- "next_steps": 1-2 sentences summarizing the immediate next actions and most recent SE activity
- "next_meeting_date": ISO date (YYYY-MM-DD) of the next scheduled call or meeting after today, or null if none found
- "next_meeting_label": short human-readable label (e.g. "POC review May 14", "Executive QBR Jun 3"), or null if none found
- "confidence": one of ["High", "Medium", "Low"] — confidence this deal closes by the close date
- "confidence_reason": one short sentence (max 15 words) explaining the confidence level

Respond with ONLY valid JSON. No explanation, no markdown."""


def summarize_deal(opp_name: str, close_date: str, se_notes: str, se_history: str, next_step: str, last_activity: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    today  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = f"""Opportunity: {opp_name}
Close date: {close_date}
Today: {today}

AE Next Step: {next_step or 'Not set'}
Last Activity: {last_activity or 'Unknown'}

SE Notes:
{se_notes or 'No SE notes'}

SE History:
{se_history or 'No SE history'}"""

    try:
        resp = client.chat.completions.create(
            model=_OPENAI_MODEL,
            max_tokens=400,
            messages=[
                {"role": "system", "content": _DEAL_SUMMARY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        raw = _strip_json_fences(resp.choices[0].message.content.strip())
        log.info("OpenAI summarize raw: %s", raw[:300])
        return json.loads(raw)
    except Exception as e:
        log.warning("OpenAI summarize failed: %s", e)
        return {"next_steps": "Could not summarize", "next_meeting_date": None, "next_meeting_label": None, "confidence": "Low", "confidence_reason": "Summarization failed"}


# ---------------------------------------------------------------------------
# Chat context
# ---------------------------------------------------------------------------

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

CHAT_SYSTEM = """You are an AI assistant embedded in the SE Forecast dashboard for the Twilio Digital Sales (Self Service) team.
You have access to pre-loaded pipeline data (open opportunities for the current and next quarter) and a run_soql tool to query Salesforce directly for additional detail.

## Revenue metrics
- iACV = Comms_Segment_Combined_iACV__c — the primary revenue metric. All dollar figures in this dashboard are iACV unless stated otherwise.
- eARR = eARR_post_Launch__c — post-launch ARR. Used as a secondary metric.
- Incremental_ACV__c and Current_eARR__c are supplemental and rarely used.

## Team scope — always apply these filters when calling run_soql
DSR opp filter (use for all pipeline/closed queries):
  (FY_16_Owner_Team__c LIKE 'DSR%'
   OR (Owner.UserRole.Name LIKE '%DSR%' AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')))

SE-tagged filter (add when asking about specific SE performance):
  Technical_Lead__r.UserRole.Name = 'SE - Self Service'
  AND Technical_Lead__r.Title LIKE '%Engineer%'

Closed Won filter: StageName = 'Closed Won'
Open pipeline filter: StageName NOT IN ('Closed Won', 'Closed Lost') AND ForecastCategoryName != 'Omitted'

## Forecast categories (open pipeline)
Pipeline → Presales_Stage__c should be '1 - Qualified'
Best Case → should be '2 - Discovery' or '3 - Technical Evaluation'
Most Likely → should be '3 - Technical Evaluation' or '4 - Technical Win Achieved'
Commit → should be '4 - Technical Win Achieved'
A mismatch means ForecastCategoryName and Presales_Stage__c are misaligned.

## Technical Win (TW)
Presales_Stage__c = '4 - Technical Win Achieved'. TW deals are the most confident pipeline signal — the SE has technically validated the deal.

## Activate vs Expansion
Activate (new logos): Owner.UserRole.Name LIKE '%Activation%' OR (FY_16_Owner_Team__c LIKE 'DSR%' AND NOT 'Expansion')
Expansion (existing accounts): Owner.UserRole.Name LIKE '%Expansion%' OR FY_16_Owner_Team__c LIKE '%Expansion%'

## SOQL examples for common questions
Closed Won this quarter for DSR team (SE-tagged, iACV ≥ $30K):
  SELECT Technical_Lead__r.Name, SUM(Comms_Segment_Combined_iACV__c) icav
  FROM Opportunity
  WHERE StageName = 'Closed Won'
  AND CloseDate = THIS_QUARTER
  AND (FY_16_Owner_Team__c LIKE 'DSR%' OR (Owner.UserRole.Name LIKE '%DSR%' AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')))
  AND Technical_Lead__r.UserRole.Name = 'SE - Self Service'
  AND Technical_Lead__r.Title LIKE '%Engineer%'
  AND Comms_Segment_Combined_iACV__c >= 30000
  GROUP BY Technical_Lead__r.Name
  ORDER BY icav DESC

Open pipeline by forecast category:
  SELECT ForecastCategoryName, COUNT(Id) cnt, SUM(Comms_Segment_Combined_iACV__c) icav
  FROM Opportunity
  WHERE StageName NOT IN ('Closed Won', 'Closed Lost')
  AND ForecastCategoryName != 'Omitted'
  AND (FY_16_Owner_Team__c LIKE 'DSR%' OR (Owner.UserRole.Name LIKE '%DSR%' AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')))
  AND CloseDate = THIS_QUARTER
  GROUP BY ForecastCategoryName

## Formatting
Answer concisely. Format currency with $ and K/M suffixes. Always scope run_soql to the DSR team.

""" + f"{_SOQL_SCHEMA}"


def build_chat_context(body: dict) -> tuple[str, str]:
    """Return (system_prompt, context) for the global /api/chat endpoint."""
    start, _end_cur, end_next, period_key, label_cur, label_next = two_quarter_range()
    data, err = fetch_pipeline(period_key, start, end_next)
    if err or not data:
        return CHAT_SYSTEM, ""

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

    return CHAT_SYSTEM, "\n".join(lines)
