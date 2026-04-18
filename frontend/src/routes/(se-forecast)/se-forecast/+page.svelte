<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { user } from '$lib/stores';

  interface Enrichment {
    business_model: string;
    category: string;
    is_lead_gen_or_marketing: boolean;
    tags: string[];
    website: string;
    enriched_at: string;
  }
  interface DealSummary {
    next_steps: string;
    next_meeting_date: string | null;
    next_meeting_label: string | null;
    confidence: 'High' | 'Medium' | 'Low';
    confidence_reason: string;
  }

  interface Deal {
    id: string; name: string; account: string; account_notes: string; account_website: string;
    se_name: string; ae_name: string; ae_role: string;
    stage: string; presales: string; forecast_cat: string;
    close_date: string; icav: number; earr: number;
    current_earr: number; incremental_acv: number;
    next_step: string; last_activity: string;
    se_notes: string; se_history: string;
    is_tw: boolean; is_expansion: boolean; mismatch: string | null;
    manager_note: string; manager_note_author: string; manager_note_at: string;
  }
  interface SEGroup { se_name: string; total_icav: number; total_earr: number; deals: Deal[]; }
  interface UnassignedDeal {
    id: string; name: string; account: string; ae_name: string;
    stage: string; presales: string; forecast_cat: string;
    close_date: string; icav: number; earr: number;
    next_step: string; last_activity: string; se_involved: string;
  }
  interface Summary {
    total_deals: number; total_icav: number;
    tw_icav: number; tw_count: number;
    no_tw_icav: number; no_tw_count: number;
    mismatch_count: number; mismatch_icav: number; mismatch_pct: number;
    unassigned_count: number; unassigned_icav: number;
    by_cat: Record<string, {icav:number;count:number;mismatch_icav:number;mismatch_count:number}>;
  }

  const STAGE_ORDER = ['', '1 - Qualified', '2 - Discovery', '3 - Technical Evaluation', '4 - Technical Win Achieved'];
  const STAGE_LABEL: Record<string,string> = {
    '': 'No Stage', '1 - Qualified': 'Qualified', '2 - Discovery': 'Discovery',
    '3 - Technical Evaluation': 'Tech Evaluation', '4 - Technical Win Achieved': 'TW Achieved',
  };
  const CAT_COLOR: Record<string,string> = {
    'Pipeline': '#6b7280', 'Best Case': '#2563eb', 'Most Likely': '#d97706', 'Commit': '#059669',
  };

  let tab = $state<'activation'|'expansion'|'tw'|'unassigned'|'top'>('activation');
  let actBySE: SEGroup[] = $state([]);
  let expBySE: SEGroup[] = $state([]);
  let twOpen: Deal[] = $state([]);
  let unassigned: UnassignedDeal[] = $state([]);
  let summary: Summary | null = $state(null);
  let periodLabel = $state('');
  let sfUrl = $state('');
  let loading = $state(false);
  let error = $state('');
  let seFilter = $state('All SEs');
  let quarterEndCur = $state('');
  let periodNext = $state('');
  let selectedQuarter = $state<'cur_quarter'|'next_quarter'>('cur_quarter');
  let selectedMonth   = $state<string|null>(null);
  let expandedDeal = $state('');
  let editingId = $state('');
  let editNote = $state('');
  let saving = $state(false);
  let lastRefreshed = $state<Date | null>(null);
  let isFLM = $derived($user?.sf_role_name === 'SE FLM - Self Service');
  let enrichCache  = $state(new Map<string, Enrichment | 'loading' | 'error'>());
  let summaryCache = $state(new Map<string, DealSummary | 'loading' | 'error'>());

  let allAssigned = $derived<Deal[]>([
    ...actBySE.flatMap(g => g.deals),
    ...expBySE.flatMap(g => g.deals),
    ...twOpen,
  ]);
  let seOptions = $derived(['All SEs', ...Array.from(new Set(allAssigned.map(d => d.se_name).filter(Boolean))).sort()]);

  // Compute quarter boundaries purely from today — no API dependency
  function quarterBounds(d: Date): { start: string; end: string } {
    const q = Math.floor(d.getMonth() / 3);
    const qStartMonth = q * 3;
    const qEndMonth = qStartMonth + 2;
    const lastDay = new Date(d.getFullYear(), qEndMonth + 1, 0).getDate();
    const pad = (n: number) => String(n).padStart(2, '0');
    return {
      start: `${d.getFullYear()}-${pad(qStartMonth + 1)}-01`,
      end:   `${d.getFullYear()}-${pad(qEndMonth + 1)}-${pad(lastDay)}`,
    };
  }

  // These are plain values computed once — no reactive state needed
  const _today = new Date();
  const _curQ = quarterBounds(_today);
  const _nextQStart = new Date(_today.getFullYear(), Math.floor(_today.getMonth() / 3) * 3 + 3, 1);
  const _nextQ = quarterBounds(_nextQStart);

  // Build months for a quarter range
  function monthsInRange(start: string, end: string) {
    const opts: {key:string;label:string;start:string;end:string}[] = [];
    const cur = new Date(start + 'T00:00:00');
    cur.setDate(1);
    const endDate = new Date(end + 'T00:00:00');
    while (cur <= endDate) {
      const y = cur.getFullYear(), m = cur.getMonth();
      const lastDay = new Date(y, m + 1, 0).getDate();
      const mo = String(m + 1).padStart(2, '0');
      const key = `${y}-${mo}`;
      opts.push({ key, label: cur.toLocaleDateString('en-US', {month:'short'}), start: `${key}-01`, end: `${y}-${mo}-${String(lastDay).padStart(2,'0')}` });
      cur.setMonth(cur.getMonth() + 1);
    }
    return opts;
  }
  const curQMonths  = monthsInRange(_curQ.start,  _curQ.end);
  const nextQMonths = monthsInRange(_nextQ.start, _nextQ.end);
  const monthOptions = [...curQMonths, ...nextQMonths];

  function makeFilter(sq: string, sm: string | null) {
    return (closeDate: string): boolean => {
      if (!closeDate) return true;
      if (sm) {
        const opt = monthOptions.find(o => o.key === sm);
        return opt ? closeDate >= opt.start && closeDate <= opt.end : true;
      }
      if (sq === 'cur_quarter')  return closeDate >= _curQ.start  && closeDate <= _curQ.end;
      if (sq === 'next_quarter') return closeDate >= _nextQ.start && closeDate <= _nextQ.end;
      return true;
    };
  }

  let topDeals = $derived.by(() => {
    const pred = makeFilter(selectedQuarter, selectedMonth);
    const fromUnassigned: Deal[] = unassigned.map(u => ({
      id: u.id, name: u.name, account: u.account, account_notes: '', account_website: '',
      se_name: '', ae_name: u.ae_name, ae_role: '',
      stage: u.stage, presales: u.presales, forecast_cat: u.forecast_cat,
      close_date: u.close_date, icav: u.icav, earr: u.earr,
      current_earr: 0, incremental_acv: 0,
      next_step: u.next_step, last_activity: u.last_activity,
      se_notes: '', se_history: '',
      is_tw: false, is_expansion: false, mismatch: null,
      manager_note: '', manager_note_author: '', manager_note_at: '',
    }));
    return [...allAssigned, ...fromUnassigned]
      .filter(d => pred(d.close_date))
      .sort((a,b) => b.icav - a.icav)
      .slice(0, 20);
  });

  let tabDeals = $derived.by(() => {
    const pred = makeFilter(selectedQuarter, selectedMonth);
    const base: Deal[] = tab === 'activation' ? actBySE.flatMap(g => g.deals)
               : tab === 'expansion'  ? expBySE.flatMap(g => g.deals)
               : tab === 'tw'         ? twOpen
               : tab === 'top'        ? topDeals : [];
    const dateFiltered = base.filter(d => pred(d.close_date));
    return seFilter === 'All SEs' ? dateFiltered : dateFiltered.filter(d => d.se_name === seFilter);
  });

  let byStage = $derived.by(() => {
    const map = new Map<string, Deal[]>();
    for (const s of STAGE_ORDER) map.set(s, []);
    for (const d of tabDeals) {
      const key = STAGE_ORDER.includes(d.presales) ? d.presales : '';
      map.get(key)!.push(d);
    }
    for (const [, deals] of map) deals.sort((a,b) => b.icav - a.icav);
    return map;
  });

  let mismatchCount = $derived(tabDeals.filter(d => d.mismatch).length);
  let mismatchIcav  = $derived(tabDeals.filter(d => d.mismatch).reduce((s,d) => s+d.icav, 0));

  // Filtered summary — recomputed whenever close filter or SE filter changes
  let filteredSummary = $derived.by(() => {
    const pred = makeFilter(selectedQuarter, selectedMonth);
    const se   = seFilter;
    const all  = [...actBySE.flatMap(g => g.deals), ...expBySE.flatMap(g => g.deals), ...twOpen]
      .filter(d => pred(d.close_date) && (se === 'All SEs' || d.se_name === se));
    const unass = unassigned.filter(d => pred(d.close_date));
    const total = all.reduce((s,d) => s+d.icav, 0);
    const twIcav = all.filter(d => d.is_tw).reduce((s,d) => s+d.icav, 0);
    const mis    = all.filter(d => d.mismatch);
    const misIcav = mis.reduce((s,d) => s+d.icav, 0);
    const byCat: Record<string,{icav:number;count:number;mismatch_icav:number;mismatch_count:number}> = {};
    for (const d of all) {
      const cat = d.forecast_cat || 'Other';
      if (!byCat[cat]) byCat[cat] = {icav:0,count:0,mismatch_icav:0,mismatch_count:0};
      byCat[cat].icav += d.icav; byCat[cat].count++;
      if (d.mismatch) { byCat[cat].mismatch_icav += d.icav; byCat[cat].mismatch_count++; }
    }
    return {
      total_deals: all.length, total_icav: total,
      tw_icav: twIcav, tw_count: all.filter(d => d.is_tw).length,
      no_tw_icav: total - twIcav, no_tw_count: all.filter(d => !d.is_tw).length,
      mismatch_count: mis.length, mismatch_icav: misIcav,
      mismatch_pct: total ? Math.round(misIcav / total * 100) : 0,
      unassigned_count: unass.length, unassigned_icav: unass.reduce((s,d)=>s+d.icav,0),
      by_cat: byCat,
    };
  });

  // Filtered tab counts
  let filteredCounts = $derived.by(() => {
    const pred = makeFilter(selectedQuarter, selectedMonth);
    const se   = seFilter;
    const filter = (d: Deal) => pred(d.close_date) && (se === 'All SEs' || d.se_name === se);
    return {
      activation: actBySE.flatMap(g => g.deals).filter(filter).length,
      expansion:  expBySE.flatMap(g => g.deals).filter(filter).length,
      tw:         twOpen.filter(filter).length,
      unassigned: unassigned.filter(d => pred(d.close_date)).length,
    };
  });

  function fmt(n: number) {
    if (!n) return '—';
    if (n >= 1_000_000) return `$${(n/1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `$${Math.ceil(n/1_000)}K`;
    return `$${n}`;
  }
  function fmtDate(s: string) {
    if (!s) return '—';
    return new Date(s + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  let _refreshTimer: ReturnType<typeof setInterval>;

  async function load() {
    loading = true; error = '';
    const r = await fetch('/api/se-forecast/pipeline');
    loading = false;
    if (!r.ok) { const d = await r.json().catch(()=>({})); error = d.error || 'Failed to load.'; return; }
    const d = await r.json();
    actBySE     = d.act_by_se    ?? [];
    expBySE     = d.exp_by_se    ?? [];
    twOpen      = d.tw_open      ?? [];
    unassigned  = d.unassigned   ?? [];
    summary     = d.summary      ?? null;
    periodLabel = d.period_label ?? '';
    sfUrl          = d.sf_instance_url ?? '';
    quarterEndCur  = d.quarter_end_cur ?? '';
    periodNext     = d.period_next ?? '';
    lastRefreshed  = new Date();
    if (tab === 'top') { enrichTopDeals(); summarizeTopDeals(); }
  }

  async function enrich(deal: Deal) {
    const key = deal.account;
    if (!key || enrichCache.has(key)) return;
    enrichCache.set(key, 'loading');
    enrichCache = new Map(enrichCache);
    try {
      const r = await fetch('/api/se-forecast/enrich', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ account_name: deal.account, account_website: deal.account_website || '' }),
      });
      const d = await r.json();
      enrichCache.set(key, r.ok ? d : 'error');
      enrichCache = new Map(enrichCache);
    } catch {
      enrichCache.set(key, 'error');
      enrichCache = new Map(enrichCache);
    }
  }

  async function enrichTopDeals() {
    await new Promise(r => setTimeout(r, 0)); // let derived settle
    const toEnrich = topDeals.filter(d => d.account && !enrichCache.has(d.account));
    for (let i = 0; i < toEnrich.length; i += 2) {
      const batch = toEnrich.slice(i, i + 2);
      await Promise.all(batch.map(d => enrich(d)));
      if (i + 2 < toEnrich.length) await new Promise(r => setTimeout(r, 600));
    }
  }

  async function summarizeDeal(deal: Deal) {
    const key = deal.id;
    if (!key || summaryCache.has(key)) return;
    summaryCache.set(key, 'loading');
    summaryCache = new Map(summaryCache);
    try {
      const r = await fetch('/api/se-forecast/summarize', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          id: deal.id, name: deal.name, close_date: deal.close_date,
          se_notes: deal.se_notes, se_history: deal.se_history,
          next_step: deal.next_step, last_activity: deal.last_activity,
        }),
      });
      const d = await r.json();
      summaryCache.set(key, r.ok ? d : 'error');
      summaryCache = new Map(summaryCache);
    } catch {
      summaryCache.set(key, 'error');
      summaryCache = new Map(summaryCache);
    }
  }

  async function summarizeTopDeals() {
    await new Promise(r => setTimeout(r, 0));
    const toSummarize = topDeals.filter(d => d.id && !summaryCache.has(d.id));
    for (let i = 0; i < toSummarize.length; i += 2) {
      const batch = toSummarize.slice(i, i + 2);
      await Promise.all(batch.map(d => summarizeDeal(d)));
      if (i + 2 < toSummarize.length) await new Promise(r => setTimeout(r, 600));
    }
  }

  onMount(() => {
    load();
    _refreshTimer = setInterval(load, 5 * 60 * 1000);
  });
  onDestroy(() => clearInterval(_refreshTimer));

  async function saveNote(deal: Deal) {
    saving = true;
    const r = await fetch(`/api/se-forecast/notes/${deal.id}`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ note: editNote }),
    });
    saving = false;
    if (!r.ok) return;
    const d = await r.json();
    deal.manager_note = d.note; deal.manager_note_author = d.author; deal.manager_note_at = d.updated_at;
    editingId = '';
  }

</script>

<div class="page">
  <!-- Header -->
  <div class="page-hd">
    <div>
      <h1>SE Forecast <span class="period">{periodLabel}</span></h1>
      <p class="sub">Digital Sales · Self Service</p>
    </div>
    <div class="hd-right">
      {#if loading}<span class="loading-dot"></span>{/if}
      {#if lastRefreshed}<span class="last-refresh">Updated {lastRefreshed.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'})}</span>{/if}
    </div>
  </div>

  <!-- Filter bar -->
  <div class="filter-bar">
    <!-- Close date: quarter tabs → month pills -->
    <div class="filter-group filter-group-date">
      <span class="filter-label">Close date</span>
      <div class="date-picker">
        <div class="q-tabs">
          <button class="q-tab" class:q-tab-active={selectedQuarter==='cur_quarter'}
            onclick={() => { selectedQuarter='cur_quarter'; selectedMonth=null; }}>
            {periodLabel || 'This Q'}
          </button>
          <button class="q-tab" class:q-tab-active={selectedQuarter==='next_quarter'}
            onclick={() => { selectedQuarter='next_quarter'; selectedMonth=null; }}>
            {periodNext || 'Next Q'}
          </button>
        </div>
        <div class="month-row">
          <button class="month-chip" class:month-chip-active={selectedMonth===null}
            onclick={() => selectedMonth=null}>All</button>
          {#each (selectedQuarter==='cur_quarter' ? curQMonths : nextQMonths) as mo (mo.key)}
            <button class="month-chip" class:month-chip-active={selectedMonth===mo.key}
              onclick={() => selectedMonth=mo.key}>{mo.label}</button>
          {/each}
        </div>
      </div>
    </div>
    <!-- SE chips -->
    <div class="filter-group filter-group-se">
      <span class="filter-label">SE</span>
      <div class="chip-list">
        {#each seOptions as opt}
          <button class="chip" class:chip-active={seFilter===opt} onclick={() => seFilter=opt}>{opt}</button>
        {/each}
      </div>
    </div>
  </div>

  {#if error}<div class="error">{error}</div>{/if}

  {#if summary}
    {@const fs = filteredSummary}
    <!-- Summary strip -->
    <div class="strip">
      <div class="sc">
        <div class="sc-title">Total Pipeline</div>
        <div class="sc-val">{fmt(fs.total_icav)}</div>
        <div class="sc-lbl">{fs.total_deals} deals</div>
      </div>
      <div class="sc sc-green">
        <div class="sc-title">TW Achieved</div>
        <div class="sc-val">{fmt(fs.tw_icav)}</div>
        <div class="sc-lbl">{fs.tw_count} deals</div>
      </div>
      <div class="sc sc-amber">
        <div class="sc-title">No TW</div>
        <div class="sc-val">{fmt(fs.no_tw_icav)}</div>
        <div class="sc-lbl">{fs.no_tw_count} deals</div>
      </div>
      {#if fs.mismatch_count > 0}
        <div class="sc sc-red">
          <div class="sc-title">Mismatch</div>
          <div class="sc-val">{fmt(fs.mismatch_icav)}</div>
          <div class="sc-lbl">{fs.mismatch_count} deals · {fs.mismatch_pct}%</div>
        </div>
      {/if}
      {#each ['Commit','Most Likely','Best Case','Pipeline'] as cat}
        {#if fs.by_cat[cat]}
          {@const c = fs.by_cat[cat]}
          <div class="sc" style="border-top-color:{c.mismatch_count>0?'#dc2626':CAT_COLOR[cat]}">
            <div class="sc-title" style="color:{CAT_COLOR[cat]}">{cat}</div>
            <div class="sc-val">{fmt(c.icav)}</div>
            <div class="sc-lbl">{c.count} deals{#if c.mismatch_count>0} · <span style="color:#dc2626">{c.mismatch_count} ⚠</span>{/if}</div>
          </div>
        {/if}
      {/each}
    </div>

    <!-- Tabs -->
    <div class="tabs">
      {#each [
        {key:'activation', label:'Activation', count: filteredCounts.activation},
        {key:'expansion',  label:'Expansion',  count: filteredCounts.expansion},
        {key:'tw',         label:'TW Open',    count: filteredCounts.tw},
        {key:'unassigned', label:'Unassigned', count: filteredCounts.unassigned},
        {key:'top',        label:'Top Opps',   count: topDeals.length},
      ] as t}
        <button class="tab" class:active={tab===t.key} onclick={() => { tab = t.key as typeof tab; expandedDeal=''; if(t.key==='top') { enrichTopDeals(); summarizeTopDeals(); } }}>
          {t.label}{#if t.count > 0} <span class="tab-count">{t.count}</span>{/if}
        </button>
      {/each}
    </div>

    <!-- SE filter context -->
    {#if seFilter !== 'All SEs' && mismatchCount > 0}
      <div class="filter-banner">
        <span class="filter-name">{seFilter}</span> — {tabDeals.length} deals · {mismatchCount} mismatch{mismatchCount!==1?'es':''} ({fmt(mismatchIcav)} iACV)
      </div>
    {/if}

    <!-- Top Opps tab -->
    {#if tab === 'top'}
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th style="width:32px">#</th>
            <th>Account / Opportunity</th>
            <th>Business Profile</th>
            <th>Next Steps & Outlook</th>
            <th>SE</th>
            <th>AE</th>
            <th>Presales Stage</th>
            <th>Forecast</th>
            <th>iACV</th>
            <th>Close</th>
          </tr></thead>
          <tbody>
            {#each topDeals as deal, i (deal.id)}
              {@const enr = enrichCache.get(deal.account)}
              <tr class="dr" class:mis={!!deal.mismatch}
                  onclick={() => { expandedDeal = expandedDeal===deal.id?'':deal.id; if(expandedDeal!==deal.id) editingId=''; }}>
                <td class="rank">{i+1}</td>
                <td class="col-acct">
                  <div class="opp-acct-row">
                    <span class="opp-acct">{deal.account || deal.name}</span>
                    {#if deal.is_expansion}<span class="type-exp">Exp</span>{:else}<span class="type-act">Act</span>{/if}
                  </div>
                  <div class="opp-name">{deal.name}</div>
                </td>
                <td class="col-enrich">
                  {#if enr === 'loading'}
                    <span class="enrich-loading">Analyzing…</span>
                  {:else if !enr || enr === 'error'}
                    <span class="dim">—</span>
                  {:else}
                    <div class="enrich-wrap">
                      <div class="enrich-top">
                        <span class="enrich-category">{enr.category}</span>
                        {#if enr.is_lead_gen_or_marketing}
                          <span class="enrich-flag">Lead Gen</span>
                        {/if}
                      </div>
                      <div class="enrich-model">{enr.business_model}</div>
                      {#if enr.tags?.length}
                        <div class="enrich-tags">
                          {#each enr.tags as tag}<span class="enrich-tag">{tag}</span>{/each}
                        </div>
                      {/if}
                    </div>
                  {/if}
                </td>
                <td class="col-summary">
                  {#if summaryCache.get(deal.id) === 'loading'}
                    <span class="enrich-loading">Analyzing…</span>
                  {:else if !summaryCache.get(deal.id) || summaryCache.get(deal.id) === 'error'}
                    <span class="dim">—</span>
                  {:else}
                    {@const sum = summaryCache.get(deal.id) as DealSummary}
                    <div class="summary-wrap">
                      <div class="summary-section">
                        <div class="summary-label">Next Steps</div>
                        <div class="summary-text">{sum.next_steps}</div>
                      </div>
                      <div class="summary-section">
                        <div class="summary-label">Next Meeting</div>
                        {#if sum.next_meeting_label}
                          <div class="summary-meeting">{sum.next_meeting_label}</div>
                        {:else}
                          <div class="summary-warn">⚠ None scheduled</div>
                        {/if}
                      </div>
                      <div class="summary-section">
                        <div class="summary-label">Confidence</div>
                        <div class="summary-conf-row">
                          <span class="summary-confidence confidence-{sum.confidence.toLowerCase()}">{sum.confidence}</span>
                          <span class="summary-reason">{sum.confidence_reason}</span>
                        </div>
                      </div>
                    </div>
                  {/if}
                </td>
                <td class="small">{#if deal.se_name}{deal.se_name}{:else}<span class="badge-unassigned">Unassigned</span>{/if}</td>
                <td class="small">{deal.ae_name || '—'}</td>
                <td>
                  {#if deal.presales}<span class="stage-pill" class:tw={deal.is_tw}>{deal.presales.replace(/^\d+ - /,'')}</span>
                  {:else}<span class="stage-missing">Not set</span>{/if}
                </td>
                <td>{#if deal.forecast_cat}<span class="cat-pill" style="color:{CAT_COLOR[deal.forecast_cat]??'#6b7280'};background:{CAT_COLOR[deal.forecast_cat]??'#6b7280'}18;border:1px solid {CAT_COLOR[deal.forecast_cat]??'#6b7280'}30">{deal.forecast_cat}</span>{:else}<span class="dim">—</span>{/if}</td>
                <td class="num">{fmt(deal.icav)}</td>
                <td class="date">{fmtDate(deal.close_date)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    <!-- TW Open: split mismatch / clean -->
    {#if tab === 'tw'}
      {#if tabDeals.length === 0}
        <div class="empty">No TW deals in current quarter.</div>
      {:else}
        {@const isTWClean = (d: Deal) => !d.mismatch && (d.forecast_cat === 'Most Likely' || d.forecast_cat === 'Commit')}
        {@const twMis   = tabDeals.filter(d => !isTWClean(d)).sort((a,b)=>b.icav-a.icav)}
        {@const twClean = tabDeals.filter(d =>  isTWClean(d)).sort((a,b)=>b.icav-a.icav)}
        <div class="tw-board">
          <!-- Mismatch column -->
          <div class="tw-col">
            <div class="tw-col-hd tw-col-hd-mis">
              <span>⚠ Mismatch</span>
              <span class="col-count">{twMis.length}</span>
              <span class="col-icav">{fmt(twMis.reduce((s,d)=>s+d.icav,0))}</span>
            </div>
            {#if twMis.length === 0}
              <div class="tw-empty">No mismatches</div>
            {:else}
              {#each twMis as deal (deal.id)}
                <div class="card card-mis" class:card-open={expandedDeal===deal.id}
                     onclick={() => { expandedDeal=expandedDeal===deal.id?'':deal.id; if(expandedDeal!==deal.id) editingId=''; }}>
                  <div class="card-top">
                    <div class="card-acct">{deal.account || deal.name}</div>
                    <span class="card-icav">{fmt(deal.icav)}</span>
                  </div>
                  <div class="card-opp">{deal.name}</div>
                  <div class="card-meta">
                    {#if deal.forecast_cat}<span class="cat-pill" style="color:{CAT_COLOR[deal.forecast_cat]??'#6b7280'};background:{CAT_COLOR[deal.forecast_cat]??'#6b7280'}18;border:1px solid {CAT_COLOR[deal.forecast_cat]??'#6b7280'}30">{deal.forecast_cat}</span>{/if}
                    <span class="card-close">{fmtDate(deal.close_date)}</span>
                  </div>
                  <div class="card-people">{deal.se_name || '—'} · {deal.ae_name || '—'}</div>
                  {#if deal.mismatch}
                    <div class="tw-mis-reason">⚠ {deal.mismatch}</div>
                  {:else if deal.forecast_cat && deal.forecast_cat !== 'Most Likely' && deal.forecast_cat !== 'Commit'}
                    <div class="tw-mis-reason">Forecast is {deal.forecast_cat} — needs Most Likely or Commit</div>
                  {/if}
                </div>
              {/each}
            {/if}
          </div>
          <!-- Clean column -->
          <div class="tw-col">
            <div class="tw-col-hd tw-col-hd-clean">
              <span>✓ Clean</span>
              <span class="col-count">{twClean.length}</span>
              <span class="col-icav">{fmt(twClean.reduce((s,d)=>s+d.icav,0))}</span>
            </div>
            {#if twClean.length === 0}
              <div class="tw-empty">No clean deals</div>
            {:else}
              {#each twClean as deal (deal.id)}
                <div class="card" class:card-open={expandedDeal===deal.id}
                     onclick={() => { expandedDeal=expandedDeal===deal.id?'':deal.id; if(expandedDeal!==deal.id) editingId=''; }}>
                  <div class="card-top">
                    <div class="card-acct">{deal.account || deal.name}</div>
                    <span class="card-icav">{fmt(deal.icav)}</span>
                  </div>
                  <div class="card-opp">{deal.name}</div>
                  <div class="card-meta">
                    {#if deal.forecast_cat}<span class="cat-pill" style="color:{CAT_COLOR[deal.forecast_cat]??'#6b7280'};background:{CAT_COLOR[deal.forecast_cat]??'#6b7280'}18;border:1px solid {CAT_COLOR[deal.forecast_cat]??'#6b7280'}30">{deal.forecast_cat}</span>{/if}
                    <span class="card-close">{fmtDate(deal.close_date)}</span>
                  </div>
                  <div class="card-people">{deal.se_name || '—'} · {deal.ae_name || '—'}</div>
                </div>
              {/each}
            {/if}
          </div>
        </div>
      {/if}
    {/if}

    <!-- Kanban board (Activation / Expansion tabs) -->
    {#if tab !== 'unassigned' && tab !== 'top' && tab !== 'tw'}
      {#if tabDeals.length === 0}
        <div class="empty">No deals for this view.</div>
      {:else}
        <div class="board">
          {#each STAGE_ORDER as stage}
            {@const deals = byStage.get(stage) ?? []}
            {#if deals.length > 0}
              {@const stageMismatches = deals.filter(d => d.mismatch).length}
              <div class="col">
                <div class="col-hd">
                  <div class="col-hd-top">
                    <span class="stage-dot" class:dot-tw={stage==='4 - Technical Win Achieved'} class:dot-empty={stage===''}></span>
                    <span class="col-title">{STAGE_LABEL[stage]}</span>
                    <span class="col-count">{deals.length}</span>
                    {#if stageMismatches > 0}<span class="col-mis">{stageMismatches} ⚠</span>{/if}
                  </div>
                  <div class="col-icav">{fmt(deals.reduce((s,d)=>s+d.icav,0))}</div>
                </div>
                <div class="col-cards">
                  {#each deals as deal (deal.id)}
                    <div class="card" class:card-mis={!!deal.mismatch} class:card-open={expandedDeal===deal.id}
                         onclick={() => { expandedDeal = expandedDeal===deal.id?'':deal.id; if(expandedDeal!==deal.id) editingId=''; }}>
                      <div class="card-top">
                        <div class="card-acct">{deal.account || deal.name}</div>
                        <span class="card-icav">{fmt(deal.icav)}</span>
                      </div>
                      <div class="card-opp">{deal.name}</div>
                      <div class="card-meta">
                        {#if deal.forecast_cat}
                          <span class="cat-pill" style="color:{CAT_COLOR[deal.forecast_cat]??'#6b7280'};background:{CAT_COLOR[deal.forecast_cat]??'#6b7280'}18;border:1px solid {CAT_COLOR[deal.forecast_cat]??'#6b7280'}30">{deal.forecast_cat}</span>
                        {/if}
                        {#if deal.is_expansion}<span class="type-exp">Exp</span>{:else}<span class="type-act">Act</span>{/if}
                        <span class="card-close">{fmtDate(deal.close_date)}</span>
                        {#if deal.mismatch}<span class="badge-mis">⚠</span>{/if}
                      </div>
                      <div class="card-people">{deal.se_name || '—'} · {deal.ae_name || '—'}</div>
                    </div>
                  {/each}
                </div>
              </div>
            {/if}
          {/each}
        </div>

        <!-- detail rendered in fixed drawer below -->
      {/if}
    {/if}<!-- end tab board -->

    <!-- Unassigned tab -->
    {#if tab === 'unassigned' && unassigned.length > 0}
      <div class="stage-section">
        <div class="stage-hd">
          <span class="stage-dot dot-empty"></span>
          <span class="stage-title">Unassigned</span>
          <span class="stage-count">{unassigned.length}</span>
          <span class="stage-icav">{fmt(unassigned.reduce((s,d)=>s+d.icav,0))}</span>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead><tr>
              <th class="col-acct">Account / Opportunity</th>
              <th class="col-ae">AE</th>
              <th class="col-cat">Forecast</th>
              <th class="col-icav">iACV</th>
              <th class="col-close">Close</th>
              <th>SE Involved?</th>
            </tr></thead>
            <tbody>
              {#each unassigned as d (d.id)}
                <tr class="dr">
                  <td class="col-acct">
                    <div class="opp-acct">{d.account || d.name}</div>
                    <div class="opp-name">{d.name}</div>
                  </td>
                  <td class="small">{d.ae_name || '—'}</td>
                  <td>
                    {#if d.forecast_cat}<span class="cat-pill" style="color:{CAT_COLOR[d.forecast_cat]??'#6b7280'};background:{CAT_COLOR[d.forecast_cat]??'#6b7280'}18;border:1px solid {CAT_COLOR[d.forecast_cat]??'#6b7280'}30">{d.forecast_cat}</span>
                    {:else}<span class="dim">—</span>{/if}
                  </td>
                  <td class="num">{fmt(d.icav)}</td>
                  <td class="date">{fmtDate(d.close_date)}</td>
                  <td class="small">{d.se_involved || '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  {/if}
</div>

<!-- Modal -->
{#if expandedDeal}
  {@const deal = tabDeals.find(d => d.id === expandedDeal)}
  {#if deal}
    <div class="modal-backdrop" onclick={() => { expandedDeal=''; editingId=''; }}></div>
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-hd">
        <div class="modal-hd-info">
          <div class="modal-stage-row">
            {#if deal.presales}<span class="modal-stage">{deal.presales.replace(/^\d+ - /,'')}</span>{/if}
            {#if deal.forecast_cat}<span class="cat-pill" style="color:{CAT_COLOR[deal.forecast_cat]??'#6b7280'};background:{CAT_COLOR[deal.forecast_cat]??'#6b7280'}18;border:1px solid {CAT_COLOR[deal.forecast_cat]??'#6b7280'}30">{deal.forecast_cat}</span>{/if}
            {#if deal.is_expansion}<span class="type-exp">Expansion</span>{:else}<span class="type-act">Activation</span>{/if}
          </div>
          <div class="modal-acct">{deal.account || deal.name}</div>
          <div class="modal-opp">{deal.name}</div>
          <div class="modal-meta-row">
            <span class="modal-icav">{fmt(deal.icav)} iACV</span>
            <span class="modal-dot">·</span>
            <span>Close {fmtDate(deal.close_date)}</span>
            <span class="modal-dot">·</span>
            <span>{deal.se_name || '—'} / {deal.ae_name || '—'}</span>
            {#if sfUrl}<span class="modal-dot">·</span><a href="{sfUrl}/lightning/r/Opportunity/{deal.id}/view" target="_blank" rel="noopener" class="sf-link">Salesforce ↗</a>{/if}
          </div>
        </div>
        <button class="modal-close" onclick={() => { expandedDeal=''; editingId=''; }}>✕</button>
      </div>
      <div class="modal-body">
        {@render dealDetail(deal)}
      </div>
    </div>
  {/if}
{/if}

{#snippet dealDetail(deal: Deal)}
  <div class="detail-panel">
    {#if deal.mismatch}
      <div class="mis-banner">⚠ <strong>Stage mismatch:</strong> {deal.mismatch}</div>
    {/if}
    <div class="detail-meta">
      {#if deal.next_step}<span><strong>Next:</strong> {deal.next_step}</span>{/if}
      {#if deal.last_activity}<span><strong>Last activity:</strong> {fmtDate(deal.last_activity)}</span>{/if}
      {#if sfUrl}<a href="{sfUrl}/lightning/r/Opportunity/{deal.id}/view" target="_blank" rel="noopener" class="sf-link">View in SF ↗</a>{/if}
    </div>
    <div class="notes-grid">
      <div class="notes-card">
        <div class="notes-hd">SE Notes</div>
        {#if deal.se_notes}<div class="notes-body">{deal.se_notes}</div>
        {:else}<div class="notes-empty">No SE notes</div>{/if}
      </div>
      <div class="notes-card">
        <div class="notes-hd">SE History</div>
        {#if deal.se_history}<div class="notes-body">{deal.se_history}</div>
        {:else}<div class="notes-empty">No history</div>{/if}
      </div>
      <div class="notes-card notes-mgr">
        <div class="notes-hd">
          Manager Notes
          {#if deal.manager_note_author}<span class="notes-meta">— {deal.manager_note_author} · {deal.manager_note_at.slice(0,10)}</span>{/if}
        </div>
        {#if isFLM && editingId === deal.id}
          <textarea class="note-ta" bind:value={editNote} placeholder="Add notes…" rows="4"></textarea>
          <div class="note-btns">
            <button class="btn-save" onclick={() => saveNote(deal)} disabled={saving}>{saving?'Saving…':'Save'}</button>
            <button class="btn-ghost" onclick={() => editingId=''}>Cancel</button>
          </div>
        {:else}
          {#if deal.manager_note}<div class="notes-body">{deal.manager_note}</div>
          {:else}<div class="notes-empty">No manager notes yet</div>{/if}
          {#if isFLM}
            <button class="btn-edit" onclick={(e)=>{e.stopPropagation();editingId=deal.id;editNote=deal.manager_note;}}>
              {deal.manager_note?'Edit':'+ Add note'}
            </button>
          {/if}
        {/if}
      </div>
    </div>
  </div>
{/snippet}

<style>
  .page { padding:28px 24px 64px; max-width:1360px; margin:0 auto; font-family:Inter,ui-sans-serif,system-ui,sans-serif; }

  .page-hd { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; gap:16px; }
  h1 { font-size:22px; font-weight:800; color:#0d122b; letter-spacing:-0.02em; margin:0 0 2px; }
  .period { font-size:14px; font-weight:500; color:rgba(13,18,43,0.4); margin-left:8px; }
  .sub { font-size:12px; color:rgba(13,18,43,0.45); margin:0; }
  .hd-right { display:flex; gap:8px; align-items:center; }
  .loading-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#f22f46; animation:pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
  .last-refresh { font-size:11px; color:rgba(13,18,43,0.35); }

  /* Filter bar */
  .filter-bar { display:flex; align-items:center; gap:20px; background:white; border:1px solid rgba(13,18,43,0.09); border-radius:10px; padding:10px 16px; margin-bottom:16px; flex-wrap:wrap; }
  .filter-group { display:flex; align-items:center; gap:8px; }
  .filter-group-se { flex:1; min-width:0; }
  .filter-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:rgba(13,18,43,0.35); white-space:nowrap; }
  .filter-group-date { flex-shrink:0; }
  .date-picker { display:flex; align-items:center; gap:10px; }
  /* Quarter tabs */
  .q-tabs { display:flex; border:1px solid rgba(13,18,43,0.14); border-radius:8px; overflow:hidden; flex-shrink:0; }
  .q-tab { padding:5px 14px; border:none; border-right:1px solid rgba(13,18,43,0.14); background:white; color:rgba(13,18,43,0.45); font-size:12px; font-weight:600; font-family:inherit; cursor:pointer; white-space:nowrap; transition:all 0.12s; }
  .q-tab:last-child { border-right:none; }
  .q-tab:hover { background:#f4f4f6; color:#0d122b; }
  .q-tab-active { background:#0d122b; color:white; }
  /* Divider between quarter and months */
  .date-picker::after { content:''; display:none; }
  /* Month pills */
  .month-row { display:flex; gap:4px; align-items:center; }
  .month-chip { padding:4px 11px; border:1px solid rgba(13,18,43,0.12); border-radius:20px; background:white; color:rgba(13,18,43,0.45); font-size:11px; font-weight:600; font-family:inherit; cursor:pointer; white-space:nowrap; transition:all 0.12s; }
  .month-chip:hover { border-color:rgba(13,18,43,0.25); color:#0d122b; }
  .month-chip-active { background:#f22f46; border-color:#f22f46; color:white; }
  /* SE chips */
  .chip-list { display:flex; flex-wrap:wrap; gap:5px; }
  .chip { padding:4px 11px; border:1px solid rgba(13,18,43,0.14); border-radius:20px; background:white; color:rgba(13,18,43,0.55); font-size:12px; font-weight:500; font-family:inherit; cursor:pointer; white-space:nowrap; transition:all 0.12s; }
  .chip:hover { border-color:rgba(13,18,43,0.3); color:#0d122b; }
  .chip-active { background:#0d122b; border-color:#0d122b; color:white; }
  .error { background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:12px 16px; color:#dc2626; font-size:13px; margin-bottom:16px; }

  /* Summary strip */
  .strip { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; }
  .sc { background:white; border:1px solid rgba(13,18,43,0.1); border-top:3px solid rgba(13,18,43,0.12); border-radius:10px; padding:10px 14px; min-width:110px; box-shadow:0 1px 4px rgba(13,18,43,0.05); }
  .sc-green { border-top-color:#059669; }
  .sc-amber { border-top-color:#d97706; }
  .sc-red { border-top-color:#dc2626; }
  .sc-title { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:rgba(13,18,43,0.4); margin-bottom:4px; }
  .sc-val { font-size:18px; font-weight:800; color:#0d122b; letter-spacing:-0.02em; }
  .sc-lbl { font-size:11px; color:rgba(13,18,43,0.5); margin-top:2px; }

  .tabs { display:flex; gap:2px; margin-bottom:16px; border-bottom:1px solid rgba(13,18,43,0.1); }
  .tab { padding:8px 16px; border:none; border-bottom:2px solid transparent; background:transparent; color:rgba(13,18,43,0.5); font-size:13px; font-weight:600; cursor:pointer; font-family:inherit; transition:all 0.15s; }
  .tab:hover { color:#0d122b; }
  .tab.active { color:#f22f46; border-bottom-color:#f22f46; }
  .tab-count { display:inline-flex; align-items:center; justify-content:center; background:rgba(13,18,43,0.08); color:rgba(13,18,43,0.6); border-radius:20px; padding:0 6px; font-size:10px; font-weight:700; min-width:18px; height:16px; margin-left:4px; }
  .tab.active .tab-count { background:rgba(242,47,70,0.12); color:#f22f46; }

  .filter-banner { background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:10px 14px; font-size:13px; color:#92400e; margin-bottom:16px; }
  .filter-name { font-weight:700; }

  /* Stage section */
  .stage-section { margin-bottom:20px; }
  .stage-hd { display:flex; align-items:center; gap:10px; padding:0 4px 8px; }
  .stage-dot { width:10px; height:10px; border-radius:50%; background:rgba(13,18,43,0.2); flex-shrink:0; }
  .dot-tw { background:#059669; }
  .dot-empty { background:#9ca3af; }
  .stage-title { font-size:13px; font-weight:700; color:#0d122b; letter-spacing:-0.01em; }
  .stage-count { font-size:12px; color:rgba(13,18,43,0.4); background:rgba(13,18,43,0.07); border-radius:20px; padding:1px 8px; }
  .stage-icav { font-size:13px; font-weight:700; color:rgba(13,18,43,0.6); margin-left:2px; }
  .stage-mis { font-size:11px; font-weight:700; color:#dc2626; background:#fef2f2; border:1px solid #fecaca; border-radius:20px; padding:1px 8px; margin-left:4px; }

  .tbl-wrap { background:white; border:1px solid rgba(13,18,43,0.1); border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(13,18,43,0.06); }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  thead tr { background:#f8f8fb; border-bottom:1px solid rgba(13,18,43,0.1); }
  th { padding:8px 12px; text-align:left; font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:rgba(13,18,43,0.4); white-space:nowrap; }

  .empty { text-align:center; padding:48px; color:rgba(13,18,43,0.35); font-size:14px; }

  /* Board */
  .board { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:14px; align-items:start; margin-bottom:20px; }

  /* Column */
  .col { display:flex; flex-direction:column; gap:0; }
  .col-hd { background:white; border:1px solid rgba(13,18,43,0.1); border-radius:10px 10px 0 0; border-bottom:none; padding:10px 14px; }
  .col-hd-top { display:flex; align-items:center; gap:6px; margin-bottom:3px; }
  .col-title { font-size:12px; font-weight:700; color:#0d122b; letter-spacing:-0.01em; }
  .col-count { font-size:11px; color:rgba(13,18,43,0.4); background:rgba(13,18,43,0.07); border-radius:20px; padding:1px 7px; }
  .col-mis { font-size:10px; font-weight:700; color:#dc2626; background:#fef2f2; border:1px solid #fecaca; border-radius:20px; padding:1px 7px; }
  .col-icav { font-size:16px; font-weight:800; color:#0d122b; letter-spacing:-0.02em; }
  .col-cards { display:flex; flex-direction:column; gap:6px; background:#f0f2f8; border:1px solid rgba(13,18,43,0.1); border-radius:0 0 10px 10px; padding:8px; min-height:40px; }

  /* Card */
  .card { background:white; border:1px solid rgba(13,18,43,0.1); border-radius:8px; padding:10px 12px; cursor:pointer; transition:box-shadow 0.15s, border-color 0.15s; }
  .card:hover { box-shadow:0 2px 8px rgba(13,18,43,0.1); border-color:rgba(13,18,43,0.2); }
  .card-mis { border-left:3px solid #dc2626; }
  .card-open { border-color:#f22f46; box-shadow:0 0 0 2px rgba(242,47,70,0.12); }
  .card-top { display:flex; justify-content:space-between; align-items:flex-start; gap:6px; margin-bottom:2px; }
  .card-acct { font-size:12px; font-weight:700; color:#0d122b; line-height:1.3; }
  .card-icav { font-size:12px; font-weight:800; color:#0d122b; white-space:nowrap; font-variant-numeric:tabular-nums; flex-shrink:0; }
  .card-opp { font-size:11px; color:rgba(13,18,43,0.45); margin-bottom:6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .card-meta { display:flex; flex-wrap:wrap; gap:4px; align-items:center; margin-bottom:5px; }
  .card-close { font-size:10px; color:rgba(13,18,43,0.4); }
  .card-people { font-size:11px; color:rgba(13,18,43,0.5); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

  .cat-pill { display:inline-block; padding:2px 7px; border-radius:20px; font-size:10px; font-weight:700; white-space:nowrap; }
  .type-act { display:inline-block; padding:1px 6px; border-radius:4px; font-size:10px; font-weight:700; background:#eff6ff; color:#1d4ed8; }
  .type-exp { display:inline-block; padding:1px 6px; border-radius:4px; font-size:10px; font-weight:700; background:#fdf4ff; color:#7e22ce; }
  .badge-mis { display:inline-block; padding:1px 6px; border-radius:20px; font-size:10px; font-weight:700; background:#fef2f2; color:#dc2626; border:1px solid #fecaca; white-space:nowrap; }
  .badge-ok { display:inline-block; padding:1px 6px; border-radius:20px; font-size:10px; font-weight:700; background:#f0fdf4; color:#15803d; border:1px solid #bbf7d0; }
  .badge-unassigned { display:inline-block; padding:1px 6px; border-radius:20px; font-size:10px; font-weight:700; background:#f3f4f6; color:#6b7280; border:1px solid #e5e7eb; }
  .rank { font-size:12px; font-weight:700; color:rgba(13,18,43,0.3); text-align:center; }
  .opp-ae { font-size:10px; color:rgba(13,18,43,0.35); margin-top:1px; }
  .col-enrich { width:220px; min-width:200px; }
  .col-summary { width:320px; min-width:280px; }
  .enrich-loading { font-size:11px; color:rgba(13,18,43,0.3); font-style:italic; }
  .enrich-wrap { display:flex; flex-direction:column; gap:4px; }
  .enrich-top { display:flex; align-items:center; gap:5px; flex-wrap:wrap; }
  .enrich-flag { padding:1px 6px; border-radius:20px; font-size:10px; font-weight:700; background:#fef3c7; color:#92400e; border:1px solid #fcd34d; white-space:nowrap; }
  .enrich-category { font-size:11px; font-weight:700; color:#0d122b; }
  .enrich-model { font-size:11px; color:rgba(13,18,43,0.55); line-height:1.45; }
  .enrich-tags { display:flex; flex-wrap:wrap; gap:3px; }
  .enrich-tag { font-size:10px; padding:1px 6px; border-radius:4px; background:rgba(13,18,43,0.06); color:rgba(13,18,43,0.5); }
  .summary-wrap { display:flex; flex-direction:column; gap:0; }
  .summary-section { padding:4px 0; border-bottom:1px solid rgba(13,18,43,0.06); }
  .summary-section:last-child { border-bottom:none; padding-bottom:0; }
  .summary-section:first-child { padding-top:0; }
  .summary-label { font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:rgba(13,18,43,0.35); margin-bottom:2px; }
  .summary-text { font-size:11px; color:#0d122b; line-height:1.5; }
  .summary-meeting { font-size:11px; font-weight:600; color:#2563eb; }
  .summary-warn { font-size:11px; font-weight:600; color:#b45309; }
  .summary-conf-row { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
  .summary-confidence { font-size:11px; font-weight:700; border-radius:4px; padding:1px 7px; white-space:nowrap; }
  .summary-reason { font-size:11px; color:rgba(13,18,43,0.5); line-height:1.4; }
  .confidence-high   { background:#d1fae5; color:#065f46; }
  .confidence-medium { background:#fef3c7; color:#92400e; }
  .confidence-low    { background:#fef2f2; color:#991b1b; }
  .stage-pill { display:inline-block; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600; background:rgba(13,18,43,0.07); color:rgba(13,18,43,0.6); white-space:nowrap; max-width:100px; overflow:hidden; text-overflow:ellipsis; }
  .stage-pill.tw { background:#d1fae5; color:#065f46; }
  .stage-missing { font-size:11px; color:#dc2626; font-weight:600; }

  /* TW two-column split */
  .tw-board { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }
  .tw-col { display:flex; flex-direction:column; gap:0; }
  .tw-col-hd { display:flex; align-items:center; gap:8px; padding:10px 14px; border-radius:10px 10px 0 0; border:1px solid transparent; border-bottom:none; font-size:13px; font-weight:700; }
  .tw-col-hd-mis { background:#fef2f2; border-color:#fecaca; color:#dc2626; }
  .tw-col-hd-clean { background:#f0fdf4; border-color:#bbf7d0; color:#15803d; }
  .tw-col-hd .col-count { font-size:11px; font-weight:400; background:rgba(0,0,0,0.08); border-radius:20px; padding:1px 7px; color:inherit; }
  .tw-col-hd .col-icav { font-size:13px; font-weight:800; margin-left:auto; color:inherit; }
  .tw-col .col-cards { border-radius:0 0 10px 10px; }
  .tw-mis-reason { font-size:10px; color:#dc2626; margin-top:4px; font-style:italic; }
  .tw-empty { background:#f8f8fb; border:1px solid rgba(13,18,43,0.08); border-radius:0 0 10px 10px; padding:24px; text-align:center; font-size:12px; color:rgba(13,18,43,0.35); }

  /* Modal */
  .modal-backdrop { position:fixed; inset:0; background:rgba(13,18,43,0.45); z-index:300; backdrop-filter:blur(2px); }
  .modal { position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); width:720px; max-width:calc(100vw - 32px); max-height:calc(100vh - 80px); background:white; border-radius:14px; box-shadow:0 20px 60px rgba(13,18,43,0.25); z-index:301; display:flex; flex-direction:column; overflow:hidden; }
  .modal-hd { display:flex; justify-content:space-between; align-items:flex-start; padding:20px 22px 16px; border-bottom:1px solid rgba(13,18,43,0.08); flex-shrink:0; gap:12px; }
  .modal-hd-info { min-width:0; flex:1; }
  .modal-stage-row { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px; }
  .modal-stage { font-size:11px; font-weight:600; color:rgba(13,18,43,0.5); background:rgba(13,18,43,0.07); border-radius:4px; padding:2px 8px; }
  .modal-acct { font-size:17px; font-weight:800; color:#0d122b; letter-spacing:-0.02em; margin-bottom:2px; }
  .modal-opp { font-size:13px; color:rgba(13,18,43,0.5); margin-bottom:8px; }
  .modal-meta-row { display:flex; flex-wrap:wrap; gap:6px; align-items:center; font-size:12px; color:rgba(13,18,43,0.5); }
  .modal-icav { font-weight:700; color:#0d122b; }
  .modal-dot { color:rgba(13,18,43,0.25); }
  .modal-body { flex:1; overflow-y:auto; }
  .modal-close { width:32px; height:32px; border:1px solid rgba(13,18,43,0.15); border-radius:8px; background:white; color:rgba(13,18,43,0.45); font-size:16px; font-family:inherit; cursor:pointer; display:flex; align-items:center; justify-content:center; flex-shrink:0; line-height:1; }
  .modal-close:hover { background:#fef2f2; color:#f22f46; border-color:#fecaca; }

  /* Unassigned table */
  .tbl-wrap { background:white; border:1px solid rgba(13,18,43,0.1); border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(13,18,43,0.06); }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  thead tr { background:#f8f8fb; border-bottom:1px solid rgba(13,18,43,0.1); }
  th { padding:8px 12px; text-align:left; font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:rgba(13,18,43,0.4); white-space:nowrap; }
  .dr { border-bottom:1px solid rgba(13,18,43,0.05); }
  td { padding:9px 12px; color:#0d122b; vertical-align:middle; }
  .opp-acct-row { display:flex; align-items:center; gap:6px; }
  .opp-acct { font-weight:600; font-size:13px; }
  .opp-name { font-size:11px; color:rgba(13,18,43,0.45); margin-top:1px; }
  .small { font-size:12px; color:rgba(13,18,43,0.65); }
  .num { font-weight:700; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .dim { color:rgba(13,18,43,0.35); }
  .date { white-space:nowrap; color:rgba(13,18,43,0.5); font-size:12px; }

  .detail-panel { padding:16px 22px 24px; }
  .notes-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; }
  @media(max-width:600px) { .notes-grid { grid-template-columns:1fr; } }
  .mis-banner { background:#fef2f2; border:1px solid #fecaca; border-radius:6px; padding:9px 13px; font-size:13px; color:#0d122b; margin-bottom:10px; }
  .detail-meta { display:flex; flex-wrap:wrap; gap:16px; margin-bottom:12px; font-size:12px; color:rgba(13,18,43,0.6); align-items:center; }
  .detail-meta strong { color:#0d122b; margin-right:3px; }
  .sf-link { font-size:12px; color:#f22f46; text-decoration:none; margin-left:auto; }
  .sf-link:hover { text-decoration:underline; }

  .notes-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; }
  @media(max-width:900px) { .notes-grid { grid-template-columns:1fr 1fr; } }
  @media(max-width:600px) { .notes-grid { grid-template-columns:1fr; } }
  .notes-card { background:white; border:1px solid rgba(13,18,43,0.1); border-radius:8px; padding:12px 14px; }
  .notes-mgr { border-color:rgba(242,47,70,0.25); }
  .notes-hd { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.14em; color:rgba(13,18,43,0.4); margin-bottom:7px; }
  .notes-meta { font-weight:400; text-transform:none; letter-spacing:0; font-size:10px; }
  .notes-body { font-size:12px; color:#0d122b; line-height:1.6; white-space:pre-wrap; max-height:140px; overflow-y:auto; }
  .notes-empty { font-size:12px; color:rgba(13,18,43,0.35); font-style:italic; }
  .note-ta { width:100%; box-sizing:border-box; background:#f8f8fb; color:#0d122b; border:1px solid rgba(13,18,43,0.2); border-bottom:2px solid #f22f46; border-radius:6px; padding:8px 10px; font-size:12px; font-family:inherit; resize:vertical; outline:none; }
  .note-btns { display:flex; gap:8px; margin-top:8px; }
  .btn-save { padding:5px 14px; border:none; border-radius:5px; background:#f22f46; color:white; font-size:12px; font-weight:700; font-family:inherit; cursor:pointer; }
  .btn-save:disabled { opacity:0.5; cursor:default; }
  .btn-ghost { padding:5px 12px; border:1px solid rgba(13,18,43,0.2); border-radius:5px; background:white; color:rgba(13,18,43,0.6); font-size:12px; font-family:inherit; cursor:pointer; }
  .btn-edit { display:inline-block; margin-top:8px; padding:4px 10px; border:1px solid rgba(242,47,70,0.3); border-radius:5px; background:transparent; color:#f22f46; font-size:12px; font-weight:600; font-family:inherit; cursor:pointer; }
  .btn-edit:hover { background:#fef2f2; }
</style>
