"""
SE Scorecard V2 — Flask Blueprint.
Data is fetched live from Salesforce on demand and cached per-team per-period.
Current quarter: 10-minute TTL. Historical quarters/years: 1-week TTL.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

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
    "dorg": {
        "label":            "DORG",
        "description":      "Digital Organization SE team",
        "motion":           "ae",
        "soql_filter":      "Technical_Lead__r.UserRole.Name = 'SE - DORG'",
        "email_owner_filter": "Owner.UserRole.Name = 'SE - DORG'",
        "criteria": [
            {
                "label":  "SE Tagged",
                "detail": "Technical Lead UserRole = 'SE - DORG'",
            },
        ],
    },
    "namer": {
        "label":            "NAMER",
        "description":      "All NAMER SEs",
        "motion":           "ae",
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
}

_DEFAULT_TEAM = "digital_sales"

# ---------------------------------------------------------------------------
# Period config
# ---------------------------------------------------------------------------

_ICAV_FIELD = sf_analysis.FIELD_CONFIG["icav_field"]
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
        f"SELECT Id, Name, CloseDate, {_ICAV_FIELD}, {_TEAM_FIELD}, Presales_Stage__c, "
        f"Technical_Lead__r.Name, Technical_Lead__r.Email, "
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


def _is_fresh(team_key: str, period_key: str, icav_min: int, ttl: int) -> bool:
    p = _cache_path(team_key, period_key, icav_min)
    return p.exists() and (time.time() - p.stat().st_mtime) < ttl


def _load_cached(team_key: str, period_key: str, icav_min: int = 0) -> list | None:
    p = _cache_path(team_key, period_key, icav_min)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _save_cached(ranked: list, team_key: str, period_key: str, icav_min: int = 0, motion: str = "dsr"):
    total   = len(ranked)
    payload = []
    for i, se in enumerate(ranked, 1):
        entry          = {k: v for k, v in se.items() if not k.startswith("_")}
        entry["rank"]  = i
        entry["tier"]  = sf_analysis.tier(i, total)
        entry["flags"] = sf_analysis.collect_se_flags(se, ranked, motion)
        entry["roast"] = sf_analysis._roast(se, ranked, motion)
        payload.append(entry)
    p   = _cache_path(team_key, period_key, icav_min)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(p)



def _get_data(team_key: str, period_key: str, icav_min: int = 0, subteam_key: str = "") -> tuple[list | None, str | None]:
    """
    Return (ranked_ses, error_msg).
    Serves from cache if fresh; otherwise fetches from Salesforce and updates cache.
    icav_min:    minimum iACV for main closed-won query — also drives notes quality floor.
    subteam_key: overrides soql_filter/email_owner_filter from parent team.
    """
    team = TEAMS.get(team_key)
    if not team:
        return None, f"Unknown team '{team_key}'"

    soql_filter        = team["soql_filter"]
    email_owner_filter = team["email_owner_filter"]
    display_label      = team["label"]

    if subteam_key:
        subteam = next((s for s in team.get("subteams", []) if s["key"] == subteam_key), None)
        if not subteam:
            return None, f"Unknown subteam '{subteam_key}' for team '{team_key}'"
        soql_filter        = subteam["soql_filter"]
        email_owner_filter = subteam["email_owner_filter"]
        display_label      = f"{team['label']} · {subteam['label']}"

    cache_key = f"{team_key}_{subteam_key}" if subteam_key else team_key
    info      = _period_info(period_key)

    # For prior-year periods, use the looser filter if the team defines one
    # (role/title filters reflect current state; only the DSR stamp is stable across years)
    period_year = int(period_key.split("_")[0])
    if not subteam_key and period_year < date.today().year and "historical_soql_filter" in team:
        soql_filter = team["historical_soql_filter"]

    if _is_fresh(cache_key, period_key, icav_min, info["ttl"]):
        return _load_cached(cache_key, period_key, icav_min), None

    if not sf.configured:
        stale = _load_cached(cache_key, period_key, icav_min)
        if stale:
            log.warning("Salesforce not configured — serving stale cache for %s/%s", cache_key, period_key)
            return stale, None
        return None, "Salesforce is not configured."

    # Run all 5 queries in parallel — they are fully independent
    core_exc: Exception | None = None
    opps = win_rate_opps = pipe_opps = email_tasks = meeting_events = None

    with ThreadPoolExecutor(max_workers=5) as pool:
        f_opps     = pool.submit(sf.query, _build_soql(soql_filter, info["start"], info["end"], icav_min))
        f_win_rate = pool.submit(sf.query, _build_win_rate_soql(soql_filter, info["start"], info["end"]))
        f_pipeline = pool.submit(sf.query, _build_pipeline_soql(soql_filter, info["end"]))
        f_email    = pool.submit(sf.query, _build_email_soql(info["start"], info["end"], email_owner_filter))
        f_meetings = pool.submit(sf.query, _build_meeting_soql(info["start"], info["end"], email_owner_filter))

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

    if core_exc is not None:
        stale = _load_cached(cache_key, period_key, icav_min)
        if stale:
            log.warning("Salesforce error — serving stale cache for %s/%s", cache_key, period_key)
            return stale, None
        return None, f"Salesforce query failed: {core_exc}"

    if not opps:
        return [], None

    ses = sf_analysis.build_ses(opps, team.get("motion", "dsr"), notes_floor=icav_min)
    sf_analysis.merge_win_rate(ses, win_rate_opps, team.get("motion", "dsr"))

    # Build opp motion map from closed-won + pipeline opps, then merge email activity
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

    ses    = [s for s in ses if s["act_wins"] + s["exp_wins"] > 0]
    if not ses:
        return None, f"No closed won TW opportunities found for {display_label} in {info['label']}."
    ranked = sf_analysis.rank_ses(ses)
    _save_cached(ranked, cache_key, period_key, icav_min, team.get("motion", "dsr"))
    log.info("Refreshed %s/%s (min $%s) SE data from Salesforce (%d opps, %d win-rate opps)",
             cache_key, period_key, icav_min, len(opps), len(win_rate_opps))
    return _load_cached(cache_key, period_key, icav_min), None


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
    """Called by /api/me — check all cached team files for this SE."""
    for team_key in TEAMS:
        # Search any cached period for this team
        for p in OUTPUT_DIR.glob(f"sf_se_data_{team_key}_*.json"):
            try:
                cached = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            se_name = _email_to_se_name(email, cached)
            if se_name:
                return {"sf_is_se": True, "sf_se_name": se_name, "sf_team": team_key}
    return {"sf_is_se": False, "sf_se_name": None, "sf_team": None}


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
    ses, err    = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": err}), 503
    team_medians = sf_analysis.compute_team_medians(ses)
    se_name      = _email_to_se_name(session.get("user_email", ""), ses)
    if se_name:
        ses = [s for s in ses if s["name"] == se_name]
    team_motion = TEAMS[team_key].get("motion", "dsr") if team_key in TEAMS else "dsr"
    return jsonify([{**s, "team_motion": team_motion, "team_medians": team_medians} for s in ses])


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/data/report")
def api_report():
    team_key    = request.args.get("team", _DEFAULT_TEAM)
    period_key  = request.args.get("period", _default_period())
    icav_min, err = _parse_icav_min(request.args.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key   = request.args.get("subteam", "")
    ses_list, err = _get_data(team_key, period_key, icav_min, subteam_key)
    if err:
        return jsonify({"error": err}), 503
    if _email_to_se_name(session.get("user_email", ""), ses_list):
        return jsonify({"error": "Access denied"}), 403

    team        = TEAMS[team_key]
    subteam     = next((s for s in team.get("subteams", []) if s["key"] == subteam_key), None) if subteam_key else None
    team_label  = f"{team['label']} · {subteam['label']}" if subteam else team["label"]

    period      = _period_info(period_key)
    total       = len(ses_list)
    act_sorted  = sorted(ses_list, key=lambda x: x["act_icav"], reverse=True)
    exp_sorted  = sorted(ses_list, key=lambda x: x["exp_icav"], reverse=True)
    deal_sorted = [s for s in sorted(ses_list, key=lambda x: x["largest_deal_value"], reverse=True)
                   if s["largest_deal_value"] > 0]

    # --- Expansion trend across comparable cached periods ---
    # "Total influenced" = TW exp_icav + non-TW exp_icav (deals SE was tagged on but didn't get full TW)
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
        prior = _load_cached(cache_key_trend, p["key"], 0)
        if prior:
            exp_trend.append(_exp_snapshot(prior, p["label"], p["key"], False))

    exp_trend.reverse()  # chronological order — oldest first

    return jsonify({
        "ranked":       ses_list,
        "total":        total,
        "icav_min":     icav_min,
        "team_icav":    sum(s["total_icav"] for s in ses_list),
        "team_wins":    sum(s["act_wins"] + s["exp_wins"] for s in ses_list),
        "act_sorted":   act_sorted,
        "exp_sorted":   exp_sorted,
        "pipe_sorted":  [],
        "deal_sorted":  deal_sorted,
        "max_act":      act_sorted[0]["act_icav"] if act_sorted else 1,
        "max_exp":      max((s["exp_icav"] for s in exp_sorted), default=1) or 1,
        "max_fut":      1,
        "max_act_icav": max(s["act_icav"] for s in ses_list) or 1,
        "max_exp_icav": max(s["exp_icav"] for s in ses_list) or 1,
        "trends":       sorted(sf_analysis.collect_team_trends(ses_list), key=lambda x: x[0]),
        "recommendations": sf_analysis.generate_recommendations(ses_list, team.get("motion", "dsr")),
        "exp_trend":    exp_trend,
        "quarter":      period["label"],
        "team_label":   team_label,
        "motion":       team.get("motion", "dsr"),
    })


@se_scorecard_v2_bp.route("/api/se-scorecard-v2/data/rankings")
def api_rankings():
    team_key    = request.args.get("team", _DEFAULT_TEAM)
    period_key  = request.args.get("period", _default_period())
    icav_min, err = _parse_icav_min(request.args.get("icav_min"))
    if err:
        return jsonify({"error": err}), 400
    subteam_key   = request.args.get("subteam", "")
    ses_list, err = _get_data(team_key, period_key, icav_min, subteam_key)
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
    })
