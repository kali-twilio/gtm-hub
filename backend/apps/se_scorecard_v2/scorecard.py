from __future__ import annotations

import json
import logging
import os
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from salesforce import sf
"""
SE Scorecard V2 — all business logic in one place.
  TEAMS          — team/subteam configuration
  FIELD_CONFIG   — Salesforce field mapping
  build_ses()    — transform raw SF opps into SE performance records
  merge_*()      — merge win rate, email, and meeting activity
  rank_ses()     — composite percentile ranking
  collect_se_flags(), generate_analysis(), compute_ae_engagement()
  period helpers, SOQL builders, cache helpers, get_data(), chat context
"""


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
            # Fallback: owner's current UserRole contains DSR but FY_16 was never stamped correctly.
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
                "detail": "Opp WHERE FY_16_Owner_Team__c LIKE 'DSR%' (stamped at assignment, frozen) OR Owner.UserRole.Name LIKE '%DSR%' AND NOT LIKE '%Twilio.org%' (fallback when FY_16 was never stamped).",
            },
            {
                "label":  "SE Tagged",
                "detail": "Opp WHERE Technical_Lead__r.UserRole.Name = 'SE - Self Service' AND Technical_Lead__r.Title LIKE '%Engineer%'. Both conditions required — role identifies the team, title excludes non-SE roles sharing the same UserRole.",
            },
            {
                "label":  "Total iACV",
                "detail": "SUM(Comms_Segment_Combined_iACV__c) on all Closed Won opps WHERE (FY_16_Owner_Team__c LIKE 'DSR%' OR Owner.UserRole.Name LIKE '%DSR%' …) — no SE tag required. Represents the full DSR team's iACV against which SE-tagged deals are measured.",
            },
        ],
    },
    "namer": {
        "label":            "NAMER",
        "description":      "All NAMER SEs",
        "motion":           "ae",
        "team_total_filter": "Owner.UserRole.Name LIKE '%NAMER%' AND (NOT Owner.UserRole.Name LIKE '%DSR%') AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')",
        # Total iACV denominator = NB + Strat universe by UserRole, so NB + Strat = Total exactly.
        # UserRole required for NAMER: FY_16 undercounts Strat by ~$1M due to AE transfers.
        "team_icav_filter": (
            "Owner.UserRole.Name LIKE '%NAMER%'"
            " AND (NOT Owner.UserRole.Name LIKE '%DSR%')"
            " AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')"
            " AND (Owner.UserRole.Name LIKE '% NB%' OR Owner.UserRole.Name LIKE '%Strat%')"
        ),
        "soql_filter":        "Technical_Lead__r.UserRole.Name LIKE 'SE - NAMER%'",
        "email_owner_filter": "Owner.UserRole.Name LIKE 'SE - NAMER%'",
        "act_icav_clause":    "Owner.UserRole.Name LIKE '% NB%'",
        "exp_icav_clause":    "Owner.UserRole.Name LIKE '%Strat%'",
        "criteria": [
            {
                "label":  "SE Tagged",
                "detail": "Opp WHERE Technical_Lead__r.UserRole.Name LIKE 'SE - NAMER%' AND StageName = 'Closed Won'. Covers all NAMER sub-roles (Retail, NB, ISV, HighTech, RegVerts, MarTech).",
            },
            {
                "label":  "Total iACV",
                "detail": "SUM(Comms_Segment_Combined_iACV__c) on Closed Won opps WHERE Owner.UserRole.Name LIKE '%NAMER%' AND role is NB or Strat. Total = NB + Strat exactly. Uses current AE role — more accurate than FY_16 for NAMER due to AE transfers.",
            },
            {
                "label":  "NB / Strat Split",
                "detail": "NB denominator: Owner.UserRole.Name LIKE '% NB%'. Strat denominator: Owner.UserRole.Name LIKE '%Strat%'. Uses current AE role (not FY_16) because NAMER AE transfers leave a ~$1M gap in Strat when using FY_16 stamp.",
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
        # Total iACV denominator = NB + Strat universe only, so NB + Strat = Total exactly.
        "team_icav_filter": (
            "Owner.UserRole.Name LIKE '%EMEA%'"
            " AND (FY_16_Owner_Team__c LIKE '% NB%' OR FY_16_Owner_Team__c LIKE '%Strat%')"
        ),
        "soql_filter":        "Technical_Lead__r.UserRole.Name LIKE 'SE - EMEA%'",
        "email_owner_filter": "Owner.UserRole.Name LIKE 'SE - EMEA%'",
        "act_icav_clause":    "FY_16_Owner_Team__c LIKE '% NB%'",
        "exp_icav_clause":    "FY_16_Owner_Team__c LIKE '%Strat%'",
        "criteria": [
            {
                "label":  "SE Tagged",
                "detail": "Opp WHERE Technical_Lead__r.UserRole.Name LIKE 'SE - EMEA%' AND StageName = 'Closed Won'. Covers North, DACH, and South sub-roles.",
            },
            {
                "label":  "Total iACV",
                "detail": "SUM(Comms_Segment_Combined_iACV__c) on Closed Won opps WHERE Owner.UserRole.Name LIKE '%EMEA%' AND FY_16_Owner_Team__c is NB or Strat. Total = NB + Strat exactly.",
            },
            {
                "label":  "NB / Strat Split",
                "detail": "NB denominator: FY_16_Owner_Team__c LIKE '% NB%'. Strat denominator: FY_16_Owner_Team__c LIKE '%Strat%'. FY_16 is frozen at opp assignment.",
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
        # UserRole required for APJ: FY_16 undercounts Strat due to AE transfers (~$300K gap).
        "team_icav_filter": (
            "Owner.UserRole.Name LIKE '%APJ%'"
            " AND (Owner.UserRole.Name LIKE '% NB%' OR Owner.UserRole.Name LIKE '%Strat%')"
        ),
        "soql_filter":        "Technical_Lead__r.UserRole.Name = 'SE - APJ'",
        "email_owner_filter": "Owner.UserRole.Name = 'SE - APJ'",
        "act_icav_clause":    "Owner.UserRole.Name LIKE '% NB%'",
        "exp_icav_clause":    "Owner.UserRole.Name LIKE '%Strat%'",
        "criteria": [
            {"label": "SE Tagged",  "detail": "Opp WHERE Technical_Lead__r.UserRole.Name = 'SE - APJ' AND StageName = 'Closed Won'."},
            {"label": "Total iACV", "detail": "SUM(Comms_Segment_Combined_iACV__c) on Closed Won opps WHERE Owner.UserRole.Name LIKE '%APJ%' AND role is NB or Strat. Uses current AE role — more accurate than FY_16 due to AE transfers."},
            {"label": "NB / Strat Split", "detail": "NB: Owner.UserRole.Name LIKE '% NB%'. Strat: LIKE '%Strat%'. Uses current AE role."},
        ],
    },
    "latam": {
        "label":            "LATAM",
        "description":      "LATAM SE team",
        "motion":           "ae",
        "team_total_filter": "Owner.UserRole.Name LIKE '%LATAM%'",
        # UserRole used for LATAM (consistent with NAMER/APJ): avoids AE-transfer undercounting.
        "team_icav_filter": (
            "Owner.UserRole.Name LIKE '%LATAM%'"
            " AND (Owner.UserRole.Name LIKE '% NB%' OR Owner.UserRole.Name LIKE '%Strat%')"
        ),
        "soql_filter":        "Technical_Lead__r.UserRole.Name LIKE 'SE - LATAM%'",
        "email_owner_filter": "Owner.UserRole.Name LIKE 'SE - LATAM%'",
        "act_icav_clause":    "Owner.UserRole.Name LIKE '% NB%'",
        "exp_icav_clause":    "Owner.UserRole.Name LIKE '%Strat%'",
        "criteria": [
            {"label": "SE Tagged",  "detail": "Opp WHERE Technical_Lead__r.UserRole.Name LIKE 'SE - LATAM%' AND StageName = 'Closed Won'. Covers Brazil (SE - LATAM - BR) and Rest of LATAM (SE - LATAM - ROL)."},
            {"label": "Total iACV", "detail": "SUM(Comms_Segment_Combined_iACV__c) on Closed Won opps WHERE Owner.UserRole.Name LIKE '%LATAM%' AND role is NB or Strat. Uses current AE role."},
            {"label": "NB / Strat Split", "detail": "NB: Owner.UserRole.Name LIKE '% NB%'. Strat: LIKE '%Strat%'. Uses current AE role — consistent with NAMER and APJ."},
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
        # iACV denominator: union of .org-role AE opps + any opp a DORG SE touched
        "team_icav_filter": (
            "Owner.UserRole.Name LIKE 'DORG%' OR Owner.UserRole.Name LIKE '%.org%'"
            " OR Technical_Lead__r.UserRole.Name = 'SE - DORG'"
        ),
        # NB = everything not Strat (matches build_ses fallback for unrecognised roles).
        "act_icav_clause":    "(NOT Owner.UserRole.Name LIKE '%Strat%')",
        "exp_icav_clause":    "Owner.UserRole.Name LIKE '%Strat%'",
        "soql_filter":        "Technical_Lead__r.UserRole.Name = 'SE - DORG'",
        "email_owner_filter": "Owner.UserRole.Name = 'SE - DORG'",
        "criteria": [
            {"label": "SE Tagged",  "detail": "Opp WHERE Technical_Lead__r.UserRole.Name = 'SE - DORG' AND StageName = 'Closed Won'."},
            {"label": "Total iACV", "detail": "SUM(Comms_Segment_Combined_iACV__c) on all Closed Won opps WHERE Owner.UserRole.Name LIKE 'DORG%' OR '%.org%' OR Technical_Lead__r.UserRole.Name = 'SE - DORG'. Union covers the full universe DORG SEs work."},
        ],
    },
}



# ---------------------------------------------------------------------------
# Monthly amortized usage snapshots — index = months ago from today
# Fields 2-9 have an underscore before "Month"; 10-14 do not (SF naming quirk).
# ---------------------------------------------------------------------------

_MONTHLY_USAGE_FIELDS: list[str] = [
    "Total_Amortized_Twilio_Usage_This_Month__c",            # 0
    "Total_Amortized_Twilio_Usage_Last_Month__c",            # 1
    *[f"Total_Amortized_Twilio_Usage_{n}_Month_Ago__c" for n in range(2, 10)],   # 2-9
    *[f"Total_Amortized_Twilio_Usage_{n}Month_Ago__c"  for n in range(10, 15)],  # 10-14
]


def _month_add(year: int, month: int, delta: int) -> tuple[int, int]:
    """Offset (year, month) by delta months (positive or negative)."""
    total = (year * 12 + month - 1) + delta
    return total // 12, total % 12 + 1


def _quarter_mrr_delta(acct: dict, close_date_str: str) -> tuple[int, int, int]:
    """
    Quarter-anchored MRR impact using monthly amortized usage snapshots.

    Identifies the 3 calendar months of the opp's close quarter and the
    3 months immediately before it, reads the corresponding snapshot fields
    (relative to today's date), and returns:
        (quarter_mrr_avg, pre_quarter_mrr_avg, delta)

    Returns (0, 0, 0) if any required snapshot is beyond the 14-month
    lookback window or is missing from the account record.
    Falls back to the caller using the rolling 3mo average instead.
    """
    try:
        close = date.fromisoformat(close_date_str)
    except (ValueError, TypeError):
        return 0, 0, 0

    today     = date.today()
    q_start   = ((close.month - 1) // 3) * 3 + 1          # first month of close quarter
    q_months  = [_month_add(close.year, q_start, i)     for i in range(3)]
    pre_months= [_month_add(close.year, q_start, i - 3) for i in range(3)]

    def _get(year: int, month: int) -> int | None:
        months_ago = (today.year - year) * 12 + (today.month - month)
        if months_ago < 0 or months_ago >= len(_MONTHLY_USAGE_FIELDS):
            return None
        raw = acct.get(_MONTHLY_USAGE_FIELDS[months_ago])
        if raw is None:
            return None
        return _acct_num(raw)

    q_vals   = [_get(y, m) for y, m in q_months]
    pre_vals = [_get(y, m) for y, m in pre_months]

    if any(v is None for v in q_vals + pre_vals):
        return 0, 0, 0

    q_avg   = round(sum(q_vals) / 3)
    pre_avg = round(sum(pre_vals) / 3)
    return q_avg, pre_avg, q_avg - pre_avg

# ---------------------------------------------------------------------------
# Field config — derived from the Self Service SE Dashboard (01Z8Z000001XBAGUA4)
# ---------------------------------------------------------------------------

FIELD_CONFIG = {
    # iACV field on Opportunity (from dashboard: Comms_Segment_Combined_iACV__c)
    "icav_field": "Comms_Segment_Combined_iACV__c",
    # eARR field on Opportunity — eARR(post-launch) No Decimal
    "earr_field": "eARR_post_launch_No_Decimal__c",

    # SE is the Technical Lead on the opportunity (not the owner/AE)
    "se_name_field": "Technical_Lead__r.Name",
    "se_email_field": "Technical_Lead__r.Email",

    # Team field — FY_16_Owner_Team__c contains values like:
    #   "DSR"                         → activate, no expansion keyword
    #   "DSR - NAMER - Activation 5"  → activate
    #   "DSR - NAMER - Expansion 1"   → expansion
    # Activate = team contains 'DSR' but NOT 'Expansion'
    # Expansion = team contains 'Expansion'
    "team_field": "FY_16_Owner_Team__c",

    # Q1 date range (used as a label only — filtering is done in SOQL)
    "quarter_label": "Q1 2026",
}

ACT_AVG_SIZE_WARNING         = 40_000
FUTURE_PIPELINE_STRONG       = 60
FUTURE_PIPELINE_WEAK         = 30
DEAL_CONCENTRATION_THRESHOLD = 0.5


def fmt(amount):
    import math
    if amount >= 1_000_000: return f"${math.ceil(amount / 100_000) / 10:.1f}M"
    if amount >= 1_000:     return f"${math.ceil(amount / 1_000)}K"
    return f"${amount}"


def _icav(opp: dict) -> int:
    val = opp.get(FIELD_CONFIG["icav_field"]) or 0
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _earr(opp: dict) -> int:
    val = opp.get(FIELD_CONFIG["earr_field"]) or 0
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _acct_num(val) -> int:
    """Safely parse an Account currency/number field (can be negative for deltas)."""
    try:
        return int(float(val or 0))
    except (TypeError, ValueError):
        return 0


def _se_name(opp: dict) -> str:
    tl = opp.get("Technical_Lead__r") or {}
    return (tl.get("Name") or "").strip()


def _se_email(opp: dict) -> str:
    tl = opp.get("Technical_Lead__r") or {}
    return (tl.get("Email") or "").strip().lower()


def _se_title(opp: dict) -> str:
    tl = opp.get("Technical_Lead__r") or {}
    return (tl.get("Title") or "").strip()


def _opp_product(opp_name: str) -> str:
    """Extract product from opp name: 'Account - Product - Description' → 'Product'."""
    parts = opp_name.split(" - ")
    return parts[1].strip() if len(parts) >= 2 else ""


def _team(opp: dict) -> str:
    return (opp.get(FIELD_CONFIG["team_field"]) or "").strip()


def _history_entries(text: str) -> int:
    """Count entries in SE_Notes_History__c — each entry starts with [DATE: Name]."""
    if not text:
        return 0
    return sum(1 for line in text.split("\n") if line.strip().startswith("["))


def _owner_role(opp: dict) -> str:
    """Owner's Salesforce UserRole.Name — the reliable Activate/Expansion signal."""
    owner = opp.get("Owner") or {}
    role  = owner.get("UserRole") or {}
    return (role.get("Name") or "").strip()


def _motion_labels(motion: str) -> tuple[str, str, str, str]:
    """Return (act_cat, exp_cat, act_lbl, exp_lbl) for a given motion string."""
    if motion == "ae":
        return "NEW BUSINESS", "STRATEGIC", "new business", "strategic"
    return "ACTIVATE", "EXPANSION", "activate", "expansion"


def _is_activate(opp: dict) -> bool:
    """DSR motion: Activate = owner's role contains 'Activation'.
    Fallback to FY_16_Owner_Team__c when owner has changed since close.
    Self-service-owned accounts are also definitionally Activate."""
    role = _owner_role(opp)
    if "Activation" in role:
        return True
    if "Expansion" in role:
        return False
    team = _team(opp)
    if "DSR" in team and "Expansion" not in team:
        return True
    return _is_self_service_account(opp)


def _is_expansion(opp: dict) -> bool:
    """DSR motion: Expansion = owner's role contains 'Expansion'.
    Fallback to FY_16_Owner_Team__c when owner has changed since close."""
    role = _owner_role(opp)
    if "Expansion" in role:
        return True
    if "Activation" in role:
        return False
    team = _team(opp)
    return "Expansion" in team


def _is_self_service_account(opp: dict) -> bool:
    """True when the account is owned by the self-service channel.
    Self-service-owned accounts are definitionally Activate — they have no expansion opps."""
    acct  = opp.get("Account") or {}
    owner = acct.get("Owner") or {}
    name  = (owner.get("Name") or "").strip()
    return "Self" in name  # matches "Self-Service", "Self Service"


def _is_new_business(opp: dict) -> bool:
    """AE motion: New Business = owner role or team field contains ' NB'."""
    role = _owner_role(opp)
    if " NB" in role:
        return True
    if "Strat" in role:
        return False
    return " NB" in _team(opp)


def _is_strategic(opp: dict) -> bool:
    """AE motion: Strategic = owner role or team field contains 'Strat'."""
    role = _owner_role(opp)
    if "Strat" in role:
        return True
    if " NB" in role:
        return False
    return "Strat" in _team(opp)


# ---------------------------------------------------------------------------
# Build SE records from raw Salesforce opportunity records
# ---------------------------------------------------------------------------

def build_ses(opps: list, motion: str = "dsr", notes_floor: int = 0, period_key: str = "") -> list:
    """
    opps       — list of Salesforce Closed Won Opportunity dicts (TW and non-TW)
    motion     — 'dsr' (Activate/Expansion) or 'ae' (New Business/Strategic)
    period_key — e.g. '2025_Q2' or '2025_FY'. Full-year periods anchor MRR to Q4 of that year.
    Returns list of SE dicts. Ranking uses TW opps only; non-TW stats are supplemental.
    """
    by_se: dict[str, dict] = {}

    for opp in opps:
        name  = _se_name(opp)
        email = _se_email(opp)
        if not name:
            continue

        if name not in by_se:
            by_se[name] = {
                "name":           name,
                "email":          email,
                "title":          _se_title(opp),
                "act_icavs":      [],   # TW activate wins
                "act_earrs":      [],   # TW activate wins eARR
                "exp_icavs":      [],   # TW expansion wins
                "exp_earrs":      [],   # TW expansion wins eARR
                "non_tw_act_icavs": [], # non-TW activate wins
                "non_tw_exp_icavs": [], # non-TW expansion wins
                "all_opps":       [],
                "exp_tw_opps":    [],  # ALL TW expansion wins (for account ARR/MRR aggregation)
            }

        icav  = _icav(opp)
        earr  = _earr(opp)
        is_tw = opp.get("Presales_Stage__c") == "4 - Technical Win Achieved"
        by_se[name]["all_opps"].append(opp)

        is_act = _is_new_business(opp) if motion == "ae" else _is_activate(opp)
        is_exp = _is_strategic(opp)   if motion == "ae" else _is_expansion(opp)

        if is_tw:
            if is_act:
                by_se[name]["act_icavs"].append(icav)
                by_se[name]["act_earrs"].append(earr)
            elif is_exp:
                by_se[name]["exp_icavs"].append(icav)
                by_se[name]["exp_earrs"].append(earr)
                by_se[name]["exp_tw_opps"].append(opp)
            else:
                by_se[name]["act_icavs"].append(icav)  # fallback
                by_se[name]["act_earrs"].append(earr)  # fallback
        else:
            if is_act:
                by_se[name]["non_tw_act_icavs"].append(icav)
            elif is_exp:
                by_se[name]["non_tw_exp_icavs"].append(icav)
            else:
                by_se[name]["non_tw_act_icavs"].append(icav)  # fallback

    ses = []
    for name, d in by_se.items():
        act_icavs = d["act_icavs"]
        act_earrs = d["act_earrs"]
        exp_icavs = d["exp_icavs"]
        exp_earrs = d["exp_earrs"]

        act_wins   = len(act_icavs)
        act_icav   = sum(act_icavs)
        act_earr   = sum(act_earrs)
        act_avg    = round(statistics.mean(act_icavs)) if act_icavs else 0
        act_median = round(statistics.median(act_icavs)) if act_icavs else 0

        exp_wins   = len(exp_icavs)
        exp_icav   = sum(exp_icavs)
        exp_earr   = sum(exp_earrs)
        exp_avg    = round(statistics.mean(exp_icavs)) if exp_icavs else 0
        exp_median = round(statistics.median(exp_icavs)) if exp_icavs else 0

        total_icav = act_icav + exp_icav
        total_earr = act_earr + exp_earr

        # Non-TW closed won (supplemental — not used for ranking)
        non_tw_act_icavs = d["non_tw_act_icavs"]
        non_tw_exp_icavs = d["non_tw_exp_icavs"]
        non_tw_act_wins  = len(non_tw_act_icavs)
        non_tw_exp_wins  = len(non_tw_exp_icavs)
        non_tw_act_icav  = sum(non_tw_act_icavs)
        non_tw_exp_icav  = sum(non_tw_exp_icavs)
        non_tw_total_icav = non_tw_act_icav + non_tw_exp_icav

        # SE notes — count TW opps with Solutions_Team_Notes fields filled
        tw_opps = [o for o in d["all_opps"] if o.get("Presales_Stage__c") == "4 - Technical Win Achieved"]

        # Per-opp detail list for "My Stats" drilldown
        def _opp_motion(opp):
            if motion == "ae":
                return "nb" if _is_new_business(opp) else ("strat" if _is_strategic(opp) else "nb")
            return "act" if _is_activate(opp) else ("exp" if _is_expansion(opp) else "act")

        tw_opps_detail = sorted([{
            "id":           opp.get("Id") or "",
            "name":         opp.get("Name") or "",
            "product":      _opp_product(opp.get("Name") or ""),
            "owner":        ((opp.get("Owner") or {}).get("Name") or ""),
            "acct":         ((opp.get("Account") or {}).get("Name") or ""),
            "close_date":   opp.get("CloseDate") or "",
            "icav":         _icav(opp),
            "earr":         _earr(opp),
            "motion":       _opp_motion(opp),
            "has_notes":    bool(opp.get("Sales_Engineer_Notes__c")),
            "has_history":  bool(opp.get("SE_Notes_History__c")),
            "note_entries": _history_entries(opp.get("SE_Notes_History__c") or ""),
            "notes_len":    len((opp.get("Sales_Engineer_Notes__c") or "").strip()),
            "history_len":  len((opp.get("SE_Notes_History__c") or "").strip()),
        } for opp in tw_opps], key=lambda x: x["icav"], reverse=True)

        note_opps         = sum(1 for o in tw_opps if o.get("Sales_Engineer_Notes__c"))
        note_history_opps = sum(1 for o in tw_opps if o.get("SE_Notes_History__c"))
        note_both_opps    = sum(1 for o in tw_opps if o.get("Sales_Engineer_Notes__c") and o.get("SE_Notes_History__c"))
        note_history_entries = sum(_history_entries(o.get("SE_Notes_History__c") or "") for o in tw_opps)

        # Notes quality: only opps with positive iACV, at or above the notes floor
        hv_opps           = [o for o in d["all_opps"] if _icav(o) >= max(notes_floor, 1)]
        note_hv_total     = len(hv_opps)
        note_hv_covered   = sum(1 for o in hv_opps if o.get("Sales_Engineer_Notes__c") and o.get("SE_Notes_History__c"))
        note_hv_entries   = sum(_history_entries(o.get("SE_Notes_History__c") or "") for o in hv_opps)
        note_hv_avg_entries = round(note_hv_entries / note_hv_total, 1) if note_hv_total > 0 else 0

        # Largest deal — TW only so it's consistent with total_icav and appears in tw_opps_detail
        tw_icavs = [(o, _icav(o)) for o in tw_opps]
        largest_opp, largest_val = max(tw_icavs, key=lambda x: x[1]) if tw_icavs else (None, 0)
        largest_name   = (largest_opp.get("Name") or "") if largest_opp else ""
        largest_id     = (largest_opp.get("Id") or "") if largest_opp else ""
        largest_dsr    = ((largest_opp.get("Owner") or {}).get("Name") or "") if largest_opp else ""
        largest_acct   = ((largest_opp.get("Account") or {}).get("Name") or "") if largest_opp else ""
        # Product is the second segment of the opp name: "Account - Product - Description"
        _name_parts    = largest_name.split(" - ")
        largest_product = _name_parts[1].strip() if len(_name_parts) >= 2 else ""
        if largest_opp:
            if motion == "ae":
                largest_motion = "New Business" if _is_new_business(largest_opp) else ("Strategic" if _is_strategic(largest_opp) else "")
            else:
                largest_motion = "Activate" if _is_activate(largest_opp) else ("Expansion" if _is_expansion(largest_opp) else "")
        else:
            largest_motion = ""

        conc = round(largest_val / total_icav * 100) if total_icav > 0 and largest_val > 0 else 0

        # Account ARR/MRR across ALL TW expansion opps
        # Used for: aggregate totals in full report, per-account detail in My Stats
        exp_tw_opps = d.get("exp_tw_opps", [])
        exp_account_detail = []
        for e_opp in exp_tw_opps:
            acct      = e_opp.get("Account") or {}
            arr       = _acct_num(acct.get("Current_ARR_Based_on_Last_6_Months__c"))
            mrr_3m    = _acct_num(acct.get("Average_Amortized_Usage_Last_3_Months__c"))

            # Quarter-anchored MRR delta: avg usage in opp's quarter vs avg of 3 months prior.
            # For full-year periods all accounts use Q4 of that year as the anchor so every
            # account is measured on the same time window (Q4 avg vs Q3 avg). Using each opp's
            # own close quarter would mix deltas across Q1-Q4, producing an incoherent sum.
            # Falls back to rolling 3mo avg vs ARR/12 baseline if snapshots aren't available.
            if period_key.endswith("_FY"):
                fy_year = int(period_key.split("_")[0])
                mrr_anchor = f"{fy_year}-12-01"
            else:
                mrr_anchor = e_opp.get("CloseDate") or ""
            q_avg, pre_avg, mrr_delta = _quarter_mrr_delta(acct, mrr_anchor)
            if q_avg == 0 and mrr_delta == 0:
                # Fallback: rolling 3-month avg vs 6-month ARR baseline
                pre_avg   = round(arr / 12) if arr else 0
                mrr_delta = mrr_3m - pre_avg
                q_avg     = mrr_3m

            mrr_pct = round((mrr_delta / pre_avg) * 100) if pre_avg > 0 else 0
            exp_account_detail.append({
                "opp_name":        e_opp.get("Name") or "",
                "acct_name":       acct.get("Name") or "",
                "icav":            _icav(e_opp),
                "arr":             arr,
                "mrr_quarter_avg": q_avg,     # avg MRR during opp's close quarter
                "mrr_pre_avg":     pre_avg,   # avg MRR in 3 months before the quarter
                "mrr_delta":       mrr_delta, # quarter_avg - pre_avg
                "mrr_pct":         mrr_pct,   # % change in monthly MRR vs pre-quarter
                "fast_growth": bool(acct.get("Fast_Revenue_Growth__c")),
                "contraction": bool(acct.get("Significant_Revenue_Contraction__c")),
            })
        exp_account_detail.sort(key=lambda x: x["arr"], reverse=True)

        # Deduplicate by account: ARR/MRR are account-level fields — count each account once.
        # After sort-by-ARR the first occurrence of each account has the highest ARR entry.
        _seen_accts: set[str] = set()
        _deduped: list = []
        for _a in exp_account_detail:
            _key = _a["acct_name"] or _a["opp_name"]
            if _key not in _seen_accts:
                _seen_accts.add(_key)
                _deduped.append(_a)
        exp_account_detail  = _deduped  # replace with deduped list (affects My Stats too)

        exp_arr_total         = sum(a["arr"]             for a in exp_account_detail)
        exp_mrr_quarter_total = sum(a["mrr_quarter_avg"] for a in exp_account_detail)
        exp_mrr_pre_total     = sum(a["mrr_pre_avg"]     for a in exp_account_detail)
        exp_mrr_delta_total   = sum(a["mrr_delta"]       for a in exp_account_detail)
        # Derive % from totals so it always matches the ↑/↓ direction of exp_mrr_delta_total.
        # Averaging per-account percentages (unweighted) can flip the sign: a small account
        # growing +33% can outweigh a large account dropping -13% in the average.
        exp_mrr_pct_avg       = round(exp_mrr_delta_total / exp_mrr_pre_total * 100) if exp_mrr_pre_total > 0 else 0

        # Expansion status — combines iACV and MRR signals across all expansion accounts.
        #   Growing     — avg MRR % ≥ +5% with more growing accounts than contracting
        #   Contracting — avg MRR % ≤ -5% with more contracting accounts than growing
        #   Mixed       — accounts moving in both directions, net near zero
        #   Expanding   — positive iACV committed but MRR flat or no snapshot data yet
        #   Retaining   — $0 median, flat MRR (pure retention)
        _has_mrr  = exp_arr_total > 0 and bool(exp_account_detail)
        if _has_mrr:
            _grow  = sum(1 for a in exp_account_detail if a["mrr_delta"] > 0)
            _contr = sum(1 for a in exp_account_detail if a["mrr_delta"] < 0)
            if exp_mrr_pct_avg >= 5 and _grow > _contr:
                exp_status = "Growing"
            elif exp_mrr_pct_avg <= -5 and _contr >= _grow:
                exp_status = "Contracting"
            elif _grow > 0 and _contr > 0:
                exp_status = "Mixed"
            elif exp_median > 0:
                exp_status = "Expanding"
            else:
                exp_status = "Retaining"
        else:
            exp_status = "Expanding" if exp_median > 0 else "Retaining"

        se = {
            "name":              name,
            "email":             d["email"],
            "title":             d.get("title", ""),
            "act_wins":          act_wins,
            "act_icav":          act_icav,
            "act_earr":          act_earr,
            "act_avg":           act_avg,
            "act_median":        act_median,
            "exp_wins":          exp_wins,
            "exp_icav":          exp_icav,
            "exp_earr":          exp_earr,
            "exp_avg":           exp_avg,
            "exp_median":        exp_median,
            "top_dsr":           "",
            "bot_dsr":           "",
            # SE notes on TW opps
            "note_opps":             note_opps,
            "note_history_opps":     note_history_opps,
            "note_both_opps":        note_both_opps,
            "note_history_entries":  note_history_entries,
            # Notes quality on high-value TW opps (>= $50K iACV)
            "note_hv_total":         note_hv_total,        # TW opps >= $50K
            "note_hv_covered":       note_hv_covered,      # of those with both notes fields filled
            "note_hv_entries":       note_hv_entries,      # total history entries on those opps
            "note_hv_avg_entries":   note_hv_avg_entries,  # avg history entries per high-value TW opp
            # Email activity — populated by merge_email_activity()
            "email_act_inq":       0,  # emails to Activate opps closing this period
            "email_act_outq":      0,  # emails to future Activate opps (pipeline building)
            "email_act_outq_icav": 0,  # iACV of those future Activate opps
            "email_exp_inq":       0,  # emails to Expansion opps closing this period
            "email_exp_outq":      0,  # emails to future Expansion opps (pipeline building)
            "email_exp_outq_icav": 0,  # iACV of those future Expansion opps
            # Meeting activity — populated by merge_meeting_activity()
            "meeting_act_inq":       0,  # meetings on Activate opps closing this period
            "meeting_act_outq":      0,  # meetings on future Activate opps (pipeline building)
            "meeting_act_outq_icav": 0,  # iACV of those future Activate opps
            "meeting_exp_inq":       0,  # meetings on Expansion opps closing this period
            "meeting_exp_outq":      0,  # meetings on future Expansion opps (pipeline building)
            "meeting_exp_outq_icav": 0,  # iACV of those future Expansion opps
            "largest_deal":         largest_name,
            "largest_deal_id":      largest_id,
            "largest_deal_acct":    largest_acct,
            "largest_deal_product": largest_product,
            "largest_deal_value":   largest_val,
            "largest_deal_dsr":     largest_dsr,
            "largest_deal_motion":  largest_motion,
            "tw_opps_detail":      tw_opps_detail,
            "exp_account_detail":  exp_account_detail,
            "exp_arr_total":          exp_arr_total,
            "exp_mrr_quarter_total":  exp_mrr_quarter_total,  # sum of per-account quarter avg MRR
            "exp_mrr_pre_total":      exp_mrr_pre_total,      # sum of per-account pre-quarter avg MRR
            "exp_mrr_delta_total":    exp_mrr_delta_total,    # quarter_total - pre_total
            "exp_mrr_pct_avg":        exp_mrr_pct_avg,        # avg % MRR change across accounts
            "exp_status":             exp_status,             # Growing/Expanding/Mixed/Contracting/Retaining
        }

        se["total_icav"]       = total_icav
        se["total_earr"]       = total_earr
        se["future_emails"]    = 0
        se["future_pct"]       = 0
        se["act_target_pct"]   = 0
        se["exp_target_pct"]   = 0
        se["exp_growing"]      = exp_status in ("Growing", "Expanding")
        se["conc"]             = conc
        # Non-TW closed won (supplemental)
        se["non_tw_act_wins"]  = non_tw_act_wins
        se["non_tw_exp_wins"]  = non_tw_exp_wins
        se["non_tw_act_icav"]  = non_tw_act_icav
        se["non_tw_exp_icav"]  = non_tw_exp_icav
        se["non_tw_total_icav"]= non_tw_total_icav
        # Win rate — populated by merge_win_rate()
        se["win_rate"]         = 0
        se["closed_won"]       = 0
        se["closed_lost"]      = 0
        # Gong calls — populated by merge_gong_calls()
        se["gong_calls"]       = None

        ses.append(se)

    return ses


# ---------------------------------------------------------------------------
# Win rate
# ---------------------------------------------------------------------------

def merge_win_rate(ses: list, win_rate_opps: list, motion: str = "dsr"):
    """Merge closed won/lost counts into SE records for activate/NB opps only.
    Expansion/Strategic opps are excluded — win rate is only meaningful for
    net-new logos where the SE drives the outcome, not renewals."""
    lookup: dict[str, dict] = {}
    for opp in win_rate_opps:
        tl   = opp.get("Technical_Lead__r") or {}
        name = (tl.get("Name") or "").strip()
        if not name:
            continue
        # Only count activate (DSR) or new business (AE) opps
        if motion == "ae":
            if not _is_new_business(opp):
                continue
        else:
            if not _is_activate(opp):
                continue
        if name not in lookup:
            lookup[name] = {"won": 0, "lost": 0}
        if opp.get("StageName") == "Closed Won":
            lookup[name]["won"] += 1
        else:
            lookup[name]["lost"] += 1

    for se in ses:
        wr = lookup.get(se["name"], {"won": 0, "lost": 0})
        # closed_won = act_wins (TW CW, respects iACV floor) so Wins column and win rate
        # numerator are always the same number. closed_lost still comes from the win rate query.
        closed_won  = se["act_wins"]
        closed_lost = wr["lost"]
        total       = closed_won + closed_lost
        se["closed_won"]  = closed_won
        se["closed_lost"] = closed_lost
        se["win_rate"]    = round(closed_won / total * 100) if total > 0 else 0


# ---------------------------------------------------------------------------
# Activity merge (emails + meetings share the same classification logic)
# ---------------------------------------------------------------------------

def _merge_activity(ses: list, records: list, period_end: str, prefix: str,
                    is_meeting: bool = False) -> None:
    """
    Shared implementation for merging Task-email or Event-meeting counts into SE records.
    Classification is via opp Owner.UserRole.Name (included in SOQL TYPEOF clause).
    prefix is 'email' or 'meeting' — determines which SE fields are written.

    For meetings only: recurring-series deduplication via RecurrenceActivityId so a
    weekly sync on one opp counts once per quarter, not 13 times.
    """
    p_end    = date.fromisoformat(period_end)
    icav_key = FIELD_CONFIG["icav_field"]

    def _blank():
        return {
            "act_inq": 0, "act_outq": 0, "act_outq_opps": {},
            "exp_inq": 0, "exp_outq": 0, "exp_outq_opps": {},
        }

    counts: dict[str, dict] = {}
    seen_series: set = set()  # only used when is_meeting=True

    for rec in records:
        owner = rec.get("Owner") or {}
        name  = (owner.get("Name") or "").strip()
        if not name:
            continue

        what   = rec.get("What") or {}
        opp_id = rec.get("WhatId") or ""

        if is_meeting:
            recurrence_id = rec.get("RecurrenceActivityId") or ""
            if recurrence_id:
                series_key = (name, opp_id, recurrence_id)
                if series_key in seen_series:
                    continue
                seen_series.add(series_key)

        opp_role = ((what.get("Owner") or {}).get("UserRole") or {}).get("Name") or ""
        if "Activation" in opp_role:
            motion = "activate"
        elif "Expansion" in opp_role:
            motion = "expansion"
        else:
            continue

        close_date_str = what.get("CloseDate") or ""
        if not close_date_str:
            continue
        try:
            close_date = date.fromisoformat(close_date_str)
        except ValueError:
            continue

        try:
            icav = int(float(what.get(icav_key) or 0))
        except (TypeError, ValueError):
            icav = 0

        if name not in counts:
            counts[name] = _blank()
        c = counts[name]

        if motion == "activate":
            if close_date <= p_end:
                c["act_inq"] += 1
            else:
                c["act_outq"] += 1
                if opp_id:
                    c["act_outq_opps"].setdefault(opp_id, icav)
        else:
            if close_date <= p_end:
                c["exp_inq"] += 1
            else:
                c["exp_outq"] += 1
                if opp_id:
                    c["exp_outq_opps"].setdefault(opp_id, icav)

    for se in ses:
        c = counts.get(se["name"], _blank())
        se[f"{prefix}_act_inq"]       = c["act_inq"]
        se[f"{prefix}_act_outq"]      = c["act_outq"]
        se[f"{prefix}_act_outq_icav"] = sum(c["act_outq_opps"].values())
        se[f"{prefix}_exp_inq"]       = c["exp_inq"]
        se[f"{prefix}_exp_outq"]      = c["exp_outq"]
        se[f"{prefix}_exp_outq_icav"] = sum(c["exp_outq_opps"].values())


def merge_email_activity(ses: list, email_tasks: list, period_end: str,
                         opp_motion_map: dict = None) -> None:
    _merge_activity(ses, email_tasks, period_end, prefix="email")


def merge_meeting_activity(ses: list, meeting_events: list, period_end: str,
                           opp_motion_map: dict = None) -> None:
    _merge_activity(ses, meeting_events, period_end, prefix="meeting", is_meeting=True)


def _prefetch_gong_stats(period_start: str, period_end: str) -> None:
    """Fetch all Gong aggregate stats for the period and store in _gong_stats_cache.
    Runs in a background thread so the result is ready when merge_gong_calls is called."""
    key = (period_start, period_end)
    if key in _gong_stats_cache:
        return
    try:
        from gong import gong as _gong
        if not _gong.configured:
            return
        all_stats: list = []
        cursor: str | None = None
        while True:
            body: dict = {
                "requestedFields": {"callsAttended": True},
                "filter": {"fromDate": period_start, "toDate": period_end},
            }
            if cursor:
                body["cursor"] = cursor
            data = _gong.post("/v2/stats/activity/aggregate", payload=body)
            all_stats.extend(data.get("usersAggregateActivityStats") or [])
            cursor = (data.get("records") or {}).get("cursor")
            if not cursor:
                break
        _gong_stats_cache[key] = all_stats
    except Exception:
        log.warning("Gong prefetch failed", exc_info=True)


def merge_gong_calls(ses: list, period_start: str, period_end: str) -> None:
    """
    Fetches total call counts per SE via POST /v2/stats/activity/aggregate and
    merges into SE records as gong_calls. Silently no-ops if Gong is not configured.
    """
    key = (period_start, period_end)
    all_stats = _gong_stats_cache.get(key)
    if all_stats is None:
        # Stats not prefetched yet — fetch synchronously
        _prefetch_gong_stats(period_start, period_end)
        all_stats = _gong_stats_cache.get(key) or []

    if not all_stats:
        return

    try:
        _GONG_EMAIL_OVERRIDES = {
            "dberg@twilio.com": "dustin.berg@sendgrid.com",
        }
        email_map:    dict[str, dict] = {}
        username_map: dict[str, dict] = {}
        for se in ses:
            if se.get("email"):
                email_map[se["email"].lower()] = se
                username_map[se["email"].lower().split("@")[0]] = se
        if not email_map:
            return
        for stat in all_stats:
            gong_email     = (stat.get("userEmailAddress") or "").lower()
            calls          = int((stat.get("userAggregateActivityStats") or {}).get("callsAttended") or 0)
            resolved_email = _GONG_EMAIL_OVERRIDES.get(gong_email, gong_email)
            se = (email_map.get(resolved_email)
                  or username_map.get(resolved_email.split("@")[0]))
            if not se:
                continue
            if se["gong_calls"] is None:
                se["gong_calls"] = 0
            se["gong_calls"] += calls
    except Exception:
        log.warning("Gong call merge failed", exc_info=True)


def get_gong_data(teams: dict, team_key: str, period_key: str, icav_min: int = 0, subteam_key: str = "") -> dict:
    """
    Fetch Gong call counts and merge into the SE list.
    Uses the in-memory cache (populated by get_data) to avoid re-querying Salesforce.
    Returns {"ses": [{name, gong_calls}, ...]} or {"error": "..."}.
    """
    cache_key = f"{team_key}_{subteam_key}" if subteam_key else team_key
    mem = _mem_cache.get((cache_key, period_key, icav_min))
    if mem:
        import copy
        ses_list = copy.deepcopy(mem[0])
    else:
        ses_list, err, *_ = get_data(teams, team_key, period_key, icav_min, subteam_key)
        if err:
            return {"error": err}
    if not ses_list:
        return {"ses": []}

    info = period_info(period_key)
    merge_gong_calls(ses_list, info["start"], info["end"])

    return {"ses": [{"name": s["name"], "gong_calls": s.get("gong_calls")} for s in ses_list]}


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_ses(ses):
    """
    Weighted composite score — each SE is percentile-ranked 0-100 per metric within
    the team, then scores are combined with the following weights:

      85%  Total iACV          primary revenue output — dominant signal
       8%  Quarter MRR %       avg % MRR growth across expansion accounts
       5%  Total ARR touched   breadth of account footprint
       2%  Notes hygiene       note_hv_covered / note_hv_total on high-value opps

    Percentile ranking (0 = team worst, 100 = team best) makes the weights fair even
    when the raw metrics are on very different scales (e.g. $M iACV vs % MRR change).
    Ties within a metric receive the same percentile score.
    """
    n = len(ses)
    if n == 0:
        return ses

    def _pct_rank(values: list) -> list:
        """Map values to percentile scores 0-100. Ties share the same score."""
        if n == 1:
            return [100.0]
        unique_sorted = sorted(set(values))
        u = len(unique_sorted)
        val_to_pct = {
            v: (rank / (u - 1) * 100 if u > 1 else 100.0)
            for rank, v in enumerate(unique_sorted)
        }
        return [val_to_pct[v] for v in values]

    icav_scores  = _pct_rank([se["total_icav"]                                       for se in ses])
    mrr_scores   = _pct_rank([se.get("exp_mrr_pct_avg", 0)                           for se in ses])
    arr_scores   = _pct_rank([se.get("exp_arr_total", 0)                             for se in ses])
    notes_scores = _pct_rank([se["note_hv_covered"] / max(se["note_hv_total"], 1)    for se in ses])

    # SEs with zero expansion/strategic wins have no ARR or MRR data — those metrics
    # don't apply to their motion. Give them a neutral 50 so they are neither penalised
    # (scored 0, as if worst on the team) nor rewarded relative to SEs who do expansion.
    for i, se in enumerate(ses):
        if se.get("exp_wins", 0) == 0:
            mrr_scores[i] = 50.0
            arr_scores[i] = 50.0

    for i, se in enumerate(ses):
        se["score_icav"]  = round(icav_scores[i],  1)
        se["score_mrr"]   = round(mrr_scores[i],   1)
        se["score_arr"]   = round(arr_scores[i],   1)
        se["score_notes"] = round(notes_scores[i], 1)
        se["composite_score"] = round(
            0.85 * icav_scores[i]  +
            0.08 * mrr_scores[i]   +
            0.05 * arr_scores[i]   +
            0.02 * notes_scores[i],
            1,
        )

    ranked = sorted(ses, key=lambda s: -s["composite_score"])
    for i, se in enumerate(ranked):
        se["rank_score"] = i + 1  # kept for tier() downstream
    return ranked


def tier(rank, total):
    pct = rank / total
    if pct <= 0.20: return "Elite"
    if pct <= 0.50: return "Strong"
    if pct <= 0.75: return "Steady"
    return "Develop"


# ---------------------------------------------------------------------------
# Flags (reused from se_analysis logic, email flags skipped when data is 0)
# ---------------------------------------------------------------------------

def collect_se_flags(se, ses, motion: str = "dsr") -> list:
    """Generate individual SE analysis items. Returns list of {cat, title, body}."""
    items = []

    act_cat, exp_cat, act_lbl, exp_lbl = _motion_labels(motion)

    has_act  = se["act_wins"] > 0
    has_exp  = se["exp_wins"] > 0
    act_only = has_act and not has_exp
    exp_only = has_exp and not has_act

    # Team context
    def _med(lst): return round(statistics.median(lst)) if lst else 0
    def _rel(val, med):
        if med == 0: return ""
        diff = round((val - med) / med * 100)
        if diff > 10:  return f"+{diff}% above team median"
        if diff < -10: return f"{diff}% below team median"
        return "at team median"

    act_ses_t             = [s for s in ses if s["act_wins"] > 0]
    exp_ses_t             = [s for s in ses if s["exp_wins"] > 0]
    notes_ses_t           = [s for s in ses if s["note_hv_total"] > 0]
    team_median_icav      = _med([s["total_icav"] for s in ses])
    team_max_icav         = max(s["total_icav"] for s in ses)
    team_median_act_icav  = _med([s["act_icav"]  for s in act_ses_t])
    team_median_act_wins  = _med([s["act_wins"]  for s in act_ses_t])
    team_act_median_deal  = _med([s["act_median"] for s in act_ses_t if s["act_median"] > 0])
    team_median_exp_icav  = _med([s["exp_icav"]  for s in exp_ses_t])
    team_median_exp_wins  = _med([s["exp_wins"]  for s in exp_ses_t])
    team_median_notes_pct = _med([round(s["note_hv_covered"] / s["note_hv_total"] * 100) for s in notes_ses_t])
    team_mrr_ses          = [s for s in ses if s.get("exp_mrr_delta_total", 0) > 0]
    team_mrr_med          = _med([s["exp_mrr_delta_total"] for s in team_mrr_ses])
    gong_ses_t            = [s for s in ses if s.get("gong_calls") is not None]
    team_gong_med         = _med([s["gong_calls"] for s in gong_ses_t]) if gong_ses_t else None

    # ── 1. Total iACV closed won ─────────────────────────────────────────────
    if se["total_icav"] > 0:
        icav_rel = _rel(se["total_icav"], team_median_icav)
        if se["total_icav"] == team_max_icav and len(ses) > 1:
            body = f"Top iACV on the team — {fmt(se['total_icav'])} vs team median {fmt(team_median_icav)}. {se['act_wins'] + se['exp_wins']} total wins."
            cat = "STRENGTH"
        elif se["total_icav"] >= team_median_icav * 1.3:
            body = f"{fmt(se['total_icav'])} closed this quarter — {icav_rel} ({fmt(team_median_icav)}). {se['act_wins'] + se['exp_wins']} wins."
            cat = "STRENGTH"
        elif se["total_icav"] < team_median_icav * 0.7:
            body = f"{fmt(se['total_icav'])} closed this quarter — {icav_rel} ({fmt(team_median_icav)}). {se['act_wins'] + se['exp_wins']} wins."
            cat = "RISK"
        else:
            body = f"{fmt(se['total_icav'])} closed this quarter, {icav_rel} ({fmt(team_median_icav)}). {se['act_wins'] + se['exp_wins']} wins."
            cat = "REVENUE"
        items.append({"cat": cat, "title": f"{fmt(se['total_icav'])} total iACV — {se['act_wins'] + se['exp_wins']} wins", "body": body})
    else:
        items.append({"cat": "RISK", "title": "No iACV closed this quarter", "body": f"No closed won TW opportunities recorded. Team median: {fmt(team_median_icav)}."})

    # ── 2. Revenue movement — MRR and expansion status ──────────────────────
    if not act_only:
        mrr_delta = se.get("exp_mrr_delta_total", 0)
        exp_status = se.get("exp_status", "")
        exp_team_ctx = f" Team {exp_lbl} median: {fmt(team_median_exp_icav)} ({team_median_exp_wins} wins)." if team_median_exp_icav else ""
        if se["exp_wins"] == 0:
            body = f"No {exp_lbl} wins this quarter.{exp_team_ctx}"
            cat = "RISK" if not act_only else exp_cat
        elif se["exp_growing"]:
            exp_rel = _rel(se["exp_icav"], team_median_exp_icav)
            pct_str = f" (+{se.get('exp_mrr_pct_avg', 0)}% vs prior qtr)" if se.get("exp_mrr_pct_avg", 0) > 0 else ""
            mrr_str = f" MRR uplift: +{fmt(mrr_delta)}/mo{pct_str}." if mrr_delta > 0 else ""
            if team_mrr_med and mrr_delta >= team_mrr_med * 1.25:
                cat = "STRENGTH"
                body = f"Accounts genuinely expanding — {fmt(se['exp_median'])} median deal, {fmt(se['exp_icav'])} total ({exp_rel}).{mrr_str} Team MRR median: +{fmt(team_mrr_med)}/mo."
            else:
                cat = "STRENGTH"
                body = f"Positive {exp_lbl} trajectory — {fmt(se['exp_icav'])} total, {fmt(se['exp_median'])} median ({exp_rel}).{mrr_str}{exp_team_ctx}"
        elif se["exp_wins"] >= 10:
            cat = exp_cat
            body = f"High {exp_lbl} load — {se['exp_wins']} wins at $0 median. Retaining accounts, not expanding.{exp_team_ctx}"
        else:
            cat = exp_cat
            body = f"Retaining — $0 median on {se['exp_wins']} {exp_lbl} wins. No MRR uplift this quarter.{exp_team_ctx}"
        items.append({"cat": cat, "title": f"{exp_lbl}: {se['exp_wins']} wins, {fmt(se['exp_icav'])} iACV", "body": body})

    # ── 3. New business deal quality ─────────────────────────────────────────
    if not exp_only:
        if se["act_wins"] == 0:
            items.append({"cat": "RISK", "title": f"No {act_lbl} wins this quarter", "body": f"Team median: {team_median_act_wins} wins, {fmt(team_median_act_icav)} iACV."})
        else:
            act_rel = _rel(se["act_icav"], team_median_act_icav)
            body = f"{se['act_wins']} wins, {fmt(se['act_icav'])} iACV — {act_rel} ({fmt(team_median_act_icav)}). "
            if se["act_wins"] >= 4 and se["act_median"] > 0:
                ratio = se["act_avg"] / se["act_median"]
                if ratio >= 2.5:
                    body += f"Whale-dependent: {fmt(se['act_avg'])} avg vs {fmt(se['act_median'])} median — one big deal driving the number."
                    cat = "RISK"
                elif ratio < 1.2 and se["act_wins"] >= 5 and se["act_median"] >= ACT_AVG_SIZE_WARNING:
                    body += f"Consistent deal sizing — {fmt(se['act_median'])} median across {se['act_wins']} wins (team deal median {fmt(team_act_median_deal)})."
                    cat = "STRENGTH"
                else:
                    body += f"Deal median: {fmt(se['act_median'])} (team {fmt(team_act_median_deal)})."
                    cat = act_cat
            elif se["act_wins"] >= 5 and se.get("act_median", 0) < ACT_AVG_SIZE_WARNING:
                body += f"High volume but median {fmt(se['act_median'])} is below the ${ACT_AVG_SIZE_WARNING//1000}K floor (team median {fmt(team_act_median_deal)})."
                cat = "RISK"
            else:
                body += f"Deal median: {fmt(se.get('act_median', 0))} (team {fmt(team_act_median_deal)})."
                cat = act_cat
            items.append({"cat": cat, "title": f"{act_lbl}: {se['act_wins']} wins, {fmt(se['act_icav'])} iACV", "body": body.strip()})

    # ── 4. Largest deal ──────────────────────────────────────────────────────
    if se.get("largest_deal_value", 0) > 0:
        pct = round(se["largest_deal_value"] / se["total_icav"] * 100) if se["total_icav"] else 0
        acct_str = f" ({se['largest_deal_acct']})" if se.get("largest_deal_acct") else ""
        dsr_str  = f" — AE/DSR: {se['largest_deal_dsr']}" if se.get("largest_deal_dsr") else ""
        if pct >= int(DEAL_CONCENTRATION_THRESHOLD * 100):
            cat = "RISK"
            body = f"{fmt(se['largest_deal_value'])}{acct_str}{dsr_str}. This deal represents {pct}% of your total iACV — concentrated quarter."
        elif pct < 20 and se["total_icav"] > 500_000:
            cat = "STRENGTH"
            body = f"{fmt(se['largest_deal_value'])}{acct_str}{dsr_str}. Only {pct}% of total iACV — revenue well distributed across deals."
        else:
            cat = "REVENUE"
            body = f"{fmt(se['largest_deal_value'])}{acct_str}{dsr_str}. {pct}% of total iACV this quarter."
        items.append({"cat": cat, "title": f"Largest deal: {fmt(se['largest_deal_value'])}", "body": body})

    # ── 5. SE notes ──────────────────────────────────────────────────────────
    if se["note_hv_total"] > 0:
        cov_pct   = round(se["note_hv_covered"] / se["note_hv_total"] * 100)
        notes_rel = _rel(cov_pct, team_median_notes_pct)
        missing   = se["note_hv_total"] - se["note_hv_covered"]
        if cov_pct == 100 and se.get("note_hv_avg_entries", 0) >= 5:
            cat  = "STRENGTH"
            body = f"All {se['note_hv_total']} high-value opps documented — {se['note_hv_avg_entries']} avg history entries. Team median coverage: {team_median_notes_pct}%."
        elif cov_pct <= 50:
            cat  = "RISK"
            body = f"{se['note_hv_covered']}/{se['note_hv_total']} high-value opps have notes ({cov_pct}%) — {missing} deal{'s' if missing>1 else ''} missing. Team median: {team_median_notes_pct}%. Undocumented wins lose attribution value."
        else:
            cat  = "HYGIENE"
            body = f"{se['note_hv_covered']}/{se['note_hv_total']} high-value opps documented ({cov_pct}%) — {notes_rel} (team median {team_median_notes_pct}%). {se.get('note_hv_avg_entries', 0)} avg entries per noted opp."
        items.append({"cat": cat, "title": f"SE notes: {cov_pct}% of high-value opps covered", "body": body})

    # ── 6. Gong calls ────────────────────────────────────────────────────────
    if se.get("gong_calls") is not None and team_gong_med is not None:
        calls     = se["gong_calls"]
        gong_rel  = _rel(calls, team_gong_med)
        if calls == 0:
            cat  = "RISK"
            body = f"No Gong calls recorded this quarter. Team median: {team_gong_med} calls. May indicate low call engagement or a recording gap."
        elif calls >= team_gong_med * 1.5:
            cat  = "STRENGTH"
            body = f"{calls} Gong calls this quarter — {gong_rel} (team median {team_gong_med}). High call volume signals strong deal engagement."
        else:
            cat  = "PIPELINE"
            body = f"{calls} Gong calls this quarter — {gong_rel} (team median {team_gong_med})."
        items.append({"cat": cat, "title": f"Gong calls: {calls}", "body": body})

    # ── 7. AE/DSR engagement breadth ────────────────────────────────────────
    opps = se.get("tw_opps_detail", [])
    unique_partners = len({o["owner"] for o in opps if o.get("owner")})
    if unique_partners > 0:
        breadth_vals = [len({o["owner"] for o in s.get("tw_opps_detail", []) if o.get("owner")}) for s in ses if s["total_icav"] > 0]
        team_med_breadth = _med(breadth_vals)
        breadth_rel = _rel(unique_partners, team_med_breadth)
        partner_names = sorted({o["owner"] for o in opps if o.get("owner")})
        names_str = ", ".join(partner_names[:4]) + ("..." if len(partner_names) > 4 else "")
        if unique_partners == 1:
            cat  = "RISK"
            body = f"All wins came through one AE/DSR partner ({names_str}). Single-partner quarters are exposed if that rep changes territory. Team median: {team_med_breadth} partners."
        elif unique_partners >= max(3, team_med_breadth * 2):
            cat  = "STRENGTH"
            body = f"Partnered with {unique_partners} AEs/DSRs ({names_str}) — {breadth_rel} (team median {team_med_breadth}). Broad coverage amplifies org capacity."
        else:
            cat  = "PIPELINE"
            body = f"Worked with {unique_partners} AE/DSR partner{'s' if unique_partners>1 else ''} ({names_str}) — {breadth_rel} (team median {team_med_breadth})."
        items.append({"cat": cat, "title": f"AE/DSR engagement: {unique_partners} partner{'s' if unique_partners!=1 else ''}", "body": body})

    return items


def compute_team_medians(ses: list) -> dict:
    """Team-level medians for display in SE profile stat boxes."""
    act_ses   = [s for s in ses if s["act_wins"] > 0]
    exp_ses   = [s for s in ses if s["exp_wins"] > 0]
    notes_ses = [s for s in ses if s["note_hv_total"] > 0]

    def med(lst):
        return round(statistics.median(lst)) if lst else 0

    arr_ses = [s for s in ses if s.get("exp_arr_total", 0) > 0]
    mrr_ses = [s for s in ses if s.get("exp_mrr_delta_total", 0) != 0]
    pct_ses = [s for s in ses if s.get("exp_mrr_pct_avg", 0) != 0]

    return {
        "total_icav":        med([s["total_icav"] for s in ses]),
        "act_wins":          med([s["act_wins"]   for s in act_ses]),
        "act_icav":          med([s["act_icav"]   for s in act_ses]),
        "act_median":        med([s["act_median"] for s in act_ses if s["act_median"] > 0]),
        "exp_wins":          med([s["exp_wins"]   for s in exp_ses]),
        "exp_icav":          med([s["exp_icav"]   for s in exp_ses]),
        "exp_median":        med([s["exp_median"] for s in exp_ses if s["exp_median"] > 0]),
        "exp_arr_total":       med([s["exp_arr_total"]       for s in arr_ses]),
        "exp_mrr_delta_total": med([s["exp_mrr_delta_total"] for s in mrr_ses]),
        "exp_mrr_pct_avg":     round(statistics.median([s["exp_mrr_pct_avg"] for s in pct_ses])) if pct_ses else 0,
        "notes_pct":         round(statistics.median(
            [s["note_hv_covered"] / s["note_hv_total"] * 100 for s in notes_ses]
        )) if notes_ses else 0,
    }


def generate_analysis(ses: list, motion: str = "dsr", ps_assists: list | None = None) -> list:
    """
    Returns list of {"cat": str, "title": str, "body": str} items describing
    team-level indicators of success and challenges. Covers: total iACV closed won,
    revenue movement and MRR, SE notes, Gong calls, total revenue touched (PS assists),
    largest deals, and AE/DSR engagement.
    """
    items = []
    n = len(ses)
    if n == 0:
        return items

    _, _, act_lbl, exp_lbl = _motion_labels(motion)
    act_cat, exp_cat, _, _ = _motion_labels(motion)

    all_opps        = [o for s in ses for o in s.get("tw_opps_detail", [])]
    team_total_icav = sum(s["total_icav"] for s in ses)
    team_act_wins   = sum(s["act_wins"]   for s in ses)
    team_exp_wins   = sum(s["exp_wins"]   for s in ses)

    def _med(lst):
        return round(statistics.median(lst)) if lst else 0

    # ── 1. Total iACV closed won ──────────────────────────────────────────────
    sorted_by_icav = sorted(ses, key=lambda s: s["total_icav"], reverse=True)
    top2_icav  = sum(s["total_icav"] for s in sorted_by_icav[:2])
    top2_pct   = round(top2_icav / team_total_icav * 100) if team_total_icav else 0
    icav_medians = [s["total_icav"] for s in ses]
    team_median_icav = _med(icav_medians)
    top_se = sorted_by_icav[0] if sorted_by_icav else None
    if top_se and n > 1:
        top_pct = round(top_se["total_icav"] / team_total_icav * 100) if team_total_icav else 0
        concentration_note = f" Top 2 SEs hold {top2_pct}% of team iACV — {'fragile if top performers slip' if top2_pct > 50 else 'reasonable distribution'}." if n >= 2 else ""
        items.append({
            "cat":   "REVENUE",
            "title": f"Team closed {fmt(team_total_icav)} iACV — {team_act_wins + team_exp_wins} wins across {n} SEs",
            "body":  (
                f"{top_se['name']} leads at {fmt(top_se['total_icav'])} ({top_pct}% of team total). "
                f"Team median: {fmt(team_median_icav)}."
                f"{concentration_note}"
            ),
        })

    # ── 2. Revenue movement — MRR delta and expansion status ─────────────────
    exp_ses_with_arr = [s for s in ses if s.get("exp_arr_total", 0) > 0]
    growing   = [s for s in ses if s.get("exp_growing")]
    retaining = [s for s in ses if not s.get("exp_growing") and s["exp_wins"] > 0]
    contracting = [s for s in exp_ses_with_arr if s.get("exp_status") == "Contracting"]
    flat_big_arr = [s for s in exp_ses_with_arr
                    if s.get("exp_status") in ("Retaining", "Expanding")
                    and s.get("exp_arr_total", 0) > 200_000]
    mrr_ses = [s for s in ses if s.get("exp_mrr_delta_total", 0) > 0]
    team_mrr_delta = sum(s.get("exp_mrr_delta_total", 0) for s in mrr_ses)
    if exp_ses_with_arr or growing or retaining:
        body = (
            f"{len(growing)} of {n} SEs driving positive {exp_lbl} MRR — accounts genuinely upselling. "
            f"{len(retaining)} retaining at $0 median. "
        )
        if team_mrr_delta > 0:
            body += f"Total team MRR uplift: +{fmt(team_mrr_delta)}/mo across expansion accounts. "
        if contracting:
            contr_arr = sum(s.get("exp_arr_total", 0) for s in contracting)
            body += f"{len(contracting)} SE{'s' if len(contracting)>1 else ''} touching contracting accounts ({fmt(contr_arr)} ARR at risk). "
        if flat_big_arr:
            total_flat = sum(s.get("exp_arr_total", 0) for s in flat_big_arr)
            body += f"{fmt(total_flat)} ARR sitting flat across {len(flat_big_arr)} SE{'s' if len(flat_big_arr)>1 else ''} — upsell opportunity."
        items.append({"cat": "EXPANSION", "title": f"{exp_lbl} revenue movement: {len(growing)} growing, {len(retaining)} retaining", "body": body.strip()})

    # ── 3. New business deal quality ──────────────────────────────────────────
    act_ses = [se for se in ses if se["act_wins"] >= 2 and se["act_icav"] > 0]
    if act_ses:
        act_medians     = [se["act_median"] for se in act_ses if se["act_median"] > 0]
        team_act_median = _med(act_medians)
        low_floor  = [se for se in act_ses if se["act_wins"] >= 3 and se["act_median"] < ACT_AVG_SIZE_WARNING]
        whale_dep  = [se for se in act_ses if se["act_wins"] >= 4 and se["act_median"] > 0
                      and se["act_avg"] / se["act_median"] >= 2.5]
        body = f"Team {act_lbl} median: {fmt(team_act_median)}. {team_act_wins} wins across {len(act_ses)} SEs. "
        if team_act_median < ACT_AVG_SIZE_WARNING:
            uplift = round((ACT_AVG_SIZE_WARNING - team_act_median) * team_act_wins)
            body += f"Median below ${ACT_AVG_SIZE_WARNING//1000}K floor — shifting it would add ~{fmt(uplift)} iACV at same win count. "
        if low_floor:
            body += f"{len(low_floor)} SE{'s' if len(low_floor)>1 else ''} closing high volume under ${ACT_AVG_SIZE_WARNING//1000}K. "
        if whale_dep:
            body += f"{len(whale_dep)} SE{'s' if len(whale_dep)>1 else ''} whale-dependent (avg/median ≥2.5×) — quarters fragile without a big deal."
        items.append({"cat": act_cat, "title": f"{act_lbl} deal quality: {fmt(team_act_median)} team median", "body": body.strip()})

    # ── 3. SE notes on high-value opps ───────────────────────────────────────
    hv_ses = [se for se in ses if se.get("note_hv_total", 0) > 0]
    if hv_ses:
        team_hv_covered = sum(se["note_hv_covered"] for se in hv_ses)
        team_hv_total   = sum(se["note_hv_total"]   for se in hv_ses)
        notes_pct       = round(team_hv_covered / team_hv_total * 100) if team_hv_total else 0
        no_notes        = [se for se in hv_ses if se["note_hv_covered"] == 0]
        avg_entries_all = _med([se["note_hv_avg_entries"] for se in hv_ses if se.get("note_hv_avg_entries", 0) > 0])
        body = f"{team_hv_covered}/{team_hv_total} high-value opps documented ({notes_pct}% coverage). "
        if no_notes:
            body += f"{len(no_notes)} SE{'s' if len(no_notes)>1 else ''} with zero notes on high-value deals. "
        if avg_entries_all:
            body += f"Team median {avg_entries_all} history entries per noted opp. "
        if notes_pct >= 90:
            body += "Strong documentation discipline across the team."
        elif notes_pct < 60:
            body += "Below 60% — undocumented wins lose attribution value and are harder to replicate."
        items.append({
            "cat":   "HYGIENE",
            "title": f"SE notes: {notes_pct}% of high-value opps documented",
            "body":  body.strip(),
        })

    # ── 4. Gong calls ────────────────────────────────────────────────────────
    gong_ses = [se for se in ses if se.get("gong_calls") is not None]
    if gong_ses:
        total_calls  = sum(se["gong_calls"] for se in gong_ses)
        med_calls    = _med([se["gong_calls"] for se in gong_ses])
        zero_calls   = [se for se in gong_ses if se["gong_calls"] == 0]
        top_caller   = max(gong_ses, key=lambda s: s["gong_calls"])
        body = f"{total_calls} Gong calls logged across {len(gong_ses)} SEs. Median: {med_calls} calls. "
        if zero_calls:
            body += f"{len(zero_calls)} SE{'s' if len(zero_calls)>1 else ''} with no recorded Gong calls — low call engagement or recording gap. "
        body += f"Top caller: {top_caller['name']} ({top_caller['gong_calls']} calls)."
        items.append({
            "cat":   "PIPELINE",
            "title": f"Gong activity: {total_calls} calls, {med_calls} median per SE",
            "body":  body.strip(),
        })

    # ── 5. Total revenue touched — PS assists ────────────────────────────────
    ps = ps_assists or []
    if ps:
        total_ps_icav = sum(p["total_icav"] for p in ps)
        total_ps_deals = sum(p["deals"] for p in ps)
        top_ps = sorted(ps, key=lambda p: p["total_icav"], reverse=True)
        body = (
            f"{len(ps)} product specialist{'s' if len(ps)>1 else ''} assisted on "
            f"{total_ps_deals} deal{'s' if total_ps_deals!=1 else ''}, "
            f"touching {fmt(total_ps_icav)} iACV. "
        )
        if top_ps:
            tp = top_ps[0]
            body += f"Top assist: {tp['name']} ({tp['deals']} deals, {fmt(tp['total_icav'])}). "
        se_names_covered = {name for p in ps for name in p.get("se_names", [])}
        if se_names_covered:
            body += f"SE coverage: {', '.join(sorted(se_names_covered)[:4])}{'...' if len(se_names_covered) > 4 else ''}."
        items.append({
            "cat":   "EFFICIENCY",
            "title": f"PS assists: {fmt(total_ps_icav)} revenue touched across {total_ps_deals} deals",
            "body":  body.strip(),
        })

    # ── 6. Largest deals ─────────────────────────────────────────────────────
    deals_with_largest = [se for se in ses if se.get("largest_deal_value", 0) > 0]
    if deals_with_largest:
        biggest = max(deals_with_largest, key=lambda s: s["largest_deal_value"])
        top3_deals = sorted(deals_with_largest, key=lambda s: s["largest_deal_value"], reverse=True)[:3]
        top3_str = ", ".join(
            f"{s['name']} {fmt(s['largest_deal_value'])}" + (f" ({s['largest_deal_acct']})" if s.get("largest_deal_acct") else "")
            for s in top3_deals
        )
        concentration = round(biggest["largest_deal_value"] / biggest["total_icav"] * 100) if biggest["total_icav"] else 0
        body = f"Largest deals this quarter: {top3_str}. "
        if concentration >= int(DEAL_CONCENTRATION_THRESHOLD * 100):
            body += f"{biggest['name']}'s top deal is {concentration}% of their total iACV — concentrated quarter."
        else:
            body += f"{biggest['name']}'s top deal is {concentration}% of their total — revenue well distributed."
        items.append({
            "cat":   "REVENUE",
            "title": f"Largest deal: {fmt(biggest['largest_deal_value'])} by {biggest['name']}",
            "body":  body.strip(),
        })

    # ── 7. AE/DSR engagement ─────────────────────────────────────────────────
    se_breadth = [
        (s["name"], len({o["owner"] for o in s.get("tw_opps_detail", []) if o.get("owner")}), s["total_icav"])
        for s in ses
    ]
    breadth_vals = [cnt for _, cnt, icav in se_breadth if cnt > 0 and icav > 0]
    if breadth_vals:
        med_breadth  = _med(breadth_vals)
        narrow       = [(name, cnt) for name, cnt, icav in se_breadth if cnt == 1 and icav > 0]
        wide         = [(name, cnt) for name, cnt, icav in se_breadth if cnt >= max(3, med_breadth * 2) and icav > 0]
        total_unique = len({o.get("owner") for s in ses for o in s.get("tw_opps_detail", []) if o.get("owner")})
        body = f"SEs engaged {total_unique} unique AE/DSR partner{'s' if total_unique!=1 else ''} this quarter. Median breadth: {med_breadth} per SE. "
        if narrow:
            body += f"{len(narrow)} SE{'s' if len(narrow)>1 else ''} ({', '.join(n for n,_ in narrow[:3])}) worked a single partner — single-rep dependency risk. "
        if wide:
            body += f"{len(wide)} SE{'s' if len(wide)>1 else ''} ({', '.join(n for n,_ in wide[:3])}) covered {med_breadth*2}+ partners — high org leverage."
        items.append({
            "cat":   "PIPELINE",
            "title": f"AE/DSR engagement: {total_unique} partners, {med_breadth} median per SE",
            "body":  body.strip(),
        })

    return items


# ---------------------------------------------------------------------------
# AE/DSR engagement leaderboard
# ---------------------------------------------------------------------------

def compute_ae_engagement(ses: list, all_owner_opps: list | None = None) -> list:
    """Aggregate AE/DSR engagement from TW opps across all SEs.
    all_owner_opps includes every Closed Won opp for the team (regardless of SE tagging)
    so AEs/DSRs with zero SE-tagged deals still appear in the table."""
    ae_data: dict[str, dict] = {}

    # First pass: AEs/DSRs who appear on TW opps (have SE engagement)
    for se in ses:
        se_name = se["name"]
        for opp in se.get("tw_opps_detail", []):
            owner = (opp.get("owner") or "").strip()
            if not owner:
                continue
            if owner not in ae_data:
                ae_data[owner] = {"name": owner, "deals": 0, "total_icav": 0, "ses": {}}
            ae_data[owner]["deals"] += 1
            ae_data[owner]["total_icav"] += opp.get("icav", 0) or 0
            ae_data[owner]["ses"][se_name] = ae_data[owner]["ses"].get(se_name, 0) + 1

    # Second pass: all owners from team opps — add zeros for those not already present
    for opp in (all_owner_opps or []):
        owner_rec = opp.get("Owner") or {}
        owner = (owner_rec.get("Name") or "").strip()
        if not owner or owner in ae_data:
            continue
        ae_data[owner] = {"name": owner, "deals": 0, "total_icav": 0, "ses": {}}

    result = []
    for d in ae_data.values():
        ses_sorted = sorted(d["ses"].items(), key=lambda x: x[1], reverse=True)
        result.append({
            "name":       d["name"],
            "deals":      d["deals"],
            "total_icav": d["total_icav"],
            "avg_icav":   round(d["total_icav"] / d["deals"]) if d["deals"] else 0,
            "se_count":   len(d["ses"]),
            "se_names":   [name for name, _ in ses_sorted[:3]],
        })

    return sorted(result, key=lambda x: (x["deals"], x["total_icav"]), reverse=True)


# ---------------------------------------------------------------------------
# Save se_data.json
# ---------------------------------------------------------------------------


def save_data(ranked, output_dir):
    total   = len(ranked)
    payload = []
    for i, se in enumerate(ranked, 1):
        entry          = {k: v for k, v in se.items() if not k.startswith("_")}
        entry["rank"]  = i
        entry["tier"]  = tier(i, total)
        entry["flags"] = collect_se_flags(se, ranked)
        entry["roast"] = _roast(se, ranked)
        payload.append(entry)
    json_path = Path(output_dir) / "sf_se_data.json"
    tmp_path  = json_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    tmp_path.replace(json_path)


def _roast(se, ranked, motion: str = "dsr"):
    n    = len(ranked)
    rank = next(i for i, s in enumerate(ranked, 1) if s["name"] == se["name"])
    t    = tier(rank, n)

    # ── Team-wide context ────────────────────────────────────────────────────
    total_icavs   = [s["total_icav"] for s in ranked]
    team_icav     = sum(total_icavs)
    median_icav   = round(statistics.median(total_icavs))

    act_ses       = [s for s in ranked if s["act_wins"] > 0]
    max_act_wins  = max(s["act_wins"] for s in ranked) if ranked else 0
    min_act_wins  = min(s["act_wins"] for s in act_ses) if act_ses else 0

    max_exp_wins  = max(s["exp_wins"] for s in ranked) if ranked else 0
    max_exp_icav  = max(s["exp_icav"] for s in ranked) if ranked else 0
    max_act_icav  = max(s["act_icav"] for s in ranked) if ranked else 0

    pipe_totals   = [s.get("email_act_outq", 0) + s.get("email_exp_outq", 0) for s in ranked]
    max_pipe      = max(pipe_totals) if pipe_totals else 0
    se_pipe       = se.get("email_act_outq", 0) + se.get("email_exp_outq", 0)

    se_arr        = se.get("exp_arr_total", 0)
    se_mrr        = se.get("exp_mrr_delta_total", 0)
    se_mrr_pct    = se.get("exp_mrr_pct_avg", 0)
    max_arr       = max((s.get("exp_arr_total", 0) for s in ranked), default=0)
    max_mrr       = max((s.get("exp_mrr_delta_total", 0) for s in ranked), default=0)

    notes_pcts    = [round(s["note_hv_covered"] / s["note_hv_total"] * 100)
                     for s in ranked if s["note_hv_total"] > 0]
    max_notes_pct = max(notes_pcts) if notes_pcts else 0
    se_notes_pct  = round(se["note_hv_covered"] / se["note_hv_total"] * 100) if se["note_hv_total"] > 0 else 0

    total_wins    = se["act_wins"] + se["exp_wins"]
    act_lbl       = "new business" if motion == "ae" else "activate"
    exp_lbl       = "strategic"    if motion == "ae" else "expansion"

    # ── TW Closed Won opp context ─────────────────────────────────────────────
    def _acct(name: str) -> str:
        a = (name.split(" - ")[0] or name).strip()
        return a if len(a) <= 22 else a[:20] + "…"

    tw_opps     = se.get("tw_opps_detail", [])
    act_opps_tw = sorted([o for o in tw_opps if o.get("motion") in ("act", "nb")],
                         key=lambda x: x.get("icav", 0), reverse=True)
    exp_opps_tw = sorted([o for o in tw_opps if o.get("motion") in ("exp", "strat")],
                         key=lambda x: x.get("icav", 0), reverse=True)
    top_act_acct = _acct(act_opps_tw[0]["name"]) if act_opps_tw else None
    top_exp_acct = _acct(exp_opps_tw[0]["name"]) if exp_opps_tw else None
    top_acct     = top_act_acct or top_exp_acct

    exp_accts    = sorted(se.get("exp_account_detail", []),
                          key=lambda a: a.get("arr", 0), reverse=True)
    top_arr_acct = _acct(exp_accts[0]["opp_name"]) if exp_accts else top_exp_acct

    # ── Unique-stat checks (priority order) ──────────────────────────────────

    # Rank 1
    if rank == 1 and n > 1:
        pct = round(se["total_icav"] / team_icav * 100) if team_icav else 0
        gap = fmt(se["total_icav"] - ranked[1]["total_icav"])
        deal_str = f" {top_acct} was the headline." if top_acct else ""
        if pct >= 30:
            return f"Carrying {pct}% of the team's quarter — {fmt(se['total_icav'])} total.{deal_str} 🐐"
        return f"Led the board by {gap} over #2 with {fmt(se['total_icav'])} total.{deal_str} 🏆"

    # Dead last
    if rank == n and n > 1:
        icav_str = f" {fmt(se['total_icav'])} on the board." if se["total_icav"] > 0 else ""
        return f"Last place this quarter.{icav_str} Not the final chapter. 📈"

    # Volume leader — dominating win count
    if se["act_wins"] == max_act_wins and max_act_wins >= 5:
        others = sum(s["act_wins"] for s in ranked) - se["act_wins"]
        acct_str = f" {top_act_acct} was just one of them." if top_act_acct else ""
        return f"{se['act_wins']} wins while the other {n-1} combined for {others}.{acct_str} Not the same sport. 🏭"

    # Rank 2
    if rank == 2:
        gap = fmt(ranked[0]["total_icav"] - se["total_icav"])
        acct_str = f" {top_acct} pushed the number." if top_acct else ""
        return f"Only {gap} behind #1.{acct_str} Hunting. 🔥"

    # Rank 3
    if rank == 3:
        acct_str = f" {top_acct} put them there." if top_acct else ""
        return f"Top 3 with {fmt(se['total_icav'])}.{acct_str} The podium suits them. 🔥"

    # AE motion: ARR + MRR leadership
    if motion == "ae":
        if se_arr > 0 and se_arr == max_arr:
            arr_accts = ", ".join(_acct(a["opp_name"]) for a in exp_accts[:2]) if exp_accts else ""
            if se_mrr > 0:
                pct_str  = f" +{se_mrr_pct}% vs prior" if se_mrr_pct > 0 else ""
                acct_str = f" ({arr_accts})" if arr_accts else ""
                return f"Carries {fmt(se_arr)} in account ARR{acct_str} and grew it {fmt(se_mrr)}/mo{pct_str}. That's a growing book. 📊"
            acct_str = f" — {arr_accts} anchor the book" if arr_accts else ""
            return f"Tops the team with {fmt(se_arr)} in account ARR{acct_str}. The accounts trust the name. 🏦"
        if se_mrr > 0 and se_mrr == max_mrr:
            pct_str  = f" (+{se_mrr_pct}% vs prior)" if se_mrr_pct > 0 else ""
            acct_str = f" {top_arr_acct} led the charge." if top_arr_acct else ""
            return f"Top MRR growth this quarter — {fmt(se_mrr)}/mo in new recurring revenue{pct_str}.{acct_str} The install base is compounding. 📈"

    # DSR: Expansion king by wins
    if motion != "ae" and se["exp_wins"] == max_exp_wins and max_exp_wins >= 15 and se["exp_wins"] > se["act_wins"]:
        acct_str = f" {top_exp_acct} was just one account." if top_exp_acct else ""
        return f"{se['exp_wins']} expansion wins.{acct_str} Doesn't chase new logos — grows every one they touch. ♟️"

    # Expansion / Strategic king by iACV
    if se["exp_icav"] == max_exp_icav and max_exp_icav > 0 and se["exp_wins"] >= (3 if motion == "ae" else 5):
        if motion == "ae" and se_arr > 0:
            acct_str = f" {top_arr_acct} was the big one." if top_arr_acct else ""
            return f"Led {exp_lbl} iACV at {fmt(se['exp_icav'])} with {fmt(se_arr)} in account ARR.{acct_str} The accounts are committing. 🔒"
        acct_str = f" {top_exp_acct} anchored it." if top_exp_acct else ""
        return f"Owns the install base — {fmt(se['exp_icav'])} in {exp_lbl} iACV.{acct_str} The accounts trust them. 🔒"

    # Highest act / new-business iACV
    if se["act_icav"] == max_act_icav and max_act_icav > 0 and se["act_icav"] > median_icav:
        acct_str = f" {top_act_acct} was the biggest." if top_act_acct else ""
        return f"Top {act_lbl} producer — {fmt(se['act_icav'])} in new revenue.{acct_str} Closes the deals that move the number. 💥"

    # Heavily concentrated quarter
    if se["conc"] >= 70:
        deal_acct = _acct(se["largest_deal"]) if se.get("largest_deal") else None
        deal_str  = f"{deal_acct}: " if deal_acct else ""
        return f"{deal_str}{fmt(se['largest_deal_value'])} — one deal changed the quarter. Everything else was secondary. 🎲"

    # Moderate concentration with big deal
    if se["conc"] >= 50 and se["largest_deal_value"] >= 200_000:
        deal_acct = _acct(se["largest_deal"]) if se.get("largest_deal") else None
        deal_str  = f"{deal_acct} alone was " if deal_acct else ""
        return f"{deal_str}{fmt(se['largest_deal_value'])}. Bet big and won. That's how quarters like this get built. 🎯"

    # Whale-dependent
    if se["act_wins"] >= 4 and se["act_median"] > 0 and se["act_avg"] / se["act_median"] >= 2.5:
        acct_str = f" {top_act_acct} was the whale." if top_act_acct else ""
        return f"{se['act_wins']} wins but one deal did the heavy lifting.{acct_str} Skilled or lucky — the board doesn't care. 🐋"

    # Consistent closer
    if se["act_wins"] >= 5 and se["act_median"] > 0 and se["act_avg"] / se["act_median"] < 1.15 and se["act_median"] >= 40_000:
        range_str = (f" {top_act_acct} to {_acct(act_opps_tw[-1]['name'])} — all in range."
                     if len(act_opps_tw) >= 2 else "")
        return f"No spikes, no dry spells — {se['act_wins']} wins at {fmt(se['act_median'])} median.{range_str} The model of consistency. 📐"

    # Top pipeline builder
    if se_pipe == max_pipe and max_pipe >= 10 and n > 1:
        return f"{se_pipe} pipeline opps while closing {total_wins} this quarter. Already building the next one. 📬"

    # Perfect notes discipline
    if se_notes_pct == 100 and se["note_hv_total"] >= 5 and se_notes_pct == max_notes_pct:
        return f"Every deal documented — {se['note_hv_total']} opps covered, zero gaps. Cleanest record on the team. 📋"

    # High win rate
    if se.get("win_rate", 0) >= 75 and (se.get("closed_won", 0) + se.get("closed_lost", 0)) >= 6:
        won  = se.get("closed_won", 0)
        lost = se.get("closed_lost", 0)
        return f"{se['win_rate']}% win rate ({won}W / {lost}L). Doesn't chase deals they can't close. 🎯"

    # High volume, modest iACV
    if total_wins >= 12 and se["total_icav"] < median_icav:
        return f"{total_wins} wins, {fmt(se['total_icav'])} total — needs bigger deals to match the effort. ⚙️"

    # Fewest wins
    if se["act_wins"] == min_act_wins and min_act_wins > 0 and se["act_wins"] <= 2 and n > 3:
        icav_str = f" {fmt(se['total_icav'])} from {total_wins} win{'s' if total_wins != 1 else ''}."
        return f"Fewest {act_lbl} wins on the team.{icav_str} The work is there — the board isn't catching up yet. 🕰️"

    # AE motion: MRR movement (mid-table)
    if motion == "ae" and se_mrr < 0 and se_arr > 0:
        acct_str = f" — {top_arr_acct} is a watch item." if top_arr_acct else ""
        return f"Install base showing {fmt(abs(se_mrr))}/mo in MRR contraction{acct_str}. {fmt(se_arr)} in ARR needs attention. ⚠️"
    if motion == "ae" and se_mrr > 0 and se_mrr_pct >= 10:
        acct_str = f" {top_arr_acct} is the standout." if top_arr_acct else ""
        return f"Accounts growing {se_mrr_pct}% QoQ in MRR — {fmt(se_mrr)}/mo added.{acct_str} That's what strategic development looks like. 📈"
    if motion == "ae" and se_arr > 0 and se["exp_wins"] >= 2:
        acct_str = f" {top_exp_acct} was the marquee." if top_exp_acct else ""
        return f"{se['exp_wins']} strategic wins, {fmt(se_arr)} in ARR.{acct_str} Solid footing. 🏛️"

    # Well above median
    if se["total_icav"] >= median_icav * 1.5:
        gap = fmt(se["total_icav"] - median_icav)
        return f"{fmt(se['total_icav'])} total — {gap} above team median. Pulls the average up just by being on it. 📊"

    # Right at median
    if abs(se["total_icav"] - median_icav) / max(median_icav, 1) <= 0.20:
        acct_str = f" {top_acct} was the anchor." if top_acct else ""
        return f"{fmt(se['total_icav'])} — right at team median.{acct_str} Solid, consistent, dependable. 🧱"

    # Below median, upper half
    if se["total_icav"] < median_icav and rank <= n // 2:
        gap = fmt(median_icav - se["total_icav"])
        return f"{fmt(se['total_icav'])} total — {gap} off the median but in the top half. Trending the right direction. 💪"

    # Below median, lower half
    if se["total_icav"] < median_icav:
        gap      = fmt(median_icav - se["total_icav"])
        wins_str = f"{total_wins} win{'s' if total_wins != 1 else ''}"
        return f"{wins_str}, {fmt(se['total_icav'])} — {gap} off the team median. That gap is closable. 💪"

    # Tier-based fallback
    wins_str = f"{total_wins} win{'s' if total_wins != 1 else ''}"
    icav_str = fmt(se["total_icav"])
    return {"Elite":   f"Elite tier — {wins_str}, {icav_str}. Still finding ways to push higher. 👑",
            "Strong":  f"{wins_str}, {icav_str}. Strong quarter, no shortcuts taken. 🔥",
            "Steady":  f"{wins_str}, {icav_str}. Solid quarter, backbone of the team. 🧱",
            "Develop": f"{wins_str}, {icav_str} this quarter. The comeback starts here. 🙏"}.get(t, f"{wins_str}, {icav_str} this quarter. 📋")



log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

_LOCAL_DEV = os.environ.get("LOCAL_DEV") == "1"

# Short-lived in-memory SE cache used in local dev (disk cache is skipped when LOCAL_DEV=1)
_mem_cache: dict = {}  # key → (ranked_list, timestamp)

# Pre-fetched Gong aggregate stats keyed by (period_start, period_end)
# Populated in a background thread when get_data runs so gong data is ready by
# the time the /data/gong endpoint is called.
_gong_stats_cache: dict = {}  # (start, end) → list of usersAggregateActivityStats

_ICAV_FIELD = FIELD_CONFIG["icav_field"]
_EARR_FIELD = FIELD_CONFIG["earr_field"]
_TEAM_FIELD = FIELD_CONFIG["team_field"]

_ICAV_PRESETS = {0, 10_000, 50_000, 100_000}

_QUARTER_ENDS   = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
_QUARTER_STARTS = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}

_CACHE_TTL_CURRENT    = 600
_CACHE_TTL_HISTORICAL = 604_800

DEFAULT_TEAM = "digital_sales"

# ---------------------------------------------------------------------------
# icav_min validation
# ---------------------------------------------------------------------------

def parse_icav_min(raw: str | None) -> tuple[int, str | None]:
    try:
        val = int(raw or 0)
    except (ValueError, TypeError):
        return 0, "icav_min must be an integer"
    if val not in _ICAV_PRESETS:
        return 0, f"icav_min must be one of {sorted(_ICAV_PRESETS)}"
    return val, None


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def period_info(period_key: str) -> dict:
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


def available_periods() -> list[dict]:
    today = date.today()
    year  = today.year
    cur_q = (today.month - 1) // 3 + 1
    periods = []
    for q in range(cur_q, 0, -1):
        label = f"Q{q} {year}" + (" (current)" if q == cur_q else "")
        periods.append({"key": f"{year}_Q{q}", "label": label})
    for y in range(year - 1, year - 4, -1):
        periods.append({"key": f"{y}_FY", "label": f"Full Year {y}"})
    return periods


def default_period() -> str:
    today = date.today()
    cur_q = (today.month - 1) // 3 + 1
    if cur_q > 1:
        return f"{today.year}_Q{cur_q - 1}"
    return f"{today.year - 1}_Q4"


# ---------------------------------------------------------------------------
# SOQL builders
# ---------------------------------------------------------------------------

def build_soql(team_filter: str, start: str, end: str, icav_min: int = 0) -> str:
    icav_clause = f"AND {_ICAV_FIELD} >= {icav_min} " if icav_min > 0 else ""
    return (
        f"SELECT Id, Name, CloseDate, {_ICAV_FIELD}, {_EARR_FIELD}, {_TEAM_FIELD}, Presales_Stage__c, "
        f"Technical_Lead__r.Name, Technical_Lead__r.Email, Technical_Lead__r.Title, "
        f"Owner.Name, Owner.UserRole.Name, "
        f"Sales_Engineer_Notes__c, SE_Notes_History__c, "
        f"Account.Name, Account.Owner.Name, "
        f"Account.Current_ARR_Based_on_Last_6_Months__c, "
        f"Account.Average_Amortized_Usage_Last_3_Months__c, "
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


def build_all_owners_soql(team_total_filter: str, start: str, end: str) -> str:
    return (
        f"SELECT Owner.Name, {_ICAV_FIELD}, Technical_Lead__c "
        f"FROM Opportunity "
        f"WHERE StageName = 'Closed Won' "
        f"AND ({team_total_filter}) "
        f"AND CloseDate >= {start} "
        f"AND CloseDate <= {end}"
    )


def build_win_rate_soql(team_filter: str, start: str, end: str) -> str:
    return (
        f"SELECT Technical_Lead__r.Name, StageName, Owner.UserRole.Name, Account.Owner.Name "
        f"FROM Opportunity "
        f"WHERE StageName IN ('Closed Won', 'Closed Lost') "
        f"AND {team_filter} "
        f"AND Technical_Lead__c != null "
        f"AND CloseDate >= {start} "
        f"AND CloseDate <= {end}"
    )


def build_pipeline_soql(team_filter: str, end: str) -> str:
    return (
        f"SELECT Id, Owner.UserRole.Name, {_ICAV_FIELD} "
        f"FROM Opportunity "
        f"WHERE StageName NOT IN ('Closed Won', 'Closed Lost') "
        f"AND {team_filter} "
        f"AND Technical_Lead__c != null "
        f"AND CloseDate > {end}"
    )


def build_email_soql(start: str, end: str, se_owner_filter: str) -> str:
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


def _opp_filter_for_child(soql_filter: str) -> str:
    """Rewrite an Opportunity soql_filter for use in a child-object WHERE clause.

    When querying FROM Demo_Engineering_Request__c, all Opportunity field
    references must be prefixed with Opportunity__r. so Salesforce can
    traverse the parent relationship.
    """
    # Order matters: replace longer/more-specific patterns first so we don't
    # double-prefix anything.
    replacements = [
        ("Technical_Lead__r.",   "Opportunity__r.Technical_Lead__r."),
        ("FY_16_Owner_Team__c",  "Opportunity__r.FY_16_Owner_Team__c"),
        ("Owner.UserRole.Name",  "Opportunity__r.Owner.UserRole.Name"),
        ("Owner.Name",           "Opportunity__r.Owner.Name"),
    ]
    result = soql_filter
    for old, new in replacements:
        result = result.replace(old, new)
    return result


def build_ps_soql(soql_filter: str, start: str, end: str) -> str:
    opp_filter = _opp_filter_for_child(soql_filter)
    return (
        f"SELECT Id, Name, Assigned_To__r.Name, Assigned_To__r.Email, "
        f"Product_Specialist_Support_Type__c, "
        f"Opportunity__r.Id, Opportunity__r.Name, Opportunity__r.CloseDate, "
        f"Opportunity__r.{_ICAV_FIELD}, Opportunity__r.Owner.Name, "
        f"Opportunity__r.Technical_Lead__r.Name, "
        f"Opportunity__r.Account.Name "
        f"FROM Demo_Engineering_Request__c "
        f"WHERE Opportunity__c != null "
        f"AND Opportunity__r.StageName = 'Closed Won' "
        f"AND Opportunity__r.CloseDate >= {start} "
        f"AND Opportunity__r.CloseDate <= {end} "
        f"AND {opp_filter} "
        f"AND Assigned_To__c != null"
    )


def compute_ps_assists(ps_records: list) -> list:
    """Aggregate Demo_Engineering_Request__c records into per-PS summary rows."""
    by_ps: dict[str, dict] = {}
    for rec in ps_records:
        ps_rel  = rec.get("Assigned_To__r") or {}
        ps_name = (ps_rel.get("Name") or "").strip()
        if not ps_name:
            continue
        opp_rel   = rec.get("Opportunity__r") or {}
        opp_id    = opp_rel.get("Id") or ""
        opp_name  = opp_rel.get("Name") or ""
        opp_icav  = opp_rel.get(_ICAV_FIELD) or 0
        try:
            opp_icav = int(float(opp_icav))
        except (TypeError, ValueError):
            opp_icav = 0
        opp_owner = ((opp_rel.get("Owner") or {}).get("Name") or "")
        se_name   = ((opp_rel.get("Technical_Lead__r") or {}).get("Name") or "")
        acct_name = ((opp_rel.get("Account") or {}).get("Name") or "")

        if ps_name not in by_ps:
            by_ps[ps_name] = {"name": ps_name, "deals": 0, "total_icav": 0,
                              "opp_ids": set(), "se_names": set(), "opps": []}
        entry = by_ps[ps_name]
        if opp_id and opp_id not in entry["opp_ids"]:
            entry["opp_ids"].add(opp_id)
            entry["deals"] += 1
            entry["total_icav"] += opp_icav
            entry["opps"].append({
                "id":       opp_id,
                "name":     opp_name,
                "icav":     opp_icav,
                "owner":    opp_owner,
                "se":       se_name,
                "account":  acct_name,
            })
        if se_name:
            entry["se_names"].add(se_name)

    result = []
    for ps in by_ps.values():
        se_list = sorted(ps["se_names"])
        result.append({
            "name":        ps["name"],
            "deals":       ps["deals"],
            "total_icav":  ps["total_icav"],
            "avg_icav":    round(ps["total_icav"] / ps["deals"]) if ps["deals"] else 0,
            "se_count":    len(ps["se_names"]),
            "se_names":    se_list[:3],
            "opps":        sorted(ps["opps"], key=lambda x: x["icav"], reverse=True),
        })
    return sorted(result, key=lambda x: x["deals"], reverse=True)


def build_meeting_soql(start: str, end: str, se_owner_filter: str) -> str:
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

_SOQL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _safe_soql_date(value: str) -> str:
    if not _SOQL_DATE_RE.match(value):
        raise ValueError(f"Invalid SOQL date parameter: {value!r}")
    return value


def cache_path(team_key: str, period_key: str, icav_min: int = 0) -> Path:
    suffix = f"_min{icav_min}" if icav_min > 0 else ""
    return OUTPUT_DIR / f"sf_se_data_{team_key}_{period_key}{suffix}.json"


def is_fresh(team_key: str, period_key: str, icav_min: int, ttl: int) -> bool:
    if _LOCAL_DEV:
        return False
    p = cache_path(team_key, period_key, icav_min)
    return p.exists() and (time.time() - p.stat().st_mtime) < ttl


def load_cached(team_key: str, period_key: str, icav_min: int = 0) -> tuple[list | None, int | None, int | None, int | None, list | None, int | None, int | None]:
    p = cache_path(team_key, period_key, icav_min)
    if not p.exists():
        return None, None, None, None, None, None, None
    raw = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        p.unlink(missing_ok=True)
        return None, None, None, None, None, None, None
    return raw.get("ses"), raw.get("team_total_icav"), raw.get("act_total_icav"), raw.get("exp_total_icav"), raw.get("ps_assists"), raw.get("team_total_wins"), raw.get("team_total_earr")


def save_cached(ranked: list, team_key: str, period_key: str, icav_min: int = 0, motion: str = "dsr",
                team_total_icav: int | None = None, act_total_icav: int | None = None, exp_total_icav: int | None = None,
                ps_assists: list | None = None, team_total_wins: int | None = None, team_total_earr: int | None = None) -> list:
    total   = len(ranked)
    payload = []
    for i, se in enumerate(ranked, 1):
        entry          = {k: v for k, v in se.items() if not k.startswith("_")}
        entry["rank"]  = i
        entry["tier"]  = tier(i, total)
        entry["flags"] = collect_se_flags(se, ranked, motion)
        entry["roast"] = _roast(se, ranked, motion)
        payload.append(entry)
    if not _LOCAL_DEV:
        result = {"ses": payload}
        if team_total_icav is not None:
            result["team_total_icav"] = team_total_icav
        if act_total_icav is not None:
            result["act_total_icav"] = act_total_icav
        if exp_total_icav is not None:
            result["exp_total_icav"] = exp_total_icav
        if ps_assists is not None:
            result["ps_assists"] = ps_assists
        if team_total_wins is not None:
            result["team_total_wins"] = team_total_wins
        if team_total_earr is not None:
            result["team_total_earr"] = team_total_earr
        p   = cache_path(team_key, period_key, icav_min)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(result), encoding="utf-8")
        tmp.replace(p)
    return payload


# ---------------------------------------------------------------------------
# Team total iACV helpers
# ---------------------------------------------------------------------------

def _build_team_total_soql(team_filter: str, start: str, end: str) -> str:
    s, e = _safe_soql_date(start), _safe_soql_date(end)
    return (
        f"SELECT SUM({_ICAV_FIELD}) total_icav FROM Opportunity "
        f"WHERE StageName = 'Closed Won' AND ({team_filter}) "
        f"AND CloseDate >= {s} AND CloseDate <= {e}"
    )


def _build_team_total_earr_soql(team_filter: str, start: str, end: str) -> str:
    s, e = _safe_soql_date(start), _safe_soql_date(end)
    return (
        f"SELECT SUM({_EARR_FIELD}) total_earr FROM Opportunity "
        f"WHERE StageName = 'Closed Won' AND ({team_filter}) "
        f"AND CloseDate >= {s} AND CloseDate <= {e}"
    )


def get_team_total_earr(team_total_filter: str, start: str, end: str) -> int | None:
    if not sf.configured:
        return None
    try:
        rows = sf.query(_build_team_total_earr_soql(team_total_filter, start, end), timeout=60)
        if rows:
            val = rows[0].get("total_earr") or rows[0].get("expr0")
            return int(float(val)) if val is not None else None
    except Exception:
        log.warning("team total eARR query failed for filter: %s", team_total_filter, exc_info=True)
    return None


def get_team_total_icav(team_total_filter: str, start: str, end: str) -> int | None:
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


def motion_total_filter(team_total_filter: str, motion: str, which: str,
                        act_clause: str | None = None, exp_clause: str | None = None) -> str:
    base = f"({team_total_filter})"
    if act_clause and exp_clause:
        clause = act_clause if which == "act" else exp_clause
    elif motion == "dsr":
        clause = ("(NOT Owner.UserRole.Name LIKE '%Expansion%') AND (NOT FY_16_Owner_Team__c LIKE '%Expansion%')"
                  if which == "act" else
                  "(Owner.UserRole.Name LIKE '%Expansion%' OR FY_16_Owner_Team__c LIKE '%Expansion%')")
    else:
        clause = "Owner.UserRole.Name LIKE '% NB%'" if which == "act" else "Owner.UserRole.Name LIKE '%Strat%'"
    return f"{base} AND {clause}"


# ---------------------------------------------------------------------------
# Main data fetch
# ---------------------------------------------------------------------------

def get_data(teams: dict, team_key: str, period_key: str, icav_min: int = 0, subteam_key: str = "") -> tuple[list | None, str | None, int | None, int | None, int | None, list | None, list | None, int | None, int | None]:
    team = teams.get(team_key)
    if not team:
        return None, f"Unknown team '{team_key}'", None, None, None, None

    soql_filter        = team["soql_filter"]
    email_owner_filter = team["email_owner_filter"]

    if subteam_key:
        subteam = next((s for s in team.get("subteams", []) if s["key"] == subteam_key), None)
        if not subteam:
            return None, f"Unknown subteam '{subteam_key}' for team '{team_key}'", None, None, None, None
        soql_filter        = subteam["soql_filter"]
        email_owner_filter = subteam["email_owner_filter"]

    cache_key   = f"{team_key}_{subteam_key}" if subteam_key else team_key
    info        = period_info(period_key)
    period_year = int(period_key.split("_")[0])
    if not subteam_key and period_year < date.today().year and "historical_soql_filter" in team:
        soql_filter = team["historical_soql_filter"]

    if is_fresh(cache_key, period_key, icav_min, info["ttl"]):
        ses, tti, ati, eti, ps_assists, ttw, tte = load_cached(cache_key, period_key, icav_min)
        return ses, None, tti, ati, eti, None, ps_assists, ttw, tte

    if not sf.configured:
        stale, tti, ati, eti, ps_assists, ttw, tte = load_cached(cache_key, period_key, icav_min)
        if stale:
            return stale, None, tti, ati, eti, None, ps_assists, ttw, tte
        return None, "Salesforce is not configured.", None, None, None, None, None, None, None

    core_exc: Exception | None = None
    opps = win_rate_opps = pipe_opps = email_tasks = meeting_events = all_owner_opps = ps_records = None
    team_total_icav = act_total_icav = exp_total_icav = team_total_earr = None
    team_total_filter = team.get("team_total_filter")
    team_icav_filter  = team.get("team_icav_filter") or team_total_filter
    act_icav_clause   = team.get("act_icav_clause")
    exp_icav_clause   = team.get("exp_icav_clause")
    motion            = team.get("motion", "dsr")
    act_filter_used   = team.get("act_icav_filter") or motion_total_filter(team_icav_filter, motion, "act", act_icav_clause, exp_icav_clause)
    exp_filter_used   = team.get("exp_icav_filter") or motion_total_filter(team_icav_filter, motion, "exp", act_icav_clause, exp_icav_clause)

    with ThreadPoolExecutor(max_workers=10) as pool:
        pool.submit(_prefetch_gong_stats, info["start"], info["end"])
        f_opps     = pool.submit(sf.query, build_soql(soql_filter, info["start"], info["end"], icav_min))
        f_win_rate = pool.submit(sf.query, build_win_rate_soql(soql_filter, info["start"], info["end"]))
        f_pipeline = pool.submit(sf.query, build_pipeline_soql(soql_filter, info["end"]))
        f_email    = pool.submit(sf.query, build_email_soql(info["start"], info["end"], email_owner_filter))
        f_meetings = pool.submit(sf.query, build_meeting_soql(info["start"], info["end"], email_owner_filter))
        f_ps       = pool.submit(sf.query, build_ps_soql(soql_filter, info["start"], info["end"]))
        if team_total_filter and not subteam_key:
            f_team_total = pool.submit(get_team_total_icav, team_icav_filter, info["start"], info["end"])
            f_act_total  = pool.submit(get_team_total_icav, act_filter_used, info["start"], info["end"])
            f_exp_total  = pool.submit(get_team_total_icav, exp_filter_used, info["start"], info["end"])
            f_all_owners = pool.submit(sf.query, build_all_owners_soql(team_total_filter, info["start"], info["end"]))
            f_team_earr  = pool.submit(get_team_total_earr, team_total_filter, info["start"], info["end"])
        else:
            f_team_total = f_act_total = f_exp_total = f_all_owners = f_team_earr = None

        try:
            opps          = f_opps.result()
            win_rate_opps = f_win_rate.result()
        except Exception as e:
            core_exc = e
            log.exception("Salesforce query failed for team %s / %s", cache_key, period_key)

        try:
            pipe_opps = f_pipeline.result()
        except Exception:
            log.warning("Pipeline query failed — classifying closed-won opps only")
            pipe_opps = []

        try:
            email_tasks = f_email.result()
        except Exception:
            log.warning("Email activity query failed for %s/%s", cache_key, period_key, exc_info=True)

        try:
            meeting_events = f_meetings.result()
        except Exception:
            log.warning("Meeting activity query failed for %s/%s", cache_key, period_key, exc_info=True)

        if f_team_total:
            try: team_total_icav = f_team_total.result()
            except Exception: log.warning("Team total iACV failed %s/%s", cache_key, period_key, exc_info=True)
        if f_act_total:
            try: act_total_icav = f_act_total.result()
            except Exception: log.warning("Act total iACV failed %s/%s", cache_key, period_key, exc_info=True)
        if f_exp_total:
            try: exp_total_icav = f_exp_total.result()
            except Exception: log.warning("Exp total iACV failed %s/%s", cache_key, period_key, exc_info=True)
        if f_all_owners:
            try: all_owner_opps = f_all_owners.result()
            except Exception: log.warning("All-owners query failed %s/%s", cache_key, period_key, exc_info=True)
        if f_team_earr:
            try: team_total_earr = f_team_earr.result()
            except Exception: log.warning("Team total eARR failed %s/%s", cache_key, period_key, exc_info=True)

        try:
            ps_records = f_ps.result()
        except Exception:
            log.warning("PS assists query failed for %s/%s", cache_key, period_key, exc_info=True)
            ps_records = []

    if act_icav_clause and exp_icav_clause and act_total_icav is not None and exp_total_icav is not None:
        team_total_icav = act_total_icav + exp_total_icav

    team_total_wins = len(all_owner_opps) if all_owner_opps is not None else None

    if core_exc is not None:
        stale, tti, ati, eti, ps_assists, ttw, tte = load_cached(cache_key, period_key, icav_min)
        if stale:
            return stale, None, tti, ati, eti, None, ps_assists, ttw, tte
        return None, f"Salesforce query failed: {core_exc}", None, None, None, None, None, None, None

    if not opps:
        return [], None, team_total_icav, act_total_icav, exp_total_icav, all_owner_opps, [], team_total_wins, team_total_earr

    ses = build_ses(opps, motion, notes_floor=icav_min, period_key=period_key)
    merge_win_rate(ses, win_rate_opps, motion)

    opp_motion_map: dict[str, str] = {}
    for opp in list(opps) + list(pipe_opps or []):
        oid = opp.get("Id") or ""
        if oid and oid not in opp_motion_map:
            if _is_activate(opp):
                opp_motion_map[oid] = "activate"
            elif _is_expansion(opp):
                opp_motion_map[oid] = "expansion"

    if email_tasks is not None:
        try:
            merge_email_activity(ses, email_tasks, info["end"], opp_motion_map)
        except Exception:
            log.warning("Email merge failed %s/%s", cache_key, period_key, exc_info=True)

    if meeting_events is not None:
        try:
            merge_meeting_activity(ses, meeting_events, info["end"], opp_motion_map)
        except Exception:
            log.warning("Meeting merge failed %s/%s", cache_key, period_key, exc_info=True)

    ses = [s for s in ses if s["act_wins"] + s["exp_wins"] > 0]
    if not ses:
        return [], None, team_total_icav, act_total_icav, exp_total_icav, all_owner_opps, [], team_total_wins, team_total_earr

    ranked = rank_ses(ses)
    ps_assists = compute_ps_assists(ps_records or [])
    result = save_cached(ranked, cache_key, period_key, icav_min, motion, team_total_icav, act_total_icav, exp_total_icav, ps_assists, team_total_wins, team_total_earr)
    _mem_cache[(cache_key, period_key, icav_min)] = (result, time.time())
    log.info("Refreshed %s/%s (min $%s): %d opps, %d PS assists", cache_key, period_key, icav_min, len(opps), len(ps_assists))
    return result, None, team_total_icav, act_total_icav, exp_total_icav, all_owner_opps, ps_assists, team_total_wins, team_total_earr


# ---------------------------------------------------------------------------
# Email → SE name matcher
# ---------------------------------------------------------------------------

def email_to_se_name(email: str, ses: list) -> str | None:
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
# Chat context builder
# ---------------------------------------------------------------------------

SF_SCHEMA_HINT = """
## Salesforce fields
  Id, Name, CloseDate, StageName, Amount, Type
  Comms_Segment_Combined_iACV__c     (iACV — primary revenue metric, use this for all dollar figures)
  eARR_post_launch_No_Decimal__c     (eARR — post-launch ARR)
  FY_16_Owner_Team__c                (team stamp frozen at opp assignment)
  Presales_Stage__c                  ('4 - Technical Win Achieved' = TW; TW is required for a win to count in rankings)
  Technical_Lead__r.Name, Technical_Lead__r.Email, Technical_Lead__r.UserRole.Name, Technical_Lead__r.Title
  Owner.Name, Owner.UserRole.Name
  Account.Name, Account.Owner.Name
  SE_Notes__c, SE_Notes_History__c, Sales_Engineer_Notes__c
  RecordType.Name
Standard date literals: TODAY, THIS_QUARTER, LAST_QUARTER, THIS_YEAR, LAST_N_DAYS:n
Always filter StageName = 'Closed Won' unless asking about open pipeline.
Limit results to 50 rows unless more are explicitly needed.

## How scorecard metrics are calculated

**iACV** = SUM(Comms_Segment_Combined_iACV__c) on Closed Won opps with Presales_Stage__c = '4 - Technical Win Achieved'.
Only TW deals count toward iACV rankings. Non-TW closed won is supplemental.

**Activate wins / iACV (DSR team)**
  Activate = Owner.UserRole.Name LIKE '%Activation%'
           OR (FY_16_Owner_Team__c LIKE 'DSR%' AND FY_16_Owner_Team__c NOT LIKE '%Expansion%')
  Fallback: Account.Owner.Name LIKE '%Self%' (self-service-owned accounts are always Activate)

**Expansion wins / iACV (DSR team)**
  Expansion = Owner.UserRole.Name LIKE '%Expansion%'
           OR FY_16_Owner_Team__c LIKE '%Expansion%'

**New Business / Strategic (AE-motion teams: NAMER, EMEA, APJ, LATAM)**
  New Business = Owner.UserRole.Name LIKE '% NB%' OR FY_16_Owner_Team__c LIKE '% NB%'
  Strategic    = Owner.UserRole.Name LIKE '%Strat%' OR FY_16_Owner_Team__c LIKE '%Strat%'

**Win rate** = Closed Won TW Activate (or NB) opps ÷ (Closed Won + Closed Lost Activate/NB opps).
Win rate only covers Activate/NB — Expansion/Strategic opps are excluded.

**Team SE filter by team**
  DSR/Self Service:  Technical_Lead__r.UserRole.Name = 'SE - Self Service' AND Technical_Lead__r.Title LIKE '%Engineer%'
  NAMER:             Technical_Lead__r.UserRole.Name LIKE 'SE - NAMER%'
  EMEA:              Technical_Lead__r.UserRole.Name LIKE 'SE - EMEA%'
  APJ:               Technical_Lead__r.UserRole.Name = 'SE - APJ'
  LATAM:             Technical_Lead__r.UserRole.Name LIKE 'SE - LATAM%'
  DORG:              Technical_Lead__r.UserRole.Name = 'SE - DORG'

**DSR opp scope filter** (use in every DSR query to get the right universe):
  (FY_16_Owner_Team__c LIKE 'DSR%'
   OR (Owner.UserRole.Name LIKE '%DSR%' AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')))

**Ranking** = composite percentile score: 85% total iACV + 8% MRR % growth + 5% total ARR touched + 2% notes hygiene.
Tiers: Elite (top 20%), Strong (21–50%), Steady (51–75%), Develop (bottom 25%).

**MRR delta** = quarter avg MRR minus 3 months prior avg MRR, from Account.Total_Amortized_Twilio_Usage_* snapshot fields.
Expansion status: Growing (avg MRR% ≥+5%, more growing than contracting), Contracting (≤-5%), Mixed, Expanding ($0 median but positive iACV), Retaining ($0 median flat MRR).

**Notes quality** = fraction of TW opps with Comms_Segment_Combined_iACV__c ≥ notes floor that have BOTH Sales_Engineer_Notes__c AND SE_Notes_History__c filled.

## SOQL example — DSR team Closed Won by SE this quarter
  SELECT Technical_Lead__r.Name,
         COUNT(Id) wins,
         SUM(Comms_Segment_Combined_iACV__c) icav
  FROM Opportunity
  WHERE StageName = 'Closed Won'
  AND Presales_Stage__c = '4 - Technical Win Achieved'
  AND CloseDate = THIS_QUARTER
  AND Technical_Lead__c != null
  AND (FY_16_Owner_Team__c LIKE 'DSR%' OR (Owner.UserRole.Name LIKE '%DSR%' AND (NOT Owner.UserRole.Name LIKE '%Twilio.org%')))
  AND Technical_Lead__r.UserRole.Name = 'SE - Self Service'
  AND Technical_Lead__r.Title LIKE '%Engineer%'
  GROUP BY Technical_Lead__r.Name
  ORDER BY SUM(Comms_Segment_Combined_iACV__c) DESC

IMPORTANT: In SOQL aggregate queries always ORDER BY the full aggregate expression — e.g. ORDER BY SUM(Comms_Segment_Combined_iACV__c) DESC — never by a SELECT alias (aliases are ignored by Salesforce in ORDER BY).
Always include Technical_Lead__c != null when filtering for SE-tagged deals.
"""


def build_chat_context(ses: list, team_key: str, period_key: str, teams: dict) -> str:
    team  = teams.get(team_key, {})
    info  = period_info(period_key)
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
            nf = "[has_notes]" if opp.get("has_notes") else "[no_notes]"
            hf = "[has_history]" if opp.get("has_history") else "[no_history]"
            lines.append(f"    deal: {opp.get('name','')} | iACV: ${opp.get('icav',0):,} | close: {opp.get('close_date','')} | motion: {opp.get('motion','')} | {nf} {hf}")
        for acct in (se.get("exp_account_detail") or [])[:5]:
            lines.append(f"    exp_acct: {acct.get('acct_name','')} | ARR: ${acct.get('arr',0):,} | MRR delta: ${acct.get('mrr_delta',0):,}/mo")
        if se.get("roast"):
            lines.append(f"  Summary: {se['roast']}")
        lines.append("")
    return "\n".join(lines)