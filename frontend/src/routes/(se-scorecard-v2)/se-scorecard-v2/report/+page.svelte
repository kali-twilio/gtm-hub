<script lang="ts">
  import { onMount } from 'svelte';
  import { getSFReport, fmt } from '$lib/api';
  import { theme, sfTeam, sfPeriod, sfSubteam } from '$lib/stores';
  import { tc, fc } from '$lib/colors';

  let data: any = $state(null);
  let view = $state<'tw' | 'all'>('tw');
  let icavMin = $state(0);
  const notesFloorLabel = $derived(icavMin === 0 ? 'All deals' : `$${icavMin >= 1000 ? icavMin/1000 + 'K' : icavMin}+`);
  let colsExpanded = $state(false);
  let rankCriteriaExpanded = $state(false);
  const motionLabels = $derived(data?.motion === 'ae'
    ? { act: 'New Business', exp: 'Strategic', actDesc: "Owner role contains ' NB'", expDesc: "Owner role contains 'Strat'" }
    : { act: 'Activate',     exp: 'Expansion', actDesc: "Owner role contains 'Activation' (DSR Activation sub-teams)", expDesc: "Owner role contains 'Expansion' (DSR Expansion sub-teams)" }
  );

  const filteredRanked = $derived(data ? data.ranked : []);
  const teamActIcav = $derived(data ? data.ranked.reduce((s: number, se: any) => s + se.act_icav, 0) : 0);
  const teamExpIcav = $derived(data ? data.ranked.reduce((s: number, se: any) => s + se.exp_icav, 0) : 0);
  const actSes      = $derived(data ? data.act_sorted.filter((s: any) => s.act_icav > 0) : []);
  const expSes      = $derived(data ? data.exp_sorted.filter((s: any) => s.exp_icav > 0) : []);
  const actTotals   = $derived({
    wins:     actSes.reduce((n: number, s: any) => n + s.act_wins, 0),
    icav:     actSes.reduce((n: number, s: any) => n + s.act_icav, 0),
    avg:      actSes.length ? Math.round(actSes.reduce((n: number, s: any) => n + s.act_avg, 0) / actSes.length) : 0,
    inq:      actSes.reduce((n: number, s: any) => n + (s.email_act_inq ?? 0), 0),
    outq:     actSes.reduce((n: number, s: any) => n + (s.email_act_outq ?? 0), 0),
    outq_icav:actSes.reduce((n: number, s: any) => n + (s.email_act_outq_icav ?? 0), 0),
  });
  const expTotals   = $derived({
    wins:     expSes.reduce((n: number, s: any) => n + s.exp_wins, 0),
    icav:     expSes.reduce((n: number, s: any) => n + s.exp_icav, 0),
    avg:      expSes.length ? Math.round(expSes.reduce((n: number, s: any) => n + s.exp_avg, 0) / expSes.length) : 0,
    inq:      data ? data.ranked.reduce((n: number, s: any) => n + (s.email_exp_inq ?? 0), 0) : 0,
    outq:     data ? data.ranked.reduce((n: number, s: any) => n + (s.email_exp_outq ?? 0), 0) : 0,
    outq_icav:data ? data.ranked.reduce((n: number, s: any) => n + (s.email_exp_outq_icav ?? 0), 0) : 0,
  });

  function med(vals: number[]): number {
    const v = vals.filter(x => x > 0).sort((a, b) => a - b);
    if (!v.length) return 0;
    const m = Math.floor(v.length / 2);
    return v.length % 2 ? v[m] : Math.round((v[m - 1] + v[m]) / 2);
  }

  function emailTotal(se: any): number {
    return (se.email_act_inq ?? 0) + (se.email_act_outq ?? 0)
         + (se.email_exp_inq ?? 0) + (se.email_exp_outq ?? 0);
  }

  const medians = $derived(data ? {
    act_icav:   med(data.ranked.map((s: any) => s.act_icav)),
    act_wins:   med(data.ranked.map((s: any) => s.act_wins)),
    exp_icav:   med(data.ranked.map((s: any) => s.exp_icav)),
    exp_wins:   med(data.ranked.map((s: any) => s.exp_wins)),
    total_icav: med(data.ranked.map((s: any) => s.total_icav)),
    win_rate:   med(data.ranked.map((s: any) => s.win_rate)),
    emails:              med(data.ranked.map((s: any) => emailTotal(s))),
    note_hv_avg_entries: med(data.ranked.map((s: any) => s.note_hv_avg_entries ?? 0)),
  } : null);

  const ICAV_PRESETS = [
    { label: 'All', value: 0 },
    { label: '$10K+', value: 10_000 },
    { label: '$30K+', value: 30_000 },
    { label: '$50K+', value: 50_000 },
    { label: '$100K+', value: 100_000 },
  ];


  function bar(value: number, max: number, color: string) {
    const w = max ? Math.round(value / max * 100) : 0;
    return `<div style="min-width:80px;width:100%;background:${$theme==='twilio'?'rgba(13,18,43,0.08)':'rgba(255,255,255,0.08)'};border-radius:2px;height:5px"><div style="height:5px;border-radius:2px;background:${color};width:${w}%"></div></div>`;
  }

  function seIcav(se: any) {
    return view === 'all' ? (se.total_icav + se.non_tw_total_icav) : se.total_icav;
  }

  async function loadWithMin(min: number) {
    icavMin = min;
    data = null;
    data = await getSFReport($sfTeam, $sfPeriod, min, $sfSubteam);
  }

  onMount(async () => { data = await getSFReport($sfTeam, $sfPeriod, icavMin, $sfSubteam); });
</script>

{#if !data}
<div class="min-h-screen flex items-center justify-center">
  <div style="font-size:18px;font-weight:700;color:var(--text-muted)">Loading intel…</div>
</div>
{:else}

<div style="position:fixed;top:{$theme==='twilio'?'68px':'26px'};left:{$theme==='twilio'?'16px':'48px'};z-index:9999">
  <a href="/se-scorecard-v2" class="p5-back-btn">◀ Back</a>
</div>

<div style="max-width:1200px;margin:0 auto;padding:60px 24px 40px">

  <div style="margin-bottom:28px">
    <div class="p5-badge" style="margin-bottom:10px">SE Scorecard V2 · {data.quarter}</div>
    <h1 style="font-size:36px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:3px 3px 0 var(--red)':''}">SE Scorecard</h1>
    <p style="font-size:13px;color:var(--text-muted);font-weight:600;margin-top:4px">{data.total} SEs · Live data from Salesforce</p>
  </div>

  <div style="display:grid;grid-template-columns:repeat({[true, teamActIcav>0, teamExpIcav>0, true].filter(Boolean).length},1fr);gap:12px;margin-bottom:24px">
    {#each [
      {label:'Team Total iACV', val:fmt(data.team_icav), show:true},
      {label:motionLabels.act+' iACV', val:fmt(teamActIcav), show:teamActIcav>0},
      {label:motionLabels.exp+' iACV', val:fmt(teamExpIcav), show:teamExpIcav>0},
      {label:'SEs Analysed',    val:String(data.total), show:true},
    ].filter(s => s.show) as s}
    <div class="p5-panel" style="padding:18px 20px">
      <div style="font-size:10px;color:var(--red);font-weight:700;text-transform:uppercase;letter-spacing:0.18em;font-style:{$theme==='p5'?'italic':'normal'};margin-bottom:6px">{s.label}</div>
      <div style="font-size:28px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text);{$theme==='p5'?'text-shadow:2px 2px 0 var(--red)':''}">{s.val}</div>
    </div>
    {/each}
  </div>

  <!-- Controls row -->
  <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;margin-bottom:20px">

    <!-- View toggle -->
    <div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-muted);margin-bottom:6px">Show</div>
      <div style="display:flex;gap:6px">
        {#each [{key:'tw',label:'Technical Wins'},{key:'all',label:'All Closed Won'}] as opt}
        <button onclick={() => view = opt.key as 'tw' | 'all'}
          style="padding:5px 12px;font-size:12px;font-weight:700;border-radius:5px;border:1px solid {view===opt.key?'var(--red)':'rgba(var(--red-rgb),0.2)'};background:{view===opt.key?'rgba(var(--red-rgb),0.1)':'transparent'};color:{view===opt.key?'var(--red)':'var(--text-muted)'};cursor:pointer"
        >{opt.label}</button>
        {/each}
      </div>
    </div>

    <!-- iACV cutoff -->
    <div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-muted);margin-bottom:6px">Min deal size</div>
      <div style="display:flex;gap:6px">
        {#each ICAV_PRESETS as p}
        <button onclick={() => loadWithMin(p.value)}
          style="padding:5px 12px;font-size:12px;font-weight:700;border-radius:5px;border:1px solid {icavMin===p.value?'var(--red)':'rgba(var(--red-rgb),0.2)'};background:{icavMin===p.value?'rgba(var(--red-rgb),0.1)':'transparent'};color:{icavMin===p.value?'var(--red)':'var(--text-muted)'};cursor:pointer"
        >{p.label}</button>
        {/each}
      </div>
    </div>


  </div>

  <!-- Column explanations (collapsible) -->
  <div style="margin-bottom:20px">
    <button onclick={() => colsExpanded = !colsExpanded}
      style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:transparent;border:1px solid rgba(var(--red-rgb),0.15);border-radius:{colsExpanded?'6px 6px 0 0':'6px'};cursor:pointer;color:var(--text-muted);font-size:12px;font-weight:600">
      <span>ℹ How columns are calculated</span>
      <span style="font-size:10px;transition:transform 0.2s;transform:{colsExpanded?'rotate(180deg)':'rotate(0)'}">▼</span>
    </button>
    {#if colsExpanded}
    <div style="border:1px solid rgba(var(--red-rgb),0.15);border-top:none;border-radius:0 0 6px 6px;overflow:hidden">
      {#each [
        [motionLabels.act, 'Sum of iACV from Closed Won TW opps classified as ' + motionLabels.act + '. ' + motionLabels.actDesc + '.'],
        [motionLabels.exp, 'Sum of iACV from Closed Won TW opps classified as ' + motionLabels.exp + '. ' + motionLabels.expDesc + (data.motion === 'dsr' ? '. A $0 median means flat retentions with no upsell.' : '') + '.'],
        ['Total iACV',  'Activate + Expansion iACV combined. In "All Closed Won" view, the non-TW delta is shown inline.'],
        ['Win Rate',    '(Closed Won) ÷ (Closed Won + Closed Lost) for this SE across the period. Displayed for reference only — not used in ranking, as close rate depends on DSR quality, not SE performance.'],
        ['Emails',      'In-Q: all emails sent to opps closing within the period, split by activate/expansion. Pipe: all emails to opps closing after the period end + their iACV. Sourced from Salesforce Tasks with TaskSubtype = Email, classified by opp owner role.'],
        ['SE Notes',    'Sales_Engineer_Notes__c ("Solutions Team Notes") and SE_Notes_History__c ("Solutions Team Notes History") on TW Closed Won opps. "notes" = opps with SE notes filled. "history" = total entry count across TW opps.'],
        ['Tier',        'Elite = top 20% · Strong = 21–50% · Steady = 51–75% · Develop = bottom 25%. Based on the ranking formula below.'],
      ] as [col, desc], i}
      <div style="display:grid;grid-template-columns:90px 1fr;gap:12px;padding:9px 14px;{i>0?'border-top:1px solid rgba(var(--red-rgb),0.08)':''}">
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--red);padding-top:1px">{col}</span>
        <span style="font-size:12px;color:var(--text-muted);line-height:1.5">{desc}</span>
      </div>
      {/each}
    </div>
    {/if}
  </div>

  <!-- Overall Rankings -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)">
      <div style="display:flex;align-items:center;justify-content:space-between">
        <h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text)">Overall Rankings</h2>
        <button
          onclick={() => rankCriteriaExpanded = !rankCriteriaExpanded}
          style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-muted);background:transparent;border:1px solid rgba(var(--red-rgb),0.2);border-radius:4px;padding:4px 10px;cursor:pointer"
        >Ranking Criteria {rankCriteriaExpanded ? '▲' : '▼'}</button>
      </div>
      {#if rankCriteriaExpanded}
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:10px">
        {#each [
          {w:'50%', label:'Total iACV',      desc:'Primary output — revenue generated this period'},
          {w:'30%', label:'Notes Coverage',  desc:notesFloorLabel+' opps with both notes fields filled ÷ total — harder to maintain across more deals'},
          {w:'20%', label:'Win Count',       desc:'Total closed won TW deals — same iACV + same notes rate, more wins = higher rank'},
        ] as c}
        <div style="display:flex;gap:8px;align-items:flex-start;padding:6px 8px;background:rgba(var(--red-rgb),0.04);border-left:3px solid rgba(var(--red-rgb),0.3);{$theme==='twilio'?'border-radius:0 4px 4px 0':''}">
          <span style="font-size:13px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--red);flex-shrink:0;min-width:32px">{c.w}</span>
          <div>
            <div style="font-size:11px;font-weight:700;color:var(--text);text-transform:uppercase;letter-spacing:0.08em">{c.label}</div>
            <div style="font-size:10px;color:var(--text-muted);margin-top:1px">{c.desc}</div>
          </div>
        </div>
        {/each}
      </div>
      <p style="font-size:10px;color:var(--text-faint);margin-top:8px">Strict tiebreaker order — highest iACV is always #1. Notes and wins only decide ties within equal or near-equal iACV.</p>
      {/if}
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)">
          <tr>{#each ['#','SE',motionLabels.act,motionLabels.exp,'Total iACV','Win Rate','Emails','SE Notes','Tier'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap">{h}</th>{/each}</tr>
        </thead>
        <tbody>
          {#each filteredRanked as se}
          {@const colors = tc(se.tier, $theme)}
          {@const nonTwWins = se.non_tw_act_wins + se.non_tw_exp_wins}
          {@const et = emailTotal(se)}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{se.rank}</td>
            <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>

            <!-- Activate: iACV + wins -->
            <td style="padding:10px 16px">
              <div style="font-weight:700;color:var(--act-color)">{fmt(se.act_icav)}{#if view==='all' && se.non_tw_act_icav > 0}<span style="font-size:10px;font-weight:400;color:var(--text-muted)"> +{fmt(se.non_tw_act_icav)}</span>{/if}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:1px">{se.act_wins} {se.act_wins === 1 ? 'win' : 'wins'}</div>
            </td>

            <!-- Expansion: iACV + wins -->
            <td style="padding:10px 16px">
              <div style="font-weight:700;color:var(--exp-color)">{fmt(se.exp_icav)}{#if view==='all' && se.non_tw_exp_icav > 0}<span style="font-size:10px;font-weight:400;color:var(--text-muted)"> +{fmt(se.non_tw_exp_icav)}</span>{/if}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:1px">{se.exp_wins} {se.exp_wins === 1 ? 'win' : 'wins'}</div>
            </td>

            <!-- Total iACV -->
            <td style="padding:10px 16px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text)">
              {fmt(seIcav(se))}{#if view==='all' && nonTwWins > 0}<div style="font-size:10px;color:var(--text-muted);font-weight:400">{nonTwWins} non-TW</div>{/if}
            </td>

            <!-- Win Rate -->
            <td style="padding:10px 16px">
              <div style="font-weight:700;color:{se.win_rate >= 50 ? 'var(--exp-color)' : se.win_rate > 0 ? 'var(--text-muted)' : 'var(--text-faint)'}">{se.win_rate > 0 ? se.win_rate+'%' : '—'}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:1px">{se.closed_won}W / {se.closed_lost}L</div>
            </td>

            <!-- Total emails -->
            <td style="padding:10px 16px;font-weight:700;color:{et > 0 ? 'var(--text)' : 'var(--text-faint)'}">
              {et > 0 ? et : '—'}
            </td>

            <!-- SE Notes: coverage + avg entries -->
            <td style="padding:10px 16px;font-size:12px;line-height:1.6">
              {#if (se.note_hv_total ?? 0) > 0}
                <div style="font-weight:700;color:{se.note_hv_covered === se.note_hv_total ? 'var(--exp-color)' : se.note_hv_covered > 0 ? 'var(--text)' : 'var(--red)'}">{se.note_hv_covered}/{se.note_hv_total}</div>
                <div style="font-size:11px;color:var(--text-muted)">{se.note_hv_avg_entries} avg entries</div>
              {:else}
                <span style="color:var(--text-faint)">—</span>
              {/if}
            </td>

            <td style="padding:10px 16px"><span style="display:inline-block;padding:2px 10px 2px 8px;font-size:10px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.1em;background:{colors.bg};color:{colors.color};{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">{se.tier}</span></td>
          </tr>
          {/each}
          {#if medians}
          <tr style="border-top:2px solid rgba(var(--red-rgb),0.15);background:rgba(var(--red-rgb),0.03)">
            <td style="padding:10px 16px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-muted)">MED</td>
            <td style="padding:10px 16px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-muted)">Team Median</td>
            <td style="padding:10px 16px">
              <div style="font-weight:700;color:var(--act-color);opacity:0.7">{fmt(medians.act_icav)}</div>
              <div style="font-size:11px;color:var(--text-muted)">{medians.act_wins} wins</div>
            </td>
            <td style="padding:10px 16px">
              <div style="font-weight:700;color:var(--exp-color);opacity:0.7">{fmt(medians.exp_icav)}</div>
              <div style="font-size:11px;color:var(--text-muted)">{medians.exp_wins} wins</div>
            </td>
            <td style="padding:10px 16px;font-weight:900;color:var(--text-muted)">{fmt(medians.total_icav)}</td>
            <td style="padding:10px 16px;font-weight:700;color:var(--text-muted)">{medians.win_rate > 0 ? medians.win_rate+'%' : '—'}</td>
            <td style="padding:10px 16px;font-weight:700;color:var(--text-muted)">{medians.emails > 0 ? medians.emails : '—'}</td>
            <td style="padding:10px 16px;font-size:12px;color:var(--text-muted)">
              {medians.note_hv_avg_entries > 0 ? medians.note_hv_avg_entries+' avg entries' : '—'}
            </td>
            <td style="padding:10px 16px">—</td>
          </tr>
          {/if}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Activate + Expansion -->
  <div style="display:flex;flex-direction:column;gap:16px;margin-bottom:20px">
    {#if actSes.length > 0}
    <div class="p5-panel">
      <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)">
        <h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);margin-bottom:2px">{motionLabels.act}</h2>
        <p style="font-size:12px;color:var(--text-muted)">{motionLabels.actDesc}</p>
      </div>
      <!-- Activate totals summary -->
      <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:0;border-bottom:2px solid rgba(var(--act-rgb),0.2)">
        {#each [{l:'Total Wins',v:String(actTotals.wins)},{l:'Total iACV',v:fmt(actTotals.icav)},{l:'Avg Deal',v:fmt(actTotals.avg)},{l:'In-Q Emails',v:String(actTotals.inq)},{l:'Pipe Emails',v:actTotals.outq > 0 ? actTotals.outq + (actTotals.outq_icav > 0 ? ' · '+fmt(actTotals.outq_icav) : '') : '—'}] as t}
        <div style="padding:12px 16px;border-right:1px solid rgba(var(--red-rgb),0.08);last:border-none">
          <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--act-color);margin-bottom:4px">{t.l}</div>
          <div style="font-size:16px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text)">{t.v}</div>
        </div>
        {/each}
      </div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="background:rgba(var(--red-rgb),0.06)"><tr>{#each ['#','SE','Wins','iACV','Avg','Median','In-Q Emails','Pipe Emails'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap">{h}</th>{/each}</tr></thead>
          <tbody>
            {#each data.act_sorted as se, i}
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
              <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{i + 1}</td>
              <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
              <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.act_wins}</td>
              <td style="padding:10px 16px;color:var(--act-color);font-weight:700">{fmt(se.act_icav)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.act_avg)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.act_median)}</td>
              <td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.email_act_inq ?? 0) > 0 ? se.email_act_inq : '—'}</td>
              <td style="padding:10px 16px;color:var(--act-color);font-weight:700">
                {#if (se.email_act_outq ?? 0) > 0}{se.email_act_outq}{#if (se.email_act_outq_icav ?? 0) > 0} <span style="font-size:11px;color:var(--text-muted);font-weight:400">{fmt(se.email_act_outq_icav)}</span>{/if}{:else}—{/if}
              </td>
            </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
    {/if}
    {#if expSes.length > 0}
    <div class="p5-panel">
      <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)">
        <h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);margin-bottom:2px">{motionLabels.exp}{data.motion === 'dsr' ? ' — Land & Expand' : ''}</h2>
        <p style="font-size:12px;color:var(--text-muted)">{motionLabels.expDesc}{data.motion === 'dsr' ? ' · $0 median = flat retentions' : ''}</p>
      </div>
      <!-- Expansion totals summary -->
      <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:0;border-bottom:2px solid rgba(var(--exp-rgb),0.2)">
        {#each [
          {l:'Total Wins',  v:String(expTotals.wins)},
          {l:'Total iACV',  v:fmt(expTotals.icav)},
          {l:'Avg Deal',    v:fmt(expTotals.avg)},
          {l:'In-Q Emails', v:expTotals.inq > 0 ? String(expTotals.inq) : '—'},
          {l:'Pipe Emails', v:expTotals.outq > 0 ? expTotals.outq + (expTotals.outq_icav > 0 ? ' · '+fmt(expTotals.outq_icav) : '') : '—'},
        ] as t}
        <div style="padding:12px 16px;border-right:1px solid rgba(var(--red-rgb),0.08)">
          <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--exp-color);margin-bottom:4px">{t.l}</div>
          <div style="font-size:16px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text)">{t.v}</div>
        </div>
        {/each}
      </div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="background:rgba(var(--red-rgb),0.06)"><tr>{#each ['#','SE','Wins','iACV','Avg','Median','Status','In-Q Emails','Pipe Emails'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap">{h}</th>{/each}</tr></thead>
          <tbody>
            {#each data.exp_sorted as se, i}
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
              <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{i + 1}</td>
              <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
              <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.exp_wins}</td>
              <td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{fmt(se.exp_icav)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.exp_avg)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.exp_median)}</td>
              <td style="padding:10px 16px">
                {#if se.exp_growing}
                  <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;background:{$theme==='twilio'?'#F0FDF4':'rgba(0,232,122,0.12)'};color:var(--exp-color);border:1px solid rgba(var(--exp-rgb),0.3);{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">Growing</span>
                {:else}
                  <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;background:{$theme==='twilio'?'var(--dark)':'rgba(255,255,255,0.05)'};color:var(--text-muted);border:1px solid rgba(var(--red-rgb),0.1);{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">Retaining</span>
                {/if}
              </td>
              <td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.email_exp_inq ?? 0) > 0 ? se.email_exp_inq : '—'}</td>
              <td style="padding:10px 16px;color:var(--exp-color);font-weight:700">
                {#if (se.email_exp_outq ?? 0) > 0}{se.email_exp_outq}{#if (se.email_exp_outq_icav ?? 0) > 0} <span style="font-size:11px;color:var(--text-muted);font-weight:400">{fmt(se.email_exp_outq_icav)}</span>{/if}{:else}—{/if}
              </td>
            </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
    {/if}
  </div>

  <!-- Largest Deals -->
  {#if data.deal_sorted?.length}
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)"><h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text)">Largest Deals</h2></div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)"><tr>{#each ['SE','Value','AE','Deal'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'}">{h}</th>{/each}</tr></thead>
        <tbody>
          {#each data.deal_sorted as se}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
            <td style="padding:10px 16px;color:{$theme==='twilio'?'#B45309':'var(--yellow)'};font-weight:900;font-style:{$theme==='p5'?'italic':'normal'}">{fmt(se.largest_deal_value)}</td>
            <td style="padding:10px 16px;color:var(--text-muted)">{se.largest_deal_dsr || '—'}</td>
            <td style="padding:10px 16px;color:var(--text-muted);font-size:12px">{se.largest_deal.slice(0,60)}{se.largest_deal.length > 60 ? '…' : ''}</td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
  {/if}

  <!-- Notes Quality -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)">
      <h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);margin-bottom:2px">SE Notes Quality</h2>
      <p style="font-size:12px;color:var(--text-muted)">Coverage = both Solutions Team Notes fields filled · Entries counted from [Date: Name] timestamps in history</p>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)">
          <tr>{#each ['SE', notesFloorLabel+' TW Opps','Both Fields Covered','Coverage %','Total Entries','Avg Entries / Opp'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap">{h}</th>{/each}</tr>
        </thead>
        <tbody>
          {#each [...data.ranked].filter((s: any) => (s.note_hv_total ?? 0) > 0).sort((a: any, b: any) => (b.note_hv_covered / b.note_hv_total) - (a.note_hv_covered / a.note_hv_total) || b.note_hv_avg_entries - a.note_hv_avg_entries) as se}
          {@const pct = se.note_hv_total > 0 ? Math.round(se.note_hv_covered / se.note_hv_total * 100) : 0}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
            <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.note_hv_total}</td>
            <td style="padding:10px 16px;font-weight:700;color:{se.note_hv_covered === se.note_hv_total ? 'var(--exp-color)' : se.note_hv_covered > 0 ? 'var(--text)' : 'var(--red)'}">{se.note_hv_covered}</td>
            <td style="padding:10px 16px">
              <div style="display:flex;align-items:center;gap:8px">
                <span style="font-weight:700;color:{pct === 100 ? 'var(--exp-color)' : pct >= 50 ? 'var(--text)' : 'var(--red)'}">{pct}%</span>
                <div style="flex:1;min-width:60px;background:rgba(var(--red-rgb),0.1);border-radius:2px;height:4px"><div style="height:4px;border-radius:2px;background:{pct === 100 ? 'var(--exp-color)' : pct >= 50 ? 'var(--text-muted)' : 'var(--red)'};width:{pct}%"></div></div>
              </div>
            </td>
            <td style="padding:10px 16px;color:var(--text-muted)">{se.note_hv_entries}</td>
            <td style="padding:10px 16px;font-weight:700;color:{se.note_hv_avg_entries >= 5 ? 'var(--exp-color)' : se.note_hv_avg_entries >= 2 ? 'var(--text)' : 'var(--text-muted)'}">{se.note_hv_avg_entries}</td>
          </tr>
          {/each}
          {#each [...data.ranked].filter((s: any) => (s.note_hv_total ?? 0) === 0) as se}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05);opacity:0.4">
            <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
            <td colspan="5" style="padding:10px 16px;font-size:11px;color:var(--text-faint)">No closed won opps ≥ {notesFloorLabel} this period</td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Trends -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)"><h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text)">Trends &amp; Flags</h2></div>
    <div style="padding:16px;display:flex;flex-direction:column;gap:8px">
      {#each data.trends as [cat, msg]}
      {@const color = fc(cat, $theme)}
      <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 14px;border-left:4px solid {color};background:rgba(var(--red-rgb),0.03);{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;font-style:{$theme==='p5'?'italic':'normal'};color:{color};width:80px;flex-shrink:0">{cat}</span>
        <span style="font-size:13px;font-weight:500;color:var(--text-muted)">{msg}</span>
      </div>
      {/each}
    </div>
  </div>

  <!-- SE Profiles grid -->
  <div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
      <div class="p5-badge">SE Profiles</div>
      <div style="flex:1;height:1px;background:rgba(var(--red-rgb),0.15)"></div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
      {#each data.ranked as se}
      {@const colors = tc(se.tier, $theme)}
      <div class="p5-panel" style="padding:16px;display:flex;flex-direction:column;gap:10px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
              <span style="font-size:11px;color:var(--text-faint);font-style:{$theme==='p5'?'italic':'normal'}">#{se.rank}</span>
              <span style="font-size:14px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text)">{se.name}</span>
            </div>
            <span style="display:inline-block;background:{colors.bg};color:{colors.color};border:1px solid {colors.color}40;padding:2px 10px 2px 8px;font-size:10px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.12em;{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">{se.tier}</span>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:18px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text);{$theme==='p5'?'text-shadow:1px 1px 0 var(--red)':''}">{fmt(se.total_icav)}</div>
            <div style="font-size:10px;color:var(--text-faint);text-transform:uppercase;letter-spacing:0.12em">total iACV</div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
          <div style="background:rgba(var(--act-rgb),0.08);border:1px solid rgba(var(--act-rgb),0.2);border-left:3px solid var(--act-color);padding:10px;{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
            <div style="font-size:9px;color:var(--act-color);font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:4px">{motionLabels.act}</div>
            <div style="font-size:14px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--act-glow)">{fmt(se.act_icav)}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:2px">{se.act_wins} wins</div>
            {@html bar(se.act_icav, data.max_act_icav, $theme==='twilio'?'#006EFF':'#3B82F6')}
          </div>
          <div style="background:rgba(var(--exp-rgb),0.08);border:1px solid rgba(var(--exp-rgb),0.2);border-left:3px solid var(--exp-color);padding:10px;{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
            <div style="font-size:9px;color:var(--exp-color);font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:4px">{motionLabels.exp}</div>
            <div style="font-size:14px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-glow)">{fmt(se.exp_icav)}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:2px">{se.exp_wins} wins</div>
            {@html bar(se.exp_icav, data.max_exp_icav, $theme==='twilio'?'#178742':'#10B981')}
          </div>
        </div>
        <!-- Individual highlights -->
        <div style="display:flex;flex-wrap:wrap;gap:10px;font-size:12px;color:var(--text-muted);border-top:1px solid rgba(var(--red-rgb),0.08);padding-top:8px">
          {#if se.largest_deal_value > 0}
          <span>Biggest deal <strong style="color:var(--text)">{fmt(se.largest_deal_value)}</strong></span>
          {/if}
          <span>Emails <strong style="color:var(--text)">{emailTotal(se)}</strong></span>
          {#if (se.note_hv_total ?? 0) > 0}
          <span>Notes <strong style="color:{se.note_hv_covered === se.note_hv_total ? 'var(--exp-color)' : se.note_hv_covered > 0 ? 'var(--text)' : 'var(--red)'}">{se.note_hv_covered}/{se.note_hv_total}</strong> · <strong style="color:var(--text)">{se.note_hv_avg_entries} avg</strong></span>
          {/if}
        </div>

        {#if se.flags?.length}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px">
          {#each se.flags as [cat, msg]}
          {@const color = fc(cat, $theme)}
          <div style="border-left:3px solid {color};background:rgba(var(--red-rgb),0.03);padding:6px 8px;min-height:44px;{$theme==='twilio'?'border-radius:0 4px 4px 0':''}">
            <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:{color};margin-bottom:2px">{cat}</div>
            <div style="font-size:10px;color:var(--text-muted);line-height:1.3">{msg}</div>
          </div>
          {/each}
        </div>
        {/if}
      </div>
      {/each}
    </div>
  </div>

</div>
{/if}
