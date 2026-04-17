"""
SE Scorecard V2 — Flask Blueprint.
Data is fetched live from Salesforce on demand and cached per-team per-period.
Current quarter: 10-minute TTL. Historical quarters/years: 1-week TTL.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import requests as http_requests
from flask import Blueprint, jsonify, request, session

from salesforce import sf
from . import sf_analysis

log = logging.getLogger(__name__)

se_scorecard_v2_bp = Blueprint("se_scorecard_v2", __name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

_ICAV_PRESETS = {0, 10_000, 30_000, 50_000, 100_000}

def _parse_icav_min(raw: str | None) -> tuple[int, str | None]:
    """Parse and validate icav_min. Returns (value, error) — only preset values allowed."""
    try:
        val = int(raw or 0)
    except (ValueError, TypeError):
        return 0, "icav_min must be an integer"
    if val not in _ICAV_PRESETS:
        return 0, f"icav_min must be one of {sorted(_ICAV_PRESETS)}"
    return val, None

# ---------------------------------------------------------------------------
# Team config — add new teams here; no other file needs to change
# ---------------------------------------------------------------------------

TEAMS = {
    "digital_sales": {
        "label":            "Digital Sales",
        "description":      "Self Service SE team (DSR)",
        "motion":           "dsr",
        "team_total_filter": (
            "(FY_16_Owner_Team__c LIKE 'DSR%'"
            " OR (Owner.UserRole.Name LIKE '%DSR%'"
            " AND (NOT (Owner.UserRole.Name LIKE '%Twilio.org%'))))"
        ),
        "soql_filter": (
            # Primary: FY_16_Owner_Team__c stamped as DSR (frozen at assignment — survives AE role changes).
            # Fallback: owner's current UserRole contains DSR but FY_16 was never stamped correctly
            #   (observed as null/'Not Found'/'Digital Sales Representative'/'Sales Operations').
            #   Excludes Twilio.org roles to avoid org-specific opps.
            "(FY_16_Owner_Team__c LIKE 'DSR%'"
            " OR (Owner.UserRole.Name LIKE '%DSR%'"
            " AND (NOT (Owner.UserRole.Name LIKE '%Twilio.org%'))))"
            " AND Technical_Lead__r.UserRole.Name = 'SE - Self Service'"
            " AND Technical_Lead__r.Title LIKE '%Engineer%'"
        ),
        # Historical periods: FY_16_Owner_Team__c didn't exist pre-2026; use SE role only
        "historical_soql_filter": (
            "Technical_Lead__r.UserRole.Name = 'SE - Self Service'"
            " AND Technical_Lead__r.Title LIKE '%Engineer%'"
        ),
        "email_owner_filter": "Owner.UserRole.Name = 'SE - Self Service'",
        "criteria": [
            {
                "label":  "DSR Opportunity",
                "detail": "FY_16_Owner_Team__c starts with 'DSR' (stamped at assignment) OR owner's current role contains 'DSR' (fallback for opps where FY_16 was never stamped). Excludes Twilio.org roles.",
            },
            {
                "label":  "SE Tagged",
                "detail": "Technical Lead role = 'SE - Self Service' and title contains 'Engineer'",
            },
        ],
    },
    "namer": {
        "label":            "NAMER",
        "description":      "All NAMER SEs",
        "motion":           "ae",
        "team_total_filter": "Owner.UserRole.Name LIKE '%NAMER%'",
        "soql_filter":      "Technical_Lead__r.UserRole.Name LIKE 'SE - NAMER%'",
        "email_owner_filter": "Owner.UserRole.Name LIKE 'SE - NAMER%'",
        "criteria": [
            {
                "label":  "SE Tagged",
                "detail": "Technical Lead UserRole starts with 'SE - NAMER'",
            },
        ],
        "subteams": [
            {"key": "namer_retail",   "label": "Retail",   "soql_filter": "Technical_Lead__r.UserRole.Name = 'SE - NAMER - Retail'",   "email_owner_filter": "Owner.UserRole.Name = 'SE - NAMER - Retail'"},
            {"key": "namer_nb",       "label": "NB",       "soql_filter": "Technical_Lead__r.UserRole.Name = 'SE - NAMER - NB'",       "email_owner_filter": "Owner.UserRole.Name = 'SE - NAMER - NB'"},
            {"key": "namer_isv",      "label": "ISV",      "soql_filter": "Technical_Lead__r.UserRole.Name IN ('SE - NAMER - ISV1', 'SE - NAMER - ISV2')", "email_owner_filter": "Owner.UserRole.Name IN ('SE - NAMER - ISV1', 'SE - NAMER - ISV2')"},
            {"key": "namer_hightech", "label": "HighTech", "soql_filter": "Technical_Lead__r.UserRole.Name IN ('SE - NAMER - HighTech1', 'SE - NAMER - HighTech2')", "email_owner_filter": "Owner.UserRole.Name IN ('SE - NAMER - HighTech1', 'SE - NAMER - HighTech2')"},
            {"key": "namer_regverts", "label": "RegVerts", "soql_filter": "Technical_Lead__r.UserRole.Name IN ('SE - NAMER - RegVerts1', 'SE - NAMER - RegVerts2')", "email_owner_filter": "Owner.UserRole.Name IN ('SE - NAMER - RegVerts1', 'SE - NAMER - RegVerts2')"},
            {"key": "namer_martech",  "label": "MarTech",  "soql_filter": "Technical_Lead__r.UserRole.Name = 'SE - NAMER - MarTech'",  "email_owner_filter": "Owner.UserRole.Name = 'SE - NAMER - MarTech'"},
        ],
    },
    "emea": {
        "label":            "EMEA",
        "description":      "All EMEA SEs",
        "motion":           "ae",
        "team_total_filter": "Owner.UserRole.Name LIKE '%EMEA%'",
        "soql_filter":      "Technical_Lead__r.UserRole.Name LIKE 'SE - EMEA%'",
        "email_owner_filter": "Owner.UserRole.Name LIKE 'SE - EMEA%'",
        "criteria": [
            {
                "label":  "SE Tagged",
                "detail": "Technical Lead UserRole starts with 'SE - EMEA'",
            },
        ],
        "subteams": [
            {"key": "emea_north", "label": "North", "soql_filter": "Technical_Lead__r.UserRole.Name = 'SE - EMEA - North'", "email_owner_filter": "Owner.UserRole.Name = 'SE - EMEA - North'"},
            {"key": "emea_dach",  "label": "DACH",  "soql_filter": "Technical_Lead__r.UserRole.Name = 'SE - EMEA - DACH'",  "email_owner_filter": "Owner.UserRole.Name = 'SE - EMEA - DACH'"},
            {"key": "emea_south", "label": "South", "soql_filter": "Technical_Lead__r.UserRole.Name = 'SE - EMEA - South'", "email_owner_filter": "Owner.UserRole.Name = 'SE - EMEA - South'"},
        ],
    },
    "apj": {
        "label":            "APJ",
        "description":      "APJ SE team",
        "motion":           "ae",
        "team_total_filter": "Owner.UserRole.Name LIKE '%APJ%'",
        "soql_filter":      "Technical_Lead__r.UserRole.Name = 'SE - APJ'",
        "email_owner_filter": "Owner.UserRole.Name = 'SE - APJ'",
        "criteria": [
            {
                "label":  "SE Tagged",
                "detail": "Technical Lead UserRole = 'SE - APJ'",
            },
        ],
    },
    "latam": {
        "label":            "LATAM",
        "description":      "LATAM SE team",
        "motion":           "ae",
        "team_total_filter": "Owner.UserRole.Name LIKE '%LATAM%'",
        "soql_filter":      "Technical_Lead__r.UserRole.Name LIKE 'SE - LATAM%'",
        "email_owner_filter": "Owner.UserRole.Name LIKE 'SE - LATAM%'",
        "criteria": [
            {
                "label":  "SE Tagged",
                "detail": "Technical Lead UserRole starts with 'SE - LATAM'",
            },
        ],
        "subteams": [
            {"key": "latam_brazil", "label": "Brazil", "soql_filter": "Technical_Lead__r.UserRole.Name = 'SE - LATAM - BR'",  "email_owner_filter": "Owner.UserRole.Name = 'SE - LATAM - BR'"},
            {"key": "latam_rol",    "label": "ROL",    "soql_filter": "Technical_Lead__r.UserRole.Name = 'SE - LATAM - ROL'", "email_owner_filter": "Owner.UserRole.Name = 'SE - LATAM - ROL'"},
        ],
    },
    "dorg": {
        "label":            "DORG",
        "description":      ".ORG SE team",
        "motion":           "ae",
        "team_total_filter": "Owner.UserRole.Name LIKE 'DORG%' OR Owner.UserRole.Name LIKE '%.org%'",
        "soql_filter":      "Technical_Lead__r.UserRole.Name = 'SE - DORG'",
        "email_owner_filter": "Owner.UserRole.Name = 'SE - DORG'",
        "criteria": [
            {
                "label":  "SE Tagged",
                "detail": "Technical Lead UserRole = 'SE - DORG'",
            },
        ],
    },
}

_DEFAULT_TEAM = "digital_sales"

# ---------------------------------------------------------------------------
# Period config
# ---------------------------------------------------------------------------

_ICAV_FIELD = sf_analysis.FIELD_CONFIG["icav_field"]
_EARR_FIELD = sf_analysis.FIELD_CONFIG["earr_field"]
_TEAM_FIELD = sf_analysis.FIELD_CONFIG["team_field"]

_QUARTER_ENDS   = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
_QUARTER_STARTS = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}

# Current quarter cache: 10 min (data is live). Historical: 1 week (never changes).
_CACHE_TTL_CURRENT    = 600
_CACHE_TTL_HISTORICAL = 604_800


def _period_info(period_key: str) -> dict:
    """Parse a period key into start, end, label, and cache TTL."""
    today = date.today()
    if "_Q" in period_key:
        year_s, q_s = period_key.split("_Q")
        year, q = int(year_s), int(q_s)
        start = f"{year}-{_QUARTER_STARTS[q]}"
        end   = f"{year}-{_QUARTER_ENDS[q]}"
        label = f"Q{q} {year}"
        qtr_end = date(year, q * 3, int(_QUARTER_ENDS[q].split("-")[1]))
        ttl = _CACHE_TTL_HISTORICAL if qtr_end < today else _CACHE_TTL_CURRENT
    else:
        year = int(period_key.split("_")[0])
        start, end = f"{year}-01-01", f"{year}-12-31"
        label = f"Full Year {year}"
        ttl   = _CACHE_TTL_HISTORICAL
    return {"start": start, "end": end, "label": label, "ttl": ttl}


def _available_periods() -> list[dict]:
    """Build the list of selectable periods: current-year quarters + prior full years."""
    today   = date.today()
    year    = today.year
    cur_q   = (today.month - 1) // 3 + 1
    periods = []

    for q in range(cur_q, 0, -1):
        key   = f"{year}_Q{q}"
        label = f"Q{q} {year}"
        if q == cur_q:
            label += " (current)"
        periods.append({"key": key, "label": label})

    for y in range(year - 1, year - 4, -1):
        periods.append({"key": f"{y}_FY", "label": f"Full Year {y}"})

    return periods


def _default_period() -> str:
    """Most recently completed quarter, or Q1 if still in Q1."""
    today = date.today()
    year  = today.year
    cur_q = (today.month - 1) // 3 + 1
    if cur_q > 1:
        return f"{year}_Q{cur_q - 1}"
    return f"{year - 1}_Q4"


def _build_soql(team_filter: str, start: str, end: str, icav_min: int = 0) -> str:
    """All Closed Won opps. Presales_Stage__c included to tag TW vs non-TW."""
    icav_clause = f"AND {_ICAV_FIELD} >= {icav_min} " if icav_min > 0 else ""
    return (
        f"SELECT Id, Name, CloseDate, {_ICAV_FIELD}, {_EARR_FIELD}, {_TEAM_FIELD}, Presales_Stage__c, "
        f"Technical_Lead__r.Name, Technical_Lead__r.Email, Technical_Lead__r.Title, "
        f"Owner.Name, Owner.UserRole.Name, "
        f"Sales_Engineer_Notes__c, SE_Notes_History__c, "
        f"Account.Name, Account.Owner.Name, "
        f"Account.Current_ARR_Based_on_Last_6_Months__c, "
        f"Account.Average_Amortized_Usage_Last_3_Months__c, "
        # Monthly amortized usage snapshots — used to compute quarter-anchored MRR delta
        f"Account.Total_Amortized_Twilio_Usage_This_Month__c, "
        f"Account.Total_Amortized_Twilio_Usage_Last_Month__c, "
        f"Account.Total_Amortized_Twilio_Usage_2_Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_3_Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_4_Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_5_Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_6_Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_7_Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_8_Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_9_Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_10Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_11Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_12Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_13Month_Ago__c, "
        f"Account.Total_Amortized_Twilio_Usage_14Month_Ago__c, "
        f"Account.Fast_Revenue_Growth__c, "
        f"Account.Significant_Revenue_Contraction__c "
        f"FROM Opportunity "
        f"WHERE StageName = 'Closed Won' "
        f"AND {team_filter} "
        f"AND Technical_Lead__c != null "
        f"AND CloseDate >= {start} "
        f"AND CloseDate <= {end} "
        f"{icav_clause}"
    )


def _build_win_rate_soql(team_filter: str, start: str, end: str) -> str:
    """Lightweight: all Closed Won + Closed Lost per SE for win rate. No iACV threshold."""
    return (
        f"SELECT Technical_Lead__r.Name, StageName, Owner.UserRole.Name, Account.Owner.Name "
        f"FROM Opportunity "
        f"WHERE StageName IN ('Closed Won', 'Closed Lost') "
        f"AND {team_filter} "
        f"AND Technical_Lead__c != null "
        f"AND CloseDate >= {start} "
        f"AND CloseDate <= {end}"
    )


def _build_pipeline_soql(team_filter: str, end: str) -> str:
    """Open opps closing after the period — used to classify out-q email targets."""
    return (
        f"SELECT Id, Owner.UserRole.Name, {_ICAV_FIELD} "
        f"FROM Opportunity "
        f"WHERE StageName NOT IN ('Closed Won', 'Closed Lost') "
        f"AND {team_filter} "
        f"AND Technical_Lead__c != null "
        f"AND CloseDate > {end}"
    )


def _build_email_soql(start: str, end: str, se_owner_filter: str) -> str:
    """Task emails sent by SEs during the period, linked to Opps.
    Opp owner role drives activate/expansion classification directly — no motion map needed."""
    return (
        f"SELECT Id, WhatId, Owner.Name, ActivityDate, "
        f"TYPEOF What "
        f"  WHEN Opportunity THEN CloseDate, StageName, Owner.UserRole.Name, {_ICAV_FIELD} "
        f"END "
        f"FROM Task "
        f"WHERE TaskSubtype = 'Email' "
        f"AND What.Type = 'Opportunity' "
        f"AND ActivityDate >= {start} "
        f"AND ActivityDate <= {end} "
        f"AND {se_owner_filter}"
    )


def _build_meeting_soql(start: str, end: str, se_owner_filter: str) -> str:
    """Calendar events (meetings) logged by SEs during the period, linked to Opps.
    Same classification logic as emails — opp owner role drives activate/expansion.

    IsRecurrence = false excludes series master records — a recurring event creates
    one master (IsRecurrence=true) plus N child occurrences (IsRecurrence=false,
    RecurrenceActivityId=<master>). Without this filter the master would be
    double-counted alongside its own occurrences.
    RecurrenceActivityId is fetched so merge_meeting_activity can further
    deduplicate: the same recurring series on the same opp counts once."""
    return (
        f"SELECT Id, WhatId, Owner.Name, ActivityDate, RecurrenceActivityId, "
        f"TYPEOF What "
        f"  WHEN Opportunity THEN CloseDate, StageName, Owner.UserRole.Name, {_ICAV_FIELD} "
        f"END "
        f"FROM Event "
        f"WHERE What.Type = 'Opportunity' "
        f"AND IsRecurrence = false "
        f"AND ActivityDate >= {start} "
        f"AND ActivityDate <= {end} "
        f"AND {se_owner_filter}"
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(team_key: str, period_key: str, icav_min: int = 0) -> Path:
    suffix = f"_min{icav_min}" if icav_min > 0 else ""
    return OUTPUT_DIR / f"sf_se_data_{team_key}_{period_key}{suffix}.json"


_LOCAL_DEV = os.environ.get("LOCAL_DEV") == "1"

_SOQL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _safe_soql_date(value: str) -> str:
    if not _SOQL_DATE_RE.match(value):
        raise ValueError(f"Invalid SOQL date parameter: {value!r}")
    return value


def _build_team_total_soql(team_filter: str, start: str, end: str) -> str:
    s = _safe_soql_date(start)
    e = _safe_soql_date(end)
    return (
        f"SELECT SUM({_ICAV_FIELD}) total_icav "
        f"FROM Opportunity "
        f"WHERE StageName = 'Closed Won' "
        f"AND {team_filter} "
        f"AND CloseDate >= {s} "
        f"AND CloseDate <= {e}"
    )


def _get_team_total_icav(team_total_filter: str, start: str, end: str) -> int | None:
    if not sf.configured:
        return None
    try:
        rows = sf.query(_build_team_total_soql(team_total_filter, start, end), timeout=60)
        if rows:
            val = rows[0].get("total_icav") or rows[0].get("expr0")
            return int(float(val)) if val is not None else None
    except Exception:
        log.warning("team total iACV query failed for filter: %s", team_total_filter, exc_info=True)
    return None


def _motion_total_filter(team_total_filter: str, motion: str, which: str) -> str:
    base = f"({team_total_filter})"
    if motion == "dsr":
        clause = "Owner.UserRole.Name LIKE '%Activation%'" if which == "act" else "Owner.UserRole.Name LIKE '%Expansion%'"
    else:
        clause = "Owner.UserRole.Name LIKE '% NB%'" if which == "act" else "Owner.UserRole.Name LIKE '%Strat%'"
    return f"{base} AND {clause}"


def _is_fresh(team_key: str, period_key: str, icav_min: int, ttl: int) -> bool:
    if _LOCAL_DEV:
        return False
    p = _cache_path(team_key, period_key, icav_min)
    return p.exists() and (time.time() - p.stat().st_mtime) < ttl


def _load_cached(team_key: str, period_key: str, icav_min: int = 0) -> tuple[list | None, int | None, int | None, int | None]:
    p = _cache_path(team_key, period_key, icav_min)
    if not p.exists():
        return None, None, None, None
    raw = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        # Old cache format — delete and treat as a miss so it gets rebuilt with current schema
        p.unlink(missing_ok=True)
        return None, None, None, None
    return raw.get("ses"), raw.get("team_total_icav"), raw.get("act_total_icav"), raw.get("exp_total_icav")


def _save_cached(ranked: list, team_key: str, period_key: str, icav_min: int = 0, motion: str = "dsr",
                  team_total_icav: int | None = None, act_total_icav: int | None = None, exp_total_icav: int | None = None) -> list:
    total   = len(ranked)
    payload = []
    for i, se in enumerate(ranked, 1):
        entry          = {k: v for k, v in se.items() if not k.startswith("_")}
        entry["rank"]  = i
        entry["tier"]  = sf_analysis.tier(i, total)
        entry["flags"] = sf_analysis.collect_se_flags(se, ranked, motion)
        entry["roast"] = sf_analysis._roast(se, ranked, motion)
        payload.append(entry)
    if not _LOCAL_DEV:
        result = {"ses": payload}
        if team_total_icav is not None:
            result["team_total_icav"] = team_total_icav
        if act_total_icav is not None:
            result["act_total_icav"] = act_total_icav
        if exp_total_icav is not None:
            result["exp_total_icav"] = exp_total_icav
        p   = _cache_path(team_key, period_key, icav_min)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(result), encoding="utf-8")
        tmp.replace(p)
    return payload



def _get_data(team_key: str, period_key: str, icav_min: int = 0, subteam_key: str = "") -> tuple[list | None, str | None, int | None, int | None, int | None]:
    """Return (ranked_ses, error_msg, team_total_icav, act_total_icav, exp_total_icav)."""
    team = TEAMS.get(team_key)
    if not team:
        return None, f"Unknown team '{team_key}'", None, None, None

    soql_filter        = team["soql_filter"]
    email_owner_filter = team["email_owner_filter"]
    display_label      = team["label"]

    if subteam_key:
        subteam = next((s for s in team.get("subteams", []) if s["key"] == subteam_key), None)
        if not subteam:
            return None, f"Unknown subteam '{subteam_key}' for team '{team_key}'", None, None, None
        soql_filter        = subteam["soql_filter"]
        email_owner_filter = subteam["email_owner_filter"]
        display_label      = f"{team['label']} · {subteam['label']}"

    cache_key = f"{team_key}_{subteam_key}" if subteam_key else team_key
    info      = _period_info(period_key)

    period_year = int(period_key.split("_")[0])
    if not subteam_key and period_year < date.today().year and "historical_soql_filter" in team:
        soql_filter = team["historical_soql_filter"]

    if _is_fresh(cache_key, period_key, icav_min, info["ttl"]):
        ses, tti, ati, eti = _load_cached(cache_key, period_key, icav_min)
        return ses, None, tti, ati, eti

    if not sf.configured:
        stale, tti, ati, eti = _load_cached(cache_key, period_key, icav_min)
        if stale:
            log.warning("Salesforce not configured — serving stale cache for %s/%s", cache_key, period_key)
            return stale, None, tti, ati, eti
        return None, "Salesforce is not configured.", None, None, None

    core_exc: Exception | None = None
    opps = win_rate_opps = pipe_opps = email_tasks = meeting_events = None
    team_total_icav: int | None = None
    act_total_icav:  int | None = None
    exp_total_icav:  int | None = None
    team_total_filter = team.get("team_total_filter")
    motion            = team.get("motion", "dsr")

    with ThreadPoolExecutor(max_workers=8) as pool:
        f_opps     = pool.submit(sf.query, _build_soql(soql_filter, info["start"], info["end"], icav_min))
        f_win_rate = pool.submit(sf.query, _build_win_rate_soql(soql_filter, info["start"], info["end"]))
        f_pipeline = pool.submit(sf.query, _build_pipeline_soql(soql_filter, info["end"]))
        f_email    = pool.submit(sf.query, _build_email_soql(info["start"], info["end"], email_owner_filter))
        f_meetings = pool.submit(sf.query, _build_meeting_soql(info["start"], info["end"], email_owner_filter))
        if team_total_filter and not subteam_key:
            f_team_total = pool.submit(_get_team_total_icav, team_total_filter, info["start"], info["end"])
            f_act_total  = pool.submit(_get_team_total_icav, _motion_total_filter(team_total_filter, motion, "act"), info["start"], info["end"])
            f_exp_total  = pool.submit(_get_team_total_icav, _motion_total_filter(team_total_filter, motion, "exp"), info["start"], info["end"])
        else:
            f_team_total = f_act_total = f_exp_total = None

        try:
            opps          = f_opps.result()
            win_rate_opps = f_win_rate.result()
        except Exception as e:
            core_exc = e
            log.exception("Salesforce query failed for team %s / %s", cache_key, period_key)

        try:
            pipe_opps = f_pipeline.result()
        except Exception:
            log.warning("Pipeline query for email motion failed — classifying closed-won opps only")
            pipe_opps = []

        try:
            email_tasks = f_email.result()
        except Exception:
            log.warning("Email activity query failed for %s/%s — skipping", cache_key, period_key, exc_info=True)

        try:
            meeting_events = f_meetings.result()
        except Exception:
            log.warning("Meeting activity query failed for %s/%s — skipping", cache_key, period_key, exc_info=True)

        if f_team_total is not None:
            try:
                team_total_icav = f_team_total.result()
            except Exception:
                log.warning("Team total iACV query failed for %s/%s — skipping", cache_key, period_key, exc_info=True)
        if f_act_total is not None:
            try:
                act_total_icav = f_act_total.result()
            except Exception:
                log.warning("Act total iACV query failed for %s/%s — skipping", cache_key, period_key, exc_info=True)
        if f_exp_total is not None:
            try:
                exp_total_icav = f_exp_total.result()
            except Exception:
                log.warning("Exp total iACV query failed for %s/%s — skipping", cache_key, period_key, exc_info=True)

    if core_exc is not None:
        stale, tti, ati, eti = _load_cached(cache_key, period_key, icav_min)
        if stale:
            log.warning("Salesforce error — serving stale cache for %s/%s", cache_key, period_key)
            return stale, None, tti, ati, eti
        return None, f"Salesforce query failed: {core_exc}", None, None, None

    if not opps:
        return [], None, team_total_icav, act_total_icav, exp_total_icav

    ses = sf_analysis.build_ses(opps, motion, notes_floor=icav_min, period_key=period_key)
    sf_analysis.merge_win_rate(ses, win_rate_opps, motion)

    opp_motion_map: dict[str, str] = {}
    for opp in opps:
        oid = opp.get("Id") or ""
        if oid:
            if sf_analysis._is_activate(opp):
                opp_motion_map[oid] = "activate"
            elif sf_analysis._is_expansion(opp):
                opp_motion_map[oid] = "expansion"
    for opp in (pipe_opps or []):
        oid = opp.get("Id") or ""
        if oid and oid not in opp_motion_map:
            if sf_analysis._is_activate(opp):
                opp_motion_map[oid] = "activate"
            elif sf_analysis._is_expansion(opp):
                opp_motion_map[oid] = "expansion"

    if email_tasks is not None:
        try:
            sf_analysis.merge_email_activity(ses, email_tasks, info["end"], opp_motion_map)
            log.info("Email activity: %d tasks, %d opp motion entries for %s/%s",
                     len(email_tasks), len(opp_motion_map), cache_key, period_key)
        except Exception:
            log.warning("Email activity merge failed for %s/%s — skipping", cache_key, period_key, exc_info=True)

    if meeting_events is not None:
        try:
            sf_analysis.merge_meeting_activity(ses, meeting_events, info["end"], opp_motion_map)
            log.info("Meeting activity: %d events for %s/%s",
                     len(meeting_events), cache_key, period_key)
        except Exception:
            log.warning("Meeting activity merge failed for %s/%s — skipping", cache_key, period_key, exc_info=True)

    ses = [s for s in ses if s["act_wins"] + s["exp_wins"] > 0]
    if not ses:
        return [], None, team_total_icav, act_total_icav, exp_total_icav
    ranked = sf_analysis.rank_ses(ses)
    result = _save_cached(ranked, cache_key, period_key, icav_min, motion, team_total_icav, act_total_icav, exp_total_icav)
    log.info("Refreshed %s/%s (min $%s) SE data from Salesforce (%d opps, %d win-rate opps)",
             cache_key, period_key, icav_min, len(opps), len(win_rate_opps))
    return result, None, team_total_icav, act_total_icav, exp_total_icav


# ---------------------------------------------------------------------------
# Email → SE name matcher
# ---------------------------------------------------------------------------

def _email_to_se_name(email: str, ses: list) -> str | None:
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
        for se in ses:
            fn, _ = names(se)
            if fn == local:
                return se["name"]

    return None


# ---------------------------------------------------------------------------
# Platform hook
# ---------------------------------------------------------------------------

def enrich_me(email: str) -> dict:
    """Called by /api/me — attach SF profile from session + SE identity from cache."""
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

    # Check cached team data to identify if this user is an SE (for My Stats page)
    for team_key in TEAMS:
        for p in OUTPUT_DIR.glob(f"sf_se_data_{team_key}_*.json"):
            try:
                raw    = json.loads(p.read_text(encoding="utf-8"))
                cached = raw.get("ses", raw) if isinstance(raw, dict) else raw
            except Exception:
                continue
            se_name = _email_to_se_name(email, cached)
            if se_name:
                out.update({"sf_is_se": True, "sf_se_name": se_name, "sf_team": team_key})
                return out

    out.update({
        "sf_is_se":  False,
        "sf_se_name": None,
        "sf_team":    session.get("sf_team"),
    })
    return out


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
    return jsonify(_available_periods())



@se_scorecard_v2_bp.route("/api/se-scorecard-v2/data/ses")
def api_ses():
    team_key    = request.args.get("team", _DEFAULT_TEAM)
    period_key  = request.args.get("period", _default_period())
    icav_min, err = _parse_icav_min(request.args.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key = request.args.get("subteam", "")
    ses, err, *_ = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": err}), 503
    team_medians = sf_analysis.compute_team_medians(ses)
    se_name      = _email_to_se_name(session.get("user_email", ""), ses)
    if se_name:
        ses = [s for s in ses if s["name"] == se_name]
    team_motion = TEAMS[team_key].get("motion", "dsr") if team_key in TEAMS else "dsr"
    return jsonify({"ses": [{**s, "team_motion": team_motion, "team_medians": team_medians} for s in ses], "sf_instance_url": sf.instance_url})


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/data/report")
def api_report():
    team_key    = request.args.get("team", _DEFAULT_TEAM)
    period_key  = request.args.get("period", _default_period())
    icav_min, err = _parse_icav_min(request.args.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key                                          = request.args.get("subteam", "")
    ses_list, err, team_total_icav, act_total_icav, exp_total_icav = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": err}), 503
    if _email_to_se_name(session.get("user_email", ""), ses_list):
        return jsonify({"error": "Access denied"}), 403

    team        = TEAMS[team_key]
    subteam     = next((s for s in team.get("subteams", []) if s["key"] == subteam_key), None) if subteam_key else None
    team_label  = f"{team['label']} · {subteam['label']}" if subteam else team["label"]

    period      = _period_info(period_key)
    total         = len(ses_list)
    unique_owners = {o["owner"] for s in ses_list for o in s.get("tw_opps_detail", []) if o.get("owner")}
    ae_dsr_count  = len(unique_owners)
    ae_to_se_ratio = round(ae_dsr_count / total, 1) if total > 0 else 0
    act_sorted  = sorted(ses_list, key=lambda x: x["act_icav"], reverse=True)
    exp_sorted  = sorted(ses_list, key=lambda x: x["exp_icav"], reverse=True)
    deal_sorted = [s for s in sorted(ses_list, key=lambda x: x["largest_deal_value"], reverse=True)
                   if s["largest_deal_value"] > 0]

    cache_key_trend = f"{team_key}_{subteam_key}" if subteam_key else team_key
    is_fy           = "_FY" in period_key
    comparable      = [p for p in _available_periods()
                       if (("_FY" in p["key"]) == is_fy) and p["key"] != period_key]

    def _exp_snapshot(ses: list, p_label: str, p_key: str, is_current: bool) -> dict:
        return {
            "period":          p_label,
            "period_key":      p_key,
            "is_current":      is_current,
            "team_exp_icav":   sum(s.get("exp_icav", 0) for s in ses),
            "team_exp_wins":   sum(s.get("exp_wins", 0) for s in ses),
            "team_influenced": sum(s.get("exp_icav", 0) + s.get("non_tw_exp_icav", 0) for s in ses),
            "ses":             {s["name"]: {
                "exp_icav":    s.get("exp_icav", 0),
                "influenced":  s.get("exp_icav", 0) + s.get("non_tw_exp_icav", 0),
            } for s in ses},
        }

    exp_trend = [_exp_snapshot(ses_list, period["label"], period_key, True)]
    for p in comparable[:3]:
        prior, *_ = _load_cached(cache_key_trend, p["key"], 0)
        if prior:
            exp_trend.append(_exp_snapshot(prior, p["label"], p["key"], False))

    exp_trend.reverse()

    se_icav         = sum(s["total_icav"] for s in ses_list)
    se_act_icav     = sum(s["act_icav"]   for s in ses_list)
    se_exp_icav     = sum(s["exp_icav"]   for s in ses_list)
    se_icav_pct     = round(se_icav     / team_total_icav * 100) if team_total_icav and team_total_icav > 0 else None
    se_act_icav_pct = round(se_act_icav / act_total_icav  * 100) if act_total_icav  and act_total_icav  > 0 else None
    se_exp_icav_pct = round(se_exp_icav / exp_total_icav  * 100) if exp_total_icav  and exp_total_icav  > 0 else None

    return jsonify({
        "ranked":           ses_list,
        "total":            total,
        "icav_min":         icav_min,
        "team_icav":        se_icav,
        "team_earr":        sum(s.get("total_earr", 0) for s in ses_list),
        "team_wins":        sum(s["act_wins"] + s["exp_wins"] for s in ses_list),
        "team_arr":         sum(s.get("exp_arr_total", 0) for s in ses_list),
        "team_total_icav":  team_total_icav,
        "act_total_icav":   act_total_icav,
        "exp_total_icav":   exp_total_icav,
        "se_icav_pct":      se_icav_pct,
        "se_act_icav_pct":  se_act_icav_pct,
        "se_exp_icav_pct":  se_exp_icav_pct,
        "act_sorted":       act_sorted,
        "exp_sorted":       exp_sorted,
        "pipe_sorted":      [],
        "deal_sorted":      deal_sorted,
        "max_act":          act_sorted[0]["act_icav"] if act_sorted else 1,
        "max_exp":          max((s["exp_icav"] for s in exp_sorted), default=1) or 1,
        "max_fut":          1,
        "max_act_icav":     max(s["act_icav"] for s in ses_list) or 1,
        "max_exp_icav":     max(s["exp_icav"] for s in ses_list) or 1,
        "trends":           sorted(sf_analysis.collect_team_trends(ses_list, team.get("motion", "dsr")), key=lambda x: x[0]),
        "recommendations":  sf_analysis.generate_recommendations(ses_list, team.get("motion", "dsr")),
        "ae_engagement":    sf_analysis.compute_ae_engagement(ses_list),
        "exp_trend":        exp_trend,
        "quarter":          period["label"],
        "team_label":       team_label,
        "motion":           team.get("motion", "dsr"),
        "sf_instance_url":  sf.instance_url,
        "ae_dsr_count":     ae_dsr_count,
        "ae_to_se_ratio":   ae_to_se_ratio,
    })


# ---------------------------------------------------------------------------
# Suggestion box — backed by Google Firestore (twilio-ckbrox project)
# FIRESTORE_PROJECT and FIRESTORE_CREDENTIALS (service account JSON, single
# line) are injected via secrets.env at deploy time and backend/apps/
# se_scorecard_v2/.env for local dev.
# ---------------------------------------------------------------------------

_SUGGESTIONS_MAX        = 500
_FIRESTORE_PROJECT      = os.environ.get("FIRESTORE_PROJECT")
_FIRESTORE_CREDENTIALS  = os.environ.get("FIRESTORE_CREDENTIALS_B64")  # base64-encoded JSON
_FIRESTORE_COLLECTION   = "se-scorecard-v2-suggestions"
_firestore_client       = None

_TWILIO_ACCOUNT_SID     = os.environ.get("TWILIO_ACCOUNT_SID")
_TWILIO_AUTH_TOKEN      = os.environ.get("TWILIO_AUTH_TOKEN")
_TWILIO_PHONE_NUMBER    = "+18446990268"

# SMS pump protection: max texts per phone number per window
_SMS_RL_LIMIT  = 100  # max messages
_SMS_RL_WINDOW = 3600 # per hour (seconds)
_sms_rl_store: dict[str, list[float]] = {}

# Pending confirmations: phone -> (text, caller_name, expires_at)
_SMS_CONFIRM_TTL = 300  # 5 minutes to confirm
_sms_pending: dict[str, tuple[str, str | None, float]] = {}

def _sms_rate_limited(phone: str) -> bool:
    """Returns True if this phone number has exceeded the SMS rate limit."""
    now = time.monotonic()
    cutoff = now - _SMS_RL_WINDOW
    ts = _sms_rl_store.setdefault(phone, [])
    while ts and ts[0] < cutoff:
        ts.pop(0)
    if len(ts) >= _SMS_RL_LIMIT:
        return True
    ts.append(now)
    return False


def _get_firestore():
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    try:
        from google.cloud import firestore
        from google.oauth2 import service_account
        if _FIRESTORE_CREDENTIALS:
            import base64
            info = json.loads(base64.b64decode(_FIRESTORE_CREDENTIALS).decode())
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/datastore"],
            )
            _firestore_client = firestore.Client(project=_FIRESTORE_PROJECT, credentials=creds)
        else:
            # Local dev fallback: use gcloud application default credentials
            _firestore_client = firestore.Client(project=_FIRESTORE_PROJECT)
        return _firestore_client
    except Exception as e:
        log.error("Firestore init failed: %s", e)
        return None


def _masked(email: str) -> str:
    return email.split("@")[0] if email else "anonymous"


def _lookup_phone(phone: str) -> dict:
    """Use Twilio Lookup v2 to get caller name and line type for a phone number.
    Returns dict with keys: caller_name (str|None), is_mobile (bool).
    """
    result = {"caller_name": None, "is_mobile": True}  # default allow if lookup unavailable
    if not (_TWILIO_ACCOUNT_SID and _TWILIO_AUTH_TOKEN):
        return result
    try:
        resp = http_requests.get(
            f"https://lookups.twilio.com/v2/PhoneNumbers/{phone}",
            params={"Fields": "caller_name,line_type_intelligence"},
            auth=(_TWILIO_ACCOUNT_SID, _TWILIO_AUTH_TOKEN),
            timeout=5,
        )
        if resp.ok:
            data = resp.json()
            name = (data.get("caller_name") or {}).get("caller_name")
            if name and name.strip():
                result["caller_name"] = name.strip().title()
            line_type = (data.get("line_type_intelligence") or {}).get("type", "")
            # Reject landlines and VoIP — only allow mobile/prepaid
            if line_type and line_type not in ("mobile", "prepaid", ""):
                result["is_mobile"] = False
                log.info("Lookup: %s is line_type=%s — rejecting", phone, line_type)
    except Exception as e:
        log.warning("Twilio Lookup failed for %s: %s", phone, e)
    return result


def _display_author(doc: dict) -> str:
    """Return display name: email prefix, Lookup name, or formatted phone."""
    source = doc.get("source", "web")
    if source == "sms":
        phone = doc.get("phone", "")
        name = doc.get("caller_name")
        if name:
            return name
        # Format +18005551234 → (800) 555-1234
        if phone.startswith("+1") and len(phone) == 12:
            return f"({phone[2:5]}) {phone[5:8]}-{phone[8:]}"
        return phone or "SMS"
    return _masked(doc.get("email", ""))


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/suggestions", methods=["GET"])
def api_suggestions_list():
    current_email = session.get("user_email", "")
    db = _get_firestore()
    if db is None:
        return jsonify({"error": "Storage unavailable"}), 503
    try:
        docs = db.collection(_FIRESTORE_COLLECTION).order_by("created_at", direction="DESCENDING").stream()
        items = []
        for doc in docs:
            s = doc.to_dict()
            items.append({
                "id":         doc.id,
                "text":       s.get("text", ""),
                "author":     _display_author(s),
                "source":     s.get("source", "web"),
                "created_at": s.get("created_at", ""),
                "is_mine":    s.get("email", "") == current_email,
            })
        return jsonify(items)
    except Exception as e:
        log.error("Firestore list failed: %s", e)
        return jsonify({"error": "Failed to load suggestions"}), 503


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/suggestions", methods=["POST"])
def api_suggestions_create():
    email = session.get("user_email", "")
    if not email:
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(text) > 1000:
        return jsonify({"error": "text too long (max 1000 chars)"}), 400
    db = _get_firestore()
    if db is None:
        return jsonify({"error": "Storage unavailable"}), 503
    try:
        count = len(db.collection(_FIRESTORE_COLLECTION).limit(_SUGGESTIONS_MAX + 1).get())
        if count >= _SUGGESTIONS_MAX:
            return jsonify({"error": "Suggestion limit reached"}), 429
        doc_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.collection(_FIRESTORE_COLLECTION).document(doc_id).set({
            "email":      email,
            "text":       text,
            "source":     "web",
            "created_at": created_at,
        })
        return jsonify({
            "id":         doc_id,
            "text":       text,
            "author":     _masked(email),
            "source":     "web",
            "created_at": created_at,
            "is_mine":    True,
        }), 201
    except Exception as e:
        log.error("Firestore create failed: %s", e)
        return jsonify({"error": "Failed to save suggestion"}), 503


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/suggestions/<suggestion_id>", methods=["DELETE"])
def api_suggestions_delete(suggestion_id: str):
    email = session.get("user_email", "")
    if not email:
        return jsonify({"error": "Unauthorized"}), 401
    db = _get_firestore()
    if db is None:
        return jsonify({"error": "Storage unavailable"}), 503
    try:
        ref = db.collection(_FIRESTORE_COLLECTION).document(suggestion_id)
        doc = ref.get()
        if not doc.exists:
            return jsonify({"error": "Not found"}), 404
        if doc.to_dict().get("email") != email:
            return jsonify({"error": "Forbidden"}), 403
        ref.delete()
        return "", 204
    except Exception as e:
        log.error("Firestore delete failed: %s", e)
        return jsonify({"error": "Failed to delete suggestion"}), 503


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/sms", methods=["POST"])
def api_sms_webhook():
    """Twilio SMS webhook — command interface for suggestions.

    Commands (case-insensitive):
      LIST                  — receive all suggestions with authors
      DELETE <number>       — delete one of your own suggestions by list index
      DELETE ALL            — delete all of your suggestions
      <anything else>       — saved as a new suggestion

    Security:
      1. HMAC-SHA1 signature validation (Twilio webhook security docs)
      2. Mobile-only via Lookup line_type_intelligence (blocks landlines/VoIP)
      3. Per-phone rate limiting (5 msgs/hour, SMS pump protection)
    """
    # ── 1. Signature validation ───────────────────────────────────────────────
    _local_dev = os.environ.get("LOCAL_DEV") == "1"
    if _TWILIO_AUTH_TOKEN and not _local_dev:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(_TWILIO_AUTH_TOKEN)
        # Use FRONTEND_URL (CloudFront domain) — the canonical URL Twilio signed.
        # request.url is the internal EC2 hostname which never matches.
        _frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
        url = f"{_frontend}/api/se-scorecard-v2/sms"
        sig = request.headers.get("X-Twilio-Signature", "")
        log.info("Twilio sig check — url=%s sig=%s", url, sig[:16] if sig else "missing")
        if not validator.validate(url, request.form, sig):
            log.warning("Twilio signature validation failed — url=%s", url)
            return "Forbidden", 403

    from_number = request.form.get("From", "").strip()
    body        = request.form.get("Body", "").strip()

    if not from_number or not body:
        return _twiml_reply("No message body received.")

    # ── 2. Per-phone rate limiting (SMS pump protection) ─────────────────────
    if _sms_rate_limited(from_number):
        log.warning("SMS rate limit exceeded for %s", from_number)
        return _twiml_reply("You've sent too many messages. Please wait an hour before trying again.")

    # ── 3. Lookup: verify mobile number + get caller name ────────────────────
    lookup = _lookup_phone(from_number) if not _local_dev else {"caller_name": None, "is_mobile": True}
    if not lookup["is_mobile"]:
        log.info("SMS from non-mobile %s — ignoring silently", from_number)
        return _twiml_empty()

    db = _get_firestore()
    if db is None:
        log.error("Firestore unavailable for SMS from %s", from_number)
        return _twiml_reply("Sorry, storage is unavailable right now. Please try again later.")

    cmd = body.strip().upper()

    def _load_all_docs_inner(db_):
        return list(db_.collection(_FIRESTORE_COLLECTION)
                       .order_by("created_at", direction="DESCENDING").stream())

    def _format_list_inner(docs, phone):
        if not docs:
            return "No suggestions yet."
        lines = []
        for i, doc in enumerate(docs, 1):
            s      = doc.to_dict()
            author = _display_author(s)
            text   = s.get("text", "")[:60]
            suffix = "..." if len(s.get("text", "")) > 60 else ""
            mine   = " *" if s.get("phone") == phone else ""
            lines.append(f"{i}. [{author}]{mine} {text}{suffix}")
        return "\n".join(lines)

    # ── CONFIRMATION FLOW ─────────────────────────────────────────────────────
    if from_number in _sms_pending:
        pending_text, pending_name, expires_at = _sms_pending[from_number]
        if time.time() > expires_at:
            del _sms_pending[from_number]
        elif cmd in ("Y", "YES"):
            del _sms_pending[from_number]
            try:
                all_docs = _load_all_docs_inner(db)
                if len(all_docs) >= _SUGGESTIONS_MAX:
                    return _twiml_reply("Sorry, we've reached our suggestion limit. Thank you for your interest!")
                doc_id     = str(uuid.uuid4())
                created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                doc = {"phone": from_number, "text": pending_text, "source": "sms", "created_at": created_at}
                if pending_name:
                    doc["caller_name"] = pending_name
                db.collection(_FIRESTORE_COLLECTION).document(doc_id).set(doc)
                log.info("SMS suggestion confirmed and saved from %s", from_number)
                updated = _load_all_docs_inner(db)
                reply = "Saved! Here are all suggestions (* = yours). Reply DELETE 1,2 to remove yours:\n\n" + _format_list_inner(updated, from_number)
                return _twiml_reply(reply)
            except Exception as e:
                log.error("Firestore SMS save failed: %s", e)
                return _twiml_reply("Sorry, something went wrong. Please try again.")
        elif cmd in ("N", "NO"):
            del _sms_pending[from_number]
            return _twiml_reply("Cancelled — suggestion not saved.")
        else:
            # Unrecognised — re-prompt
            preview = pending_text[:80] + ("..." if len(pending_text) > 80 else "")
            return _twiml_reply(f'Reply Y to confirm or N to cancel:\n"{preview}"')

    def _load_all_docs():
        return _load_all_docs_inner(db)

    def _format_list(docs):
        return _format_list_inner(docs, from_number)

    # ── DELETE ────────────────────────────────────────────────────────────────
    if cmd.startswith("DELETE"):
        arg = body.strip()[6:].strip()
        try:
            docs = _load_all_docs()

            if arg.upper() == "ALL":
                mine = [d for d in docs if d.to_dict().get("phone") == from_number]
                if not mine:
                    return _twiml_reply("You have no suggestions to delete.")
                for d in mine:
                    db.collection(_FIRESTORE_COLLECTION).document(d.id).delete()
                log.info("SMS DELETE ALL: removed %d for %s", len(mine), from_number)
                # Reload and return updated list
                updated = _load_all_docs()
                reply = f"Deleted all {len(mine)} of your suggestion{'s' if len(mine) != 1 else ''}.\n\n" + _format_list(updated)
                return _twiml_reply(reply)

            # DELETE 1,2,3 — comma-separated indices into the full list
            try:
                indices = [int(x.strip()) - 1 for x in arg.split(",") if x.strip()]
                if not indices:
                    raise ValueError
            except ValueError:
                return _twiml_reply("Usage: DELETE 1  or  DELETE 1,2,3  or  DELETE ALL")

            errors, deleted = [], []
            for idx in sorted(set(indices)):
                if idx < 0 or idx >= len(docs):
                    errors.append(f"#{idx+1} doesn't exist")
                    continue
                d = docs[idx]
                if d.to_dict().get("phone") != from_number:
                    errors.append(f"#{idx+1} isn't yours")
                    continue
                db.collection(_FIRESTORE_COLLECTION).document(d.id).delete()
                deleted.append(idx + 1)

            log.info("SMS DELETE %s by %s — deleted=%s errors=%s", arg, from_number, deleted, errors)
            parts = []
            if deleted:
                parts.append(f"Deleted #{', #'.join(str(n) for n in deleted)}.")
            if errors:
                parts.append("Skipped: " + "; ".join(errors) + ".")
            updated = _load_all_docs()
            reply = " ".join(parts) + "\n\n" + _format_list(updated)
            return _twiml_reply(reply)

        except Exception as e:
            log.error("Firestore delete (SMS) failed: %s", e)
            return _twiml_reply("Failed to delete suggestion.")

    # ── SUBMIT (default) — ask for confirmation before saving ────────────────
    if len(body) > 1000:
        return _twiml_reply("Your message is too long (max 1000 characters). Please shorten it and try again.")

    preview = body[:80] + ("..." if len(body) > 80 else "")
    _sms_pending[from_number] = (body, lookup["caller_name"], time.time() + _SMS_CONFIRM_TTL)
    return _twiml_reply(f'Confirm your suggestion? Reply Y to save or N to cancel:\n"{preview}"')


def _twiml_reply(message: str):
    """Return a TwiML response with XML-escaped message body."""
    import xml.sax.saxutils as saxutils
    from flask import Response
    safe = saxutils.escape(message)
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'
    return Response(twiml, mimetype="text/xml")

def _twiml_empty():
    """Return an empty TwiML response — no reply sent."""
    from flask import Response
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', mimetype="text/xml")


# ---------------------------------------------------------------------------
# AI Chatbot — answers questions about the loaded Salesforce data
# ---------------------------------------------------------------------------

_OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
_OPENAI_MODEL     = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

_SOQL_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

# Fields the AI may reference in SOQL (prevent hallucinated field names causing 400s)
_SF_SCHEMA_HINT = """
Salesforce Opportunity fields available:
  Id, Name, CloseDate, StageName, Amount, Type
  Comms_Segment_Combined_iACV__c  (iACV — primary revenue metric)
  eARR_post_launch_No_Decimal__c  (eARR)
  FY_16_Owner_Team__c             (team stamp)
  Presales_Stage__c               (TW status; '4 - Technical Win Achieved' = TW)
  Technical_Lead__r.Name, Technical_Lead__r.Email, Technical_Lead__r.UserRole.Name
  Owner.Name, Owner.UserRole.Name
  Account.Name, Account.Owner.Name
  SE_Notes__c, SE_Notes_History__c, Sales_Engineer_Notes__c
  RecordType.Name
Standard date literal: TODAY, THIS_QUARTER, LAST_QUARTER, THIS_YEAR, LAST_N_DAYS:n
Always filter StageName = 'Closed Won' unless asking about pipeline/open deals.
Limit results to 50 rows unless the question needs more.
"""

_SOQL_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "run_soql",
            "description": (
                "Execute a SOQL SELECT query against the Twilio Salesforce org. "
                "Use this when the pre-loaded scorecard data doesn't contain enough detail "
                "to answer the question — e.g. specific account names, deal notes, pipeline "
                "queries, or cross-team comparisons."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "soql": {
                        "type": "string",
                        "description": "A valid SOQL SELECT statement. Only SELECT is allowed.",
                    }
                },
                "required": ["soql"],
            },
        },
    }
]


def _build_chat_context(ses: list, team_key: str, period_key: str) -> str:
    team  = TEAMS.get(team_key, {})
    info  = _period_info(period_key)
    lines = [
        f"SE Scorecard data — team: {team.get('label', team_key)}, period: {info['label']}",
        f"Total SEs: {len(ses)}",
        "",
    ]
    for se in ses:
        lines.append(f"SE: {se['name']} | title: {se.get('title','')} | email: {se.get('email','')}")
        lines.append(f"  Rank: {se.get('rank','?')} | Tier: {se.get('tier','?')} | Total iACV: ${se.get('total_icav',0):,}")
        lines.append(f"  Activate wins: {se.get('act_wins',0)} iACV ${se.get('act_icav',0):,} | Expansion wins: {se.get('exp_wins',0)} iACV ${se.get('exp_icav',0):,}")
        lines.append(f"  Win rate: {se.get('win_rate',0)}% ({se.get('closed_won',0)}W/{se.get('closed_lost',0)}L)")
        lines.append(f"  Largest deal: {se.get('largest_deal','')} (${se.get('largest_deal_value',0):,}) acct: {se.get('largest_deal_acct','')}")
        for opp in (se.get("tw_opps_detail") or [])[:10]:
            notes_flag = "[has_notes]" if opp.get("has_notes") else "[no_notes]"
            history_flag = "[has_history]" if opp.get("has_history") else "[no_history]"
            lines.append(f"    deal: {opp.get('name','')} | product: {opp.get('product','')} | iACV: ${opp.get('icav',0):,} | close: {opp.get('close_date','')} | motion: {opp.get('motion','')} | {notes_flag} {history_flag} | note_entries: {opp.get('note_entries',0)} | notes_len: {opp.get('notes_len',0)}")
        for acct in (se.get("exp_account_detail") or [])[:5]:
            lines.append(f"    exp_acct: {acct.get('acct_name','')} | ARR: ${acct.get('arr',0):,} | MRR delta: ${acct.get('mrr_delta',0):,}/mo | MRR%: {acct.get('mrr_pct',0)}%")
        roast = se.get("roast", "")
        if roast:
            lines.append(f"  Summary: {roast}")
        lines.append("")
    return "\n".join(lines)


def _execute_soql_tool(soql: str) -> str:
    """Run a SOQL query and return results as compact text. Only SELECT allowed."""
    if not _SOQL_SELECT_RE.match(soql):
        return "Error: only SELECT queries are permitted."
    if not sf.configured:
        return "Error: Salesforce is not configured."
    try:
        rows = sf.query(soql, timeout=30)
    except Exception as e:
        return f"Query error: {e}"
    if not rows:
        return "No records returned."
    # Serialize rows as compact lines, stripping the 'attributes' key SF adds
    lines = []
    for row in rows[:100]:
        fields = {k: v for k, v in row.items() if k != "attributes"}
        lines.append(str(fields))
    return "\n".join(lines)


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/chat", methods=["POST"])
def api_chat():
    """AI chatbot with Salesforce tool access."""
    if not _OPENAI_API_KEY:
        return jsonify({"error": "AI chatbot is not configured (missing OPENAI_API_KEY)."}), 503

    body        = request.get_json(silent=True) or {}
    message     = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > 2000:
        return jsonify({"error": "message too long (max 2000 chars)"}), 400

    team_key    = body.get("team", _DEFAULT_TEAM)
    period_key  = body.get("period", _default_period())
    icav_min, err = _parse_icav_min(body.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key = body.get("subteam", "")
    if subteam_key == "none":
        subteam_key = ""

    ses, err, *_ = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": f"Could not load data: {err}"}), 503
    if not ses:
        return jsonify({"answer": "No SE data is available for the selected team and period."}), 200

    context = _build_chat_context(ses, team_key, period_key)
    team_info = TEAMS.get(team_key, {})
    period_info = _period_info(period_key)

    system_prompt = (
        "You are an AI assistant embedded in the Twilio SE Scorecard dashboard. "
        "You have access to pre-loaded Salesforce opportunity data for a team of Solutions Engineers, "
        f"and a run_soql tool to query Salesforce directly when you need more detail.\n\n"
        f"Current context: team={team_info.get('label', team_key)}, period={period_info['label']} "
        f"(CloseDate {period_info['start']} to {period_info['end']}), "
        f"team SOQL filter: {team_info.get('soql_filter','')}\n\n"
        f"{_SF_SCHEMA_HINT}\n"
        "Answer questions clearly and concisely. Format numbers with $ and K/M suffixes. "
        "When using run_soql, apply the team's SOQL filter so results stay scoped to this team."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Pre-loaded scorecard data:\n\n{context}\n\nQuestion: {message}"},
    ]

    try:
        # Agentic loop: up to 3 tool calls before forcing a final answer
        for _ in range(3):
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {_OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": _OPENAI_MODEL,
                    "max_tokens": 1024,
                    "messages": messages,
                    "tools": _SOQL_TOOL,
                    "tool_choice": "auto",
                },
                timeout=60,
            )
            resp.raise_for_status()
            choice = resp.json()["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            if choice["finish_reason"] != "tool_calls":
                return jsonify({"answer": msg.get("content", "No response generated.")})

            # Execute each tool call and append results
            for tc in msg.get("tool_calls", []):
                if tc["function"]["name"] == "run_soql":
                    try:
                        args = json.loads(tc["function"]["arguments"])
                        result = _execute_soql_tool(args.get("soql", ""))
                    except Exception as e:
                        result = f"Tool error: {e}"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

        # Fallback: ask for a final answer without tools
        messages.append({"role": "user", "content": "Please summarise what you found."})
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {_OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": _OPENAI_MODEL, "max_tokens": 1024, "messages": messages},
            timeout=60,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"].get("content", "No response generated.")
        return jsonify({"answer": answer})

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        log.error("Chat API HTTP error %s: %s", status, e)
        if status == 429:
            body_text = e.response.text if e.response is not None else ""
            if "insufficient_quota" in body_text:
                return jsonify({"error": "OpenAI quota exceeded — please add credits at platform.openai.com."}), 503
            return jsonify({"error": "Rate limited by AI provider. Please wait a moment and try again."}), 503
        log.error("Response body: %s", e.response.text[:500] if e.response is not None else "")
        return jsonify({"error": f"AI request failed (HTTP {status}). Please try again."}), 503
    except Exception as e:
        log.error("Chat API error: %s", e, exc_info=True)
        return jsonify({"error": f"AI request failed: {type(e).__name__}. Please try again."}), 503


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/data/rankings")
def api_rankings():
    team_key    = request.args.get("team", _DEFAULT_TEAM)
    period_key  = request.args.get("period", _default_period())
    icav_min, err = _parse_icav_min(request.args.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key       = request.args.get("subteam", "")
    ses_list, err, *_ = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": err}), 503
    if _email_to_se_name(session.get("user_email", ""), ses_list):
        return jsonify({"error": "Access denied"}), 403

    team       = TEAMS[team_key]
    subteam    = next((s for s in team.get("subteams", []) if s["key"] == subteam_key), None) if subteam_key else None
    team_label = f"{team['label']} · {subteam['label']}" if subteam else team["label"]

    period = _period_info(period_key)
    total  = len(ses_list)
    TIER_CFG = {
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
        "total":       total,
        "team_total":  sum(s["total_icav"] for s in ses_list),
        "quarter":     period["label"],
        "team_label":  team_label,
        "motion":      team.get("motion", "dsr"),
    })
