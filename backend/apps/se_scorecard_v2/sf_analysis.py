"""
SE Scorecard V2 — data layer.
Computes the same SE metrics as se_analysis.py but from live Salesforce opportunity records.
Owl scores (Salesforce hygiene %) still come from a CSV upload.
"""

import statistics
from pathlib import Path

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
    Fallback to FY_16_Owner_Team__c when owner has changed since close."""
    role = _owner_role(opp)
    if "Activation" in role:
        return True
    if "Expansion" in role:
        return False
    team = _team(opp)
    return "DSR" in team and "Expansion" not in team


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

def build_ses(opps: list, motion: str = "dsr") -> list:
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

        # Notes quality on all closed won opps in the query (already filtered by icav_min at SOQL level)
        hv_opps           = list(d["all_opps"])
        note_hv_total     = len(hv_opps)
        note_hv_covered   = sum(1 for o in hv_opps if o.get("Sales_Engineer_Notes__c") and o.get("SE_Notes_History__c"))
        note_hv_entries   = sum(_history_entries(o.get("SE_Notes_History__c") or "") for o in hv_opps)
        note_hv_avg_entries = round(note_hv_entries / note_hv_total, 1) if note_hv_total > 0 else 0

        # Largest deal
        all_icavs = [(o, _icav(o)) for o in d["all_opps"]]
        largest_opp, largest_val = max(all_icavs, key=lambda x: x[1]) if all_icavs else (None, 0)
        largest_name = (largest_opp.get("Name") or "") if largest_opp else ""
        largest_dsr  = ((largest_opp.get("Owner") or {}).get("Name") or "") if largest_opp else ""

        conc = round(largest_val / total_icav * 100) if total_icav > 0 and largest_val > 0 else 0

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
            "largest_deal":      largest_name,
            "largest_deal_value": largest_val,
            "largest_deal_dsr":  largest_dsr,
            "tw_opps_detail":    tw_opps_detail,
        }

        se["total_icav"]       = total_icav
        se["future_emails"]    = 0
        se["future_pct"]       = 0
        se["act_target_pct"]   = 0
        se["exp_target_pct"]   = 0
        se["exp_growing"]      = exp_median > 0
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

def merge_win_rate(ses: list, win_rate_opps: list):
    """Merge closed won/lost counts into SE records. Mutates ses in place."""
    lookup: dict[str, dict] = {}
    for opp in win_rate_opps:
        tl   = opp.get("Technical_Lead__r") or {}
        name = (tl.get("Name") or "").strip()
        if not name:
            continue
        if name not in lookup:
            lookup[name] = {"won": 0, "lost": 0}
        if opp.get("StageName") == "Closed Won":
            lookup[name]["won"] += 1
        else:
            lookup[name]["lost"] += 1

    for se in ses:
        wr              = lookup.get(se["name"], {"won": 0, "lost": 0})
        total           = wr["won"] + wr["lost"]
        se["closed_won"]  = wr["won"]
        se["closed_lost"] = wr["lost"]
        se["win_rate"]    = round(wr["won"] / total * 100) if total > 0 else 0


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
# Ranking (identical weights to se_analysis.py)
# ---------------------------------------------------------------------------

def rank_ses(ses):
    """
    Ranking criteria (lower rank_score = better):

    Lexicographic sort — each criterion is a strict tiebreaker for the one before it:
      1. Total iACV        (highest iACV always ranks highest — no weighting can override)
      2. Notes coverage    note_hv_covered / note_hv_total on high-value opps
      3. Win count         act_wins + exp_wins — same iACV + same notes rate, more deals wins
    """
    def sort_key(se):
        notes_rate = se["note_hv_covered"] / max(se["note_hv_total"], 1)
        wins = se["act_wins"] + se["exp_wins"]
        return (-se["total_icav"], -notes_rate, -wins)

    ranked = sorted(ses, key=sort_key)
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


def _roast(se, ranked):
    max_act_wins = max(s["act_wins"] for s in ranked)
    min_act_wins = min(s["act_wins"] for s in ranked if s["act_wins"] > 0) if any(s["act_wins"] > 0 for s in ranked) else 0

    if se["act_wins"] == max_act_wins and max_act_wins > 0:
        others = sum(s["act_wins"] for s in ranked) - se["act_wins"]
        return f"{se['act_wins']} activate wins. The other {len(ranked)-1} SEs combined for {others}. Not playing the same sport. 🏭"

    if se["exp_wins"] >= 30:
        return f"{se['exp_wins']} expansion wins. Already mentally in next quarter. ♟️"

    if se["conc"] >= 65:
        return f"{se['conc']}% of the quarter came from one deal. Masterclass or a prayer. 🎲"

    if se["act_wins"] == min_act_wins and min_act_wins > 0:
        return f"{se['act_wins']} activate wins. Fewest on the team. The comeback arc starts now. 📉"

    if se["act_wins"] >= 5 and se["act_median"] > 0 and se["act_avg"] / se["act_median"] < 1.15:
        return f"{fmt(se['act_avg'])} avg, {fmt(se['act_median'])} median. Most consistent closer on the team. 📐"

    t = tier(next(i for i, s in enumerate(ranked, 1) if s["name"] == se["name"]), len(ranked))
    return {"Elite": "Quietly elite. No drama, just revenue. 👑",
            "Strong": "Doing the work. Every quarter. 🔥",
            "Steady": "Steady and reliable. The backbone. 🧱",
            "Develop": "The comeback arc is still being written. 🙏"}.get(t, "Getting it done. 📋")
