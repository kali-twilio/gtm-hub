#!/usr/bin/env python3
"""SE Power Rankings  |  python3 se_rankings.py scorecard.csv"""

import csv, sys
from pathlib import Path

EXCLUDE = {"Nitin Dua", "Q1"}

def parse_dollar(value):
    if not value or value.strip() in ("", "-"):
        return 0
    v = value.strip().lstrip("$").replace(",", "")
    try:
        if "M" in v: return int(float(v.replace("M", "")) * 1_000_000)
        if "K" in v: return int(float(v.replace("K", "")) * 1_000)
        return int(float(v))
    except (ValueError, AttributeError):
        return 0

def parse_pct(value):
    try:
        return int(value.strip().rstrip("%"))
    except (ValueError, AttributeError):
        return 0

def parse_int(value):
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return 0

def fmt(n):
    if n >= 1_000_000: return f"${n / 1_000_000:.1f}M"
    if n >= 1_000:     return f"${n / 1_000:.0f}K"
    return f"${n}"

def load(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    # Find the header row (column 1 == "SE")
    header_idx = next((i for i, r in enumerate(rows) if len(r) > 1 and r[1].strip() == "SE"), None)
    if header_idx is None:
        sys.exit("SE header not found")
    data_rows = rows[header_idx + 1:]

    ses = []
    for row in data_rows:
        if len(row) < 20:
            continue
        name = row[1].strip()
        if not name or name in EXCLUDE or not row[2].strip().endswith("%"):
            continue

        act_icav      = parse_dollar(row[4])
        exp_icav      = parse_dollar(row[8])
        future_emails = parse_int(row[18]) + parse_int(row[22])
        total_emails  = parse_int(row[15]) + parse_int(row[19])
        largest_deal_value = parse_dollar(row[24]) if len(row) > 24 else 0
        total_icav    = act_icav + exp_icav

        ses.append({
            "name":               name,
            "owl":                parse_pct(row[2]),
            "act_wins":           parse_int(row[3]),
            "act_icav":           act_icav,
            "act_avg":            parse_dollar(row[5]),
            "act_median":         parse_dollar(row[6]),
            "act_inq":            parse_int(row[16]),
            "exp_wins":           parse_int(row[7]),
            "exp_icav":           exp_icav,
            "exp_median":         parse_dollar(row[10]),
            "exp_growing":        parse_dollar(row[10]) > 0,
            "total":              total_icav,
            "future":             future_emails,
            "future_pct":         round(future_emails / total_emails * 100) if total_emails else 0,
            "total_emails":       total_emails,
            "largest_deal":       row[23].strip() if len(row) > 23 else "",
            "largest_deal_value": largest_deal_value,
            "conc":               round(largest_deal_value / total_icav * 100) if total_icav > 0 and largest_deal_value > 0 else 0,
        })
    return ses

def rank(ses):
    def rank_by(key):
        return {se["name"]: i + 1 for i, se in enumerate(sorted(ses, key=lambda x: x[key], reverse=True))}

    r_total    = rank_by("total")
    r_activate = rank_by("act_icav")
    r_exp_med  = rank_by("exp_median")
    r_future   = rank_by("future_pct")
    r_owl      = rank_by("owl")

    for se in ses:
        n = se["name"]
        # 65% on total iACV is the minimum weight where higher revenue always wins
        se["score"] = (
            r_total[n]    * 0.65 +
            r_activate[n] * 0.10 +
            r_exp_med[n]  * 0.10 +
            r_future[n]   * 0.08 +
            r_owl[n]      * 0.07
        )
    return sorted(ses, key=lambda x: x["score"])

def tier(rank, total):
    pct = rank / total
    if pct <= 0.20: return "Elite"
    if pct <= 0.50: return "Strong"
    if pct <= 0.75: return "Steady"
    return "Develop"

def get_roast(se, ranked):
    """Stat-specific roast for each SE based on their most extreme/notable number."""
    max_act_wins = max(s["act_wins"] for s in ranked)
    max_future   = max(s["future_pct"] for s in ranked)
    min_emails   = min(s["total_emails"] for s in ranked)
    min_act_wins = min(s["act_wins"] for s in ranked if s["act_wins"] > 0)

    # CJ Chang — lowest Owl on team
    if se["owl"] < 50:
        return f"{se['owl']}% Owl. The pipeline exists. Salesforce has no idea. A mystery wrapped in a closed deal. 🦉"

    # Prasanth — most activate wins on team
    if se["act_wins"] == max_act_wins:
        others = sum(s["act_wins"] for s in ranked) - se["act_wins"]
        return f"{se['act_wins']} activate wins. The other 9 SEs combined for {others}. He is not playing the same sport. 🏭"

    # Connor — Santa's AI Lab is too good not to use
    if "Santa" in se["largest_deal"]:
        return f"Closed {fmt(se['largest_deal_value'])} with Santa's AI Lab. Yes, Santa. The real MVP of Christmas and Q1. 🎅"

    # Justin — most expansion wins + highest future pipeline
    if se["exp_wins"] >= 30:
        return f"{se['exp_wins']} expansion wins and {se['future']} emails building Q2+. He's already mentally living in next quarter. ♟️"

    # Dustin — expansion-only, zero activate in-Q emails
    if se["exp_icav"] > 1_000_000 and se["act_inq"] == 0:
        return f"{fmt(se['exp_icav'])} in expansion on zero activate in-Q emails. Ignored half the playbook. Still top 3. Infuriating. 🤔"

    # Yuriy — one deal is 70%+ of quarter, thin future pipeline
    if se["conc"] >= 65 and se["future_pct"] <= 15:
        return f"{se['conc']}% of the quarter came from one deal. Q2 pipeline at {se['future_pct']}%. This is either a masterclass or a prayer. 🎲"

    # Andre — fewest total emails on team
    if se["total_emails"] == min_emails:
        epm = round(se["total"] / se["total_emails"]) if se["total_emails"] else 0
        return f"{se['total_emails']} total emails. {fmt(se['total'])} closed. That's {fmt(epm)} per email sent. Do not tell him to send more. 📧"

    # Ben — fewest activate wins on team
    if se["act_wins"] == min_act_wins:
        return f"{se['act_wins']} activate wins. Fewest on the team. The upside here is that literally anywhere is up. The comeback arc starts now. 📉"

    # Tara — high renewal load, 100% owl (check before consistent-closer to avoid overlap)
    if se["exp_wins"] >= 12 and not se["exp_growing"] and se["owl"] == 100:
        return f"{se['exp_wins']} expansion wins at $0 median and a perfect Owl score. Ran every renewal, logged every note. Unsung. 🗂️"

    # Essie — tight avg/median spread (consistent closer)
    if se["act_wins"] >= 5 and se["act_median"] > 0 and se["act_avg"] / se["act_median"] < 1.15:
        return f"{fmt(se['act_avg'])} avg, {fmt(se['act_median'])} median. The most consistent closer on the team. Not flashy. Extremely bankable. 📐"

    # Generic fallback by tier
    t = tier(next(i for i,s in enumerate(ranked,1) if s["name"]==se["name"]), len(ranked))
    fallbacks = {"Elite":"Quietly elite. No drama, just revenue. 👑",
                 "Strong":"Doing the work. Every quarter. 🔥",
                 "Steady":"Steady and reliable. The backbone. 🧱",
                 "Develop":"The comeback arc is still being written. 🙏"}
    return fallbacks.get(t, "Getting it done. 📋")

TIER_CFG={
    "Elite":  {"color":"#FFB800","bg":"#1a1200","label":"🐐 GOAT TIER"},
    "Strong": {"color":"#3B82F6","bg":"#0a1628","label":"🔥 ON FIRE"},
    "Steady": {"color":"#10B981","bg":"#071a12","label":"😤 GRINDING"},
    "Develop":{"color":"#EF4444","bg":"#1a0a0a","label":"💀 SEND HELP"},
}

def generate(ranked):
    total=len(ranked)
    max_a=max(s["act_icav"] for s in ranked) or 1
    max_e=max(s["exp_icav"] for s in ranked) or 1
    max_f=max(s["future"] for s in ranked) or 1
    team_total=sum(s["total"] for s in ranked)
    team_owl=round(sum(s["owl"] for s in ranked)/total)

    tick_parts=[f"#{i} {s['name']} {fmt(s['total'])}" for i,s in enumerate(ranked,1)]
    tick_parts+=[f"🏆 GOAT: {ranked[0]['name']}",
                 f"💀 THOUGHTS & PRAYERS: {ranked[-1]['name']}",
                 f"🔮 PIPELINE KING: {max(ranked,key=lambda x:x['future'])['name']}"]
    ticker="  ·  ".join(tick_parts)

    cards=""
    for i,se in enumerate(ranked,1):
        t=tier(i,total); cfg=TIER_CFG[t]; delay=(i-1)*180
        aw=round(se["act_icav"]/max_a*100); ew=round(se["exp_icav"]/max_e*100)
        fw=round(se["future"]/max_f*100)
        roast=get_roast(se,ranked)
        medal=["🥇","🥈","🥉"][i-1] if i<=3 else ""
        is_one=i==1; is_dev=t=="Develop"
        owl_col="#EF4444" if se["owl"]<75 else ("#FFB800" if se["owl"]==100 else "#9ca3af")
        float_dur=f"{3.5+i*0.25:.2f}s"; float_del=f"{i*0.35:.2f}s"
        enter="slamDown" if is_one else "flipIn" if i<=3 else "slideUp" if i<=7 else "wobbleIn"
        grow=('<span class="badge-grow">📈 GROWING</span>' if se["exp_growing"]
              else '<span class="badge-ret">😐 RETAINING</span>')

        cards+=f"""
<div class="rc {'rc-one' if is_one else 'rc-dev' if is_dev else ''}"
     style="--enter:{enter};--delay:{delay}ms;--fdur:{float_dur};--fdel:{float_del};--tc:{cfg['color']}">
  {'<div class="crown">👑</div>' if is_one else ''}
  <div class="ci">
    <div class="rn">{i}</div>
    <div class="cb">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px">
        <div>
          <div class="tlbl">{medal} {cfg['label']}</div>
          <div class="sname">{se['name']}</div>
          <div style="margin-top:7px">{grow}</div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div class="ticav">{fmt(se['total'])}</div>
          <div class="ticav-lbl">total iACV</div>
        </div>
      </div>
      <div class="roast" style="border-left-color:{cfg['color']}50;background:{cfg['bg']}">{roast}</div>
      <div class="sgrid2">
        <div class="sbox">
          <div class="slbl">🎯 Activate</div>
          <div class="sval" style="color:#60a5fa">{fmt(se['act_icav'])}</div>
          <div class="ssub">{se['act_wins']} wins · med {fmt(se['act_median'])}</div>
          <div class="bw"><div class="bf" style="--w:{aw}%;--c:#3B82F6;animation-delay:{delay+500}ms"></div></div>
        </div>
        <div class="sbox">
          <div class="slbl">📈 Expansion</div>
          <div class="sval" style="color:#34d399">{fmt(se['exp_icav'])}</div>
          <div class="ssub">{se['exp_wins']} wins · med {fmt(se['exp_median'])}</div>
          <div class="bw"><div class="bf" style="--w:{ew}%;--c:#10B981;animation-delay:{delay+600}ms"></div></div>
        </div>
      </div>
      <div class="sgrid3">
        <div class="mbox">
          <div class="slbl">🦉 Owl%</div>
          <div class="mval" style="color:{owl_col}">{se['owl']}%</div>
          <div class="bw"><div class="bf" style="--w:{se['owl']}%;--c:{owl_col};animation-delay:{delay+700}ms"></div></div>
        </div>
        <div class="mbox">
          <div class="slbl">🔮 Future Q%</div>
          <div class="mval" style="color:#a78bfa">{se['future_pct']}%</div>
          <div class="bw"><div class="bf" style="--w:{fw}%;--c:#8b5cf6;animation-delay:{delay+800}ms"></div></div>
        </div>
        <div class="mbox">
          <div class="slbl">✉️ Fut. Emails</div>
          <div class="mval" style="color:#f9a8d4">{se['future']}</div>
        </div>
      </div>
    </div>
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SE Power Rankings 🏆</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#06080f;font-family:ui-sans-serif,system-ui,sans-serif;color:#fff;min-height:100vh;overflow-x:hidden;padding-bottom:76px}}

/* ── INTRO ── */
#intro{{position:fixed;inset:0;background:#06080f;z-index:999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;animation:introOut 0s 2.8s forwards}}
@keyframes introOut{{to{{opacity:0;pointer-events:none;visibility:hidden}}}}
.intro-title{{font-size:clamp(2rem,8vw,4rem);font-weight:900;text-transform:uppercase;animation:pulse .4s ease infinite alternate}}
@keyframes pulse{{from{{opacity:.3}}to{{opacity:1}}}}
.lbar{{width:300px;height:4px;background:#fff2;border-radius:99px;overflow:hidden}}
.lfill{{height:100%;background:linear-gradient(90deg,#3B82F6,#FFB800,#EF4444);animation:lfill 2.5s ease forwards}}
@keyframes lfill{{from{{width:0}}to{{width:100%}}}}
.ltxt{{font-size:.75rem;letter-spacing:.2em;text-transform:uppercase;color:#3B82F6;animation:pulse .7s ease infinite alternate}}

/* ── BACKGROUND CANVAS ── */
#bg{{position:fixed;inset:0;pointer-events:none;z-index:0}}
#confetti{{position:fixed;inset:0;pointer-events:none;z-index:998}}

/* ── TICKER ── */
.ticker{{position:fixed;bottom:0;left:0;right:0;height:56px;background:#0d1117;border-top:2px solid #FFB80030;z-index:997;overflow:hidden;display:flex;align-items:center}}
.ticker-inner{{white-space:nowrap;animation:tickerScroll 60s linear infinite;font-size:.85rem;letter-spacing:.07em;color:#94a3b8;padding-left:100%}}
.ticker-inner span{{color:#FFB800;font-weight:800}}
@keyframes tickerScroll{{from{{transform:translateX(0)}}to{{transform:translateX(-100%)}}}}

/* ── HERO ── */
.hero{{text-align:center;padding:80px 24px 28px;position:relative;z-index:1;animation:fadeDown .8s 3s both}}
@keyframes fadeDown{{from{{opacity:0;transform:translateY(-30px)}}to{{opacity:1;transform:translateY(0)}}}}
.eyebrow{{font-size:.65rem;letter-spacing:.3em;text-transform:uppercase;color:#3B82F6;font-weight:700;margin-bottom:14px;animation:eyebrowGlow 2s ease infinite alternate}}
@keyframes eyebrowGlow{{from{{color:#3B82F6}}to{{color:#60a5fa;text-shadow:0 0 20px #3B82F6}}}}
.hero-title{{font-size:clamp(3rem,12vw,7rem);font-weight:900;letter-spacing:-.04em;line-height:.9;text-transform:uppercase;
  background:linear-gradient(135deg,#fff 0%,#FFB800 40%,#fff 60%,#64748b 100%);
  background-size:300% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent;
  animation:shimmer 4s linear infinite}}
@keyframes shimmer{{from{{background-position:0% center}}to{{background-position:300% center}}}}
.hero-sub{{color:#334155;font-size:.8rem;margin-top:14px;letter-spacing:.1em;text-transform:uppercase}}
.divider{{width:80px;height:4px;background:linear-gradient(90deg,#3B82F6,#8b5cf6,#FFB800);margin:18px auto 0;border-radius:2px;
  animation:dividerPulse 2s ease infinite alternate}}
@keyframes dividerPulse{{from{{width:60px;opacity:.7}}to{{width:120px;opacity:1}}}}

/* ── SUMMARY ── */
.summary{{display:flex;justify-content:center;gap:24px;padding:20px 24px;flex-wrap:wrap;position:relative;z-index:1;animation:fadeDown .8s 3.2s both}}
.sum-item{{text-align:center;background:#ffffff06;border:1px solid #ffffff10;border-radius:12px;padding:14px 22px;
  animation:sumFloat 4s ease infinite}}
@keyframes sumFloat{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-5px)}}}}
.sum-val{{font-size:1.8rem;font-weight:900}}
.sum-lbl{{font-size:.6rem;text-transform:uppercase;letter-spacing:.12em;color:#475569;margin-top:3px}}

/* ── CARDS ── */
.rankings{{max-width:820px;margin:0 auto;padding:12px 20px 20px;display:flex;flex-direction:column;gap:14px;position:relative;z-index:1}}

.rc{{position:relative;
  animation:var(--enter) .6s cubic-bezier(.22,1,.36,1) var(--delay) both,
             cardFloat var(--fdur) ease var(--fdel) infinite}}
@keyframes cardFloat{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-7px)}}}}

.crown{{text-align:center;font-size:2.5rem;
  animation:crownIn 1s 3.8s both,crownBob 2s 5s ease infinite}}
@keyframes crownIn{{0%{{opacity:0;transform:translateY(-40px) scale(0)}}60%{{transform:translateY(8px) scale(1.2)}}100%{{opacity:1;transform:translateY(0) scale(1)}}}}
@keyframes crownBob{{0%,100%{{transform:rotate(-8deg) scale(1)}}50%{{transform:rotate(8deg) scale(1.15)}}}}

.ci{{border-radius:18px;background:#0c1220;overflow:hidden;position:relative;
  border:1px solid var(--tc,#fff2);
  transition:transform .2s,box-shadow .3s}}
.ci:hover{{transform:translateY(-4px) scale(1.015)}}

/* #1 pulsing glow */
.rc-one .ci{{animation:eliteGlow 2.5s ease infinite}}
@keyframes eliteGlow{{
  0%,100%{{box-shadow:0 0 60px #FFB80040,0 0 120px #FFB80015}}
  50%{{box-shadow:0 0 100px #FFB80070,0 0 200px #FFB80030,0 0 8px #FFB80060 inset}}
}}

/* Develop cards shake continuously */
.rc-dev .ci{{animation:devWiggle 3s ease infinite}}
@keyframes devWiggle{{
  0%,80%,100%{{transform:rotate(0)}}
  82%{{transform:rotate(-1.2deg)}}84%{{transform:rotate(1.2deg)}}
  86%{{transform:rotate(-.8deg)}}88%{{transform:rotate(.8deg)}}
  90%{{transform:rotate(-.4deg)}}92%{{transform:rotate(.4deg)}}
}}

.rn{{position:absolute;right:-5px;top:-15px;font-size:8rem;font-weight:900;line-height:1;
  pointer-events:none;user-select:none;z-index:0;
  color:var(--tc,#fff);opacity:.12;
  -webkit-text-stroke:2px color-mix(in srgb,var(--tc) 40%,transparent);
  animation:rnPulse 3s ease infinite}}
@keyframes rnPulse{{0%,100%{{opacity:.10}}50%{{opacity:.20}}}}

.cb{{position:relative;z-index:1;padding:22px 26px}}

.tlbl{{font-size:.6rem;letter-spacing:.15em;text-transform:uppercase;color:var(--tc);font-weight:800;margin-bottom:6px;
  animation:labelGlow 2s ease infinite alternate}}
@keyframes labelGlow{{from{{opacity:.8}}to{{opacity:1;text-shadow:0 0 12px var(--tc)}}}}

.sname{{font-size:clamp(1.1rem,3vw,1.5rem);font-weight:900;color:#fff;letter-spacing:-.02em;line-height:1.1}}
.ticav{{font-size:clamp(1.4rem,4vw,2rem);font-weight:900;color:#fff;line-height:1}}
.ticav-lbl{{font-size:.6rem;color:#4b5563;text-transform:uppercase;letter-spacing:.08em;margin-top:2px}}
.roast{{font-size:.7rem;color:color-mix(in srgb,var(--tc) 70%,#aaa);font-style:italic;
  margin-bottom:14px;padding:8px 12px;border-radius:8px;border-left:2px solid}}

.badge-grow{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.6rem;font-weight:800;letter-spacing:.08em;
  background:#10B98118;color:#10B981;border:1px solid #10B98140;
  animation:badgePulse 2s ease infinite alternate}}
.badge-ret{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.6rem;font-weight:800;letter-spacing:.08em;
  background:#fff08;color:#6b7280;border:1px solid #fff1}}
@keyframes badgePulse{{from{{box-shadow:none}}to{{box-shadow:0 0 8px #10B98160}}}}

.sgrid2{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}}
.sgrid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}}
.sbox,.mbox{{background:#ffffff06;border:1px solid #fff08;border-radius:10px;padding:11px 13px}}
.slbl{{font-size:.55rem;text-transform:uppercase;letter-spacing:.12em;color:#374151;margin-bottom:4px}}
.sval{{font-size:1.1rem;font-weight:800;line-height:1.2}}
.ssub{{font-size:.6rem;color:#374151;margin-top:2px;margin-bottom:7px}}
.mval{{font-size:1rem;font-weight:800}}
.bw{{background:#fff08;border-radius:99px;height:3px;overflow:hidden;margin-top:6px}}
.bf{{height:100%;border-radius:99px;background:var(--c);width:0;
  animation:barFill .9s cubic-bezier(.34,1.56,.64,1) forwards,barBreath 3s 2s ease infinite}}
@keyframes barFill{{to{{width:var(--w)}}}}
@keyframes barBreath{{0%,100%{{opacity:1}}50%{{opacity:.6}}}}

/* ── METHODOLOGY ── */
.meth{{max-width:820px;margin:0 auto 28px;padding:0 20px;position:relative;z-index:1;animation:fadeDown .8s 3.4s both}}
.meth-title{{font-size:.6rem;letter-spacing:.2em;text-transform:uppercase;color:#475569;font-weight:700;margin-bottom:14px;text-align:center}}
.meth-grid{{background:#0c1220;border:1px solid #ffffff10;border-radius:14px;overflow:hidden}}
.meth-row{{display:flex;align-items:flex-start;gap:16px;padding:14px 18px;border-bottom:1px solid #ffffff08}}
.meth-row:last-child{{border-bottom:none}}
.meth-pct{{font-size:1.4rem;font-weight:900;min-width:54px;line-height:1;padding-top:2px;text-align:center}}
.meth-info{{flex:1}}
.meth-name{{font-size:.75rem;font-weight:700;color:#e2e8f0;margin-bottom:3px}}
.meth-desc{{font-size:.65rem;color:#475569;line-height:1.5}}
.meth-note{{font-size:.6rem;color:#334155;text-align:center;margin-top:10px;font-style:italic}}

/* ── ENTRANCE KEYFRAMES ── */
@keyframes slamDown{{0%{{opacity:0;transform:translateY(-120px) scale(1.1)}}70%{{transform:translateY(8px) scale(.99)}}85%{{transform:translateY(-4px)}}100%{{opacity:1;transform:translateY(0) scale(1)}}}}
@keyframes flipIn{{0%{{opacity:0;transform:perspective(600px) rotateX(-40deg) translateY(30px)}}100%{{opacity:1;transform:perspective(600px) rotateX(0deg) translateY(0)}}}}
@keyframes slideUp{{from{{opacity:0;transform:translateY(50px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes wobbleIn{{0%{{opacity:0;transform:rotate(-2deg) translateY(30px)}}50%{{transform:rotate(1deg)}}100%{{opacity:1;transform:rotate(0) translateY(0)}}}}
</style>
</head>
<body>

<div id="intro">
  <div class="intro-title">⚡ LOADING ⚡</div>
  <div class="lbar"><div class="lfill"></div></div>
  <div class="ltxt">Calculating who's the GOAT...</div>
</div>

<canvas id="bg"></canvas>
<canvas id="confetti"></canvas>

<div class="ticker">
  <div class="ticker-inner">{"  ·  ".join(f"<span>#{i+1}</span> {s['name']} {fmt(s['total'])}" for i,s in enumerate(ranked))}  ·  <span>🏆 GOAT: {ranked[0]['name']}</span>  ·  <span>💀 PRAYERS: {ranked[-1]['name']}</span>  ·  <span>🔮 PIPELINE KING: {max(ranked,key=lambda x:x['future'])['name']}</span>  ·  {"  ·  ".join(f"<span>#{i+1}</span> {s['name']} {fmt(s['total'])}" for i,s in enumerate(ranked))}</div>
</div>

<div class="hero">
  <div class="eyebrow">🏆 Q1 Season · Official Results</div>
  <h1 class="hero-title">Power<br>Rankings</h1>
  <div class="divider"></div>
  <div class="hero-sub">DSR Sales Engineering · {total} SEs · Ranked by total iACV</div>
</div>

<div class="summary">
  <div class="sum-item" style="animation-delay:.1s"><div class="sum-val" style="color:#FFB800">{fmt(team_total)}</div><div class="sum-lbl">Team iACV</div></div>
  <div class="sum-item" style="animation-delay:.3s"><div class="sum-val" style="color:#3B82F6">{team_owl}%</div><div class="sum-lbl">Avg Owl %</div></div>
  <div class="sum-item" style="animation-delay:.5s"><div class="sum-val" style="color:#10B981">{total}</div><div class="sum-lbl">SEs Ranked</div></div>
</div>

<div class="meth">
  <div class="meth-title">📊 HOW RANKINGS ARE CALCULATED</div>
  <div class="meth-grid">
    <div class="meth-row">
      <div class="meth-pct" style="color:#FFB800">65%</div>
      <div class="meth-info">
        <div class="meth-name">Total iACV</div>
        <div class="meth-desc">Combined activate + expansion revenue. Primary driver — no SE with more total revenue can rank below one with less.</div>
      </div>
    </div>
    <div class="meth-row">
      <div class="meth-pct" style="color:#60a5fa">10%</div>
      <div class="meth-info">
        <div class="meth-name">Activate iACV</div>
        <div class="meth-desc">New logo revenue only (deals &gt;$30K, no prior contract). Rewards new business contribution beyond the total.</div>
      </div>
    </div>
    <div class="meth-row">
      <div class="meth-pct" style="color:#34d399">10%</div>
      <div class="meth-info">
        <div class="meth-name">Expansion Median</div>
        <div class="meth-desc">Quality signal — are existing accounts genuinely growing? A $0 median means most wins are flat retentions with no new iACV.</div>
      </div>
    </div>
    <div class="meth-row">
      <div class="meth-pct" style="color:#a78bfa">8%</div>
      <div class="meth-info">
        <div class="meth-name">Future Pipeline %</div>
        <div class="meth-desc">Out-of-quarter emails as % of all emails sent. Are they closing this quarter or building Q2+? Higher = investing forward.</div>
      </div>
    </div>
    <div class="meth-row">
      <div class="meth-pct" style="color:#fbbf24">7%</div>
      <div class="meth-info">
        <div class="meth-name">Owl %</div>
        <div class="meth-desc">Salesforce hygiene — presales stage management and deal note updates. Measures deal awareness and pipeline visibility.</div>
      </div>
    </div>
  </div>
  <div class="meth-note">Each metric is converted to a 1–{total} rank, then weighted. 65% on total iACV is the mathematical minimum where higher revenue always wins.</div>
</div>

<div class="rankings">{cards}</div>

<script>
// ── BACKGROUND STARFIELD ──
const bg=document.getElementById('bg');
const bgc=bg.getContext('2d');
let stars=[];
function resizeBg(){{bg.width=window.innerWidth;bg.height=document.body.scrollHeight;}}
resizeBg();
for(let i=0;i<200;i++) stars.push({{x:Math.random()*bg.width,y:Math.random()*bg.height,r:Math.random()*1.5+.3,s:Math.random()*.4+.1,o:Math.random(),d:Math.random()>.5?1:-1}});
function drawBg(){{
  bgc.clearRect(0,0,bg.width,bg.height);
  stars.forEach(s=>{{
    s.o+=s.d*s.s*.02; if(s.o>1||s.o<0)s.d*=-1;
    bgc.save();bgc.globalAlpha=s.o*.7;bgc.fillStyle='#fff';
    bgc.beginPath();bgc.arc(s.x,s.y,s.r,0,Math.PI*2);bgc.fill();bgc.restore();
  }});
  requestAnimationFrame(drawBg);
}}
drawBg();

// ── CONFETTI ──
const cc=document.getElementById('confetti');
const ctx=cc.getContext('2d');
function resizeCc(){{cc.width=window.innerWidth;cc.height=window.innerHeight;}}
resizeCc();
const COLS=['#FFB800','#3B82F6','#10B981','#EF4444','#8b5cf6','#f9a8d4','#fff'];
let parts=[];
function mkp(burst){{
  return{{x:burst?Math.random()*cc.width:Math.random()*cc.width,
    y:burst?Math.random()*cc.height*.3:-10,
    r:Math.random()*6+3,color:COLS[Math.floor(Math.random()*COLS.length)],
    speed:Math.random()*4+2,angle:Math.random()*360,spin:(Math.random()-.5)*8,
    drift:(Math.random()-.5)*3,life:1,decay:Math.random()*.015+.006,
    shape:Math.random()>.5?'r':'c'}};
}}
function burst(n,b=true){{for(let i=0;i<n;i++)parts.push(mkp(b));}}
let confettiRunning=false;
function drawConfetti(){{
  ctx.clearRect(0,0,cc.width,cc.height);
  parts=parts.filter(p=>p.life>0);
  parts.forEach(p=>{{
    ctx.save();ctx.globalAlpha=p.life;ctx.fillStyle=p.color;
    ctx.translate(p.x,p.y);ctx.rotate(p.angle*Math.PI/180);
    if(p.shape==='r')ctx.fillRect(-p.r,-p.r/2,p.r*2,p.r);
    else{{ctx.beginPath();ctx.arc(0,0,p.r,0,Math.PI*2);ctx.fill();}}
    ctx.restore();
    p.y+=p.speed;p.x+=p.drift;p.angle+=p.spin;p.life-=p.decay;
  }});
  requestAnimationFrame(drawConfetti);
}}
drawConfetti();

// Initial burst on reveal
setTimeout(()=>{{burst(200,true);}},3100);
setTimeout(()=>{{burst(120,true);}},3600);
setTimeout(()=>{{burst(80,true);}},4300);

// Continuous drizzle — a few particles every second forever
setInterval(()=>{{burst(6,false);}},800);

// Extra burst when hovering #1
document.querySelector('.rc-one')?.addEventListener('mouseenter',()=>burst(50,true));

window.addEventListener('resize',()=>{{resizeBg();resizeCc();}});
</script>
</body></html>"""

def main():
    path=Path(sys.argv[1]) if len(sys.argv)>1 else Path("DSR SE Scorecard - Roster.csv")
    if not path.exists(): sys.exit(f"Not found: {path}")
    ses=load(path); ranked=rank(ses); html=generate(ranked)
    out=Path("se_rankings.html")
    out.write_text(html,encoding="utf-8")
    print(f"Written → {out}")

if __name__=="__main__": main()
