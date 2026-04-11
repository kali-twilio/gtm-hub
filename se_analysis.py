#!/usr/bin/env python3
"""SE Scorecard — data layer. Called by app.py."""

import csv
import sys
import json
from pathlib import Path

EXCLUDE = {"Nitin Dua", "Q1"}

OWL_WARNING_THRESHOLD        = 75
ACT_AVG_SIZE_WARNING         = 40_000
FUTURE_PIPELINE_STRONG       = 60
FUTURE_PIPELINE_WEAK         = 30
DEAL_CONCENTRATION_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_dollar(value):
    if not value or value.strip() in ("", "-", "N/A"):
        return 0
    v = value.strip().lstrip("$").replace(",", "")
    try:
        if "M" in v: return int(float(v.replace("M", "")) * 1_000_000)
        if "K" in v: return int(float(v.replace("K", "")) * 1_000)
        return int(float(v))
    except (ValueError, AttributeError):
        return 0

def parse_pct(value):
    if not value or value.strip() in ("", "-"):
        return 0
    try:
        return int(value.strip().rstrip("%"))
    except ValueError:
        return 0

def parse_int(value):
    if not value or value.strip() in ("", "-"):
        return 0
    try:
        return int(value.strip())
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def fmt(amount):
    if amount >= 1_000_000: return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:     return f"${amount / 1_000:.0f}K"
    return f"${amount}"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ses(filepath):
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    data_start = None
    for i, row in enumerate(rows):
        if len(row) > 1 and row[1].strip() == "SE":
            data_start = i + 1
            break

    if data_start is None:
        print("ERROR: Could not find SE header row.")
        sys.exit(1)

    ses = []
    for row in rows[data_start:]:
        if len(row) < 20:
            continue
        name = row[1].strip()
        if not name or name in EXCLUDE:
            continue
        if not row[2].strip().endswith("%"):
            continue

        se = {
            "name":      name,
            "owl_pct":   parse_pct(row[2]),
            "act_wins":  parse_int(row[3]),
            "act_icav":  parse_dollar(row[4]),
            "act_avg":   parse_dollar(row[5]),
            "act_median":parse_dollar(row[6]),
            "exp_wins":  parse_int(row[7]),
            "exp_icav":  parse_dollar(row[8]),
            "exp_avg":   parse_dollar(row[9]),
            "exp_median":parse_dollar(row[10]),
            "top_dsr":   row[11].strip(),
            "bot_dsr":   row[13].strip(),
            "email_act_total": parse_int(row[15]),
            "email_act_inq":   parse_int(row[16]),
            "email_act_noopp": parse_int(row[17]),
            "email_act_outq":  parse_int(row[18]),
            "email_exp_total": parse_int(row[19]),
            "email_exp_inq":   parse_int(row[20]),
            "email_exp_noopp": parse_int(row[21]),
            "email_exp_outq":  parse_int(row[22]),
            "largest_deal":       row[23].strip() if len(row) > 23 else "",
            "largest_deal_value": parse_dollar(row[24]) if len(row) > 24 else 0,
            "largest_deal_dsr":   row[25].strip() if len(row) > 25 else "",
        }

        se["total_icav"]    = se["act_icav"] + se["exp_icav"]
        se["future_emails"] = se["email_act_outq"] + se["email_exp_outq"]
        total_emails        = se["email_act_total"] + se["email_exp_total"]
        se["future_pct"]    = round(se["future_emails"] / total_emails * 100) if total_emails else 0
        se["act_target_pct"]= round(se["email_act_inq"] / se["email_act_total"] * 100) if se["email_act_total"] else 0
        se["exp_target_pct"]= round(se["email_exp_inq"] / se["email_exp_total"] * 100) if se["email_exp_total"] else 0
        se["exp_growing"]   = se["exp_median"] > 0
        se["conc"]          = round(se["largest_deal_value"] / se["total_icav"] * 100) if se["total_icav"] > 0 and se["largest_deal_value"] > 0 else 0

        ses.append(se)

    return ses


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_ses(ses):
    def assign_ranks(ses, key, reverse=True):
        ordered = sorted(ses, key=lambda x: x[key], reverse=reverse)
        return {se["name"]: i + 1 for i, se in enumerate(ordered)}

    r_total  = assign_ranks(ses, "total_icav")
    r_act    = assign_ranks(ses, "act_icav")
    r_exp_q  = assign_ranks(ses, "exp_median")
    r_future = assign_ranks(ses, "future_pct")
    r_owl    = assign_ranks(ses, "owl_pct")

    for se in ses:
        n = se["name"]
        se["rank_score"] = (
            r_total[n]  * 0.65 +
            r_act[n]    * 0.10 +
            r_exp_q[n]  * 0.10 +
            r_future[n] * 0.08 +
            r_owl[n]    * 0.07
        )

    return sorted(ses, key=lambda x: x["rank_score"])


def tier(rank, total):
    pct = rank / total
    if pct <= 0.20: return "Elite"
    if pct <= 0.50: return "Strong"
    if pct <= 0.75: return "Steady"
    return "Develop"


# ---------------------------------------------------------------------------
# Flags & roasts
# ---------------------------------------------------------------------------

def collect_se_flags(se, ses):
    flags = []
    team_emails     = [s["email_act_total"] + s["email_exp_total"] for s in ses]
    team_email_avg  = sum(team_emails) / len(team_emails)
    max_act_wins    = max(s["act_wins"] for s in ses)

    if se["owl_pct"] < OWL_WARNING_THRESHOLD:
        flags.append(("HYGIENE", f"{se['owl_pct']}% Owl — below {OWL_WARNING_THRESHOLD}% hygiene threshold."))

    if se["total_icav"] > 0:
        act_pct = se["act_icav"] / se["total_icav"]
        exp_pct = se["exp_icav"] / se["total_icav"]
        if act_pct > 0.85 and se["act_icav"] > 200_000:
            flags.append(("MOTION", f"{round(act_pct*100)}% activate-only — expansion not contributing."))
        elif exp_pct > 0.85 and se["exp_icav"] > 200_000:
            flags.append(("MOTION", f"{round(exp_pct*100)}% expansion-only — new business is light."))

    if se["total_icav"] > 0 and se["largest_deal_value"] > se["total_icav"] * DEAL_CONCENTRATION_THRESHOLD:
        pct = round(se["largest_deal_value"] / se["total_icav"] * 100)
        flags.append(("RISK", f"Largest deal = {pct}% of total iACV ({fmt(se['largest_deal_value'])})."))
    elif se["total_icav"] > 500_000 and se["largest_deal_value"] > 0:
        pct = round(se["largest_deal_value"] / se["total_icav"] * 100)
        if pct < 20:
            flags.append(("STRENGTH", f"Largest deal is {pct}% of iACV — revenue well distributed across deals."))

    if se["act_wins"] >= 5 and se["act_avg"] < ACT_AVG_SIZE_WARNING:
        flags.append(("ACTIVATE", f"{fmt(se['act_avg'])} avg on {se['act_wins']} wins — below ${ACT_AVG_SIZE_WARNING//1000}K floor."))

    if se["act_wins"] >= 4 and se["act_median"] > 0:
        ratio = se["act_avg"] / se["act_median"]
        if ratio >= 2.5:
            flags.append(("ACTIVATE", f"High variance — {fmt(se['act_avg'])} avg vs {fmt(se['act_median'])} median. Outlier deals driving total."))
        elif 1.0 <= ratio < 1.3 and se["act_wins"] >= 5 and se["act_avg"] >= ACT_AVG_SIZE_WARNING:
            flags.append(("ACTIVATE", f"Consistent sizing — {fmt(se['act_avg'])} avg vs {fmt(se['act_median'])} median. Repeatable deal pattern."))

    if se["act_wins"] == max_act_wins:
        flags.append(("ACTIVATE", f"Highest activate volume on team — {se['act_wins']} wins."))
    elif se["act_wins"] <= 5 and se["act_wins"] > 0:
        flags.append(("ACTIVATE", f"Low activate volume — {se['act_wins']} wins this quarter."))

    se_total_emails = se["email_act_total"] + se["email_exp_total"]
    if se["future_pct"] < FUTURE_PIPELINE_WEAK:
        flags.append(("PIPELINE", f"Only {se['future_pct']}% future pipeline — Q2+ runway is thin."))
    elif se["future_pct"] >= FUTURE_PIPELINE_STRONG:
        flags.append(("PIPELINE", f"{se['future_pct']}% future pipeline — {se['future_emails']} emails building Q2+."))

    if se_total_emails < team_email_avg * 0.45:
        flags.append(("PIPELINE", f"Low total activity — {se_total_emails} emails vs {round(team_email_avg)} team avg."))

    if se["exp_growing"]:
        flags.append(("EXPANSION", f"Growing — {fmt(se['exp_median'])} median. Accounts upselling."))
    elif se["exp_wins"] >= 10 and not se["exp_growing"]:
        flags.append(("EXPANSION", f"High renewal load — {se['exp_wins']} wins at $0 median. Flat retentions."))
    elif se["exp_icav"] > 0:
        flags.append(("EXPANSION", f"Retaining — $0 median on {se['exp_wins']} wins."))
    else:
        flags.append(("EXPANSION", "No expansion contribution this quarter."))

    return flags


def get_roast(se, ranked):
    max_act_wins = max(s["act_wins"] for s in ranked)
    min_emails   = min(s["email_act_total"] + s["email_exp_total"] for s in ranked)
    min_act_wins = min(s["act_wins"] for s in ranked if s["act_wins"] > 0)
    total_emails = se["email_act_total"] + se["email_exp_total"]

    if se["owl_pct"] < 50:
        return f"{se['owl_pct']}% Owl. The pipeline exists. Salesforce has no idea. A mystery wrapped in a closed deal. 🦉"

    if se["act_wins"] == max_act_wins:
        others = sum(s["act_wins"] for s in ranked) - se["act_wins"]
        return f"{se['act_wins']} activate wins. The other {len(ranked)-1} SEs combined for {others}. Not playing the same sport. 🏭"

    if "Santa" in se["largest_deal"]:
        return f"Closed {fmt(se['largest_deal_value'])} with Santa's AI Lab. Yes, Santa. The real MVP of Q1. 🎅"

    if se["exp_wins"] >= 30:
        return f"{se['exp_wins']} expansion wins and {se['future_emails']} emails building Q2+. Already mentally in next quarter. ♟️"

    if se["exp_icav"] > 1_000_000 and se["email_act_inq"] == 0:
        return f"{fmt(se['exp_icav'])} in expansion on zero activate in-Q emails. Ignored half the playbook. Still top 3. Infuriating. 🤔"

    if se["conc"] >= 65 and se["future_pct"] <= 15:
        return f"{se['conc']}% of the quarter came from one deal. Q2 pipeline at {se['future_pct']}%. Masterclass or a prayer. 🎲"

    if total_emails == min_emails:
        epm = round(se["total_icav"] / total_emails) if total_emails else 0
        return f"{total_emails} total emails. {fmt(se['total_icav'])} closed. {fmt(epm)} per email. Do not tell him to send more. 📧"

    if se["act_wins"] == min_act_wins:
        return f"{se['act_wins']} activate wins. Fewest on the team. The comeback arc starts now. 📉"

    if se["exp_wins"] >= 12 and not se["exp_growing"] and se["owl_pct"] == 100:
        return f"{se['exp_wins']} expansion wins at $0 median and a perfect Owl score. Ran every renewal, logged every note. Unsung. 🗂️"

    if se["act_wins"] >= 5 and se["act_median"] > 0 and se["act_avg"] / se["act_median"] < 1.15:
        return f"{fmt(se['act_avg'])} avg, {fmt(se['act_median'])} median. Most consistent closer on the team. Extremely bankable. 📐"

    t = tier(next(i for i, s in enumerate(ranked, 1) if s["name"] == se["name"]), len(ranked))
    return {"Elite": "Quietly elite. No drama, just revenue. 👑",
            "Strong": "Doing the work. Every quarter. 🔥",
            "Steady": "Steady and reliable. The backbone. 🧱",
            "Develop": "The comeback arc is still being written. 🙏"}.get(t, "Getting it done. 📋")


# ---------------------------------------------------------------------------
# Team trends
# ---------------------------------------------------------------------------

def collect_team_trends(ses):
    trends = []
    n = len(ses)

    growing   = [se for se in ses if se["exp_growing"]]
    retaining = [se for se in ses if not se["exp_growing"] and se["exp_icav"] > 0]
    flat      = [se for se in ses if se["exp_icav"] == 0]
    trends.append(("EXPANSION", (
        f"{len(growing)} of {n} SEs have a positive expansion median — accounts genuinely growing. "
        f"{len(retaining)} are retaining at $0 median. {len(flat)} have no expansion contribution."
    )))

    builders = [se for se in ses if se["future_pct"] >= FUTURE_PIPELINE_STRONG]
    weak     = [se for se in ses if se["future_pct"] < FUTURE_PIPELINE_WEAK]
    avg_fut  = round(sum(se["future_pct"] for se in ses) / n)
    trends.append(("PIPELINE", (
        f"Team avg future pipeline investment: {avg_fut}% of email activity. "
        f"{len(builders)} SE{'s' if len(builders)!=1 else ''} above {FUTURE_PIPELINE_STRONG}% (building Q2+). "
        f"{len(weak)} SE{'s' if len(weak)!=1 else ''} below {FUTURE_PIPELINE_WEAK}% (short-term focus only)."
    )))

    act_only = [se for se in ses if se["total_icav"] > 0 and se["act_icav"] / se["total_icav"] > 0.85 and se["act_icav"] > 200_000]
    exp_only = [se for se in ses if se["total_icav"] > 0 and se["exp_icav"] / se["total_icav"] > 0.85 and se["exp_icav"] > 200_000]
    if act_only or exp_only:
        trends.append(("MOTION", (
            f"{len(act_only)} SE{'s are' if len(act_only)!=1 else ' is'} running activate-only (>85% of iACV from new logos). "
            f"{len(exp_only)} SE{'s are' if len(exp_only)!=1 else ' is'} running expansion-only. "
            f"Two-motion operators generate more durable revenue."
        )))

    low_act = [se for se in ses if se["act_wins"] >= 5 and se["act_avg"] < ACT_AVG_SIZE_WARNING]
    if low_act:
        avg_team = round(sum(se["act_avg"] for se in ses if se["act_wins"] > 0) / sum(1 for se in ses if se["act_wins"] > 0))
        trends.append(("ACTIVATE", (
            f"{len(low_act)} SE{'s are' if len(low_act)!=1 else ' is'} closing high volumes of activate deals "
            f"below the ${ACT_AVG_SIZE_WARNING//1000}K avg threshold. "
            f"Team activate avg is {fmt(avg_team)}. Landing small may cap expansion potential."
        )))

    below_owl = [se for se in ses if se["owl_pct"] < OWL_WARNING_THRESHOLD]
    avg_owl   = round(sum(se["owl_pct"] for se in ses) / n)
    if below_owl:
        trends.append(("HYGIENE", (
            f"Team avg Owl: {avg_owl}%. "
            f"{len(below_owl)} SE{'s are' if len(below_owl)!=1 else ' is'} below the {OWL_WARNING_THRESHOLD}% threshold — "
            f"deals not being staged or documented, creating pipeline blind spots."
        )))
    else:
        trends.append(("HYGIENE", f"Team avg Owl: {avg_owl}%. All SEs above {OWL_WARNING_THRESHOLD}% hygiene threshold."))

    top2_total = sum(se["total_icav"] for se in sorted(ses, key=lambda x: x["total_icav"], reverse=True)[:2])
    team_total = sum(se["total_icav"] for se in ses)
    top2_pct   = round(top2_total / team_total * 100) if team_total else 0
    trends.append(("RISK", (
        f"Top 2 SEs account for {top2_pct}% of team iACV ({fmt(top2_total)} of {fmt(team_total)}). "
        f"{'High concentration — team performance is fragile if top performers have a down quarter.' if top2_pct > 50 else 'Revenue is reasonably distributed across the team.'}"
    )))

    return trends


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
        entry["roast"] = get_roast(se, ranked)
        payload.append(entry)
    json_path = Path(output_dir) / "se_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
