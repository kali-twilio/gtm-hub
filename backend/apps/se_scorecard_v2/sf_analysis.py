"""
SE Scorecard V2 — data layer.
Computes the same SE metrics as se_analysis.py but from live Salesforce opportunity records.
Owl scores (Salesforce hygiene %) still come from a CSV upload.
"""

import statistics
from datetime import date as _date
from pathlib import Path

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
        close = _date.fromisoformat(close_date_str)
    except (ValueError, TypeError):
        return 0, 0, 0

    today     = _date.today()
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

    # Minimum iACV to count as an Activate win (matches dashboard filter)
    "activate_min_icav": 30_000,

    # Q1 date range (used as a label only — filtering is done in SOQL)
    "quarter_label": "Q1 2026",
}

ACT_AVG_SIZE_WARNING         = 40_000
FUTURE_PIPELINE_STRONG       = 60
FUTURE_PIPELINE_WEAK         = 30
DEAL_CONCENTRATION_THRESHOLD = 0.5


def fmt(amount):
    if amount >= 1_000_000: return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:     return f"${amount / 1_000:.0f}K"
    return f"${amount}"


def _icav(opp: dict) -> int:
    val = opp.get(FIELD_CONFIG["icav_field"]) or 0
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

def build_ses(opps: list, motion: str = "dsr", notes_floor: int = 0) -> list:
    """
    opps   — list of Salesforce Closed Won Opportunity dicts (TW and non-TW)
    motion — 'dsr' (Activate/Expansion) or 'ae' (New Business/Strategic)
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
                "act_icavs":      [],   # TW activate wins
                "exp_icavs":      [],   # TW expansion wins
                "non_tw_act_icavs": [], # non-TW activate wins
                "non_tw_exp_icavs": [], # non-TW expansion wins
                "all_opps":       [],
                "exp_tw_opps":    [],  # ALL TW expansion wins (for account ARR/MRR aggregation)
            }

        icav  = _icav(opp)
        is_tw = opp.get("Presales_Stage__c") == "4 - Technical Win Achieved"
        by_se[name]["all_opps"].append(opp)

        is_act = _is_new_business(opp) if motion == "ae" else _is_activate(opp)
        is_exp = _is_strategic(opp)   if motion == "ae" else _is_expansion(opp)

        if is_tw:
            if is_act:
                by_se[name]["act_icavs"].append(icav)
            elif is_exp:
                by_se[name]["exp_icavs"].append(icav)
                by_se[name]["exp_tw_opps"].append(opp)
            else:
                by_se[name]["act_icavs"].append(icav)  # fallback
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
        exp_icavs = d["exp_icavs"]

        act_wins   = len(act_icavs)
        act_icav   = sum(act_icavs)
        act_avg    = round(statistics.mean(act_icavs)) if act_icavs else 0
        act_median = round(statistics.median(act_icavs)) if act_icavs else 0

        exp_wins   = len(exp_icavs)
        exp_icav   = sum(exp_icavs)
        exp_avg    = round(statistics.mean(exp_icavs)) if exp_icavs else 0
        exp_median = round(statistics.median(exp_icavs)) if exp_icavs else 0

        total_icav = act_icav + exp_icav

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
            "name":         opp.get("Name") or "",
            "owner":        ((opp.get("Owner") or {}).get("Name") or ""),
            "close_date":   opp.get("CloseDate") or "",
            "icav":         _icav(opp),
            "motion":       _opp_motion(opp),
            "has_notes":    bool(opp.get("Sales_Engineer_Notes__c")),
            "has_history":  bool(opp.get("SE_Notes_History__c")),
            "note_entries": _history_entries(opp.get("SE_Notes_History__c") or ""),
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

        # Largest deal
        all_icavs = [(o, _icav(o)) for o in d["all_opps"]]
        largest_opp, largest_val = max(all_icavs, key=lambda x: x[1]) if all_icavs else (None, 0)
        largest_name   = (largest_opp.get("Name") or "") if largest_opp else ""
        largest_dsr    = ((largest_opp.get("Owner") or {}).get("Name") or "") if largest_opp else ""
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
            # Falls back to rolling 3mo avg vs ARR/12 baseline if snapshots aren't available
            # (e.g. data older than 14 months, or fields missing for this account).
            q_avg, pre_avg, mrr_delta = _quarter_mrr_delta(acct, e_opp.get("CloseDate") or "")
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
            "act_wins":          act_wins,
            "act_icav":          act_icav,
            "act_avg":           act_avg,
            "act_median":        act_median,
            "exp_wins":          exp_wins,
            "exp_icav":          exp_icav,
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
            "largest_deal":        largest_name,
            "largest_deal_value":  largest_val,
            "largest_deal_dsr":    largest_dsr,
            "largest_deal_motion": largest_motion,
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
# Email activity
# ---------------------------------------------------------------------------

def merge_email_activity(ses: list, email_tasks: list, period_end: str,
                         opp_motion_map: dict):
    """
    Merge Task-email counts into SE records. Mutates ses in place.

    Classification uses the opp's Owner.UserRole.Name directly (included in the
    email SOQL TYPEOF clause) — not the motion map. This means ALL DSR expansion
    opp emails are counted regardless of whether the SE is tagged as TL on the opp.

    Activate (opp owner role contains 'Activation'):
      email_act_inq       – emails to Activate opps closing this period
      email_act_outq      – emails to future Activate opps (pipeline building)
      email_act_outq_icav – iACV of those future Activate opps

    Expansion (opp owner role contains 'Expansion'):
      email_exp_inq       – emails to Expansion opps closing this period
      email_exp_outq      – emails to future Expansion opps (pipeline building)
      email_exp_outq_icav – iACV of those future Expansion opps

    DSR Account emails (WhatId = Account, account owned by DSR):
      email_exp_acct      – direct account emails (no opp on call)
    """
    from datetime import date as _date
    p_end    = _date.fromisoformat(period_end)
    icav_key = FIELD_CONFIG["icav_field"]

    def _blank():
        return {
            "act_inq": 0, "act_outq": 0, "act_outq_opps": {},
            "exp_inq": 0, "exp_outq": 0, "exp_outq_opps": {},
        }

    counts: dict[str, dict] = {}

    for task in email_tasks:
        owner = task.get("Owner") or {}
        name  = (owner.get("Name") or "").strip()
        if not name:
            continue

        what     = task.get("What") or {}
        what_typ = (what.get("attributes") or {}).get("type") or ""
        opp_id   = task.get("WhatId") or ""

        if name not in counts:
            counts[name] = _blank()
        c = counts[name]

        # Opportunity email — classify via opp owner role (included in TYPEOF)
        opp_role = ((what.get("Owner") or {}).get("UserRole") or {}).get("Name") or ""
        if "Activation" in opp_role:
            motion = "activate"
        elif "Expansion" in opp_role:
            motion = "expansion"
        else:
            continue  # not a DSR activate/expand opp

        close_date_str = what.get("CloseDate") or ""
        if not close_date_str:
            continue
        try:
            close_date = _date.fromisoformat(close_date_str)
        except ValueError:
            continue

        try:
            icav = int(float(what.get(icav_key) or 0))
        except (TypeError, ValueError):
            icav = 0

        if motion == "activate":
            if close_date <= p_end:
                c["act_inq"] += 1
            else:
                c["act_outq"] += 1
                if opp_id:
                    c["act_outq_opps"].setdefault(opp_id, icav)
        else:  # expansion
            if close_date <= p_end:
                c["exp_inq"] += 1
            else:
                c["exp_outq"] += 1
                if opp_id:
                    c["exp_outq_opps"].setdefault(opp_id, icav)

    for se in ses:
        c = counts.get(se["name"], _blank())
        se["email_act_inq"]       = c["act_inq"]
        se["email_act_outq"]      = c["act_outq"]
        se["email_act_outq_icav"] = sum(c["act_outq_opps"].values())
        se["email_exp_inq"]       = c["exp_inq"]
        se["email_exp_outq"]      = c["exp_outq"]
        se["email_exp_outq_icav"] = sum(c["exp_outq_opps"].values())


# ---------------------------------------------------------------------------
# Meeting activity
# ---------------------------------------------------------------------------

def merge_meeting_activity(ses: list, meeting_events: list, period_end: str,
                           opp_motion_map: dict):
    """
    Merge Event meeting counts into SE records. Mutates ses in place.
    Identical classification logic to merge_email_activity — opp owner role
    drives activate/expansion split.

    Activate (opp owner role contains 'Activation'):
      meeting_act_inq       – meetings on Activate opps closing this period
      meeting_act_outq      – meetings on future Activate opps (pipeline building)
      meeting_act_outq_icav – iACV of those future Activate opps

    Expansion (opp owner role contains 'Expansion'):
      meeting_exp_inq       – meetings on Expansion opps closing this period
      meeting_exp_outq      – meetings on future Expansion opps (pipeline building)
      meeting_exp_outq_icav – iACV of those future Expansion opps
    """
    from datetime import date as _date
    p_end    = _date.fromisoformat(period_end)
    icav_key = FIELD_CONFIG["icav_field"]

    def _blank():
        return {
            "act_inq": 0, "act_outq": 0, "act_outq_opps": {},
            "exp_inq": 0, "exp_outq": 0, "exp_outq_opps": {},
        }

    counts: dict[str, dict] = {}
    # Deduplicate recurring series: same recurring series on same opp for same SE
    # counts as one meeting. Without this, a weekly sync recurring 13x in the quarter
    # inflates the count 13-fold. Key = (se_name, opp_id, recurrence_series_id).
    seen_series: set = set()

    for event in meeting_events:
        owner = event.get("Owner") or {}
        name  = (owner.get("Name") or "").strip()
        if not name:
            continue

        what          = event.get("What") or {}
        opp_id        = event.get("WhatId") or ""
        recurrence_id = event.get("RecurrenceActivityId") or ""

        # Skip duplicate occurrences of the same recurring series on the same opp
        if recurrence_id:
            series_key = (name, opp_id, recurrence_id)
            if series_key in seen_series:
                continue
            seen_series.add(series_key)

        if name not in counts:
            counts[name] = _blank()
        c = counts[name]

        opp_role = ((what.get("Owner") or {}).get("UserRole") or {}).get("Name") or ""
        if "Activation" in opp_role:
            motion = "activate"
        elif "Expansion" in opp_role:
            motion = "expansion"
        else:
            continue  # not a DSR activate/expand opp

        close_date_str = what.get("CloseDate") or ""
        if not close_date_str:
            continue
        try:
            close_date = _date.fromisoformat(close_date_str)
        except ValueError:
            continue

        try:
            icav = int(float(what.get(icav_key) or 0))
        except (TypeError, ValueError):
            icav = 0

        if motion == "activate":
            if close_date <= p_end:
                c["act_inq"] += 1
            else:
                c["act_outq"] += 1
                if opp_id:
                    c["act_outq_opps"].setdefault(opp_id, icav)
        else:  # expansion
            if close_date <= p_end:
                c["exp_inq"] += 1
            else:
                c["exp_outq"] += 1
                if opp_id:
                    c["exp_outq_opps"].setdefault(opp_id, icav)

    for se in ses:
        c = counts.get(se["name"], _blank())
        se["meeting_act_inq"]       = c["act_inq"]
        se["meeting_act_outq"]      = c["act_outq"]
        se["meeting_act_outq_icav"] = sum(c["act_outq_opps"].values())
        se["meeting_exp_inq"]       = c["exp_inq"]
        se["meeting_exp_outq"]      = c["exp_outq"]
        se["meeting_exp_outq_icav"] = sum(c["exp_outq_opps"].values())


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

def collect_se_flags(se, ses, motion: str = "dsr"):
    flags = []
    n = len(ses)

    # Motion-specific category names and message text
    act_cat = "NEW BUSINESS" if motion == "ae" else "ACTIVATE"
    exp_cat = "STRATEGIC"    if motion == "ae" else "EXPANSION"
    act_lbl = "new business" if motion == "ae" else "activate"
    exp_lbl = "strategic"    if motion == "ae" else "expansion"

    # Determine which motions this SE actually participates in
    has_act  = se["act_wins"] > 0
    has_exp  = se["exp_wins"] > 0
    act_only = has_act and not has_exp
    exp_only = has_exp and not has_act

    # Pre-compute team context
    max_act_wins         = max(s["act_wins"] for s in ses)
    act_ses              = [s for s in ses if s["act_wins"] > 0]
    act_medians          = [s["act_median"] for s in act_ses if s["act_median"] > 0]
    team_act_median      = round(statistics.median(act_medians)) if act_medians else 0
    team_median_act_wins = round(statistics.median([s["act_wins"] for s in act_ses])) if act_ses else 0
    team_median_act_icav = round(statistics.median([s["act_icav"] for s in act_ses])) if act_ses else 0
    exp_ses              = [s for s in ses if s["exp_wins"] > 0]
    team_median_exp_icav = round(statistics.median([s["exp_icav"] for s in exp_ses])) if exp_ses else 0
    team_median_exp_wins = round(statistics.median([s["exp_wins"] for s in exp_ses])) if exp_ses else 0
    notes_ses            = [s for s in ses if s["note_hv_total"] > 0]
    team_median_notes_pct = round(statistics.median(
        [s["note_hv_covered"] / s["note_hv_total"] * 100 for s in notes_ses]
    )) if notes_ses else 0
    team_median_icav     = round(statistics.median([s["total_icav"] for s in ses]))
    team_pipe_max        = max(s.get("email_act_outq", 0) + s.get("email_exp_outq", 0) for s in ses)
    team_meet_max        = max(
        s.get("meeting_act_inq", 0) + s.get("meeting_act_outq", 0) +
        s.get("meeting_exp_inq", 0) + s.get("meeting_exp_outq", 0) for s in ses
    )

    def _rel(val, med):
        """Return a short relative label vs a team median."""
        if med == 0:
            return ""
        diff = round((val - med) / med * 100)
        if diff > 10:
            return f"+{diff}% above median"
        if diff < -10:
            return f"{diff}% below median"
        return "at team median"

    # --- ACTIVATE / NEW BUSINESS --- (skip entirely for expansion/strategic-only SEs)
    if not exp_only:
        if se["act_wins"] == 0:
            flags.append((act_cat, f"No {act_lbl} wins this quarter. Team median: {team_median_act_wins} wins."))
        elif se["act_wins"] == max_act_wins:
            others = sum(s["act_wins"] for s in ses) - se["act_wins"]
            flags.append((act_cat, (
                f"Highest {act_lbl} volume on team — {se['act_wins']} wins "
                f"(team median {team_median_act_wins}). Rest of team combined: {others}."
            )))
        elif se["act_wins"] <= 2:
            flags.append((act_cat, (
                f"Low {act_lbl} volume — {se['act_wins']} win{'s' if se['act_wins'] > 1 else ''} "
                f"vs team median {team_median_act_wins} wins."
            )))
        else:
            act_rel = _rel(se["act_icav"], team_median_act_icav)
            flags.append((act_cat, (
                f"{se['act_wins']} wins, {fmt(se['act_icav'])} iACV — {act_rel} "
                f"(team median {fmt(team_median_act_icav)})."
            )))

        if se["act_wins"] >= 4:
            if se["act_wins"] >= 5 and se["act_median"] < ACT_AVG_SIZE_WARNING:
                flags.append((act_cat, (
                    f"{fmt(se['act_median'])} median on {se['act_wins']} wins — "
                    f"below ${ACT_AVG_SIZE_WARNING//1000}K floor. Team deal median {fmt(team_act_median)}."
                )))
            if se["act_median"] > 0:
                ratio = se["act_avg"] / se["act_median"]
                if ratio >= 2.5:
                    flags.append((act_cat, (
                        f"Whale-dependent — {fmt(se['act_avg'])} avg vs {fmt(se['act_median'])} median. "
                        f"One big deal skewing the numbers."
                    )))
                elif ratio < 1.2 and se["act_wins"] >= 5 and se["act_median"] >= ACT_AVG_SIZE_WARNING:
                    flags.append(("STRENGTH", (
                        f"Consistent {act_lbl} sizing — {fmt(se['act_median'])} median across "
                        f"{se['act_wins']} wins (team deal median {fmt(team_act_median)})."
                    )))

    # --- EXPANSION / STRATEGIC --- (skip entirely for activate/NB-only SEs)
    if not act_only:
        exp_team_ctx = f" Team {exp_lbl} median: {fmt(team_median_exp_icav)} ({team_median_exp_wins} wins)." if team_median_exp_icav > 0 else ""
        if se["exp_growing"]:
            exp_rel = _rel(se["exp_icav"], team_median_exp_icav)
            flags.append((exp_cat, (
                f"Growing — {fmt(se['exp_median'])} median, {fmt(se['exp_icav'])} total "
                f"({exp_rel} for {exp_lbl}).{exp_team_ctx}"
            )))
        elif se["exp_wins"] >= 10:
            flags.append((exp_cat, (
                f"High {exp_lbl} load — {se['exp_wins']} wins at $0 median. "
                f"Retaining, not expanding.{exp_team_ctx}"
            )))
        elif se["exp_wins"] > 0:
            flags.append((exp_cat, (
                f"Retaining — $0 median on {se['exp_wins']} {exp_lbl} wins.{exp_team_ctx}"
            )))
        else:
            flags.append((exp_cat, f"No {exp_lbl} contribution this quarter.{exp_team_ctx}"))

    # --- MOTION --- (only meaningful when SE has wins in both motions)
    if has_act and has_exp and se["total_icav"] > 0:
        act_pct = se["act_icav"] / se["total_icav"]
        exp_pct = se["exp_icav"] / se["total_icav"]
        if act_pct > 0.85 and se["act_icav"] > 200_000:
            flags.append(("MOTION", f"{round(act_pct*100)}% of iACV from {act_lbl} — {exp_lbl} not contributing."))
        elif exp_pct > 0.85 and se["exp_icav"] > 200_000:
            flags.append(("MOTION", f"{round(exp_pct*100)}% of iACV from {exp_lbl} — {act_lbl} light."))

    # --- PIPELINE (emails) ---
    total_pipe = se.get("email_act_outq", 0) + se.get("email_exp_outq", 0)
    total_inq  = se.get("email_act_inq", 0) + se.get("email_exp_inq", 0)
    pipe_icav  = se.get("email_act_outq_icav", 0) + se.get("email_exp_outq_icav", 0)
    team_median_pipe = round(statistics.median(
        [s.get("email_act_outq", 0) + s.get("email_exp_outq", 0) for s in ses]
    ))

    if total_pipe == 0 and total_inq == 0:
        flags.append(("RISK", f"Zero email activity recorded — no in-Q or pipeline engagement. Team median: {team_median_pipe} pipeline emails."))
    elif total_pipe == 0:
        flags.append(("RISK", f"No pipeline emails — {total_inq} in-Q emails but nothing building for next quarter. Team median: {team_median_pipe}."))
    elif total_pipe == team_pipe_max and total_pipe > 0:
        pipe_str = f"{total_pipe} pipeline emails" + (f" · {fmt(pipe_icav)}" if pipe_icav > 0 else "")
        flags.append(("STRENGTH", f"Top pipeline builder on the team — {pipe_str} (team median {team_median_pipe})."))
    elif total_pipe >= 20 and pipe_icav > 500_000:
        flags.append(("STRENGTH", f"Strong pipeline footprint — {total_pipe} outq emails, {fmt(pipe_icav)} in future deals."))
    else:
        pipe_rel = _rel(total_pipe, team_median_pipe)
        if total_pipe > 0:
            flags.append(("PIPELINE", f"{total_pipe} pipeline emails ({pipe_rel}, team median {team_median_pipe})."))

    # --- MEETINGS ---
    total_meet     = (se.get("meeting_act_inq", 0) + se.get("meeting_act_outq", 0) +
                      se.get("meeting_exp_inq", 0) + se.get("meeting_exp_outq", 0))
    meet_inq       = se.get("meeting_act_inq", 0) + se.get("meeting_exp_inq", 0)
    meet_pipe      = se.get("meeting_act_outq", 0) + se.get("meeting_exp_outq", 0)
    team_median_meet = round(statistics.median(
        [s.get("meeting_act_inq", 0) + s.get("meeting_act_outq", 0) +
         s.get("meeting_exp_inq", 0) + s.get("meeting_exp_outq", 0) for s in ses]
    ))

    if team_meet_max > 0:
        if total_meet == 0:
            flags.append(("RISK", f"Zero meetings recorded. Team median: {team_median_meet}."))
        elif total_meet == team_meet_max and len(ses) > 1:
            flags.append(("STRENGTH", f"Most meetings on the team — {total_meet} ({meet_inq} in-Q, {meet_pipe} pipeline). Team median: {team_median_meet}."))
        else:
            meet_rel = _rel(total_meet, team_median_meet)
            flags.append(("MEETINGS", f"{total_meet} meetings ({meet_inq} in-Q, {meet_pipe} pipeline) — {meet_rel} (team median {team_median_meet})."))

    # --- RISK: deal concentration ---
    if se["total_icav"] > 0 and se["largest_deal_value"] > se["total_icav"] * DEAL_CONCENTRATION_THRESHOLD:
        pct = round(se["largest_deal_value"] / se["total_icav"] * 100)
        flags.append(("RISK", f"Largest deal is {pct}% of total iACV ({fmt(se['largest_deal_value'])}) — concentrated quarter."))
    elif se["total_icav"] > 500_000 and se["largest_deal_value"] > 0:
        pct = round(se["largest_deal_value"] / se["total_icav"] * 100)
        if pct < 20:
            flags.append(("STRENGTH", f"Revenue well distributed — largest deal is only {pct}% of {fmt(se['total_icav'])} total."))

    # --- RISK: notes on high-value opps ---
    if se["note_hv_total"] > 0:
        cov_pct = round(se["note_hv_covered"] / se["note_hv_total"] * 100)
        notes_rel = _rel(cov_pct, team_median_notes_pct)
        if cov_pct <= 50:
            missing = se["note_hv_total"] - se["note_hv_covered"]
            flags.append(("RISK", (
                f"{se['note_hv_covered']}/{se['note_hv_total']} opps documented ({cov_pct}%) — "
                f"{missing} deal{'s' if missing > 1 else ''} missing notes. "
                f"Team median: {team_median_notes_pct}% coverage."
            )))
        elif cov_pct == 100 and se["note_hv_avg_entries"] >= 5:
            flags.append(("STRENGTH", (
                f"Notes discipline — {se['note_hv_avg_entries']} avg history entries on "
                f"{se['note_hv_total']} opps. Team median coverage: {team_median_notes_pct}%."
            )))
        else:
            flags.append(("NOTES", (
                f"{se['note_hv_covered']}/{se['note_hv_total']} opps documented ({cov_pct}%) — "
                f"{notes_rel} (team median {team_median_notes_pct}%)."
            )))

    return flags


def compute_team_medians(ses: list) -> dict:
    """Team-level medians for display in SE profile stat boxes."""
    act_ses   = [s for s in ses if s["act_wins"] > 0]
    exp_ses   = [s for s in ses if s["exp_wins"] > 0]
    notes_ses = [s for s in ses if s["note_hv_total"] > 0]

    def med(lst):
        return round(statistics.median(lst)) if lst else 0

    return {
        "total_icav": med([s["total_icav"] for s in ses]),
        "act_wins":   med([s["act_wins"]   for s in act_ses]),
        "act_icav":   med([s["act_icav"]   for s in act_ses]),
        "act_median": med([s["act_median"] for s in act_ses if s["act_median"] > 0]),
        "exp_wins":   med([s["exp_wins"]   for s in exp_ses]),
        "exp_icav":   med([s["exp_icav"]   for s in exp_ses]),
        "exp_median": med([s["exp_median"] for s in exp_ses if s["exp_median"] > 0]),
        "notes_pct":  round(statistics.median(
            [s["note_hv_covered"] / s["note_hv_total"] * 100 for s in notes_ses]
        )) if notes_ses else 0,
    }


def collect_team_trends(ses):
    trends = []
    n = len(ses)

    # EXPANSION
    growing   = [se for se in ses if se["exp_growing"]]
    retaining = [se for se in ses if not se["exp_growing"] and se["exp_wins"] > 0]
    flat      = [se for se in ses if se["exp_wins"] == 0]
    trends.append(("EXPANSION", (
        f"{len(growing)} of {n} SEs show a positive expansion median — accounts genuinely upselling. "
        f"{len(retaining)} retaining at $0 median. {len(flat)} with no expansion contribution."
    )))

    # ACTIVATE — deal quality + volume issues
    act_ses    = [se for se in ses if se["act_wins"] > 0]
    if act_ses:
        act_medians      = [se["act_median"] for se in act_ses if se["act_median"] > 0]
        team_act_median  = round(statistics.median(act_medians)) if act_medians else 0
        low_floor        = [se for se in act_ses if se["act_wins"] >= 5 and se["act_median"] < ACT_AVG_SIZE_WARNING]
        whale_dep        = [se for se in act_ses if se["act_wins"] >= 4 and se["act_median"] > 0
                            and se["act_avg"] / se["act_median"] >= 2.5]
        msg = f"Team activate median {fmt(team_act_median)}."
        if low_floor:
            msg += f" {len(low_floor)} SE{'s' if len(low_floor) > 1 else ''} closing high volume below the ${ACT_AVG_SIZE_WARNING//1000}K floor."
        if whale_dep:
            msg += f" {len(whale_dep)} SE{'s' if len(whale_dep) > 1 else ''} with high avg/median variance — whale-dependent quarters."
        trends.append(("ACTIVATE", msg))

    # MOTION
    act_only = [se for se in ses if se["total_icav"] > 0 and se["act_icav"] / se["total_icav"] > 0.85 and se["act_icav"] > 200_000]
    exp_only = [se for se in ses if se["total_icav"] > 0 and se["exp_icav"] / se["total_icav"] > 0.85 and se["exp_icav"] > 200_000]
    if act_only or exp_only:
        trends.append(("MOTION", (
            f"{len(act_only)} SE{'s' if len(act_only) != 1 else ''} running activate-only (>85% from new logos). "
            f"{len(exp_only)} SE{'s' if len(exp_only) != 1 else ''} expansion-only."
        )))

    # PIPELINE — email engagement
    pipe_ses        = [se for se in ses if (se.get("email_act_outq", 0) + se.get("email_exp_outq", 0)) > 0]
    zero_email      = [se for se in ses if (se.get("email_act_outq", 0) + se.get("email_exp_outq", 0)
                                           + se.get("email_act_inq", 0) + se.get("email_exp_inq", 0)) == 0]
    total_pipe_icav   = sum(se.get("email_act_outq_icav", 0) + se.get("email_exp_outq_icav", 0) for se in ses)
    total_pipe_emails = sum(se.get("email_act_outq", 0) + se.get("email_exp_outq", 0) for se in ses)
    pipe_msg = f"{len(pipe_ses)} of {n} SEs building pipeline via email — {total_pipe_emails} outq emails"
    if total_pipe_icav > 0:
        pipe_msg += f", {fmt(total_pipe_icav)} in tracked future deals"
    pipe_msg += "."
    if zero_email:
        pipe_msg += f" {len(zero_email)} SE{'s' if len(zero_email) > 1 else ''} with zero email activity recorded."
    trends.append(("PIPELINE", pipe_msg))

    # MEETINGS — calendar activity
    def _meet_total(se):
        return (se.get("meeting_act_inq", 0) + se.get("meeting_act_outq", 0) +
                se.get("meeting_exp_inq", 0) + se.get("meeting_exp_outq", 0))
    meet_ses       = [se for se in ses if _meet_total(se) > 0]
    zero_meetings  = [se for se in ses if _meet_total(se) == 0]
    total_meetings = sum(_meet_total(se) for se in ses)
    total_meet_pipe = sum(se.get("meeting_act_outq", 0) + se.get("meeting_exp_outq", 0) for se in ses)
    if total_meetings > 0:
        meet_msg = (f"{len(meet_ses)} of {n} SEs have logged meetings — "
                    f"{total_meetings} total ({total_meet_pipe} on pipeline opps).")
        if zero_meetings:
            meet_msg += f" {len(zero_meetings)} SE{'s' if len(zero_meetings) > 1 else ''} with zero meetings recorded."
        trends.append(("MEETINGS", meet_msg))

    # RISK — revenue concentration + notes gap
    sorted_icav = sorted(ses, key=lambda x: x["total_icav"], reverse=True)
    top2_total  = sum(se["total_icav"] for se in sorted_icav[:2])
    team_total  = sum(se["total_icav"] for se in ses)
    top2_pct    = round(top2_total / team_total * 100) if team_total else 0
    risk_msg    = (
        f"Top 2 SEs account for {top2_pct}% of team iACV ({fmt(top2_total)} of {fmt(team_total)}). "
        f"{'High concentration — fragile if top performers slip.' if top2_pct > 50 else 'Revenue reasonably distributed.'}"
    )
    hv_ses = [se for se in ses if se["note_hv_total"] > 0]
    if hv_ses:
        team_hv_covered = sum(se["note_hv_covered"] for se in hv_ses)
        team_hv_total   = sum(se["note_hv_total"] for se in hv_ses)
        notes_pct       = round(team_hv_covered / team_hv_total * 100) if team_hv_total else 0
        no_notes        = sum(1 for se in hv_ses if se["note_hv_covered"] == 0)
        if notes_pct < 70 or no_notes > 0:
            risk_msg += (
                f" Notes gap: {team_hv_covered}/{team_hv_total} high-value opps documented ({notes_pct}%)"
                + (f", {no_notes} SE{'s' if no_notes > 1 else ''} with none" if no_notes else "")
                + "."
            )
    trends.append(("RISK", risk_msg))

    return trends


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def generate_recommendations(ses: list, motion: str = "dsr") -> list:
    """
    Data-driven recommendations for the SE org leader.
    Returns list of {"cat": str, "title": str, "body": str}.

    Sources used (no email/note body text — all structural signals):
      - Email and meeting inq/outq counts (where SEs spend activity time)
      - tw_opps_detail per SE (opp-level note coverage, iACV, motion)
      - Win rate, deal sizing (act_median, act_avg), concentration
      - Expansion ARR/MRR signals, exp_status
      - Composite ranking scores
    """
    recs = []
    n = len(ses)
    if n < 2:
        return recs

    act_lbl = "new business" if motion == "ae" else "activate"
    exp_lbl = "strategic"    if motion == "ae" else "expansion"

    # ── Aggregates ────────────────────────────────────────────────────────────
    team_total_icav  = sum(s["total_icav"]  for s in ses)
    team_act_icav    = sum(s["act_icav"]    for s in ses)
    team_exp_icav    = sum(s["exp_icav"]    for s in ses)
    team_act_wins    = sum(s["act_wins"]    for s in ses)
    team_exp_wins    = sum(s["exp_wins"]    for s in ses)

    total_emails_inq  = sum(s.get("email_act_inq",  0) + s.get("email_exp_inq",  0) for s in ses)
    total_emails_outq = sum(s.get("email_act_outq", 0) + s.get("email_exp_outq", 0) for s in ses)
    total_meet_inq    = sum(s.get("meeting_act_inq",  0) + s.get("meeting_exp_inq",  0) for s in ses)
    total_meet_outq   = sum(s.get("meeting_act_outq", 0) + s.get("meeting_exp_outq", 0) for s in ses)
    total_pipe_icav   = sum(s.get("email_act_outq_icav", 0) + s.get("email_exp_outq_icav", 0) for s in ses)

    # Aggregate all TW opp detail rows across every SE
    all_opps = [o for s in ses for o in s.get("tw_opps_detail", [])]

    # ── 1. Time allocation: in-Q vs pipeline ─────────────────────────────────
    total_emails = total_emails_inq + total_emails_outq
    total_meets  = total_meet_inq + total_meet_outq
    if total_emails > 0:
        inq_email_pct  = round(total_emails_inq  / total_emails * 100)
        outq_email_pct = round(total_emails_outq / total_emails * 100)
        inq_meet_pct   = round(total_meet_inq  / total_meets * 100) if total_meets > 0 else 0
        outq_meet_pct  = round(total_meet_outq / total_meets * 100) if total_meets > 0 else 0
        meet_str = (f" Meetings follow the same pattern: {inq_meet_pct}% in-Q, {outq_meet_pct}% pipeline."
                    if total_meets > 0 else "")
        if inq_email_pct >= 65:
            recs.append({
                "cat":   "PIPELINE",
                "title": f"SE effort is {inq_email_pct}% in-quarter — next quarter is underfunded",
                "body":  (
                    f"{total_emails_inq} of {total_emails} emails target opps closing this period. "
                    f"Only {total_emails_outq} emails build future pipeline"
                    + (f" ({fmt(total_pipe_icav)} in tracked deals)" if total_pipe_icav else "") + "."
                    + meet_str
                    + " Recommend a team target of 40–50% outbound pipeline activity."
                ),
            })
        elif outq_email_pct >= 55 and total_pipe_icav > team_total_icav * 0.5:
            recs.append({
                "cat":   "PIPELINE",
                "title": f"Pipeline investment is healthy — {fmt(total_pipe_icav)} in future deals",
                "body":  (
                    f"{outq_email_pct}% of emails target future pipeline. "
                    f"{fmt(total_pipe_icav)} tracked across next-quarter opportunities. "
                    "Maintain this cadence to keep the next quarter loaded."
                ),
            })

    # ── 2. Pipeline concentration ─────────────────────────────────────────────
    if total_emails_outq > 0:
        se_outq = sorted(ses, key=lambda s: s.get("email_act_outq", 0) + s.get("email_exp_outq", 0), reverse=True)
        top1_outq = se_outq[0].get("email_act_outq", 0) + se_outq[0].get("email_exp_outq", 0)
        top2_outq = top1_outq + (se_outq[1].get("email_act_outq", 0) + se_outq[1].get("email_exp_outq", 0) if n >= 2 else 0)
        top2_pct  = round(top2_outq / total_emails_outq * 100)
        zero_pipe = [s for s in ses if s.get("email_act_outq", 0) + s.get("email_exp_outq", 0) == 0]
        if top2_pct >= 70 and len(zero_pipe) >= 2:
            recs.append({
                "cat":   "COACHING",
                "title": f"Pipeline building concentrated in {min(2,n-len(zero_pipe))} SE{'s' if min(2,n-len(zero_pipe))>1 else ''}",
                "body":  (
                    f"Top 2 SEs account for {top2_pct}% of all pipeline emails. "
                    f"{len(zero_pipe)} SE{'s' if len(zero_pipe)>1 else ''} sent zero pipeline emails this period. "
                    "If top builders miss next quarter, the team has no bench. "
                    "Coach zero-pipeline SEs on prospecting cadence."
                ),
            })

    # ── 3. Deal sizing — activate median below floor ──────────────────────────
    act_ses = [s for s in ses if s["act_wins"] >= 2]
    if act_ses:
        act_medians = [s["act_median"] for s in act_ses if s["act_median"] > 0]
        if act_medians:
            team_act_med = round(statistics.median(act_medians))
            below_floor  = [s for s in act_ses if s["act_median"] < ACT_AVG_SIZE_WARNING and s["act_wins"] >= 3]
            whale_dep    = [s for s in act_ses if s["act_wins"] >= 4 and s["act_median"] > 0
                            and s["act_avg"] / s["act_median"] >= 2.5]
            if team_act_med < ACT_AVG_SIZE_WARNING:
                recs.append({
                    "cat":   "REVENUE",
                    "title": f"Team {act_lbl} median {fmt(team_act_med)} is below the ${ACT_AVG_SIZE_WARNING//1000}K deal floor",
                    "body":  (
                        f"{len(below_floor)} SE{'s' if len(below_floor)>1 else ''} closing high volume under ${ACT_AVG_SIZE_WARNING//1000}K. "
                        f"Shifting the median to ${ACT_AVG_SIZE_WARNING//1000}K+ would add "
                        f"~{fmt(round((ACT_AVG_SIZE_WARNING - team_act_med) * team_act_wins))} in team iACV at the same win count. "
                        "Focus coaching on deal qualification and minimum viable scope."
                    ),
                })
            if whale_dep:
                recs.append({
                    "cat":   "REVENUE",
                    "title": f"{len(whale_dep)} SE{'s' if len(whale_dep)>1 else ''} whale-dependent — avg vs median gap signals outlier quarters",
                    "body":  (
                        ("Their" if len(whale_dep)==1 else "These SEs'") +
                        " quarters are propped up by one large deal. "
                        "High avg/median ratio (≥2.5×) means a missed whale collapses the number. "
                        "Encourage consistent mid-size deal flow alongside the large pursuits."
                    ),
                })

    # ── 4. Expansion untapped — high ARR, flat MRR ───────────────────────────
    exp_ses_with_arr = [s for s in ses if s.get("exp_arr_total", 0) > 0]
    if exp_ses_with_arr:
        contracting  = [s for s in exp_ses_with_arr if s.get("exp_status") == "Contracting"]
        flat_big_arr = [s for s in exp_ses_with_arr
                        if s.get("exp_status") in ("Retaining", "Expanding")
                        and s.get("exp_arr_total", 0) > 200_000]
        total_flat_arr = sum(s.get("exp_arr_total", 0) for s in flat_big_arr)
        if flat_big_arr:
            recs.append({
                "cat":   "EXPANSION",
                "title": f"{fmt(total_flat_arr)} ARR sitting flat — expansion opportunity for {len(flat_big_arr)} SE{'s' if len(flat_big_arr)>1 else ''}",
                "body":  (
                    f"{len(flat_big_arr)} SE{'s' if len(flat_big_arr)>1 else ''} {'have' if len(flat_big_arr)>1 else 'has'} "
                    f"large ARR accounts showing flat or Retaining status. "
                    "Accounts with $200K+ ARR and no MRR growth are candidates for new use-case expansion. "
                    "Prioritise account mapping and QBRs with these customers."
                ),
            })
        if contracting:
            contr_arr = sum(s.get("exp_arr_total", 0) for s in contracting)
            recs.append({
                "cat":   "RISK",
                "title": f"{len(contracting)} SE{'s' if len(contracting)>1 else ''} with contracting accounts — {fmt(contr_arr)} ARR at risk",
                "body":  (
                    f"{'These SEs touch' if len(contracting)>1 else 'This SE touches'} accounts "
                    f"where quarter MRR dropped ≥5%. Contraction in expansion accounts compresses "
                    "net revenue even when new logo wins look healthy. Investigate churn drivers."
                ),
            })

    # ── 5. Notes → attribution gap ───────────────────────────────────────────
    if all_opps:
        hv_opps     = [o for o in all_opps if o["icav"] >= 50_000]
        hv_covered  = sum(1 for o in hv_opps if o["has_notes"] and o["has_history"])
        hv_total    = len(hv_opps)
        hv_pct      = round(hv_covered / hv_total * 100) if hv_total else 0

        # iACV breakdown by coverage
        covered_icav   = sum(o["icav"] for o in hv_opps if o["has_notes"] and o["has_history"])
        uncovered_icav = sum(o["icav"] for o in hv_opps if not (o["has_notes"] and o["has_history"]))

        if hv_pct < 70 and uncovered_icav > 0:
            recs.append({
                "cat":   "HYGIENE",
                "title": f"{100-hv_pct}% of high-value opps undocumented — {fmt(uncovered_icav)} iACV without SE notes",
                "body":  (
                    f"{hv_covered}/{hv_total} opps ≥$50K have both SE notes fields filled ({hv_pct}% coverage). "
                    f"{fmt(uncovered_icav)} in closed wins has no SE attribution documented. "
                    "Undocumented wins are invisible in attribution reports and harder to replicate. "
                    "Set a team expectation: all opps ≥$50K require notes before quarter close."
                ),
            })

        # Attention distribution: what share of total opp count drives the iACV?
        if all_opps:
            sorted_opps   = sorted(all_opps, key=lambda o: o["icav"], reverse=True)
            top20_count   = max(1, round(len(sorted_opps) * 0.20))
            top20_icav    = sum(o["icav"] for o in sorted_opps[:top20_count])
            top20_pct_rev = round(top20_icav / team_total_icav * 100) if team_total_icav else 0
            top20_noted   = sum(1 for o in sorted_opps[:top20_count] if o["has_notes"] and o["has_history"])
            top20_noted_pct = round(top20_noted / top20_count * 100)
            recs.append({
                "cat":   "EFFICIENCY",
                "title": f"Top 20% of opps ({top20_count} deals) drive {top20_pct_rev}% of team iACV",
                "body":  (
                    f"The {top20_count} highest-value closed wins represent {fmt(top20_icav)} of "
                    f"{fmt(team_total_icav)} total iACV. "
                    f"{top20_noted_pct}% of these high-impact deals have full SE notes. "
                    + (f"The {top20_count - top20_noted} undocumented top-20% deals are the highest-leverage notes gap to close."
                       if top20_noted < top20_count else
                       "All top-20% deals are fully documented — strong discipline on the deals that matter most.")
                ),
            })

    # ── 6. Win rate — qualification signal ───────────────────────────────────
    wr_ses = [s for s in ses if (s.get("closed_won", 0) + s.get("closed_lost", 0)) >= 4]
    if wr_ses:
        wr_vals   = [s["win_rate"] for s in wr_ses]
        team_wr   = round(statistics.mean(wr_vals))
        low_wr    = [s for s in wr_ses if s["win_rate"] < 40]
        high_wr   = [s for s in wr_ses if s["win_rate"] >= 75]
        if low_wr:
            recs.append({
                "cat":   "COACHING",
                "title": f"{len(low_wr)} SE{'s' if len(low_wr)>1 else ''} below 40% win rate — deal qualification gap",
                "body":  (
                    f"Team average win rate: {team_wr}%. "
                    f"{len(low_wr)} SE{'s' if len(low_wr)>1 else ''} {'are' if len(low_wr)>1 else 'is'} closing fewer than 40% of contested deals. "
                    "Low win rates at high volume burn SE capacity on deals they won't close. "
                    "Review deal selection criteria: are SEs chasing unwinnable opps?"
                ),
            })
        if high_wr and len(high_wr) < n // 2:
            top_wr_se  = max(wr_ses, key=lambda s: s["win_rate"])
            recs.append({
                "cat":   "COACHING",
                "title": f"Win rate gap: {top_wr_se['win_rate']}% top vs {min(wr_vals)}% bottom — spread insights",
                "body":  (
                    f"{len(high_wr)} SE{'s' if len(high_wr)>1 else ''} at ≥75% win rate vs {len(low_wr)} below 40%. "
                    f"The delta suggests a discovery or qualification pattern difference. "
                    "Pair high-win-rate SEs with lower performers for deal review sessions."
                ),
            })

    # ── 7. Meeting investment vs email investment ─────────────────────────────
    if total_emails > 0 and total_meets > 0:
        meet_per_email = round(total_meets / total_emails, 2)
        if meet_per_email < 0.2:
            recs.append({
                "cat":   "EFFICIENCY",
                "title": "SE engagement is primarily email-based — meetings underutilised",
                "body":  (
                    f"{total_meets} meetings logged vs {total_emails} emails "
                    f"({round(meet_per_email*100)}% meeting-to-email ratio). "
                    "High-value expansion accounts typically close faster with live touchpoints. "
                    "For $100K+ opps, target at least one recorded meeting per quarter close."
                ),
            })
        elif meet_per_email > 1.5:
            recs.append({
                "cat":   "EFFICIENCY",
                "title": "High meeting load relative to emails — check async engagement balance",
                "body":  (
                    f"{total_meets} meetings vs {total_emails} emails. "
                    "Heavy meeting investment may be appropriate for enterprise deals, but "
                    "ensure async email follow-up is happening to advance opps between calls."
                ),
            })

    return recs


# ---------------------------------------------------------------------------
# Save se_data.json
# ---------------------------------------------------------------------------

import json

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
    max_icav      = max(total_icavs)

    act_ses       = [s for s in ranked if s["act_wins"] > 0]
    max_act_wins  = max(s["act_wins"] for s in ranked) if ranked else 0
    min_act_wins  = min(s["act_wins"] for s in act_ses) if act_ses else 0

    exp_ses        = [s for s in ranked if s["exp_wins"] > 0]
    max_exp_wins   = max(s["exp_wins"] for s in ranked) if ranked else 0
    max_exp_icav   = max(s["exp_icav"] for s in ranked) if ranked else 0
    max_act_icav   = max(s["act_icav"] for s in ranked) if ranked else 0

    pipe_totals    = [s.get("email_act_outq", 0) + s.get("email_exp_outq", 0) for s in ranked]
    max_pipe       = max(pipe_totals) if pipe_totals else 0
    se_pipe        = se.get("email_act_outq", 0) + se.get("email_exp_outq", 0)

    notes_pcts     = [round(s["note_hv_covered"] / s["note_hv_total"] * 100)
                      for s in ranked if s["note_hv_total"] > 0]
    max_notes_pct  = max(notes_pcts) if notes_pcts else 0
    se_notes_pct   = round(se["note_hv_covered"] / se["note_hv_total"] * 100) if se["note_hv_total"] > 0 else 0

    total_wins     = se["act_wins"] + se["exp_wins"]
    max_total_wins = max(s["act_wins"] + s["exp_wins"] for s in ranked) if ranked else 0

    act_lbl = "new business" if motion == "ae" else "activate"
    exp_lbl = "strategic"    if motion == "ae" else "expansion"

    # ── Unique-stat checks (priority order) ──────────────────────────────────

    # Rank 1
    if rank == 1 and n > 1:
        pct = round(se["total_icav"] / team_icav * 100) if team_icav else 0
        gap = fmt(se["total_icav"] - ranked[1]["total_icav"])
        if pct >= 30:
            return f"Carrying {pct}% of the team's quarter on their back. 🐐"
        return f"Led the board by {gap} over #2. Comfortable at the top. 🏆"

    # Dead last
    if rank == n and n > 1:
        return f"Last on the board this quarter. Not the final chapter. 📈"

    # Volume leader — dominating win count
    if se["act_wins"] == max_act_wins and max_act_wins >= 5:
        others = sum(s["act_wins"] for s in ranked) - se["act_wins"]
        return f"{se['act_wins']} wins while the other {n-1} combined for {others}. Not the same sport. 🏭"

    # Rank 2 — chasing the top
    if rank == 2:
        gap = fmt(ranked[0]["total_icav"] - se["total_icav"])
        return f"Only {gap} behind #1. Hunting. 🔥"

    # Rank 3
    if rank == 3:
        return f"Top 3 and not done building. The podium suits them. 🔥"

    # Expansion king by wins
    if se["exp_wins"] == max_exp_wins and max_exp_wins >= 15 and se["exp_wins"] > se["act_wins"]:
        return f"Doesn't chase new logos — turns every existing account into a bigger one. ♟️"

    # Expansion king by iACV
    if se["exp_icav"] == max_exp_icav and max_exp_icav > 0 and se["exp_wins"] >= 5:
        return f"Owns the install base. {fmt(se['exp_icav'])} says the accounts trust them. 🔒"

    # Highest act iACV
    if se["act_icav"] == max_act_icav and max_act_icav > 0 and se["act_icav"] > median_icav:
        return f"Closes the deals that move the number. Top {act_lbl} producer on the team. 💥"

    # Heavily concentrated quarter
    if se["conc"] >= 70:
        return f"One deal. One meeting that changed the quarter. {fmt(se['largest_deal_value'])} later, here we are. 🎲"

    # Moderate concentration with big deal
    if se["conc"] >= 50 and se["largest_deal_value"] >= 200_000:
        return f"Bet big on one deal and won. That's how {fmt(se['largest_deal_value'])} quarters get built. 🎯"

    # Whale-dependent
    if se["act_wins"] >= 4 and se["act_median"] > 0 and se["act_avg"] / se["act_median"] >= 2.5:
        return f"One whale propped up the whole quarter. Skilled or lucky — the board doesn't care. 🐋"

    # Consistent closer
    if se["act_wins"] >= 5 and se["act_median"] > 0 and se["act_avg"] / se["act_median"] < 1.15 and se["act_median"] >= 40_000:
        return f"No spikes, no dry spells — {se['act_wins']} wins at {fmt(se['act_median'])} median. The model of consistency. 📐"

    # Top pipeline builder
    if se_pipe == max_pipe and max_pipe >= 10 and n > 1:
        return f"While everyone else closed this quarter, they were already building next one. 📬"

    # Perfect notes discipline
    if se_notes_pct == 100 and se["note_hv_total"] >= 5 and se_notes_pct == max_notes_pct:
        return f"Every deal documented, every note filed. Cleanest record on the team. 📋"

    # High win rate
    if se.get("win_rate", 0) >= 75 and (se.get("closed_won", 0) + se.get("closed_lost", 0)) >= 6:
        return f"{se['win_rate']}% win rate. Doesn't chase deals they can't close. 🎯"

    # High volume, modest iACV — small deal factory
    if total_wins >= 12 and se["total_icav"] < median_icav:
        return f"{total_wins} wins on the board — needs bigger deals to match the effort. ⚙️"

    # Fewest wins
    if se["act_wins"] == min_act_wins and min_act_wins > 0 and se["act_wins"] <= 2 and n > 3:
        return f"Fewest wins on the team this quarter. The work is there — the board isn't catching up yet. 🕰️"

    # Well above median
    if se["total_icav"] >= median_icav * 1.5:
        return f"Running well above the pack. Pulls the team average up just by being on it. 📊"

    # Right at median
    if abs(se["total_icav"] - median_icav) / max(median_icav, 1) <= 0.20:
        return f"Right at team median — solid, consistent, reliable. The definition of dependable. 🧱"

    # Below median, upper half of table
    if se["total_icav"] < median_icav and rank <= n // 2:
        return f"Just below the median but trending the right direction. 💪"

    # Below median, lower half
    if se["total_icav"] < median_icav:
        gap = fmt(median_icav - se["total_icav"])
        return f"{gap} off the team median. That gap is closable. 💪"

    # Tier-based fallback with win count for differentiation
    wins_str = f"{total_wins} win{'s' if total_wins != 1 else ''}"
    return {"Elite":   f"Elite tier. {wins_str} and still finding ways to push higher. 👑",
            "Strong":  f"Strong quarter — {wins_str}, no shortcuts taken. 🔥",
            "Steady":  f"{wins_str} and holding steady. The backbone of the team. 🧱",
            "Develop": f"{wins_str} this quarter. The comeback starts here. 🙏"}.get(t, f"{wins_str} this quarter. 📋")
