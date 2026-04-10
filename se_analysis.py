#!/usr/bin/env python3
"""
SE Scorecard Analyzer
---------------------
Usage: python se_analysis.py "DSR SE Scorecard - Roster.csv"

Reads a DSR SE Scorecard CSV and outputs ranked analysis across:
  - New business (Activate) performance
  - Land & expand (Expansion) performance
  - Forward pipeline investment (out-of-quarter emails)
  - Deal hygiene (Owl %)
  - Overall rankings with tier assignment

Context built into this script:
  - Activate = new logos, no prior contract, deals >$30K
  - Expansion = existing customers, includes flat renewals ($0 iACV) + upsell
    A $0 expansion median means most wins are flat retentions, not growth
  - Owl % = deal awareness + Salesforce hygiene (presales stage management)
  - Out-of-Q emails = pipeline being nurtured for future quarters
"""

import csv
import sys
from pathlib import Path

# SEs to exclude from analysis (e.g. data known to be incomplete)
# "Q1" is the summary row at the bottom of the CSV, not an SE
EXCLUDE = {"Nitin Dua", "Q1"}

# Thresholds for automated flags
OWL_WARNING_THRESHOLD = 75       # Owl % below this triggers a hygiene flag
ACT_AVG_SIZE_WARNING = 40_000    # Avg activate deal size below this is flagged (if 5+ wins)
FUTURE_PIPELINE_STRONG = 60      # Future email % above this = pipeline builder
FUTURE_PIPELINE_WEAK = 30        # Future email % below this = short-term focus only
DEAL_CONCENTRATION_THRESHOLD = 0.5  # Largest deal as % of activate iACV triggers flag


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_dollar(value):
    """Convert $1.5M / $126K / $0K strings to integer dollars."""
    if not value or value.strip() in ("", "-", "N/A"):
        return 0
    v = value.strip().lstrip("$").replace(",", "")
    try:
        if "M" in v:
            return int(float(v.replace("M", "")) * 1_000_000)
        elif "K" in v:
            return int(float(v.replace("K", "")) * 1_000)
        else:
            return int(float(v))
    except (ValueError, AttributeError):
        return 0


def parse_pct(value):
    """Convert '88%' to integer 88."""
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
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt(amount):
    """Format dollar amount as $1.5M / $126K / $0."""
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    else:
        return f"${amount}"


def fmt_pct(value):
    return f"{value}%"


def bar(value, max_value, width=20):
    """Simple ASCII bar chart."""
    if max_value == 0:
        return " " * width
    filled = int((value / max_value) * width)
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ses(filepath):
    """Parse the CSV and return a list of SE dicts."""
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    # Find the header row (contains 'SE' in column index 1)
    data_start = None
    for i, row in enumerate(rows):
        if len(row) > 1 and row[1].strip() == "SE":
            data_start = i + 1
            break

    if data_start is None:
        print("ERROR: Could not find SE header row. Check CSV format.")
        sys.exit(1)

    ses = []
    for row in rows[data_start:]:
        if len(row) < 20:
            continue
        name = row[1].strip()
        if not name or name in EXCLUDE:
            continue
        # Data rows have an Owl % in column 2
        if not row[2].strip().endswith("%"):
            continue

        se = {
            "name": name,
            "owl_pct": parse_pct(row[2]),
            # Activate
            "act_wins":   parse_int(row[3]),
            "act_icav":   parse_dollar(row[4]),
            "act_avg":    parse_dollar(row[5]),
            "act_median": parse_dollar(row[6]),
            # Expansion
            "exp_wins":   parse_int(row[7]),
            "exp_icav":   parse_dollar(row[8]),
            "exp_avg":    parse_dollar(row[9]),
            "exp_median": parse_dollar(row[10]),
            # DSR
            "top_dsr":    row[11].strip(),
            "bot_dsr":    row[13].strip(),
            # Emails — Activate
            "email_act_total": parse_int(row[15]),
            "email_act_inq":   parse_int(row[16]),
            "email_act_noopp": parse_int(row[17]),
            "email_act_outq":  parse_int(row[18]),
            # Emails — Expansion
            "email_exp_total": parse_int(row[19]),
            "email_exp_inq":   parse_int(row[20]),
            "email_exp_noopp": parse_int(row[21]),
            "email_exp_outq":  parse_int(row[22]),
            # Largest deal
            "largest_deal":       row[23].strip() if len(row) > 23 else "",
            "largest_deal_value": parse_dollar(row[24]) if len(row) > 24 else 0,
            "largest_deal_dsr":   row[25].strip() if len(row) > 25 else "",
        }

        # Derived metrics
        se["total_icav"] = se["act_icav"] + se["exp_icav"]
        se["future_emails"] = se["email_act_outq"] + se["email_exp_outq"]
        total_emails = se["email_act_total"] + se["email_exp_total"]
        se["future_pct"] = round(se["future_emails"] / total_emails * 100) if total_emails else 0
        se["act_target_pct"] = round(se["email_act_inq"] / se["email_act_total"] * 100) if se["email_act_total"] else 0
        se["exp_target_pct"] = round(se["email_exp_inq"] / se["email_exp_total"] * 100) if se["email_exp_total"] else 0
        se["exp_growing"] = se["exp_median"] > 0

        ses.append(se)

    return ses


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_ses(ses):
    """
    Weighted rank across 5 dimensions.

    65% total iACV is the minimum weight that prevents any iACV inversion on
    this dataset — i.e. no SE with more total revenue can rank below one with less.
    The remaining 35% rewards quality so close iACV cases are meaningfully split.

      Total iACV       65%   primary driver
      Activate iACV    10%   new business contribution
      Expansion median 10%   are accounts growing or just retained?
      Future pipeline   8%   investing in Q2+ or living quarter to quarter?
      Owl %             7%   deal awareness and Salesforce hygiene
    """
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
    """Assign a tier label based on rank position."""
    pct = rank / total
    if pct <= 0.20:
        return "Elite"
    elif pct <= 0.50:
        return "Strong"
    elif pct <= 0.75:
        return "Steady"
    else:
        return "Develop"


# ---------------------------------------------------------------------------
# Output sections
# ---------------------------------------------------------------------------

W = 90  # report width

def divider(title=""):
    if title:
        pad = (W - len(title) - 2) // 2
        print("\n" + "=" * pad + f" {title} " + "=" * (W - pad - len(title) - 2))
    else:
        print("=" * W)


def print_rankings(ranked):
    divider("Q1 OVERALL RANKINGS")
    print(f"\n  Total iACV 65% · Activate 10% · Expansion quality 10% · Future pipeline 8% · Owl% 7%")
    print(f"  (65% is the minimum weight where total iACV never loses to lower-revenue SEs)\n")

    total = len(ranked)
    hdr = f"  {'#':<4} {'SE':<28} {'Activate':<12} {'Expansion':<12} {'Total':<12} {'Owl%':<7} {'FutQ%':<8} {'Tier'}"
    print(hdr)
    print("  " + "-" * (W - 2))

    max_icav = max(se["total_icav"] for se in ranked)
    for i, se in enumerate(ranked, 1):
        t = tier(i, total)
        print(
            f"  {i:<4} {se['name']:<28} "
            f"{fmt(se['act_icav']):<12} {fmt(se['exp_icav']):<12} "
            f"{fmt(se['total_icav']):<12} {fmt_pct(se['owl_pct']):<7} "
            f"{se['future_pct']}%{'':<5} {t}"
        )
    print()


def print_activate(ses):
    divider("ACTIVATE — New Business (>$30K, no prior contract)")
    print(f"\n  Every win here is new committed spend. Avg vs. median spread shows deal consistency.\n")

    sorted_ses = sorted(ses, key=lambda x: x["act_icav"], reverse=True)
    max_icav = sorted_ses[0]["act_icav"]

    print(f"  {'SE':<28} {'Wins':<7} {'iACV':<12} {'Avg':<10} {'Median':<10} {'Volume'}")
    print("  " + "-" * (W - 2))
    for se in sorted_ses:
        b = bar(se["act_icav"], max_icav, 18)
        print(
            f"  {se['name']:<28} {se['act_wins']:<7} "
            f"{fmt(se['act_icav']):<12} {fmt(se['act_avg']):<10} "
            f"{fmt(se['act_median']):<10} {b}"
        )
    print()


def print_expansion(ses):
    divider("EXPANSION — Land & Expand (all deal sizes, includes retention)")
    print(f"\n  $0 median = majority of wins are flat retentions (no new iACV)")
    print(f"  Positive median = majority of accounts are genuinely growing\n")

    sorted_ses = sorted(ses, key=lambda x: x["exp_icav"], reverse=True)
    max_icav = sorted_ses[0]["exp_icav"] if sorted_ses[0]["exp_icav"] > 0 else 1

    print(f"  {'SE':<28} {'Wins':<7} {'iACV':<12} {'Avg':<10} {'Median':<10} {'Status':<12} {'Volume'}")
    print("  " + "-" * (W - 2))
    for se in sorted_ses:
        status = "Growing" if se["exp_growing"] else "Retaining"
        b = bar(se["exp_icav"], max_icav, 16)
        print(
            f"  {se['name']:<28} {se['exp_wins']:<7} "
            f"{fmt(se['exp_icav']):<12} {fmt(se['exp_avg']):<10} "
            f"{fmt(se['exp_median']):<10} {status:<12} {b}"
        )
    print()


def print_pipeline(ses):
    divider("PIPELINE HEALTH — Deal Hygiene & Forward Investment")
    print(f"\n  Owl%  = Presales stage management & Salesforce note hygiene")
    print(f"  InQ   = Emails working current-quarter pipeline (closing mode)")
    print(f"  OutQ  = Emails nurturing future-quarter pipeline (building mode)")
    print(f"  FutQ% = OutQ emails as % of all emails sent\n")

    sorted_ses = sorted(ses, key=lambda x: x["future_emails"], reverse=True)
    max_future = sorted_ses[0]["future_emails"] if sorted_ses[0]["future_emails"] > 0 else 1

    print(f"  {'SE':<28} {'Owl%':<7} {'Act InQ':<10} {'Act OutQ':<10} {'Exp InQ':<10} {'Exp OutQ':<10} {'FutQ%':<8} {'Investment'}")
    print("  " + "-" * (W - 2))
    for se in sorted_ses:
        b = bar(se["future_emails"], max_future, 14)
        print(
            f"  {se['name']:<28} {fmt_pct(se['owl_pct']):<7} "
            f"{se['email_act_inq']:<10} {se['email_act_outq']:<10} "
            f"{se['email_exp_inq']:<10} {se['email_exp_outq']:<10} "
            f"{se['future_pct']}%{'':<5} {b}"
        )
    print()


def print_largest_deals(ses):
    divider("LARGEST DEALS THIS QUARTER")
    print()
    sorted_ses = sorted(ses, key=lambda x: x["largest_deal_value"], reverse=True)
    print(f"  {'SE':<28} {'Value':<12} {'DSR':<28} {'Deal'}")
    print("  " + "-" * (W - 2))
    for se in sorted_ses:
        if se["largest_deal_value"] > 0:
            deal = se["largest_deal"][:40] + "..." if len(se["largest_deal"]) > 40 else se["largest_deal"]
            print(f"  {se['name']:<28} {fmt(se['largest_deal_value']):<12} {se['largest_deal_dsr']:<28} {deal}")
    print()


def collect_team_trends(ses):
    """Team-level observations only — patterns across the whole group."""
    trends = []
    n = len(ses)

    # Expansion growth split
    growing = [se for se in ses if se["exp_growing"]]
    retaining = [se for se in ses if not se["exp_growing"] and se["exp_icav"] > 0]
    flat = [se for se in ses if se["exp_icav"] == 0]
    trends.append(("EXPANSION", (
        f"{len(growing)} of {n} SEs have a positive expansion median — accounts genuinely growing. "
        f"{len(retaining)} are retaining at $0 median. {len(flat)} have no expansion contribution."
    )))

    # Pipeline investment split
    builders = [se for se in ses if se["future_pct"] >= FUTURE_PIPELINE_STRONG]
    weak = [se for se in ses if se["future_pct"] < FUTURE_PIPELINE_WEAK]
    avg_fut = round(sum(se["future_pct"] for se in ses) / n)
    trends.append(("PIPELINE", (
        f"Team avg future pipeline investment: {avg_fut}% of email activity. "
        f"{len(builders)} SE{'s' if len(builders)!=1 else ''} above {FUTURE_PIPELINE_STRONG}% (building Q2+). "
        f"{len(weak)} SE{'s' if len(weak)!=1 else ''} below {FUTURE_PIPELINE_WEAK}% (short-term focus only)."
    )))

    # Single-motion split
    act_only = [se for se in ses if se["total_icav"] > 0 and se["act_icav"] / se["total_icav"] > 0.85 and se["act_icav"] > 200_000]
    exp_only = [se for se in ses if se["total_icav"] > 0 and se["exp_icav"] / se["total_icav"] > 0.85 and se["exp_icav"] > 200_000]
    if act_only or exp_only:
        trends.append(("MOTION", (
            f"{len(act_only)} SE{'s are' if len(act_only)!=1 else ' is'} running activate-only (>85% of iACV from new logos). "
            f"{len(exp_only)} SE{'s are' if len(exp_only)!=1 else ' is'} running expansion-only. "
            f"Two-motion operators generate more durable revenue."
        )))

    # Activate deal size floor
    low_act = [se for se in ses if se["act_wins"] >= 5 and se["act_avg"] < ACT_AVG_SIZE_WARNING]
    if low_act:
        avg_team = round(sum(se["act_avg"] for se in ses if se["act_wins"] > 0) / sum(1 for se in ses if se["act_wins"] > 0))
        trends.append(("ACTIVATE", (
            f"{len(low_act)} SE{'s are' if len(low_act)!=1 else ' is'} closing high volumes of activate deals "
            f"below the ${ACT_AVG_SIZE_WARNING//1000}K avg threshold. "
            f"Team activate avg is {fmt(avg_team)}. Landing small may cap expansion potential."
        )))

    # Owl hygiene across team
    below_owl = [se for se in ses if se["owl_pct"] < OWL_WARNING_THRESHOLD]
    avg_owl = round(sum(se["owl_pct"] for se in ses) / n)
    if below_owl:
        trends.append(("HYGIENE", (
            f"Team avg Owl: {avg_owl}%. "
            f"{len(below_owl)} SE{'s are' if len(below_owl)!=1 else ' is'} below the {OWL_WARNING_THRESHOLD}% threshold — "
            f"deals not being staged or documented, creating pipeline blind spots."
        )))
    else:
        trends.append(("HYGIENE", f"Team avg Owl: {avg_owl}%. All SEs above {OWL_WARNING_THRESHOLD}% hygiene threshold."))

    # Revenue concentration
    top2_total = sum(se["total_icav"] for se in sorted(ses, key=lambda x: x["total_icav"], reverse=True)[:2])
    team_total = sum(se["total_icav"] for se in ses)
    top2_pct = round(top2_total / team_total * 100) if team_total else 0
    trends.append(("RISK", (
        f"Top 2 SEs account for {top2_pct}% of team iACV ({fmt(top2_total)} of {fmt(team_total)}). "
        f"{'High concentration — team performance is fragile if top performers have a down quarter.' if top2_pct > 50 else 'Revenue is reasonably distributed across the team.'}"
    )))

    return trends


def collect_se_flags(se, ses):
    """Individual flags for a single SE."""
    flags = []

    # Team-level denominators for relative signals
    team_emails = [s["email_act_total"] + s["email_exp_total"] for s in ses]
    team_email_avg = sum(team_emails) / len(team_emails)
    max_act_wins = max(s["act_wins"] for s in ses)

    # Owl hygiene
    if se["owl_pct"] < OWL_WARNING_THRESHOLD:
        flags.append(("HYGIENE", f"{se['owl_pct']}% Owl — below {OWL_WARNING_THRESHOLD}% hygiene threshold."))

    # Single motion
    if se["total_icav"] > 0:
        act_pct = se["act_icav"] / se["total_icav"]
        exp_pct = se["exp_icav"] / se["total_icav"]
        if act_pct > 0.85 and se["act_icav"] > 200_000:
            flags.append(("MOTION", f"{round(act_pct*100)}% activate-only — expansion not contributing."))
        elif exp_pct > 0.85 and se["exp_icav"] > 200_000:
            flags.append(("MOTION", f"{round(exp_pct*100)}% expansion-only — new business is light."))

    # Deal concentration (risk)
    if se["total_icav"] > 0 and se["largest_deal_value"] > se["total_icav"] * DEAL_CONCENTRATION_THRESHOLD:
        pct = round(se["largest_deal_value"] / se["total_icav"] * 100)
        flags.append(("RISK", f"Largest deal = {pct}% of total iACV ({fmt(se['largest_deal_value'])})."))
    # Well-distributed revenue (positive signal for high-volume closers)
    elif se["total_icav"] > 500_000 and se["largest_deal_value"] > 0:
        pct = round(se["largest_deal_value"] / se["total_icav"] * 100)
        if pct < 20:
            flags.append(("STRENGTH", f"Largest deal is {pct}% of iACV — revenue well distributed across deals."))

    # Activate deal size floor
    if se["act_wins"] >= 5 and se["act_avg"] < ACT_AVG_SIZE_WARNING:
        flags.append(("ACTIVATE", f"{fmt(se['act_avg'])} avg on {se['act_wins']} wins — below ${ACT_AVG_SIZE_WARNING//1000}K floor."))

    # Activate deal variance (avg vs median spread)
    if se["act_wins"] >= 4 and se["act_median"] > 0:
        ratio = se["act_avg"] / se["act_median"]
        if ratio >= 2.5:
            flags.append(("ACTIVATE", f"High variance — {fmt(se['act_avg'])} avg vs {fmt(se['act_median'])} median. Outlier deals driving total."))
        elif 1.0 <= ratio < 1.3 and se["act_wins"] >= 5 and se["act_avg"] >= ACT_AVG_SIZE_WARNING:
            flags.append(("ACTIVATE", f"Consistent sizing — {fmt(se['act_avg'])} avg vs {fmt(se['act_median'])} median. Repeatable deal pattern."))

    # Activate volume relative to team
    if se["act_wins"] == max_act_wins:
        flags.append(("ACTIVATE", f"Highest activate volume on team — {se['act_wins']} wins."))
    elif se["act_wins"] <= 5 and se["act_wins"] > 0:
        flags.append(("ACTIVATE", f"Low activate volume — {se['act_wins']} wins this quarter."))

    # Future pipeline and total email activity
    se_total_emails = se["email_act_total"] + se["email_exp_total"]
    if se["future_pct"] < FUTURE_PIPELINE_WEAK:
        flags.append(("PIPELINE", f"Only {se['future_pct']}% future pipeline — Q2+ runway is thin."))
    elif se["future_pct"] >= FUTURE_PIPELINE_STRONG:
        flags.append(("PIPELINE", f"{se['future_pct']}% future pipeline — {se['future_emails']} emails building Q2+."))

    if se_total_emails < team_email_avg * 0.45:
        flags.append(("PIPELINE", f"Low total activity — {se_total_emails} emails vs {round(team_email_avg)} team avg."))

    # Expansion status
    if se["exp_growing"]:
        flags.append(("EXPANSION", f"Growing — {fmt(se['exp_median'])} median. Accounts upselling."))
    elif se["exp_wins"] >= 10 and not se["exp_growing"]:
        flags.append(("EXPANSION", f"High renewal load — {se['exp_wins']} wins at $0 median. Flat retentions."))
    elif se["exp_icav"] > 0:
        flags.append(("EXPANSION", f"Retaining — $0 median on {se['exp_wins']} wins."))
    else:
        flags.append(("EXPANSION", "No expansion contribution this quarter."))

    return flags


def _wrap_print(msg, indent="    "):
    words = msg.split()
    line = indent
    for word in words:
        if len(line) + len(word) + 1 > W - 4:
            print(line)
            line = indent + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)


def print_trends(ses):
    divider("TEAM TRENDS")
    trends = collect_team_trends(ses)
    print()
    current_cat = None
    for cat, msg in sorted(trends, key=lambda x: x[0]):
        if cat != current_cat:
            print(f"\n  [{cat}]")
            current_cat = cat
        _wrap_print(msg)
    print()


def print_se_profiles(ranked):
    divider("SE PROFILES")
    print()
    total = len(ranked)
    for i, se in enumerate(ranked, 1):
        t = tier(i, total)
        act_note = f"Activate: {fmt(se['act_icav'])} ({se['act_wins']} wins, median {fmt(se['act_median'])})"
        exp_note = f"Expansion: {fmt(se['exp_icav'])} ({'growing' if se['exp_growing'] else 'retaining'}, median {fmt(se['exp_median'])})"
        print(f"  {i}. {se['name']} [{t}]  —  Total: {fmt(se['total_icav'])}")
        print(f"     {act_note}  |  {exp_note}")
        print(f"     Owl: {fmt_pct(se['owl_pct'])}  |  Future pipeline: {se['future_emails']} emails ({se['future_pct']}% of activity)")
        flags = collect_se_flags(se, ranked)
        for cat, msg in flags:
            _wrap_print(f"↳ [{cat}] {msg}", indent="     ")
        print()


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

TIER_STYLE = {
    "Elite":   ("bg-amber-400",  "text-amber-400",  "border-amber-400/40"),
    "Strong":  ("bg-blue-400",   "text-blue-400",   "border-blue-400/40"),
    "Steady":  ("bg-emerald-400","text-emerald-400","border-emerald-400/40"),
    "Develop": ("bg-red-400",    "text-red-400",    "border-red-400/40"),
}
FLAG_STYLE = {
    "PIPELINE": ("bg-blue-500/10",   "text-blue-300",   "border-blue-500/30"),
    "EXPANSION":("bg-emerald-500/10","text-emerald-300","border-emerald-500/30"),
    "HYGIENE":  ("bg-red-500/10",    "text-red-300",    "border-red-500/30"),
    "ACTIVATE": ("bg-orange-500/10", "text-orange-300", "border-orange-500/30"),
    "RISK":     ("bg-rose-500/10",   "text-rose-300",   "border-rose-500/30"),
    "MOTION":   ("bg-purple-500/10", "text-purple-300", "border-purple-500/30"),
    "STRENGTH": ("bg-cyan-500/10",   "text-cyan-300",   "border-cyan-500/30"),
}


def pct_bar(value, max_val, color="bg-blue-500"):
    w = round((value / max_val) * 100) if max_val else 0
    return f'<div class="w-full bg-white/10 rounded-full h-1.5"><div class="{color} h-1.5 rounded-full" style="width:{w}%"></div></div>'


def generate_html(ranked, ses, output_path="se_report.html"):
    total = len(ranked)
    team_icav = sum(se["total_icav"] for se in ses)
    avg_owl = round(sum(se["owl_pct"] for se in ses) / total) if total else 0

    # --- Rankings rows ---
    rank_rows = ""
    for i, se in enumerate(ranked, 1):
        t = tier(i, total)
        _, tc, bc = TIER_STYLE[t]
        rank_rows += f"""<tr class="border-b border-white/5 hover:bg-white/5">
          <td class="px-4 py-3 text-gray-500 font-mono text-sm">{i}</td>
          <td class="px-4 py-3 font-medium text-white">{se['name']}</td>
          <td class="px-4 py-3 font-mono text-blue-300">{fmt(se['act_icav'])}</td>
          <td class="px-4 py-3 font-mono text-emerald-300">{fmt(se['exp_icav'])}</td>
          <td class="px-4 py-3 font-mono font-semibold text-white">{fmt(se['total_icav'])}</td>
          <td class="px-4 py-3 text-sm {'text-red-400' if se['owl_pct'] < 75 else 'text-gray-300'}">{se['owl_pct']}%</td>
          <td class="px-4 py-3 text-sm text-gray-300">{se['future_pct']}%</td>
          <td class="px-4 py-3"><span class="px-2 py-0.5 rounded text-xs font-semibold border {tc} {bc}">{t}</span></td>
        </tr>"""

    # --- Activate rows ---
    act_sorted = sorted(ses, key=lambda x: x["act_icav"], reverse=True)
    max_act = act_sorted[0]["act_icav"] if act_sorted else 1
    act_rows = ""
    for se in act_sorted:
        act_rows += f"""<tr class="border-b border-white/5 hover:bg-white/5">
          <td class="px-4 py-3 font-medium text-white">{se['name']}</td>
          <td class="px-4 py-3 text-center text-gray-300">{se['act_wins']}</td>
          <td class="px-4 py-3 font-mono font-semibold text-blue-300">{fmt(se['act_icav'])}</td>
          <td class="px-4 py-3 font-mono text-gray-300">{fmt(se['act_avg'])}</td>
          <td class="px-4 py-3 font-mono text-gray-300">{fmt(se['act_median'])}</td>
          <td class="px-4 py-3 w-36">{pct_bar(se['act_icav'], max_act, 'bg-blue-500')}</td>
        </tr>"""

    # --- Expansion rows ---
    exp_sorted = sorted(ses, key=lambda x: x["exp_icav"], reverse=True)
    max_exp = max((se["exp_icav"] for se in exp_sorted), default=1) or 1
    exp_rows = ""
    for se in exp_sorted:
        badge = '<span class="px-2 py-0.5 rounded text-xs bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Growing</span>' if se["exp_growing"] else '<span class="px-2 py-0.5 rounded text-xs bg-white/5 text-gray-400 border border-white/10">Retaining</span>'
        exp_rows += f"""<tr class="border-b border-white/5 hover:bg-white/5">
          <td class="px-4 py-3 font-medium text-white">{se['name']}</td>
          <td class="px-4 py-3 text-center text-gray-300">{se['exp_wins']}</td>
          <td class="px-4 py-3 font-mono font-semibold text-emerald-300">{fmt(se['exp_icav'])}</td>
          <td class="px-4 py-3 font-mono text-gray-300">{fmt(se['exp_avg'])}</td>
          <td class="px-4 py-3 font-mono text-gray-300">{fmt(se['exp_median'])}</td>
          <td class="px-4 py-3">{badge}</td>
          <td class="px-4 py-3 w-36">{pct_bar(se['exp_icav'], max_exp, 'bg-emerald-500')}</td>
        </tr>"""

    # --- Pipeline rows ---
    pipe_sorted = sorted(ses, key=lambda x: x["future_emails"], reverse=True)
    max_fut = pipe_sorted[0]["future_emails"] if pipe_sorted and pipe_sorted[0]["future_emails"] else 1
    pipe_rows = ""
    for se in pipe_sorted:
        owl_cls = "text-red-400 font-semibold" if se["owl_pct"] < 75 else "text-gray-300"
        pipe_rows += f"""<tr class="border-b border-white/5 hover:bg-white/5">
          <td class="px-4 py-3 font-medium text-white">{se['name']}</td>
          <td class="px-4 py-3 text-center {owl_cls}">{se['owl_pct']}%</td>
          <td class="px-4 py-3 text-center text-gray-300">{se['email_act_inq']}</td>
          <td class="px-4 py-3 text-center text-gray-300">{se['email_act_outq']}</td>
          <td class="px-4 py-3 text-center text-gray-300">{se['email_exp_inq']}</td>
          <td class="px-4 py-3 text-center text-gray-300">{se['email_exp_outq']}</td>
          <td class="px-4 py-3 text-center text-gray-300">{se['future_pct']}%</td>
          <td class="px-4 py-3 w-36">{pct_bar(se['future_emails'], max_fut, 'bg-purple-500')}</td>
        </tr>"""

    # --- Deals rows ---
    deal_sorted = sorted(ses, key=lambda x: x["largest_deal_value"], reverse=True)
    deal_rows = ""
    for se in deal_sorted:
        if se["largest_deal_value"] > 0:
            name = se["largest_deal"][:50] + "…" if len(se["largest_deal"]) > 50 else se["largest_deal"]
            deal_rows += f"""<tr class="border-b border-white/5 hover:bg-white/5">
              <td class="px-4 py-3 font-medium text-white">{se['name']}</td>
              <td class="px-4 py-3 font-mono font-semibold text-white">{fmt(se['largest_deal_value'])}</td>
              <td class="px-4 py-3 text-gray-400">{se['largest_deal_dsr']}</td>
              <td class="px-4 py-3 text-gray-300 text-sm">{name}</td>
            </tr>"""

    # --- Team trends ---
    def flag_pill(cat, msg):
        """Wide pill for the team trends section."""
        bg, tc, bc = FLAG_STYLE.get(cat, ("bg-white/5","text-gray-300","border-white/10"))
        return (f'<div class="rounded-lg border {bc} {bg} px-4 py-3 flex gap-3 items-start">'
                f'<span class="text-xs font-bold {tc} mt-0.5 shrink-0 w-24">{cat}</span>'
                f'<span class="text-sm text-gray-300">{msg}</span></div>')

    def flag_chip(cat, msg):
        """Compact equal-height chip for SE profile cards."""
        bg, tc, bc = FLAG_STYLE.get(cat, ("bg-white/5","text-gray-300","border-white/10"))
        return (f'<div class="rounded-md border {bc} {bg} px-3 py-2 flex flex-col justify-between" style="min-height:52px">'
                f'<div class="text-[9px] font-bold {tc} uppercase tracking-widest mb-1">{cat}</div>'
                f'<div class="text-[11px] text-gray-300 leading-snug">{msg}</div></div>')

    trends_html = "\n".join(flag_pill(cat, msg) for cat, msg in sorted(collect_team_trends(ses), key=lambda x: x[0]))

    # --- SE profile cards ---
    max_act_icav = max(se["act_icav"] for se in ranked) or 1
    max_exp_icav = max(se["exp_icav"] for se in ranked) or 1
    profile_cards = ""
    for i, se in enumerate(ranked, 1):
        t = tier(i, total)
        _, tc, bc = TIER_STYLE[t]
        exp_badge = "Growing" if se["exp_growing"] else "Retaining"
        exp_badge_cls = "text-emerald-400" if se["exp_growing"] else "text-gray-400"
        owl_cls = "text-red-400" if se["owl_pct"] < 75 else "text-white"
        act_bar_w = round(se["act_icav"] / max_act_icav * 100)
        exp_bar_w = round(se["exp_icav"] / max_exp_icav * 100)
        flags = collect_se_flags(se, ranked)
        se_flags_html = "\n".join(flag_chip(cat, msg) for cat, msg in flags)
        profile_cards += f"""<div class="bg-white/5 rounded-xl border border-white/10 p-5 hover:border-white/20 transition-colors flex flex-col gap-3">

          <!-- Header -->
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="flex items-center gap-2 mb-1.5">
                <span class="text-xs text-gray-500 font-mono">#{i}</span>
                <span class="text-sm font-semibold text-white">{se['name']}</span>
              </div>
              <span class="px-2 py-0.5 rounded text-xs font-semibold border {tc} {bc}">{t}</span>
            </div>
            <div class="text-right shrink-0">
              <div class="text-xl font-bold text-white">{fmt(se['total_icav'])}</div>
              <div class="text-xs text-gray-500">total iACV</div>
            </div>
          </div>

          <!-- Stats grid -->
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="bg-blue-500/10 rounded-lg p-3">
              <div class="text-gray-500 mb-1 uppercase tracking-wide text-[10px]">Activate</div>
              <div class="font-mono font-semibold text-blue-300 text-sm">{fmt(se['act_icav'])}</div>
              <div class="text-gray-500 mt-0.5">{se['act_wins']} wins · med {fmt(se['act_median'])}</div>
              <div class="mt-2 w-full bg-white/10 rounded-full h-1"><div class="bg-blue-500 h-1 rounded-full" style="width:{act_bar_w}%"></div></div>
            </div>
            <div class="bg-emerald-500/10 rounded-lg p-3">
              <div class="text-gray-500 mb-1 uppercase tracking-wide text-[10px]">Expansion <span class="{exp_badge_cls}">· {exp_badge}</span></div>
              <div class="font-mono font-semibold text-emerald-300 text-sm">{fmt(se['exp_icav'])}</div>
              <div class="text-gray-500 mt-0.5">{se['exp_wins']} wins · med {fmt(se['exp_median'])}</div>
              <div class="mt-2 w-full bg-white/10 rounded-full h-1"><div class="bg-emerald-500 h-1 rounded-full" style="width:{exp_bar_w}%"></div></div>
            </div>
          </div>

          <!-- Quick stats row -->
          <div class="flex gap-5 text-xs text-gray-500 border-t border-white/5 pt-2.5">
            <span>Owl <span class="{owl_cls} font-semibold">{se['owl_pct']}%</span></span>
            <span>Future Q <span class="text-white font-semibold">{se['future_pct']}%</span></span>
            <span>Fwd Emails <span class="text-white font-semibold">{se['future_emails']}</span></span>
          </div>

          <!-- Flags — uniform grid, always 2 columns -->
          {f'<div class="grid grid-cols-2 gap-1.5">{se_flags_html}</div>' if flags else ''}
        </div>"""

    def th(label):
        return f'<th class="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</th>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SE Scorecard — Q1</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>body{{background:#0a0f1e;font-family:ui-sans-serif,system-ui,sans-serif}}</style>
</head>
<body class="text-gray-100 min-h-screen">
<div class="max-w-7xl mx-auto px-6 py-10">

  <div class="mb-8">
    <h1 class="text-2xl font-bold text-white mb-1">SE Scorecard</h1>
    <p class="text-gray-400 text-sm">Q1 · {total} SEs · Ranked across revenue, expansion quality, pipeline investment &amp; hygiene</p>
  </div>

  <div class="grid grid-cols-3 gap-4 mb-8">
    <div class="bg-white/5 rounded-xl border border-white/10 p-5">
      <div class="text-xs text-gray-400 mb-1">Team Total iACV</div>
      <div class="text-2xl font-bold text-white">{fmt(team_icav)}</div>
    </div>
    <div class="bg-white/5 rounded-xl border border-white/10 p-5">
      <div class="text-xs text-gray-400 mb-1">Team Avg Owl %</div>
      <div class="text-2xl font-bold text-white">{avg_owl}%</div>
    </div>
    <div class="bg-white/5 rounded-xl border border-white/10 p-5">
      <div class="text-xs text-gray-400 mb-1">SEs Analysed</div>
      <div class="text-2xl font-bold text-white">{total}</div>
    </div>
  </div>

  <div class="bg-white/5 rounded-xl border border-white/10 mb-6 overflow-hidden">
    <div class="px-5 py-4 border-b border-white/10">
      <h2 class="font-semibold text-white">Overall Rankings</h2>
      <p class="text-xs text-gray-400 mt-0.5">Total iACV 65% · Activate 10% · Expansion quality 10% · Future pipeline 8% · Owl% 7%</p>
    </div>
    <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead class="border-b border-white/10 bg-white/3">
        <tr>{th('#')}{th('SE')}{th('Activate')}{th('Expansion')}{th('Total iACV')}{th('Owl%')}{th('Future Q%')}{th('Tier')}</tr>
      </thead>
      <tbody>{rank_rows}</tbody>
    </table>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
    <div class="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
      <div class="px-5 py-4 border-b border-white/10">
        <h2 class="font-semibold text-white">Activate — New Business</h2>
        <p class="text-xs text-gray-400 mt-0.5">New logos, no prior contract, deals &gt;$30K</p>
      </div>
      <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="border-b border-white/10"><tr>{th('SE')}{th('Wins')}{th('iACV')}{th('Avg')}{th('Median')}{th('Volume')}</tr></thead>
        <tbody>{act_rows}</tbody>
      </table>
      </div>
    </div>
    <div class="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
      <div class="px-5 py-4 border-b border-white/10">
        <h2 class="font-semibold text-white">Expansion — Land &amp; Expand</h2>
        <p class="text-xs text-gray-400 mt-0.5">Existing customers · $0 median = mostly flat retentions</p>
      </div>
      <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="border-b border-white/10"><tr>{th('SE')}{th('Wins')}{th('iACV')}{th('Avg')}{th('Median')}{th('Status')}{th('Volume')}</tr></thead>
        <tbody>{exp_rows}</tbody>
      </table>
      </div>
    </div>
  </div>

  <div class="bg-white/5 rounded-xl border border-white/10 mb-6 overflow-hidden">
    <div class="px-5 py-4 border-b border-white/10">
      <h2 class="font-semibold text-white">Pipeline Health</h2>
      <p class="text-xs text-gray-400 mt-0.5">Owl% = Salesforce hygiene &amp; presales stage management · OutQ = future quarter pipeline · FutQ% = OutQ as % of all emails</p>
    </div>
    <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead class="border-b border-white/10"><tr>{th('SE')}{th('Owl%')}{th('Act InQ')}{th('Act OutQ')}{th('Exp InQ')}{th('Exp OutQ')}{th('FutQ%')}{th('Investment')}</tr></thead>
      <tbody>{pipe_rows}</tbody>
    </table>
    </div>
  </div>

  <div class="bg-white/5 rounded-xl border border-white/10 mb-6 overflow-hidden">
    <div class="px-5 py-4 border-b border-white/10"><h2 class="font-semibold text-white">Largest Deals</h2></div>
    <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead class="border-b border-white/10"><tr>{th('SE')}{th('Value')}{th('DSR')}{th('Deal')}</tr></thead>
      <tbody>{deal_rows}</tbody>
    </table>
    </div>
  </div>

  <div class="bg-white/5 rounded-xl border border-white/10 mb-6 overflow-hidden">
    <div class="px-5 py-4 border-b border-white/10"><h2 class="font-semibold text-white">Trends &amp; Flags</h2></div>
    <div class="p-5 flex flex-col gap-3">{trends_html}</div>
  </div>

  <div class="mb-2"><h2 class="font-semibold text-white mb-4">SE Profiles</h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">{profile_cards}</div>
  </div>

</div>
</body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report written to {output_path}")

    # Save raw SE data so the individual SE profile page can read it
    import json
    json_path = Path(output_path).parent / "se_data.json"
    payload = []
    for i, se in enumerate(ranked, 1):
        entry = dict(se)
        entry["rank"] = i
        entry["tier"] = tier(i, total)
        entry["flags"] = collect_se_flags(se, ranked)
        payload.append(entry)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    print(f"SE data written to {json_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    html_mode = "--html" in args
    args = [a for a in args if a != "--html"]

    if not args:
        default = Path("DSR SE Scorecard - Roster.csv")
        if default.exists():
            filepath = default
        else:
            print("Usage: python se_analysis.py <path_to_scorecard.csv> [--html]")
            sys.exit(1)
    else:
        filepath = Path(args[0])

    if not filepath.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)

    ses = load_ses(filepath)
    if not ses:
        print("No SE data found. Check that the CSV matches expected format.")
        sys.exit(1)

    ranked = rank_ses(ses)

    if html_mode:
        generate_html(ranked, ses)
        return

    print("\n" + "=" * W)
    print(f"  DSR SE SCORECARD ANALYSIS  |  {len(ses)} SEs  |  Excluded: {', '.join(EXCLUDE) or 'none'}")
    print("=" * W)

    print_rankings(ranked)
    print_activate(ses)
    print_expansion(ses)
    print_pipeline(ses)
    print_largest_deals(ses)
    print_trends(ses)
    print_se_profiles(ranked)

    divider()
    print(f"  END OF REPORT")
    divider()
    print()


if __name__ == "__main__":
    main()
