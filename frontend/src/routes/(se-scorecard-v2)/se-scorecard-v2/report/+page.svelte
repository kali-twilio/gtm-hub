<script lang="ts">
  import { onMount } from 'svelte';
  import { getSFReport, fmt, fmtMrr } from '$lib/api';
  import { theme, sfTeam, sfPeriod, sfSubteam, user } from '$lib/stores';
  import { tc, fc } from '$lib/colors';

  let data: any = $state(null);
  let view = $state<'tw' | 'all'>('tw');
  let icavMin = $state(0);
  const notesFloorLabel = $derived(icavMin === 0 ? 'All deals' : `$${icavMin >= 1000 ? icavMin/1000 + 'K' : icavMin}+`);
  let rankCriteriaExpanded = $state(false);
  let colTipIdx = $state(-1);
  let actColTipIdx = $state(-1);
  let expColTipIdx = $state(-1);
  let notesFilter = $state(false);
  let showActivity = $state(false);
  let titleFilter   = $state('');
  let productFilter = $state('');

  // Returns a copy of an SE with iACV/wins recalculated from only fully-documented
  // TW opps (both Sales_Engineer_Notes__c and SE_Notes_History__c filled).
  function _notesFiltered(se: any): any {
    const keep = (se.tw_opps_detail ?? []).filter((o: any) => o.has_notes && o.has_history);
    const actMots = new Set(['act', 'nb']);
    const actOpps = keep.filter((o: any) => actMots.has(o.motion));
    const expOpps = keep.filter((o: any) => !actMots.has(o.motion));
    const act_icav = actOpps.reduce((s: number, o: any) => s + (o.icav ?? 0), 0);
    const exp_icav = expOpps.reduce((s: number, o: any) => s + (o.icav ?? 0), 0);
    const medianOf = (arr: any[]) => {
      const s = [...arr].sort((a: any, b: any) => a.icav - b.icav);
      return s.length ? s[Math.floor(s.length / 2)].icav : 0;
    };
    const act_wins   = actOpps.length;
    const closed_lost = se.closed_lost ?? 0;
    const wr_total    = act_wins + closed_lost;
    return {
      ...se,
      act_icav,  act_wins,
      act_avg:    act_wins ? Math.round(act_icav / act_wins) : 0,
      act_median: medianOf(actOpps),
      exp_icav,  exp_wins: expOpps.length,
      exp_avg:    expOpps.length ? Math.round(exp_icav / expOpps.length) : 0,
      exp_median: medianOf(expOpps),
      total_icav: act_icav + exp_icav,
      closed_won: act_wins,
      win_rate:   wr_total > 0 ? Math.round(act_wins / wr_total * 100) : 0,
    };
  }

  const motionLabels = $derived(data?.motion === 'ae'
    ? { act: 'New Business', exp: 'Strategic', actDesc: "Owner role contains ' NB'", expDesc: "Owner role contains 'Strat'" }
    : { act: 'Activate',     exp: 'Expansion', actDesc: "Owner role contains 'Activation' (DSR Activation sub-teams)", expDesc: "Owner role contains 'Expansion' (DSR Expansion sub-teams)" }
  );
  const colDefs = $derived(data ? [
    {h:'#',              show:true,          tip:`Rank by composite score: 85% iACV · 8% MRR% · 5% ARR · 2% notes. Each metric percentile-ranked 0–100 within the team.`},
    {h:'SE',             show:true,          tip:seLevelTip},
    {h:motionLabels.act, show:hasActCol,     tip:`Sum of iACV from Technical Win Closed Won opps classified as ${motionLabels.act}. ${motionLabels.actDesc}. Only TW opps count toward ranking.`},
    {h:motionLabels.exp, show:hasExpCol,     tip:`Sum of iACV from Technical Win Closed Won opps classified as ${motionLabels.exp}. ${motionLabels.expDesc}. Only TW opps count toward ranking.`},
    {h:'Total iACV',     show:true,          tip:`${motionLabels.act} + ${motionLabels.exp} iACV combined (TW only). In "All Closed Won" view the non-TW delta is shown inline.`},
    {h:'Quarter MRR Δ', show:hasArrCol,     tip:`Total MRR change across the SE's ${motionLabels.exp.toLowerCase()} accounts: avg monthly usage in the opp's close quarter minus avg of the 3 months prior. % is total-based so it always matches the ↑/↓ direction. Each account counted once.`},
    {h:'SE Notes',       show:hasNotesCol,   tip:'Opps with both Sales_Engineer_Notes__c and SE_Notes_History__c filled ÷ total TW Closed Won opps above the iACV floor. Avg entries = history entry count per opp.'},
    {h:'Emails',         show:hasEmailCol,   tip:`Salesforce Tasks (TaskSubtype = Email) sent to Opportunities during the period. Classified by opp owner role into ${motionLabels.act.toLowerCase()} vs ${motionLabels.exp.toLowerCase()}, and in-Q (closing this period) vs pipeline (future opps).`},
    {h:'Meetings',       show:hasMeetingCol, tip:`Salesforce Events linked to Opportunities during the period. Recurring series deduplicated — same series on the same opp counts once. In-Q vs pipeline split matches email logic.`},
  ].filter(c => c.show) : []);

  function titleLevel(t: string): number {
    const l = t.toLowerCase();
    if (l.includes('flex strategic') || l.includes('senior presales architect')) return 6;
    if (l.includes('presales architect') || l.includes('solutions architect')) return 5;
    if (l.includes('principal')) return 4;
    if (l.includes('senior presales engineer')) return 3;
    return 0;
  }
  const titleGroups = $derived(data ? (() => {
    const titles = [...new Set<string>(data.ranked.map((s: any) => s.title || '').filter(Boolean))];
    const byLevel: Record<number, string[]> = {};
    for (const t of titles) {
      const lvl = titleLevel(t);
      if (!byLevel[lvl]) byLevel[lvl] = [];
      byLevel[lvl].push(t);
    }
    for (const lvl of Object.keys(byLevel)) byLevel[+lvl].sort((a, b) => a.localeCompare(b));
    return Object.entries(byLevel)
      .sort(([a], [b]) => +b - +a)
      .map(([lvl, titles]) => ({ level: +lvl, label: +lvl > 0 ? `Level ${lvl}` : 'Other', titles }));
  })() : []);

  function titleMatchesFilter(t: string, f: string): boolean {
    if (!f) return true;
    if (f.startsWith('level:')) return titleLevel(t) === +f.slice(6);
    return t === f;
  }

  function primaryProduct(se: any): string {
    const opps: any[] = se.tw_opps_detail ?? [];
    const totals: Record<string, number> = {};
    for (const o of opps) {
      const p = o.product || '';
      if (p) totals[p] = (totals[p] ?? 0) + (o.icav ?? 0);
    }
    const entries = Object.entries(totals);
    if (!entries.length) return '';
    return entries.sort((a, b) => b[1] - a[1])[0][0];
  }

  const productList = $derived(data ? (() => {
    // Only include products where at least one SE (after title filter) has it as their primary.
    // Sum by each SE's total iACV so ranking reflects actual output, not raw opp counts.
    const base = titleFilter ? data.ranked.filter((s: any) => titleMatchesFilter(s.title || '', titleFilter)) : data.ranked;
    const totals: Record<string, number> = {};
    for (const se of base as any[]) {
      const p = primaryProduct(se);
      if (p) totals[p] = (totals[p] ?? 0) + ((se as any).total_icav ?? 0);
    }
    return Object.entries(totals).sort((a, b) => b[1] - a[1]).map(([p]) => p);
  })() : []);

  const filteredRanked = $derived(data ? (() => {
    let base = titleFilter ? data.ranked.filter((s: any) => titleMatchesFilter(s.title || '', titleFilter)) : data.ranked;
    if (productFilter) base = base.filter((s: any) => primaryProduct(s) === productFilter);
    if (!notesFilter) return base;
    const mapped = base.map(_notesFiltered);
    const sorted = [...mapped].sort((a: any, b: any) => b.total_icav - a.total_icav);
    return sorted.map((se: any, i: number) => ({ ...se, rank: i + 1 }));
  })() : []);
  const seLevelTip = $derived(filteredRanked.length ? (() => {
    const counts: Record<number, number> = {};
    for (const s of filteredRanked as any[]) {
      const lvl = titleLevel((s as any).title || '');
      counts[lvl] = (counts[lvl] ?? 0) + 1;
    }
    const n = filteredRanked.length;
    const parts = Object.entries(counts)
      .sort(([a], [b]) => +b - +a)
      .map(([lvl, c]) => `${+lvl > 0 ? `L${lvl}` : 'SE'}: ${c}`);
    return `${n} SE${n !== 1 ? 's' : ''} · ${parts.join(' · ')}`;
  })() : '');
  const actKey    = (s: any) => s.act_icav + (view === 'all' ? (s.non_tw_act_icav ?? 0) : 0);
  const actSorted = $derived(filteredRanked.filter((s: any) => actKey(s) > 0).sort((a: any, b: any) => actKey(b) - actKey(a)));
  const expSorted = $derived([...filteredRanked].filter((s: any) => s.exp_wins > 0).sort((a: any, b: any) => b.exp_icav - a.exp_icav));
  const dealSorted = $derived(data ? (() => {
    let base = data.deal_sorted ?? [];
    if (titleFilter)   base = base.filter((s: any) => titleMatchesFilter(s.title || '', titleFilter));
    if (productFilter) base = base.filter((s: any) => primaryProduct(s) === productFilter);
    return base;
  })() : []);
  const maxActIcav = $derived(actSorted.length ? Math.max(...actSorted.map((s: any) => s.act_icav)) : 1);
  const maxExpIcav = $derived(expSorted.length ? Math.max(...expSorted.map((s: any) => s.exp_icav)) : 1);
  const teamActIcav   = $derived(filteredRanked.reduce((s: number, se: any) => s + se.act_icav + (view === 'all' ? (se.non_tw_act_icav ?? 0) : 0), 0));
  const teamExpIcav   = $derived(filteredRanked.reduce((s: number, se: any) => s + se.exp_icav + (view === 'all' ? (se.non_tw_exp_icav ?? 0) : 0), 0));
  const teamTotalIcav = $derived(filteredRanked.reduce((s: number, se: any) => s + se.total_icav + (view === 'all' ? (se.non_tw_total_icav ?? 0) : 0), 0));

  // Column visibility flags — hide columns that have no data for any SE
  const hasActCol     = $derived(teamActIcav > 0 && teamExpIcav > 0);
  const hasExpCol     = $derived(teamExpIcav > 0 && teamActIcav > 0);
  const hasArrCol     = $derived(filteredRanked.some((s: any) => (s.exp_arr_total ?? 0) > 0));
  // When notes filter is on every remaining opp already has both fields filled → column is trivially 100%, hide it
  const hasNotesCol   = $derived(!notesFilter && filteredRanked.some((s: any) => (s.note_hv_total ?? 0) > 0));
  const hasWinRateCol = $derived(filteredRanked.some((s: any) => s.win_rate > 0));
  const hasEmailCol   = $derived(showActivity && filteredRanked.some((s: any) => emailTotal(s) > 0));
  const hasMeetingCol = $derived(showActivity && filteredRanked.some((s: any) => meetingTotal(s) > 0));
  const actSes      = $derived(actSorted.filter((s: any) => actKey(s) > 0));
  const expSes      = $derived(expSorted.filter((s: any) => s.exp_wins > 0));
  const actTotals   = $derived({
    wins:      actSes.reduce((n: number, s: any) => n + s.act_wins + (view === 'all' ? (s.non_tw_act_wins ?? 0) : 0), 0),
    icav:      actSes.reduce((n: number, s: any) => n + s.act_icav + (view === 'all' ? (s.non_tw_act_icav ?? 0) : 0), 0),
    avg:       actSes.length ? Math.round(actSes.reduce((n: number, s: any) => n + s.act_avg, 0) / actSes.length) : 0,
    inq:       actSes.reduce((n: number, s: any) => n + (s.email_act_inq ?? 0), 0),
    outq:      actSes.reduce((n: number, s: any) => n + (s.email_act_outq ?? 0), 0),
    outq_icav: actSes.reduce((n: number, s: any) => n + (s.email_act_outq_icav ?? 0), 0),
    meet_inq:       actSes.reduce((n: number, s: any) => n + (s.meeting_act_inq ?? 0), 0),
    meet_outq:      actSes.reduce((n: number, s: any) => n + (s.meeting_act_outq ?? 0), 0),
    meet_outq_icav: actSes.reduce((n: number, s: any) => n + (s.meeting_act_outq_icav ?? 0), 0),
  });
  const actTeamStats = $derived((() => {
    const wins = actSes.reduce((n: number, s: any) => n + s.act_wins, 0);
    const icav = actSes.reduce((n: number, s: any) => n + s.act_icav, 0);
    const actMots = new Set(['act', 'nb']);
    const deals = actSes
      .flatMap((s: any) => {
        const base: any[] = s.tw_opps_detail ?? [];
        const opps = notesFilter
          ? base.filter((o: any) => o.has_notes && o.has_history && actMots.has(o.motion))
          : base.filter((o: any) => actMots.has(o.motion));
        return opps.map((o: any) => o.icav ?? 0);
      })
      .filter((v: number) => v > 0)
      .sort((a: number, b: number) => a - b);
    const m = Math.floor(deals.length / 2);
    const deal_median = deals.length === 0 ? 0 : deals.length % 2 ? deals[m] : Math.round((deals[m-1] + deals[m]) / 2);
    const closed_won  = actSes.reduce((n: number, s: any) => n + (s.closed_won  ?? 0), 0);
    const closed_lost = actSes.reduce((n: number, s: any) => n + (s.closed_lost ?? 0), 0);
    return {
      avg: wins > 0 ? Math.round(icav / wins) : 0,
      deal_median,
      win_rate: (closed_won + closed_lost) > 0 ? Math.round(closed_won / (closed_won + closed_lost) * 100) : 0,
      closed_won,
      closed_lost,
    };
  })());
  const actMedians = $derived(actSes.length ? (() => {
    const m = (vals: number[]) => {
      const v = [...vals].sort((a: number, b: number) => a - b);
      if (!v.length) return 0;
      const mid = Math.floor(v.length / 2);
      return v.length % 2 ? v[mid] : Math.round((v[mid - 1] + v[mid]) / 2);
    };
    return {
      wins:       m(actSes.map((s: any) => s.act_wins + (view === 'all' ? (s.non_tw_act_wins ?? 0) : 0))),
      icav:       m(actSes.map((s: any) => s.act_icav + (view === 'all' ? (s.non_tw_act_icav ?? 0) : 0))),
      win_rate:   m(actSes.filter((s: any) => s.win_rate > 0).map((s: any) => s.win_rate)),
      email_inq:  m(actSes.map((s: any) => s.email_act_inq ?? 0)),
      email_outq: m(actSes.map((s: any) => s.email_act_outq ?? 0)),
      meet_inq:   m(actSes.map((s: any) => s.meeting_act_inq ?? 0)),
      meet_outq:  m(actSes.map((s: any) => s.meeting_act_outq ?? 0)),
    };
  })() : null);
  const expTotals   = $derived({
    wins:           expSes.reduce((n: number, s: any) => n + s.exp_wins, 0),
    icav:           expSes.reduce((n: number, s: any) => n + s.exp_icav, 0),
    avg:            expSes.length ? Math.round(expSes.reduce((n: number, s: any) => n + s.exp_avg, 0) / expSes.length) : 0,
    inq:            filteredRanked.reduce((n: number, s: any) => n + (s.email_exp_inq ?? 0), 0),
    outq:           filteredRanked.reduce((n: number, s: any) => n + (s.email_exp_outq ?? 0), 0),
    outq_icav:      filteredRanked.reduce((n: number, s: any) => n + (s.email_exp_outq_icav ?? 0), 0),
    arr_total:      filteredRanked.reduce((n: number, s: any) => n + (s.exp_arr_total ?? 0), 0),
    mrr_delta_total:filteredRanked.reduce((n: number, s: any) => n + (s.exp_mrr_delta_total ?? 0), 0),
    meet_inq:       filteredRanked.reduce((n: number, s: any) => n + (s.meeting_exp_inq ?? 0), 0),
    meet_outq:      filteredRanked.reduce((n: number, s: any) => n + (s.meeting_exp_outq ?? 0), 0),
    meet_outq_icav: filteredRanked.reduce((n: number, s: any) => n + (s.meeting_exp_outq_icav ?? 0), 0),
  });

  function fmtMrrDelta(delta: number): string {
    if (delta === 0) return '→ flat';
    const sign = delta > 0 ? '↑' : '↓';
    return `${sign} ${fmtMrr(Math.abs(delta))}/mo`;
  }

  const stratOnly     = $derived(teamExpIcav > 0 && teamActIcav === 0);
  const actOnly       = $derived(teamActIcav > 0 && teamExpIcav === 0);
  const singleMotion  = $derived(stratOnly || actOnly);
  const summaryCards  = $derived(data ? [
    {label:'SE-Influenced iACV',     val:fmt(teamTotalIcav),                   color:null,                                                                                                                                                 show:true},
    {label:'SE Impact %',            val:(data.se_icav_pct != null ? data.se_icav_pct+'%' : null), color:null,                                                                                                                           show:data.se_icav_pct != null},
    {label:motionLabels.act+' iACV', val:fmt(teamActIcav),                     color:null,                                                                                                                                                 show:teamActIcav>0 && teamExpIcav>0},
    {label:motionLabels.exp+' iACV', val:fmt(teamExpIcav),                     color:null,                                                                                                                                                 show:teamExpIcav>0 && teamActIcav>0},
    {label:'Account ARR',            val:fmt(expTotals.arr_total),             color:null,                                                                                                                                                 show:stratOnly && expTotals.arr_total>0},
    {label:'Qtr MRR Δ',              val:fmtMrrDelta(expTotals.mrr_delta_total), color:expTotals.mrr_delta_total>0?($theme==='twilio'?'#178742':'#10B981'):expTotals.mrr_delta_total<0?($theme==='twilio'?'#DC2626':'#EF4444'):'var(--text-muted)', show:stratOnly && expTotals.arr_total>0},
    {label:'SEs Analysed',           val:String(data.total),                   color:null,                                                                                                                                                 show:true},
  ].filter((s: any) => s.show && s.val != null) : []);

const actStatCols = $derived(data ? [
    {l:'Total Wins',  v:String(actTotals.wins)},
    {l:'Total iACV',  v:fmt(actTotals.icav)},
    {l:'Avg Deal',    v:fmt(actTotals.avg)},
    {l:'In-Q Emails', v:actTotals.inq > 0 ? String(actTotals.inq) : '—'},
    {l:'Pipe Emails', v:actTotals.outq > 0 ? actTotals.outq + (actTotals.outq_icav > 0 ? ' · '+fmt(actTotals.outq_icav) : '') : '—'},
    ...(actTotals.meet_inq > 0 || actTotals.meet_outq > 0 ? [{l:'In-Q Meets', v:actTotals.meet_inq > 0 ? String(actTotals.meet_inq) : '—'}] : []),
    ...(actTotals.meet_outq > 0 ? [{l:'Pipe Meets', v:String(actTotals.meet_outq)}] : []),
  ] : []);

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

  function meetingTotal(se: any): number {
    return (se.meeting_act_inq ?? 0) + (se.meeting_act_outq ?? 0)
         + (se.meeting_exp_inq ?? 0) + (se.meeting_exp_outq ?? 0);
  }

  const medians = $derived(data ? {
    act_icav:   med(filteredRanked.map((s: any) => s.act_icav + (view === 'all' ? (s.non_tw_act_icav ?? 0) : 0))),
    act_wins:   med(filteredRanked.map((s: any) => s.act_wins + (view === 'all' ? (s.non_tw_act_wins ?? 0) : 0))),
    exp_icav:   med(filteredRanked.map((s: any) => s.exp_icav + (view === 'all' ? (s.non_tw_exp_icav ?? 0) : 0))),
    exp_wins:   med(filteredRanked.map((s: any) => s.exp_wins + (view === 'all' ? (s.non_tw_exp_wins ?? 0) : 0))),
    total_icav: med(filteredRanked.map((s: any) => s.total_icav + (view === 'all' ? (s.non_tw_total_icav ?? 0) : 0))),
    win_rate:   med(data.ranked.map((s: any) => s.win_rate)),
    emails:              med(data.ranked.map((s: any) => emailTotal(s))),
    meetings:            med(data.ranked.map((s: any) => meetingTotal(s))),
    note_hv_avg_entries: med(data.ranked.map((s: any) => s.note_hv_avg_entries ?? 0)),
    mrr_delta: (() => {
      const vals = filteredRanked
        .filter((s: any) => (s.exp_arr_total ?? 0) > 0)
        .map((s: any) => s.exp_mrr_delta_total ?? 0)
        .sort((a: number, b: number) => a - b);
      if (!vals.length) return null;
      const m = Math.floor(vals.length / 2);
      return vals.length % 2 ? vals[m] : Math.round((vals[m - 1] + vals[m]) / 2);
    })(),
  } : null);

  function computeExpStatus(se: any): string {
    const iCAV     = se.exp_icav ?? 0;
    const arr      = se.exp_arr_total ?? 0;
    const mrrDelta = se.exp_mrr_delta_total ?? 0;
    const wins     = se.exp_wins ?? 0;
    // MRR actively growing — accounts using more regardless of new iACV
    if (mrrDelta > 0) return iCAV > 0 ? 'Growing' : 'Growing';
    // New iACV committed; MRR flat (deal in, usage not yet ramped)
    if (iCAV > 0 && mrrDelta === 0) return 'Expanding';
    // New deals signed but accounts are losing MRR simultaneously
    if (iCAV > 0 && mrrDelta < 0) return 'Mixed';
    // No new wins; accounts actively shrinking in usage
    if (mrrDelta < 0) return 'Contracting';
    // Large ARR footprint but no growth signal at all
    if (arr > 0 && wins > 0) return 'Retaining';
    // Zero expansion contribution
    return 'Retaining';
  }

  function expStatusColor(status: string): string {
    if (status === 'Growing')     return $theme === 'twilio' ? '#178742' : '#10B981';
    if (status === 'Expanding')   return $theme === 'twilio' ? '#006EFF' : '#3B82F6';
    if (status === 'Mixed')       return $theme === 'twilio' ? '#B45309' : '#FFB800';
    if (status === 'Contracting') return $theme === 'twilio' ? '#DC2626' : '#EF4444';
    return 'var(--text-muted)';
  }

  let activeSection = $state('rankings');
  let navHovered = $state(false);

  const navSections = $derived(data ? [
    { id: 'rankings',  label: 'Standings' },
    { id: 'activate',  label: motionLabels.act,  show: actSes.length > 0 && !singleMotion },
    { id: 'expansion', label: motionLabels.exp,  show: expSes.length > 0 && !singleMotion },
    { id: 'deals',     label: 'Largest Deals',   show: dealSorted.length > 0 },
    { id: 'notes',     label: 'Notes Quality',   show: !notesFilter },
    { id: 'trends',    label: 'Trends & Flags' },
    { id: 'recs',      label: 'Recommendations', show: !!(data.recommendations?.length) },
    { id: 'profiles',  label: 'SE Profiles' },
  ].filter((s: any) => s.show !== false) : []);

  $effect(() => {
    if (!data || typeof window === 'undefined') return;
    const ids = navSections.map((s: any) => s.id);
    function onScroll() {
      for (let i = ids.length - 1; i >= 0; i--) {
        const el = document.getElementById(ids[i]);
        if (el && el.getBoundingClientRect().top <= 100) {
          activeSection = ids[i];
          return;
        }
      }
      if (ids.length) activeSection = ids[0];
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  });

  const ICAV_PRESETS = [
    { label: 'All', value: 0 },
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

  let icavLoading = $state(false);
  async function loadWithMin(min: number) {
    if (min === icavMin) return;
    icavMin = min;
    icavLoading = true;
    data = await getSFReport($sfTeam, $sfPeriod, min, $sfSubteam);
    icavLoading = false;
  }

  onMount(async () => { data = await getSFReport($sfTeam, $sfPeriod, icavMin, $sfSubteam); });
</script>

{#if $user?.sf_access === 'se_restricted'}
<div class="min-h-screen flex items-center justify-center">
  <div style="max-width:420px;width:100%;padding:32px 24px;text-align:center">
    <div style="font-size:36px;margin-bottom:16px">🔒</div>
    <div style="font-size:18px;font-weight:800;color:var(--text);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px">Access Denied</div>
    <div style="font-size:13px;color:var(--text-muted);font-weight:500;margin-bottom:24px">The Full Report is only available to SE managers and leaders.</div>
    <a href="/se-scorecard-v2/me" style="display:inline-block;padding:10px 24px;background:var(--red);color:white;font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;text-decoration:none;border-radius:4px">View My Stats instead</a>
  </div>
</div>
{:else if !data}
<div class="min-h-screen flex items-center justify-center">
  <div style="font-size:18px;font-weight:700;color:var(--text-muted)">Loading intel…</div>
</div>
{:else}

<div style="position:fixed;top:68px;left:16px;z-index:9999">
  <a href="/se-scorecard-v2" class="p5-back-btn">◀ Back</a>
</div>

<!-- Section nav -->
{#if navSections.length > 1}
<nav
  onmouseenter={() => navHovered = true}
  onmouseleave={() => navHovered = false}
  style="position:fixed;right:20px;top:50%;transform:translateY(-50%);z-index:200;display:flex;flex-direction:column;align-items:flex-end;gap:2px"
>
  <!-- connecting line -->
  <div style="position:absolute;right:4px;top:12px;bottom:12px;width:1px;background:rgba(var(--red-rgb),0.15);pointer-events:none"></div>
  {#each navSections as sec}
  {@const isActive = activeSection === sec.id}
  <div
    onclick={() => { const el = document.getElementById(sec.id); if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 72, behavior: 'smooth' }); }}
    style="display:flex;align-items:center;gap:8px;cursor:pointer;padding:4px 0;position:relative"
  >
    <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:{isActive?'var(--red)':'var(--text-muted)'};max-width:{navHovered||isActive?'140px':'0'};overflow:hidden;white-space:nowrap;transition:max-width 0.2s ease,opacity 0.15s;opacity:{navHovered||isActive?1:0}">{sec.label}</span>
    <div style="width:{isActive?9:5}px;height:{isActive?9:5}px;border-radius:50%;background:{isActive?'var(--red)':'rgba(var(--red-rgb),0.3)'};border:1px solid {isActive?'var(--red)':'rgba(var(--red-rgb),0.4)'};transition:all 0.15s;flex-shrink:0"></div>
  </div>
  {/each}
</nav>
{/if}

<div style="max-width:1200px;margin:0 auto;padding:60px 24px 40px">

  <div style="margin-bottom:28px">
    <h1 style="font-size:36px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:3px 3px 0 var(--red)':''}">Full Report</h1>
    <p style="font-size:16px;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;color:var(--red);margin-top:4px">{data.team_label} · {data.quarter}</p>
    <p style="font-size:13px;color:var(--text-muted);font-weight:600;margin-top:4px">{data.total} SEs · Live data from Salesforce</p>
  </div>

  <div style="display:grid;grid-template-columns:repeat({summaryCards.length},1fr);gap:8px;margin-bottom:24px">
    {#each summaryCards as s}
    <div class="p5-stat-chip">
      <div style="font-size:9px;color:var(--red);font-weight:800;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};margin-bottom:6px">{s.label}</div>
      <div style="font-size:28px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:{s.color ?? 'var(--text)'};{$theme==='p5'?'text-shadow:2px 2px 0 rgba(var(--red-rgb),0.4)':''};line-height:1">{s.val}</div>
    </div>
    {/each}
  </div>

  <!-- Controls row — sticky -->
  <div style="position:sticky;top:68px;z-index:90;margin:0 -24px;padding:10px 24px;background:var(--bg);border-bottom:1px solid rgba(var(--red-rgb),0.1);backdrop-filter:blur(8px);margin-bottom:0">
  <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start">

    <!-- View toggle -->
    <div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-muted);margin-bottom:6px">Show</div>
      <div style="display:flex;gap:6px">
        {#each [{key:'tw',label:'Technical Wins'},{key:'all',label:'All Closed Won'}] as opt}
        <button onclick={() => view = opt.key as 'tw' | 'all'} class="p5-ctrl {view === opt.key ? 'active' : ''}">{opt.label}</button>
        {/each}
      </div>
    </div>

    <!-- iACV cutoff -->
    <div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-muted);margin-bottom:6px">iACV</div>
      <select
        value={icavMin}
        onchange={(e) => loadWithMin(+((e.currentTarget as HTMLSelectElement).value))}
        style="padding:5px 10px;font-size:12px;font-weight:600;border-radius:5px;border:1px solid {icavMin>0?'var(--red)':'rgba(var(--red-rgb),0.2)'};background:var(--bg);color:{icavMin>0?'var(--red)':'var(--text-muted)'};cursor:pointer;outline:none;opacity:{icavLoading?0.5:1};transition:opacity 0.15s"
      >
        {#each ICAV_PRESETS as p}
        <option value={p.value}>{icavLoading && icavMin === p.value ? '…' : p.label}</option>
        {/each}
      </select>
    </div>

    <!-- Activity columns toggle -->
    <div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-muted);margin-bottom:6px">Activity</div>
      <button onclick={() => showActivity = !showActivity} class="p5-ctrl {showActivity ? 'active' : ''}">{showActivity ? '✓ Emails & Meetings' : 'Emails & Meetings'}</button>
    </div>

    <!-- Notes filter -->
    <div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-muted);margin-bottom:6px">Notes Filter</div>
      <button onclick={() => notesFilter = !notesFilter} class="p5-ctrl {notesFilter ? 'active' : ''}">{notesFilter ? '✓ Documented Only' : 'Documented Only'}</button>
    </div>

    <!-- Title filter -->
    {#if titleGroups.length > 0}
    <div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-muted);margin-bottom:6px">Job Title</div>
      <select
        value={titleFilter}
        onchange={(e) => { titleFilter = (e.currentTarget as HTMLSelectElement).value; productFilter = ''; }}
        style="padding:5px 10px;font-size:12px;font-weight:600;border-radius:5px;border:1px solid {titleFilter?'var(--red)':'rgba(var(--red-rgb),0.2)'};background:var(--bg);color:{titleFilter?'var(--red)':'var(--text-muted)'};cursor:pointer;outline:none"
      >
        <option value="">All Titles</option>
        {#each titleGroups as grp}
        <optgroup label="───────────────">
          <option value="level:{grp.level}">{grp.label} — All</option>
          {#each grp.titles as t}
          <option value={t}>↳ {t}</option>
          {/each}
        </optgroup>
        {/each}
      </select>
    </div>
    {/if}

    <!-- Product filter -->
    {#if productList.length > 1}
    <div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-muted);margin-bottom:6px">Primary Product</div>
      <select
        value={productFilter}
        onchange={(e) => productFilter = (e.currentTarget as HTMLSelectElement).value}
        style="padding:5px 10px;font-size:12px;font-weight:600;border-radius:5px;border:1px solid {productFilter?'var(--red)':'rgba(var(--red-rgb),0.2)'};background:var(--bg);color:{productFilter?'var(--red)':'var(--text-muted)'};cursor:pointer;outline:none"
      >
        <option value="">All Products</option>
        {#each productList as p}
        <option value={p}>{p}</option>
        {/each}
      </select>
    </div>
    {/if}

  </div>
  </div>

  <div style="margin-bottom:20px"></div>

  <!-- Overall Rankings (multi-motion only) -->
  {#if !singleMotion}
  <div id="rankings" class="p5-panel" style="margin-bottom:20px">
    <div class="p5-panel-header">
      <h2 class="p5-panel-header-title">Standings</h2>
      <button onclick={() => rankCriteriaExpanded = !rankCriteriaExpanded} class="p5-ctrl {rankCriteriaExpanded ? 'active' : ''}">Criteria {rankCriteriaExpanded ? '▲' : '▼'}</button>
    </div>
    <div>
      {#if rankCriteriaExpanded}
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:10px">
        {#each [
          {w:'85%', label:'Total iACV',       desc:'Primary revenue output — dominant signal'},
          {w:'8%',  label:'Quarter MRR %',   desc:'Avg % MRR growth across expansion accounts — are accounts genuinely growing?'},
          {w:'5%',  label:'Total ARR Touched',desc:'Sum of current ARR across expansion accounts — breadth of account footprint'},
          {w:'2%',  label:'Notes Hygiene',   desc:notesFloorLabel+' opps with both SE notes fields filled ÷ total'},
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
      <p style="font-size:10px;color:var(--text-faint);margin-top:8px">Each metric is percentile-ranked 0–100 within the team, then combined with these weights into a composite score. Percentile ranking makes the weights fair across metrics with different scales ($M iACV vs % MRR).</p>
      {/if}
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)">
          <tr>
            {#each colDefs as {h, tip}, idx}
            <th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap;position:relative"
              onmouseenter={() => tip ? colTipIdx = idx : null}
              onmouseleave={() => colTipIdx = -1}
            >
              <span style="{tip ? 'border-bottom:1px dashed rgba(var(--red-rgb),0.4);cursor:help;padding-bottom:1px' : ''}">{h}</span>
              {#if colTipIdx === idx && tip}
              <div style="position:absolute;top:calc(100% + 4px);{idx > 5 ? 'right:0' : 'left:0'};z-index:400;width:280px;background:{$theme==='twilio'?'#fff':'#0f1117'};border:1px solid rgba(var(--red-rgb),0.2);border-radius:6px;padding:10px 12px;box-shadow:0 6px 24px rgba(0,0,0,0.2);font-size:11px;font-weight:400;text-transform:none;letter-spacing:0;color:var(--text-muted);line-height:1.5;white-space:normal;pointer-events:none">
                {tip}
              </div>
              {/if}
            </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each filteredRanked as se}
          {@const et = emailTotal(se)}
          {@const vActIcav = se.act_icav + (view==='all' ? (se.non_tw_act_icav ?? 0) : 0)}
          {@const vActWins = se.act_wins + (view==='all' ? (se.non_tw_act_wins ?? 0) : 0)}
          {@const vExpIcav = se.exp_icav + (view==='all' ? (se.non_tw_exp_icav ?? 0) : 0)}
          {@const vExpWins = se.exp_wins + (view==='all' ? (se.non_tw_exp_wins ?? 0) : 0)}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{se.rank}</td>
            <td style="padding:10px 16px"><a href="/se-scorecard-v2/me?se={encodeURIComponent(se.name)}" title={se.title || undefined} style="font-weight:700;color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{se.name}</a></td>

            {#if hasActCol}
            <td style="padding:10px 16px">
              <div style="font-weight:700;color:var(--act-color)">{fmt(vActIcav)}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:1px">{vActWins} {vActWins === 1 ? 'win' : 'wins'}</div>
            </td>
            {/if}

            {#if hasExpCol}
            <td style="padding:10px 16px">
              <div style="font-weight:700;color:var(--exp-color)">{fmt(vExpIcav)}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:1px">{vExpWins} {vExpWins === 1 ? 'win' : 'wins'}</div>
            </td>
            {/if}

            <!-- Total iACV -->
            <td style="padding:10px 16px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text)">
              {fmt(seIcav(se))}
            </td>

            {#if hasArrCol}
            {@const seDelta = se.exp_mrr_delta_total ?? 0}
            {@const mrrPct = se.exp_mrr_pct_avg ?? 0}
            <td style="padding:10px 16px">
              {#if (se.exp_arr_total ?? 0) > 0}
                <div style="font-weight:700;color:{seDelta > 0 ? ($theme==='twilio'?'#178742':'#10B981') : seDelta < 0 ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'}">
                  {fmtMrrDelta(seDelta)}{#if mrrPct !== 0} <span style="font-size:11px;font-weight:600">({mrrPct > 0 ? '+' : ''}{mrrPct}%)</span>{/if}
                </div>
              {:else}
                <span style="color:var(--text-faint)">—</span>
              {/if}
            </td>
            {/if}

            {#if hasNotesCol}
            <td style="padding:10px 16px;font-size:12px;line-height:1.6">
              {#if (se.note_hv_total ?? 0) > 0}
                <div style="font-weight:700;color:{se.note_hv_covered === se.note_hv_total ? 'var(--exp-color)' : se.note_hv_covered > 0 ? 'var(--text)' : 'var(--red)'}">{se.note_hv_covered}/{se.note_hv_total}</div>
                <div style="font-size:11px;color:var(--text-muted)">{se.note_hv_avg_entries} avg entries</div>
              {:else}
                <span style="color:var(--text-faint)">—</span>
              {/if}
            </td>
            {/if}

            {#if hasEmailCol}
            <td style="padding:10px 16px;font-weight:700;color:{et > 0 ? 'var(--text)' : 'var(--text-faint)'}">
              {et > 0 ? et : '—'}
            </td>
            {/if}

            {#if hasMeetingCol}
            {@const mt = meetingTotal(se)}
            <td style="padding:10px 16px;font-weight:700;color:{mt > 0 ? 'var(--text)' : 'var(--text-faint)'}">
              {mt > 0 ? mt : '—'}
            </td>
            {/if}

          </tr>
          {/each}
          {#if medians}
          <tr style="border-top:2px solid rgba(var(--red-rgb),0.15);background:rgba(var(--red-rgb),0.03)">
            <td style="padding:10px 16px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-muted)">MED</td>
            <td style="padding:10px 16px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-muted)">Team Median</td>
            {#if hasActCol}<td style="padding:10px 16px"><div style="font-weight:700;color:var(--act-color);opacity:0.7">{fmt(medians.act_icav)}</div><div style="font-size:11px;color:var(--text-muted)">{medians.act_wins} wins</div></td>{/if}
            {#if hasExpCol}<td style="padding:10px 16px"><div style="font-weight:700;color:var(--exp-color);opacity:0.7">{fmt(medians.exp_icav)}</div><div style="font-size:11px;color:var(--text-muted)">{medians.exp_wins} wins</div></td>{/if}
            <td style="padding:10px 16px;font-weight:900;color:var(--text-muted)">{fmt(medians.total_icav)}</td>
            {#if hasArrCol}<td style="padding:10px 16px">
              {#if medians.mrr_delta !== null}
                <div style="font-weight:700;color:{medians.mrr_delta > 0 ? ($theme==='twilio'?'#178742':'#10B981') : medians.mrr_delta < 0 ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'};opacity:0.7">{fmtMrrDelta(medians.mrr_delta)}</div>
              {:else}
                <span style="color:var(--text-faint)">—</span>
              {/if}
            </td>{/if}
            {#if hasNotesCol}<td style="padding:10px 16px;font-size:12px;color:var(--text-muted)">{medians.note_hv_avg_entries > 0 ? medians.note_hv_avg_entries+' avg entries' : '—'}</td>{/if}
            {#if hasEmailCol}<td style="padding:10px 16px;font-weight:700;color:var(--text-muted)">{medians.emails > 0 ? medians.emails : '—'}</td>{/if}
            {#if hasMeetingCol}<td style="padding:10px 16px;font-weight:700;color:var(--text-muted)">{medians.meetings > 0 ? medians.meetings : '—'}</td>{/if}
          </tr>
          {/if}
        </tbody>
      </table>
    </div>
  </div>

  {/if}

  <!-- Activate + Expansion (multi-motion only) -->
  {#if !singleMotion}
  <div style="display:flex;flex-direction:column;gap:16px;margin-bottom:20px">
    {#if actSes.length > 0}
    <div id="activate" class="p5-panel">
      <div class="p5-panel-header">
        <h2 class="p5-panel-header-title">{motionLabels.act}</h2>
      </div>
      <div style="padding:6px 16px 8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid rgba(var(--red-rgb),0.08)">{motionLabels.actDesc}</div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="background:rgba(var(--red-rgb),0.06)"><tr>
            {#each [
              {h:'#',show:true, tip:'Ranked by Activate iACV within this period, highest to lowest.'},
              {h:'SE',show:true, tip:seLevelTip},
              {h:'Wins',show:true, tip:`Count of Technical Win Closed Won ${motionLabels.act} opps. ${motionLabels.actDesc}. Only TW opps count toward ranking.`},
              {h:'iACV',show:true, tip:`Sum of iACV from Technical Win Closed Won ${motionLabels.act} opps. Incremental Annual Contract Value — the net new ARR committed on close.`},
              {h:'Median',show:true, tip:`Median deal size (iACV) across this SE's ${motionLabels.act.toLowerCase()} wins. More robust than average — less skewed by a single large deal.`},
              {h:'Win Rate',show:hasWinRateCol, tip:`Closed Won ÷ (Closed Won + Closed Lost) for ${motionLabels.act} opps. Only counts opps that reached a final stage this period.`},
              {h:'In-Q Emails',show:showActivity && actTotals.inq>0, tip:`Salesforce Task emails sent to ${motionLabels.act} opps that closed this quarter. Measures engagement on deals that converted this period.`},
              {h:'Pipe Emails',show:showActivity && actTotals.outq>0, tip:`Emails to ${motionLabels.act} opps closing a future quarter. Indicates early-stage pipeline development.`},
              {h:'In-Q Meets',show:showActivity && actTotals.meet_inq>0, tip:`Meetings on ${motionLabels.act} opps closing this quarter. Recurring series deduplicated — same series on the same opp counts once.`},
              {h:'Pipe Meets',show:showActivity && actTotals.meet_outq>0, tip:`Meetings on pipeline ${motionLabels.act} opps (future quarter). Shows investment in building future pipeline.`},
            ].filter(c=>c.show) as {h, tip}, idx}
            <th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap;position:relative"
              onmouseenter={() => tip ? actColTipIdx = idx : null}
              onmouseleave={() => actColTipIdx = -1}
            >
              <span style="{tip ? 'border-bottom:1px dashed rgba(var(--red-rgb),0.4);cursor:help;padding-bottom:1px' : ''}">{h}</span>
              {#if actColTipIdx === idx && tip}
              <div style="position:absolute;top:calc(100% + 4px);{idx > 5 ? 'right:0' : 'left:0'};z-index:400;width:280px;background:{$theme==='twilio'?'#fff':'#0f1117'};border:1px solid rgba(var(--red-rgb),0.2);border-radius:6px;padding:10px 12px;box-shadow:0 6px 24px rgba(0,0,0,0.2);font-size:11px;font-weight:400;text-transform:none;letter-spacing:0;color:var(--text-muted);line-height:1.5;white-space:normal;pointer-events:none">
                {tip}
              </div>
              {/if}
            </th>
            {/each}
          </tr></thead>
          <tbody>
            {#each actSorted as se, i}
            {@const vActWins = se.act_wins + (view === 'all' ? (se.non_tw_act_wins ?? 0) : 0)}
            {@const vActIcav = se.act_icav + (view === 'all' ? (se.non_tw_act_icav ?? 0) : 0)}
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
              <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{i + 1}</td>
              <td style="padding:10px 16px"><a href="/se-scorecard-v2/me?se={encodeURIComponent(se.name)}" title={se.title || undefined} style="font-weight:700;color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{se.name}</a></td>
              <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{vActWins}</td>
              <td style="padding:10px 16px;color:var(--act-color);font-weight:700">{fmt(vActIcav)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.act_median)}</td>
              {#if hasWinRateCol}
              <td style="padding:10px 16px">
                <div style="font-weight:700;color:{se.win_rate >= 50 ? 'var(--exp-color)' : se.win_rate > 0 ? 'var(--text-muted)' : 'var(--text-faint)'}">{se.win_rate > 0 ? se.win_rate+'%' : '—'}</div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:1px">{se.closed_won}W / {se.closed_lost}L</div>
              </td>
              {/if}
              {#if showActivity && actTotals.inq > 0}<td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.email_act_inq ?? 0) > 0 ? se.email_act_inq : '—'}</td>{/if}
              {#if showActivity && actTotals.outq > 0}<td style="padding:10px 16px;color:var(--act-color);font-weight:700">{#if (se.email_act_outq ?? 0) > 0}{se.email_act_outq}{#if (se.email_act_outq_icav ?? 0) > 0} <span style="font-size:11px;color:var(--text-muted);font-weight:400">{fmt(se.email_act_outq_icav)}</span>{/if}{:else}—{/if}</td>{/if}
              {#if showActivity && actTotals.meet_inq > 0}<td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.meeting_act_inq ?? 0) > 0 ? se.meeting_act_inq : '—'}</td>{/if}
              {#if showActivity && actTotals.meet_outq > 0}<td style="padding:10px 16px;color:var(--act-color);font-weight:700">{#if (se.meeting_act_outq ?? 0) > 0}{se.meeting_act_outq}{#if (se.meeting_act_outq_icav ?? 0) > 0} <span style="font-size:11px;color:var(--text-muted);font-weight:400">{fmt(se.meeting_act_outq_icav)}</span>{/if}{:else}—{/if}</td>{/if}
            </tr>
            {/each}
            {#if actMedians}
            <tr style="border-top:2px solid rgba(var(--act-rgb),0.2);background:rgba(var(--act-rgb),0.04)">
              <td style="padding:10px 16px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--act-color)">MED</td>
              <td style="padding:10px 16px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--act-color)">Team Median</td>
              <td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.wins} {actMedians.wins === 1 ? 'win' : 'wins'}</td>
              <td style="padding:10px 16px;font-weight:900;color:var(--act-color);opacity:0.8">{fmt(actMedians.icav)}</td>
              <td style="padding:10px 16px;color:var(--act-color);font-size:11px;opacity:0.8">
                {#if actTeamStats.deal_median > 0}
                <div style="font-weight:700">{fmt(actTeamStats.deal_median)}</div>
                {:else}<span style="color:var(--text-faint)">—</span>{/if}
              </td>
              {#if hasWinRateCol}
              <td style="padding:10px 16px">
                {#if actMedians.win_rate > 0}
                <div style="font-weight:700;color:{actMedians.win_rate >= 50 ? 'var(--exp-color)' : 'var(--text-muted)'};opacity:0.8">{actMedians.win_rate}%</div>
                {:else}<span style="color:var(--text-faint)">—</span>{/if}
              </td>
              {/if}
              {#if showActivity && actTotals.inq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.email_inq > 0 ? actMedians.email_inq : '—'}</td>{/if}
              {#if showActivity && actTotals.outq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.email_outq > 0 ? actMedians.email_outq : '—'}</td>{/if}
              {#if showActivity && actTotals.meet_inq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.meet_inq > 0 ? actMedians.meet_inq : '—'}</td>{/if}
              {#if showActivity && actTotals.meet_outq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.meet_outq > 0 ? actMedians.meet_outq : '—'}</td>{/if}
            </tr>
            {/if}
          </tbody>
        </table>
      </div>
    </div>
    {/if}
    {#if expSes.length > 0}
    <div id="expansion" class="p5-panel">
      <div class="p5-panel-header">
        <h2 class="p5-panel-header-title">{motionLabels.exp}</h2>
      </div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="background:rgba(var(--red-rgb),0.06)">
            <tr>
              {#each [
                {h:'#',          tip:'',                                                                                                                                                                                        show:true},
                {h:'SE',         tip:seLevelTip,                                                                                                                                                                            show:true},
                {h:'Wins',       tip:`Count of Technical Win Closed Won ${motionLabels.exp} opps. ${motionLabels.expDesc}. Only TW opps count toward ranking.`,                                                                 show:true},
                {h:'iACV',       tip:`Net new ARR committed on close — sum of Comms_Segment_Combined_iACV__c across this SE's TW ${motionLabels.exp.toLowerCase()} wins.`,                                                      show:true},
                {h:'Acct ARR',   tip:`Current_ARR_Based_on_Last_6_Months__c on each expansion account. Each account counted once even if the SE has multiple opps on it.`,                                                      show:expTotals.arr_total>0},
                {h:'Qtr MRR Δ',  tip:`Avg monthly usage in the opp's close quarter minus avg of the 3 prior months. Anchored to the quarter the SE was involved — shows real account trajectory. % is total-based so direction always matches the ↑/↓ sign.`, show:expTotals.arr_total>0},
                {h:'In-Q Emails',tip:`Salesforce Task emails sent to ${motionLabels.exp} opps closing this quarter.`,                                                                                                           show:showActivity && expTotals.inq>0},
                {h:'Pipe Emails',tip:`Emails to ${motionLabels.exp} opps closing a future quarter — pipeline development signal.`,                                                                                              show:showActivity && expTotals.outq>0},
                {h:'In-Q Meets', tip:`Meetings on ${motionLabels.exp} opps closing this quarter. Recurring series deduplicated.`,                                                                                               show:showActivity && expTotals.meet_inq>0},
                {h:'Pipe Meets', tip:`Meetings on pipeline ${motionLabels.exp} opps (future quarter).`,                                                                                                                        show:showActivity && expTotals.meet_outq>0},
                {h:'Status',     tip:`Growing — any net MRR increase. Expanding — new iACV with flat MRR (usage not yet ramped). Mixed — new iACV but MRR declining (losing ground on existing accounts). Contracting — MRR dropping, no new wins to offset. Retaining — no growth signal.`, show:true},
              ].filter(c=>c.show) as {h, tip}, idx}
              <th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap;position:relative"
                onmouseenter={() => tip ? expColTipIdx = idx : null}
                onmouseleave={() => expColTipIdx = -1}
              >
                <span style="{tip ? 'border-bottom:1px dashed rgba(var(--red-rgb),0.4);cursor:help;padding-bottom:1px' : ''}">{h}</span>
                {#if expColTipIdx === idx && tip}
                <div style="position:absolute;top:calc(100% + 4px);{idx > 5 ? 'right:0' : 'left:0'};z-index:400;width:280px;background:{$theme==='twilio'?'#fff':'#0f1117'};border:1px solid rgba(var(--red-rgb),0.2);border-radius:6px;padding:10px 12px;box-shadow:0 6px 24px rgba(0,0,0,0.2);font-size:11px;font-weight:400;text-transform:none;letter-spacing:0;color:var(--text-muted);line-height:1.5;white-space:normal;pointer-events:none">
                  {tip}
                </div>
                {/if}
              </th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each expSes as se, i}
            {@const expSt = computeExpStatus(se)}
            {@const expStColor = expStatusColor(expSt)}
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
              <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{i + 1}</td>
              <td style="padding:10px 16px"><a href="/se-scorecard-v2/me?se={encodeURIComponent(se.name)}" title={se.title || undefined} style="font-weight:700;color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{se.name}</a></td>
              <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.exp_wins}</td>
              <td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{fmt(se.exp_icav)}</td>
              {#if expTotals.arr_total > 0}
              {@const seArr = se.exp_arr_total ?? 0}
              {@const seDelta = se.exp_mrr_delta_total ?? 0}
              {@const mrrPct = se.exp_mrr_pct_avg ?? 0}
              {@const mrrQ = se.exp_mrr_quarter_total ?? 0}
              {@const mrrPre = se.exp_mrr_pre_total ?? 0}
              <td style="padding:10px 16px;font-weight:700;color:{seArr > 0 ? ($theme==='twilio'?'#178742':'#10B981') : 'var(--text-faint)'}">
                {seArr > 0 ? fmt(seArr) : '—'}
              </td>
              <td style="padding:10px 16px">
                {#if seArr > 0}
                  <div style="font-weight:700;color:{seDelta > 0 ? ($theme==='twilio'?'#178742':'#10B981') : seDelta < 0 ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'}">
                    {fmtMrrDelta(seDelta)}{#if mrrPct !== 0} <span style="font-size:11px;font-weight:600">({mrrPct > 0 ? '+' : ''}{mrrPct}%)</span>{/if}
                  </div>
                  {#if mrrPre > 0 || mrrQ > 0}<div style="font-size:10px;color:var(--text-muted);margin-top:1px">{fmt(mrrPre)} → {fmt(mrrQ)}/mo</div>{/if}
                {:else}
                  <span style="color:var(--text-faint)">—</span>
                {/if}
              </td>
              {/if}
              {#if showActivity && expTotals.inq > 0}<td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.email_exp_inq ?? 0) > 0 ? se.email_exp_inq : '—'}</td>{/if}
              {#if showActivity && expTotals.outq > 0}<td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{#if (se.email_exp_outq ?? 0) > 0}{se.email_exp_outq}{#if (se.email_exp_outq_icav ?? 0) > 0} <span style="font-size:11px;color:var(--text-muted);font-weight:400">{fmt(se.email_exp_outq_icav)}</span>{/if}{:else}—{/if}</td>{/if}
              {#if showActivity && expTotals.meet_inq > 0}<td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.meeting_exp_inq ?? 0) > 0 ? se.meeting_exp_inq : '—'}</td>{/if}
              {#if showActivity && expTotals.meet_outq > 0}<td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{#if (se.meeting_exp_outq ?? 0) > 0}{se.meeting_exp_outq}{#if (se.meeting_exp_outq_icav ?? 0) > 0} <span style="font-size:11px;color:var(--text-muted);font-weight:400">{fmt(se.meeting_exp_outq_icav)}</span>{/if}{:else}—{/if}</td>{/if}
              <td style="padding:10px 16px">
                <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;background:{expStColor}18;color:{expStColor};border:1px solid {expStColor}40;{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">{expSt}</span>
              </td>
            </tr>
            {/each}
            <!-- Totals row -->
            <tr style="border-top:2px solid rgba(var(--exp-rgb),0.2);background:rgba(var(--exp-rgb),0.04)">
              <td style="padding:10px 16px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--exp-color)">TOT</td>
              <td style="padding:10px 16px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--exp-color)">Team Total</td>
              <td style="padding:10px 16px;font-weight:700;color:var(--exp-color);text-align:center">{expTotals.wins}</td>
              <td style="padding:10px 16px;font-weight:900;color:var(--exp-color)">{fmt(expTotals.icav)}</td>
              {#if expTotals.arr_total > 0}
              <td style="padding:10px 16px;font-weight:700;color:{$theme==='twilio'?'#178742':'#10B981'}">{fmt(expTotals.arr_total)}</td>
              <td style="padding:10px 16px">
                <div style="font-weight:700;color:{expTotals.mrr_delta_total > 0 ? ($theme==='twilio'?'#178742':'#10B981') : expTotals.mrr_delta_total < 0 ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'}">
                  {fmtMrrDelta(expTotals.mrr_delta_total)}
                </div>
              </td>
              {/if}
              {#if showActivity && expTotals.inq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--exp-color)">{expTotals.inq}</td>{/if}
              {#if showActivity && expTotals.outq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--exp-color)">{expTotals.outq}{#if expTotals.outq_icav > 0} <span style="font-size:11px;color:var(--text-muted);font-weight:400">{fmt(expTotals.outq_icav)}</span>{/if}</td>{/if}
              {#if showActivity && expTotals.meet_inq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--exp-color)">{expTotals.meet_inq}</td>{/if}
              {#if showActivity && expTotals.meet_outq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--exp-color)">{expTotals.meet_outq}</td>{/if}
              <td style="padding:10px 16px"></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    {/if}
  </div>
  {/if}

  <!-- Single-motion merged table -->
  {#if singleMotion}
  <div id="rankings" class="p5-panel" style="margin-bottom:20px">
    <div class="p5-panel-header">
      <h2 class="p5-panel-header-title">Standings</h2>
      <button onclick={() => rankCriteriaExpanded = !rankCriteriaExpanded} class="p5-ctrl {rankCriteriaExpanded ? 'active' : ''}">Criteria {rankCriteriaExpanded ? '▲' : '▼'}</button>
    </div>
    <div>
      {#if rankCriteriaExpanded}
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:10px">
        {#each [
          {w:'85%', label:'Total iACV',       desc:'Primary revenue output — dominant signal'},
          {w:'8%',  label:'Quarter MRR %',   desc:'Avg % MRR growth across expansion accounts — are accounts genuinely growing?'},
          {w:'5%',  label:'Total ARR Touched',desc:'Sum of current ARR across expansion accounts — breadth of account footprint'},
          {w:'2%',  label:'Notes Hygiene',   desc:notesFloorLabel+' opps with both SE notes fields filled ÷ total'},
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
      <p style="font-size:10px;color:var(--text-faint);margin-top:8px">Each metric is percentile-ranked 0–100 within the team, then combined with these weights into a composite score.</p>
      {/if}
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)"><tr>
          {#each (stratOnly ? [
            {h:'#',           tip:'', show:true},
            {h:'SE',          tip:seLevelTip, show:true},
            {h:'Wins',        tip:`Count of TW Closed Won ${motionLabels.exp} opps.`, show:true},
            {h:'iACV',        tip:`Net new ARR committed on close across this SE's TW ${motionLabels.exp.toLowerCase()} wins.`, show:true},
            {h:'Acct ARR',    tip:`Current ARR on each ${motionLabels.exp.toLowerCase()} account. Each account counted once.`, show:expTotals.arr_total>0},
            {h:'Qtr MRR Δ',   tip:`Avg monthly usage in the opp's close quarter vs the 3 prior months.`, show:expTotals.arr_total>0},
            {h:'SE Notes',    tip:'Opps with both SE notes fields filled ÷ total TW opps above iACV floor.', show:hasNotesCol},
            {h:'In-Q Emails', tip:`Emails to ${motionLabels.exp} opps closing this quarter.`, show:showActivity && expTotals.inq>0},
            {h:'Pipe Emails', tip:`Emails to ${motionLabels.exp} pipeline opps.`, show:showActivity && expTotals.outq>0},
            {h:'In-Q Meets',  tip:`Meetings on ${motionLabels.exp} opps closing this quarter.`, show:showActivity && expTotals.meet_inq>0},
            {h:'Pipe Meets',  tip:`Meetings on pipeline ${motionLabels.exp} opps.`, show:showActivity && expTotals.meet_outq>0},
            {h:'Status',      tip:`Growing — net MRR increase. Expanding — new iACV, flat MRR. Mixed — new iACV but MRR declining. Contracting — MRR dropping, no new wins. Retaining — no growth signal.`, show:true},
          ] : [
            {h:'#',           tip:'', show:true},
            {h:'SE',          tip:seLevelTip, show:true},
            {h:'Wins',        tip:`Count of TW Closed Won ${motionLabels.act} opps.`, show:true},
            {h:'iACV',        tip:`Net new ARR committed on close across this SE's TW ${motionLabels.act.toLowerCase()} wins.`, show:true},
            {h:'Median',      tip:`Median deal size (iACV) — less skewed by a single large deal.`, show:true},
            {h:'Win Rate',    tip:`Closed Won ÷ (Closed Won + Closed Lost).`, show:hasWinRateCol},
            {h:'SE Notes',    tip:'Opps with both SE notes fields filled ÷ total TW opps above iACV floor.', show:hasNotesCol},
            {h:'In-Q Emails', tip:`Emails to ${motionLabels.act} opps closing this quarter.`, show:showActivity && actTotals.inq>0},
            {h:'Pipe Emails', tip:`Emails to ${motionLabels.act} pipeline opps.`, show:showActivity && actTotals.outq>0},
            {h:'In-Q Meets',  tip:`Meetings on ${motionLabels.act} opps closing this quarter.`, show:showActivity && actTotals.meet_inq>0},
            {h:'Pipe Meets',  tip:`Meetings on pipeline ${motionLabels.act} opps.`, show:showActivity && actTotals.meet_outq>0},
          ]).filter(c=>c.show) as {h, tip}, idx}
          <th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap;position:relative"
            onmouseenter={() => tip ? colTipIdx = idx : null}
            onmouseleave={() => colTipIdx = -1}
          >
            <span style="{tip ? 'border-bottom:1px dashed rgba(var(--red-rgb),0.4);cursor:help;padding-bottom:1px' : ''}">{h}</span>
            {#if colTipIdx === idx && tip}
            <div style="position:absolute;top:calc(100% + 4px);{idx > 5 ? 'right:0' : 'left:0'};z-index:400;width:280px;background:{$theme==='twilio'?'#fff':'#0f1117'};border:1px solid rgba(var(--red-rgb),0.2);border-radius:6px;padding:10px 12px;box-shadow:0 6px 24px rgba(0,0,0,0.2);font-size:11px;font-weight:400;text-transform:none;letter-spacing:0;color:var(--text-muted);line-height:1.5;white-space:normal;pointer-events:none">{tip}</div>
            {/if}
          </th>
          {/each}
        </tr></thead>
        <tbody>
          {#if stratOnly}
            {#each expSes as se, i}
            {@const expSt = computeExpStatus(se)}
            {@const expStColor = expStatusColor(expSt)}
            {@const seArr = se.exp_arr_total ?? 0}
            {@const seDelta = se.exp_mrr_delta_total ?? 0}
            {@const mrrPct = se.exp_mrr_pct_avg ?? 0}
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
              <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{se.rank ?? i+1}</td>
              <td style="padding:10px 16px"><a href="/se-scorecard-v2/me?se={encodeURIComponent(se.name)}" title={se.title || undefined} style="font-weight:700;color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{se.name}</a></td>
              <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.exp_wins}</td>
              <td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{fmt(se.exp_icav)}</td>
              {#if expTotals.arr_total > 0}
              <td style="padding:10px 16px;font-weight:700;color:{seArr > 0 ? ($theme==='twilio'?'#178742':'#10B981') : 'var(--text-faint)'}">
                {seArr > 0 ? fmt(seArr) : '—'}
              </td>
              <td style="padding:10px 16px">
                {#if seArr > 0}
                  <div style="font-weight:700;color:{seDelta > 0 ? ($theme==='twilio'?'#178742':'#10B981') : seDelta < 0 ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'}">
                    {fmtMrrDelta(seDelta)}{#if mrrPct !== 0} <span style="font-size:11px;font-weight:600">({mrrPct > 0 ? '+' : ''}{mrrPct}%)</span>{/if}
                  </div>
                {:else}<span style="color:var(--text-faint)">—</span>{/if}
              </td>
              {/if}
              {#if hasNotesCol}
              <td style="padding:10px 16px;font-size:12px;line-height:1.6">
                {#if (se.note_hv_total ?? 0) > 0}
                  <div style="font-weight:700;color:{se.note_hv_covered === se.note_hv_total ? 'var(--exp-color)' : se.note_hv_covered > 0 ? 'var(--text)' : 'var(--red)'}">{se.note_hv_covered}/{se.note_hv_total}</div>
                  <div style="font-size:11px;color:var(--text-muted)">{se.note_hv_avg_entries} avg entries</div>
                {:else}<span style="color:var(--text-faint)">—</span>{/if}
              </td>
              {/if}
              {#if showActivity && expTotals.inq > 0}<td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.email_exp_inq ?? 0) > 0 ? se.email_exp_inq : '—'}</td>{/if}
              {#if showActivity && expTotals.outq > 0}<td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{(se.email_exp_outq ?? 0) > 0 ? se.email_exp_outq : '—'}</td>{/if}
              {#if showActivity && expTotals.meet_inq > 0}<td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.meeting_exp_inq ?? 0) > 0 ? se.meeting_exp_inq : '—'}</td>{/if}
              {#if showActivity && expTotals.meet_outq > 0}<td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{(se.meeting_exp_outq ?? 0) > 0 ? se.meeting_exp_outq : '—'}</td>{/if}
              <td style="padding:10px 16px">
                <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;background:{expStColor}18;color:{expStColor};border:1px solid {expStColor}40;{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">{expSt}</span>
              </td>
            </tr>
            {/each}
            <!-- strat totals row -->
            <tr style="border-top:2px solid rgba(var(--exp-rgb),0.2);background:rgba(var(--exp-rgb),0.04)">
              <td style="padding:10px 16px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--exp-color)">TOT</td>
              <td style="padding:10px 16px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--exp-color)">Team Total</td>
              <td style="padding:10px 16px;font-weight:700;color:var(--exp-color);text-align:center">{expTotals.wins}</td>
              <td style="padding:10px 16px;font-weight:900;color:var(--exp-color)">{fmt(expTotals.icav)}</td>
              {#if expTotals.arr_total > 0}
              <td style="padding:10px 16px;font-weight:700;color:{$theme==='twilio'?'#178742':'#10B981'}">{fmt(expTotals.arr_total)}</td>
              <td style="padding:10px 16px"><div style="font-weight:700;color:{expTotals.mrr_delta_total > 0 ? ($theme==='twilio'?'#178742':'#10B981') : expTotals.mrr_delta_total < 0 ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'}">{fmtMrrDelta(expTotals.mrr_delta_total)}</div></td>
              {/if}
              {#if hasNotesCol}<td style="padding:10px 16px"></td>{/if}
              {#if showActivity && expTotals.inq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--exp-color)">{expTotals.inq}</td>{/if}
              {#if showActivity && expTotals.outq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--exp-color)">{expTotals.outq}</td>{/if}
              {#if showActivity && expTotals.meet_inq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--exp-color)">{expTotals.meet_inq}</td>{/if}
              {#if showActivity && expTotals.meet_outq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--exp-color)">{expTotals.meet_outq}</td>{/if}
              <td style="padding:10px 16px"></td>
            </tr>
          {:else}
            {#each actSes as se, i}
            {@const vActWins = se.act_wins + (view === 'all' ? (se.non_tw_act_wins ?? 0) : 0)}
            {@const vActIcav = se.act_icav + (view === 'all' ? (se.non_tw_act_icav ?? 0) : 0)}
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
              <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{se.rank ?? i+1}</td>
              <td style="padding:10px 16px"><a href="/se-scorecard-v2/me?se={encodeURIComponent(se.name)}" title={se.title || undefined} style="font-weight:700;color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{se.name}</a></td>
              <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{vActWins}</td>
              <td style="padding:10px 16px;color:var(--act-color);font-weight:700">{fmt(vActIcav)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.act_median)}</td>
              {#if hasWinRateCol}
              <td style="padding:10px 16px">
                <div style="font-weight:700;color:{se.win_rate >= 50 ? 'var(--exp-color)' : se.win_rate > 0 ? 'var(--text-muted)' : 'var(--text-faint)'}">{se.win_rate > 0 ? se.win_rate+'%' : '—'}</div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:1px">{se.closed_won}W / {se.closed_lost}L</div>
              </td>
              {/if}
              {#if hasNotesCol}
              <td style="padding:10px 16px;font-size:12px;line-height:1.6">
                {#if (se.note_hv_total ?? 0) > 0}
                  <div style="font-weight:700;color:{se.note_hv_covered === se.note_hv_total ? 'var(--exp-color)' : se.note_hv_covered > 0 ? 'var(--text)' : 'var(--red)'}">{se.note_hv_covered}/{se.note_hv_total}</div>
                  <div style="font-size:11px;color:var(--text-muted)">{se.note_hv_avg_entries} avg entries</div>
                {:else}<span style="color:var(--text-faint)">—</span>{/if}
              </td>
              {/if}
              {#if showActivity && actTotals.inq > 0}<td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.email_act_inq ?? 0) > 0 ? se.email_act_inq : '—'}</td>{/if}
              {#if showActivity && actTotals.outq > 0}<td style="padding:10px 16px;color:var(--act-color);font-weight:700">{(se.email_act_outq ?? 0) > 0 ? se.email_act_outq : '—'}</td>{/if}
              {#if showActivity && actTotals.meet_inq > 0}<td style="padding:10px 16px;color:var(--text);font-weight:700">{(se.meeting_act_inq ?? 0) > 0 ? se.meeting_act_inq : '—'}</td>{/if}
              {#if showActivity && actTotals.meet_outq > 0}<td style="padding:10px 16px;color:var(--act-color);font-weight:700">{(se.meeting_act_outq ?? 0) > 0 ? se.meeting_act_outq : '—'}</td>{/if}
            </tr>
            {/each}
            <!-- act totals row -->
            {#if actMedians}
            <tr style="border-top:2px solid rgba(var(--act-rgb),0.2);background:rgba(var(--act-rgb),0.04)">
              <td style="padding:10px 16px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--act-color)">MED</td>
              <td style="padding:10px 16px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--act-color)">Team Median</td>
              <td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.wins} {actMedians.wins === 1 ? 'win' : 'wins'}</td>
              <td style="padding:10px 16px;font-weight:900;color:var(--act-color);opacity:0.8">{fmt(actMedians.icav)}</td>
              <td style="padding:10px 16px;color:var(--act-color);font-size:11px;opacity:0.8">{actTeamStats.deal_median > 0 ? fmt(actTeamStats.deal_median) : '—'}</td>
              {#if hasWinRateCol}<td style="padding:10px 16px">{actMedians.win_rate > 0 ? actMedians.win_rate+'%' : '—'}</td>{/if}
              {#if hasNotesCol}<td style="padding:10px 16px"></td>{/if}
              {#if showActivity && actTotals.inq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.email_inq > 0 ? actMedians.email_inq : '—'}</td>{/if}
              {#if showActivity && actTotals.outq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.email_outq > 0 ? actMedians.email_outq : '—'}</td>{/if}
              {#if showActivity && actTotals.meet_inq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.meet_inq > 0 ? actMedians.meet_inq : '—'}</td>{/if}
              {#if showActivity && actTotals.meet_outq > 0}<td style="padding:10px 16px;font-weight:700;color:var(--act-color);opacity:0.8">{actMedians.meet_outq > 0 ? actMedians.meet_outq : '—'}</td>{/if}
            </tr>
            {/if}
          {/if}
        </tbody>
      </table>
    </div>
  </div>
  {/if}

  <!-- Largest Deals -->
  {#if dealSorted.length > 0}
  <div id="deals" class="p5-panel" style="margin-bottom:20px">
    <div class="p5-panel-header"><h2 class="p5-panel-header-title">Largest Deals</h2></div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)"><tr>{#each ['#','SE','Value','Motion','AE','Account','Product'] as h}<th title={h==='SE'?seLevelTip:undefined} style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};{h==='SE'&&seLevelTip?'cursor:help;border-bottom:1px dashed rgba(var(--red-rgb),0.4)':''}">{h}</th>{/each}</tr></thead>
        <tbody>
          {#each dealSorted as se, i}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{i + 1}</td>
            <td style="padding:10px 16px"><a href="/se-scorecard-v2/me?se={encodeURIComponent(se.name)}" title={se.title || undefined} style="font-weight:700;color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{se.name}</a></td>
            <td style="padding:10px 16px;color:{$theme==='twilio'?'#B45309':'var(--yellow)'};font-weight:900;font-style:{$theme==='p5'?'italic':'normal'}">{fmt(se.largest_deal_value)}</td>
            <td style="padding:10px 16px">
              {#if se.largest_deal_motion}
              <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;border-radius:4px;background:{se.largest_deal_motion==='Activate'||se.largest_deal_motion==='New Business' ? 'rgba(var(--act-rgb),0.1)' : 'rgba(var(--exp-rgb),0.1)'};color:{se.largest_deal_motion==='Activate'||se.largest_deal_motion==='New Business' ? 'var(--act-color)' : 'var(--exp-color)'}">{se.largest_deal_motion}</span>
              {:else}—{/if}
            </td>
            <td style="padding:10px 16px;color:var(--text-muted)">{se.largest_deal_dsr || '—'}</td>
            <td style="padding:10px 16px;font-weight:600;color:var(--text)">{se.largest_deal_acct || se.largest_deal.split(' - ')[0] || '—'}</td>
            <td style="padding:10px 16px;color:var(--text-muted);font-size:12px">{se.largest_deal_product || '—'}</td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
  {/if}

  <!-- Notes Quality — hidden when notes filter is on (all shown opps are already fully documented) -->
  {#if !notesFilter}
  <div id="notes" class="p5-panel" style="margin-bottom:20px">
    <div class="p5-panel-header">
      <h2 class="p5-panel-header-title">SE Notes Quality</h2>
    </div>
    <div style="padding:6px 16px 8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid rgba(var(--red-rgb),0.08)">Coverage = both Solutions Team Notes fields filled · Entries counted from [Date: Name] timestamps in history</div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)">
          <tr>{#each ['#', 'SE', notesFloorLabel+' TW Opps','Both Fields Covered','Coverage %','Total Entries','Avg Entries / Opp'] as h}<th title={h==='SE'?seLevelTip:undefined} style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap;{h==='SE'&&seLevelTip?'cursor:help;border-bottom:1px dashed rgba(var(--red-rgb),0.4)':''}">{h}</th>{/each}</tr>
        </thead>
        <tbody>
          {#each [...filteredRanked].filter((s: any) => (s.note_hv_total ?? 0) > 0).sort((a: any, b: any) => (b.note_hv_covered / b.note_hv_total) - (a.note_hv_covered / a.note_hv_total) || b.note_hv_avg_entries - a.note_hv_avg_entries) as se, i}
          {@const pct = se.note_hv_total > 0 ? Math.round(se.note_hv_covered / se.note_hv_total * 100) : 0}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;text-align:center;width:32px">{i + 1}</td>
            <td style="padding:10px 16px"><a href="/se-scorecard-v2/me?se={encodeURIComponent(se.name)}" title={se.title || undefined} style="font-weight:700;color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{se.name}</a></td>
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
          {#each [...filteredRanked].filter((s: any) => (s.note_hv_total ?? 0) === 0) as se}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05);opacity:0.4">
            <td style="padding:10px 16px;text-align:center;width:32px">—</td>
            <td style="padding:10px 16px"><a href="/se-scorecard-v2/me?se={encodeURIComponent(se.name)}" title={se.title || undefined} style="font-weight:700;color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{se.name}</a></td>
            <td colspan="5" style="padding:10px 16px;font-size:11px;color:var(--text-faint)">No closed won opps ≥ {notesFloorLabel} this period</td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
  {/if}

  <!-- Trends -->
  <div id="trends" class="p5-panel" style="margin-bottom:20px">
    <div class="p5-panel-header"><h2 class="p5-panel-header-title">Trends &amp; Flags</h2></div>
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

  <!-- Recommendations -->
  {#if data.recommendations?.length}
  <div id="recs" class="p5-panel" style="margin-bottom:20px">
    <div class="p5-panel-header">
      <h2 class="p5-panel-header-title">Recommendations</h2>
    </div>
    <div style="padding:6px 16px 8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid rgba(var(--red-rgb),0.08)">Data-driven actions to increase iACV and revenue — derived from deal sizing, expansion MRR signals, notes quality, and AE/DSR partner breadth</div>
    <div style="padding:16px;display:flex;flex-direction:column;gap:10px">
      {#each data.recommendations as rec}
      {@const recColor =
        rec.cat === 'REVENUE'    ? ($theme==='twilio' ? '#006EFF' : '#3B82F6') :
        rec.cat === 'EXPANSION'  ? ($theme==='twilio' ? '#178742' : '#10B981') :
        rec.cat === 'PIPELINE'   ? ($theme==='twilio' ? '#7C3AED' : '#A78BFA') :
        rec.cat === 'EFFICIENCY' ? ($theme==='twilio' ? '#B45309' : '#FFB800') :
        rec.cat === 'HYGIENE'    ? ($theme==='twilio' ? '#0891B2' : '#22D3EE') :
        rec.cat === 'COACHING'   ? ($theme==='twilio' ? '#DC2626' : '#EF4444') :
        rec.cat === 'RISK'       ? ($theme==='twilio' ? '#DC2626' : '#EF4444') :
        'var(--text-muted)'}
      <div style="display:flex;gap:0;border-left:4px solid {recColor};background:rgba(var(--red-rgb),0.02);{$theme==='twilio'?'border-radius:0 8px 8px 0':''}">
        <div style="padding:12px 16px;flex:1">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:5px">
            <span style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:{recColor};flex-shrink:0">{rec.cat}</span>
            <span style="font-size:13px;font-weight:700;color:var(--text)">{rec.title}</span>
          </div>
          <p style="font-size:12px;color:var(--text-muted);line-height:1.6;margin:0">{rec.body}</p>
        </div>
      </div>
      {/each}
    </div>
  </div>
  {/if}

  <!-- SE Profiles grid -->
  <div id="profiles">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
      <div class="p5-badge">SE Profiles</div>
      <div style="flex:1;height:1px;background:rgba(var(--red-rgb),0.15)"></div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
      {#each filteredRanked as se}
      <div class="p5-panel" style="padding:16px;display:flex;flex-direction:column;gap:10px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
              <span style="font-size:11px;color:var(--text-faint);font-style:{$theme==='p5'?'italic':'normal'}">#{se.rank}</span>
              <span style="font-size:14px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text)">{se.name}</span>
            </div>
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
            {@html bar(se.act_icav, maxActIcav, $theme==='twilio'?'#006EFF':'#3B82F6')}
          </div>
          <div style="background:rgba(var(--exp-rgb),0.08);border:1px solid rgba(var(--exp-rgb),0.2);border-left:3px solid var(--exp-color);padding:10px;{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
            <div style="font-size:9px;color:var(--exp-color);font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:4px">{motionLabels.exp}</div>
            <div style="font-size:14px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-glow)">{fmt(se.exp_icav)}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:2px">{se.exp_wins} wins</div>
            {@html bar(se.exp_icav, maxExpIcav, $theme==='twilio'?'#178742':'#10B981')}
          </div>
        </div>
        <!-- Individual highlights -->
        <div style="display:flex;flex-wrap:wrap;gap:10px;font-size:12px;color:var(--text-muted);border-top:1px solid rgba(var(--red-rgb),0.08);padding-top:8px">
          {#if se.largest_deal_value > 0}
          <span>Biggest deal <strong style="color:var(--text)">{fmt(se.largest_deal_value)}</strong></span>
          {/if}
          <span>Emails <strong style="color:var(--text)">{emailTotal(se)}</strong></span>
          {#if meetingTotal(se) > 0}
          <span>Meets <strong style="color:var(--text)">{meetingTotal(se)}</strong></span>
          {/if}
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
