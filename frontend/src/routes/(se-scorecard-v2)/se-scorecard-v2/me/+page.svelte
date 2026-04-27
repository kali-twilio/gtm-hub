<script lang="ts">
  import { onMount } from 'svelte';
  import { user, theme, sfTeam, sfPeriod, sfSubteam } from '$lib/stores';
  import { getSFSEs, getSFGong, getSFPeriods, fmt, fmtMrr } from '$lib/api';
  import { page } from '$app/stores';
  import { tc, fc } from '$lib/colors';

  interface Period { key: string; label: string; }

  let ses: any[] = $state([]);
  let periods: Period[] = $state([]);
  let selected = $state('');
  let se: any = $state(null);
  let sfInstanceUrl = $state('');
  let loading = $state(false);
  let showLoading = $state(false);
  let gongCalls = $state<number | null>(null);
  let gongLoading = $state(false);

  async function loadData(periodKey: string) {
    loading = true;
    gongCalls = null;
    const t = setTimeout(() => { if (loading) showLoading = true; }, 400);
    const data = await getSFSEs($sfTeam, periodKey, 0, $sfSubteam);
    clearTimeout(t);
    loading = false;
    showLoading = false;
    if (!data) return;
    sfInstanceUrl = data.sf_instance_url ?? '';
    ses = [...data.ses].sort((a, b) => a.name.localeCompare(b.name));
    // For restricted SEs the backend already filtered ses to just their row
    if (isOwnProfile() && ses.length === 1) {
      se = ses[0];
      selected = ses[0].name;
    } else {
      // Maintain selection across period switches; auto-select SE ICs on first load
      const target = selected || ($user?.sf_is_se ? ($user.sf_se_name ?? '') : '');
      const found = target ? ses.find(s => s.name === target) : null;
      se = found ?? null;
      // Keep selected populated so the "not found" error shows when SE has no data this period
      if (target) selected = target;
    }
    // Fetch Gong data separately after SF loads
    const seName = se?.name ?? selected;
    if (seName) {
      gongLoading = true;
      const g = await getSFGong($sfTeam, periodKey, 0, $sfSubteam);
      gongLoading = false;
      const row = g?.ses?.find((s: any) => s.name === seName);
      gongCalls = row?.gong_calls ?? null;
    }
  }

  function onPeriodChange(key: string) {
    sfPeriod.set(key);
    loadData(key);
  }

  function onSelect(e: Event) {
    selected = (e.target as HTMLSelectElement).value;
    se = ses.find(s => s.name === selected) ?? null;
    gongCalls = null;
    if (selected) {
      gongLoading = true;
      getSFGong($sfTeam, $sfPeriod, 0, $sfSubteam).then(g => {
        gongLoading = false;
        const row = g?.ses?.find((s: any) => s.name === selected);
        gongCalls = row?.gong_calls ?? null;
      });
    }
  }

  const isOwnProfile = () => ($user?.sf_is_se || $user?.sf_access === 'se_restricted') ?? false;

  let actSortKey = $state('icav');
  let actSortAsc = $state(false);
  let expSortKey = $state('icav');
  let expSortAsc = $state(false);

  function oppAccount(name: string): string {
    return (name.split(' - ')[0] ?? name).trim();
  }

  function sortOpps(opps: any[], key: string, asc: boolean, acctMap: Record<string, any> = {}): any[] {
    const getVal = (o: any): string | number => {
      if (key === 'account')   return oppAccount(o.name ?? '').toLowerCase();
      if (key === 'product')   return (o.product ?? '').toLowerCase();
      if (key === 'owner')     return (o.owner ?? '').toLowerCase();
      if (key === 'close_date') return o.close_date ?? '';
      if (key === 'arr')       return acctMap[o.name]?.arr ?? 0;
      if (key === 'mrr_delta') return acctMap[o.name]?.mrr_delta ?? 0;
      return o[key] ?? 0;
    };
    return [...opps].sort((a, b) => {
      const av = getVal(a), bv = getVal(b);
      if (typeof av === 'string') return asc ? av.localeCompare(bv as string) : (bv as string).localeCompare(av);
      return asc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
  }

  function setActSort(key: string) {
    if (key === actSortKey) actSortAsc = !actSortAsc;
    else { actSortKey = key; actSortAsc = false; }
  }

  function setExpSort(key: string) {
    if (key === expSortKey) expSortAsc = !expSortAsc;
    else { expSortKey = key; expSortAsc = false; }
  }

  onMount(async () => {
    periods = await getSFPeriods();
    const seName = $page.url.searchParams.get('se');
    if (seName) selected = seName;
    // Force restricted SEs onto their own team/subteam so the API call targets the right data
    if (isOwnProfile() && $user?.sf_team) {
      sfTeam.set($user.sf_team);
      sfSubteam.set($user.sf_subteam ?? 'none');
    }
    // Default to previous (most complete) quarter: second entry in the list, which is
    // the first non-current period. Only auto-select if viewing own profile so managers
    // retain whatever period they had selected.
    if (isOwnProfile() && periods.length > 1) {
      const prev = periods[1];
      sfPeriod.set(prev.key);
      await loadData(prev.key);
    } else {
      await loadData($sfPeriod);
    }
  });
</script>

<div class="w-full mx-auto px-4 py-8" style="max-width:min(100%,900px)">

  <div style="margin-bottom:20px">
    <div class="p5-badge" style="margin-bottom:8px">SE Scorecard · {periods.find(p => p.key === $sfPeriod)?.label ?? $sfPeriod}</div>
    <h1 style="font-size:32px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:2px 2px 0 var(--red)':''}">My Stats</h1>
    <div style="width:50px;height:3px;background:var(--red);{$theme==='p5'?'transform:skewX(-20deg);box-shadow:0 0 8px var(--red)':'border-radius:2px'};margin-top:8px"></div>
  </div>

  <!-- Period selector -->
  {#if periods.length > 0}
  <div style="margin-bottom:20px">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--text-muted);margin-bottom:8px">Period</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">
      {#each periods as p}
      <button onclick={() => onPeriodChange(p.key)} disabled={loading} class="p5-ctrl {$sfPeriod === p.key ? 'active' : ''}" style="opacity:{loading && $sfPeriod !== p.key ? '0.5' : '1'}">{p.label}</button>
      {/each}
    </div>
  </div>
  {/if}

  {#if showLoading}
  <div style="margin-bottom:20px">
    <div style="font-size:11px;color:var(--text-muted);font-weight:600;letter-spacing:0.06em;margin-bottom:8px">Loading period data…</div>
    <div style="height:4px;background:rgba(var(--red-rgb),0.12);border-radius:99px;overflow:hidden">
      <div style="height:100%;border-radius:99px;background:var(--red);animation:loadFill 10s linear forwards,shimmer 1.8s ease-in-out infinite"></div>
    </div>
  </div>
  {/if}

  {#if !isOwnProfile()}
  <div style="position:fixed;top:68px;left:16px;z-index:9999">
    <a href="/se-scorecard-v2" class="p5-back-btn">◀ Back</a>
  </div>
  {/if}

  {#if !isOwnProfile()}
  <div style="margin-bottom:24px">
    <div class="p5-badge" style="font-size:10px;margin-bottom:10px">{$theme==='p5'?'Select Operative':'Select SE'}</div>
    <div style="position:relative">
      <select onchange={onSelect} value={selected}>
        <option value="">— Choose —</option>
        {#each ses as s}
          <option value={s.name} selected={s.name === selected}>{s.name}</option>
        {/each}
      </select>
      <div style="position:absolute;right:14px;top:50%;transform:translateY(-50%);color:var(--red);font-size:12px;pointer-events:none">▼</div>
    </div>
  </div>
  {/if}

  <div style="transition:opacity 0.2s;opacity:{loading ? 0.4 : 1}">
  {#if se}
  {@const isAE = se.team_motion === 'ae'}
  {@const actLabel = isAE ? 'New Business' : 'Activate'}
  {@const expLabel = isAE ? 'Strategic' : 'Expansion'}
  {@const showAct = se.act_wins > 0 || se.act_icav > 0}
  {@const showExp = se.exp_wins > 0 || se.exp_icav > 0}
  {@const tm = se.team_medians ?? {}}
  {@const mrrDelta = se.exp_mrr_delta_total ?? 0}
  {@const mrrUp    = mrrDelta > 0}
  {@const mrrDown  = mrrDelta < 0}
  {@const mrrColor = mrrUp ? ($theme==='twilio'?'#178742':'#10B981') : mrrDown ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'}
  <div class="p5-panel" style="padding:24px;width:100%">

    <div style="margin-bottom:20px">
      <div style="font-size:24px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:2px 2px 0 rgba(232,0,61,0.5)':''}">{se.name}</div>
      {#if se.title}<div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-top:4px;letter-spacing:0.04em">{se.title}</div>{/if}
    </div>

    <div style="height:2px;background:linear-gradient(90deg,var(--red),transparent);{$theme==='p5'?'transform:skewX(-20deg);transform-origin:left':'border-radius:1px'};margin-bottom:20px"></div>

    <div style="display:grid;grid-template-columns:{se.exp_arr_total > 0 ? 'repeat(4, 1fr)' : showAct && showExp ? '1fr 1fr' : '1fr'};gap:8px;margin-bottom:20px">
      {#if showAct}
      <div style="background:rgba(var(--act-rgb),0.08);border:1px solid rgba(var(--act-rgb),0.2);border-left:4px solid var(--act-color);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--act-color);margin-bottom:8px">{actLabel}</div>
        <div style="font-size:26px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--act-glow);line-height:1">{fmt(se.act_icav)}</div>
        {#if tm.act_icav}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px;margin-bottom:8px">{fmt(tm.act_icav)}</div>{:else}<div style="margin-bottom:8px"></div>{/if}
        <div style="border-top:1px solid rgba(var(--act-rgb),0.15);padding-top:8px">
          <div style="font-size:12px;color:var(--text-muted)">{se.act_wins} wins · Med {fmt(se.act_median)}</div>
          {#if tm.act_wins != null}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px">{tm.act_wins} wins · {fmt(tm.act_median)}</div>{/if}
        </div>
      </div>
      {/if}
      {#if showExp}
      <div style="background:rgba(var(--exp-rgb),0.08);border:1px solid rgba(var(--exp-rgb),0.2);border-left:4px solid var(--exp-color);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-color);margin-bottom:8px">{#if se.exp_arr_total > 0}{expLabel} <span style="text-transform:none">iACV</span>{:else if !isAE}{expLabel} · {se.exp_status ?? (se.exp_growing ? 'Growing' : 'Retaining')}{:else}{expLabel}{/if}</div>
        <div style="font-size:26px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-glow);line-height:1">{fmt(se.exp_icav)}</div>
        {#if tm.exp_icav}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px;margin-bottom:8px">{fmt(tm.exp_icav)}</div>{:else}<div style="margin-bottom:8px"></div>{/if}
        <div style="border-top:1px solid rgba(var(--exp-rgb),0.15);padding-top:8px">
          <div style="font-size:12px;color:var(--text-muted)">{se.exp_wins} wins · Med {fmt(se.exp_median)}</div>
          {#if tm.exp_wins != null}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px">{tm.exp_wins} wins · {fmt(tm.exp_median)}</div>{/if}
        </div>
      </div>
      {/if}

      {#if se.exp_arr_total > 0}
      <div style="background:rgba(var(--exp-rgb),0.08);border:1px solid rgba(var(--exp-rgb),0.2);border-left:4px solid var(--exp-color);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-color);margin-bottom:8px">Acct ARR</div>
        <div style="font-size:26px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-glow);line-height:1">{fmt(se.exp_arr_total)}</div>
        {#if tm.exp_arr_total}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px;margin-bottom:8px">{fmt(tm.exp_arr_total)}</div>{:else}<div style="margin-bottom:8px"></div>{/if}
        <div style="border-top:1px solid rgba(var(--exp-rgb),0.15);padding-top:8px">
          <div style="font-size:12px;color:var(--text-muted)">{se.exp_account_detail?.length ?? 0} accts</div>
        </div>
      </div>
      <div style="background:rgba(var(--exp-rgb),0.08);border:1px solid rgba(var(--exp-rgb),0.2);border-left:4px solid var(--exp-color);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-color);margin-bottom:8px">Qtr MRR Δ</div>
        <div style="font-size:26px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:{mrrColor};line-height:1">{mrrUp ? '+' : ''}{fmtMrr(mrrDelta)}<span style="font-size:13px;font-weight:700;opacity:0.7">/mo</span></div>
        {#if tm.exp_mrr_delta_total}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px;margin-bottom:8px">{tm.exp_mrr_delta_total > 0 ? '+' : ''}{fmtMrr(tm.exp_mrr_delta_total)}/mo</div>{:else}<div style="margin-bottom:8px"></div>{/if}
        <div style="border-top:1px solid rgba(var(--exp-rgb),0.15);padding-top:8px">
          <div style="font-size:12px;color:var(--text-muted)">{se.exp_mrr_pct_avg > 0 ? '+' : ''}{se.exp_mrr_pct_avg}% vs prior qtr</div>
          {#if tm.exp_mrr_pct_avg}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px">{tm.exp_mrr_pct_avg > 0 ? '+' : ''}{tm.exp_mrr_pct_avg}%</div>{/if}
        </div>
      </div>
      {/if}
    </div>

    {#if gongCalls !== null || gongLoading || se.largest_deal_value > 0}
    <div style="display:grid;grid-template-columns:{(gongCalls !== null || gongLoading) && se.largest_deal_value > 0 ? '1fr 2fr' : '1fr'};gap:8px;margin-bottom:20px">
      {#if gongCalls !== null || gongLoading}
      <div style="background:rgba(var(--red-rgb),0.04);border:1px solid rgba(var(--red-rgb),0.15);border-left:4px solid var(--red);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;color:var(--text-muted);margin-bottom:6px">Gong Calls</div>
        {#if gongLoading}
        <div style="font-size:26px;font-weight:900;color:var(--text-faint);line-height:1;animation:pulse 1.2s ease-in-out infinite">…</div>
        {:else}
        <div style="font-size:26px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text);line-height:1">{gongCalls}</div>
        {/if}
      </div>
      {/if}
      {#if se.largest_deal_value > 0}
      <div style="background:rgba(var(--red-rgb),0.04);border:1px solid rgba(var(--red-rgb),0.15);border-left:4px solid var(--red);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text-muted)">{$theme==='p5'?'◆ ':''}Largest Deal</div>
          {#if se.largest_deal_motion}<span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;border-radius:4px;background:{se.largest_deal_motion==='Activate'||se.largest_deal_motion==='New Business'?'rgba(var(--act-rgb),0.1)':'rgba(var(--exp-rgb),0.1)'};color:{se.largest_deal_motion==='Activate'||se.largest_deal_motion==='New Business'?'var(--act-color)':'var(--exp-color)'}">{se.largest_deal_motion}</span>{/if}
        </div>
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
          <div style="font-size:14px;color:var(--text);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{se.largest_deal}</div>
          <div style="font-size:16px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:{$theme==='p5'?'var(--yellow)':'#B45309'};white-space:nowrap">{fmt(se.largest_deal_value)}</div>
        </div>
        {#if se.largest_deal_dsr}<div style="font-size:11px;color:var(--text-muted);margin-top:4px">AE: {se.largest_deal_dsr}</div>{/if}
      </div>
      {/if}
    </div>
    {/if}

    {#if se.flags?.length}
    <div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <div class="p5-badge" style="font-size:10px">Analysis</div>
        <div style="flex:1;height:1px;background:rgba(var(--red-rgb),0.15)"></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px">
        {#each se.flags as item}
        {@const itemColor =
          item.cat === 'REVENUE'    ? ($theme==='twilio' ? '#006EFF' : '#3B82F6') :
          item.cat === 'EXPANSION'  ? ($theme==='twilio' ? '#178742' : '#10B981') :
          item.cat === 'PIPELINE'   ? ($theme==='twilio' ? '#7C3AED' : '#A78BFA') :
          item.cat === 'EFFICIENCY' ? ($theme==='twilio' ? '#B45309' : '#FFB800') :
          item.cat === 'HYGIENE'    ? ($theme==='twilio' ? '#0891B2' : '#22D3EE') :
          item.cat === 'COACHING'   ? ($theme==='twilio' ? '#DC2626' : '#EF4444') :
          item.cat === 'RISK'       ? ($theme==='twilio' ? '#DC2626' : '#EF4444') :
          item.cat === 'STRENGTH'   ? ($theme==='twilio' ? '#178742' : '#10B981') :
          item.cat === 'NOTES'      ? ($theme==='twilio' ? '#0891B2' : '#22D3EE') :
          fc(item.cat, $theme)}
        <div style="border-left:4px solid {itemColor};background:rgba(var(--red-rgb),0.02);padding:10px 14px;{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:{itemColor};flex-shrink:0">{item.cat}</span>
            <span style="font-size:12px;font-weight:700;color:var(--text)">{item.title}</span>
          </div>
          <p style="font-size:12px;color:var(--text-muted);line-height:1.6;margin:0">{item.body}</p>
        </div>
        {/each}
      </div>
    </div>
    {/if}

  </div>

  <!-- TW Closed Won opp detail tables -->
  {#if se.tw_opps_detail?.length}
  {@const rawActOpps = se.tw_opps_detail.filter((o: any) => isAE ? o.motion === 'nb' : o.motion === 'act')}
  {@const rawExpOpps = se.tw_opps_detail.filter((o: any) => isAE ? o.motion === 'strat' : o.motion === 'exp')}
  {@const expAcctMap = Object.fromEntries((se.exp_account_detail ?? []).map((a: any) => [a.opp_name, a]))}
  {@const actOpps = sortOpps(rawActOpps, actSortKey, actSortAsc)}
  {@const expOpps = sortOpps(rawExpOpps, expSortKey, expSortAsc, expAcctMap)}
  {@const expGrouped = (() => {
    const map = new Map<string, any[]>();
    for (const opp of expOpps) {
      const a = oppAccount(opp.name);
      if (!map.has(a)) map.set(a, []);
      map.get(a)!.push(opp);
    }
    return [...map.entries()].map(([acct, opps]) => ({
      acct,
      opps,
      acctData: opps.map((o: any) => expAcctMap[o.name]).find((a: any) => a != null) ?? null,
    }));
  })()}

  <!-- New Business / Activate table -->
  {#if actOpps.length > 0}
  <div class="p5-panel" style="width:100%;margin-top:14px">
    <div style="padding:14px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px">
      <div class="p5-badge" style="font-size:9px;padding:2px 8px;background:rgba(var(--act-rgb),0.12);color:var(--act-color)">{actLabel} · TW Closed Won</div>
      <span style="font-size:10px;font-weight:700;color:var(--text-muted)">{actOpps.length} opp{actOpps.length !== 1 ? 's' : ''}</span>
    </div>
    <div style="padding:0 20px 14px">
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:11px">
          <thead>
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.1)">
              {#each [
                {key:'account',    label:'Account',  align:'left',  pad:'4px 8px 6px 0'},
                {key:'product',    label:'Product',  align:'left',  pad:'4px 8px 6px'},
                {key:'owner',      label:'AE',       align:'left',  pad:'4px 8px 6px'},
                {key:'close_date', label:'Date',     align:'right', pad:'4px 8px 6px'},
                {key:'icav',       label:'iACV',     align:'right', pad:'4px 8px 6px'},
                {key:'has_notes',  label:'Notes',    align:'right', pad:'4px 0 6px 8px'},
              ] as col}
              <th onclick={() => setActSort(col.key)}
                style="text-align:{col.align};padding:{col.pad};font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:{actSortKey===col.key?'var(--red)':'var(--text-muted)'};white-space:nowrap;cursor:pointer;user-select:none">
                {col.label}{actSortKey===col.key ? (actSortAsc ? ' ▲' : ' ▼') : ''}
              </th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each actOpps as opp, i}
            {@const notesOk = opp.has_notes && opp.has_history}
            {@const notesPartial = opp.has_notes || opp.has_history}
            {@const notesColor = notesOk ? ($theme==='twilio'?'#178742':'#10B981') : notesPartial ? ($theme==='twilio'?'#B45309':'#FFB800') : ($theme==='twilio'?'#DC2626':'#EF4444')}
            {@const sfOppUrl = opp.id && sfInstanceUrl ? `${sfInstanceUrl}/${opp.id}` : null}
            <tr style="border-bottom:{i < actOpps.length-1 ? '1px solid rgba(var(--red-rgb),0.05)' : 'none'}">
              <td style="padding:5px 8px 5px 0;color:var(--text);font-weight:600;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title={oppAccount(opp.name)}>
                {#if sfOppUrl}<a href={sfOppUrl} target="_blank" rel="noopener noreferrer" style="color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{oppAccount(opp.name)}</a>
                {:else}{oppAccount(opp.name)}{/if}
              </td>
              <td style="padding:5px 8px;color:var(--text-muted);white-space:nowrap">{opp.product || '—'}</td>
              <td style="padding:5px 8px;color:var(--text-muted);white-space:nowrap">{opp.owner}</td>
              <td style="padding:5px 8px;color:var(--text-muted);text-align:right;white-space:nowrap">{opp.close_date}</td>
              <td style="padding:5px 8px;font-weight:700;color:var(--act-color);text-align:right;white-space:nowrap">{fmt(opp.icav)}</td>
              <td style="padding:5px 0 5px 8px;text-align:right;white-space:nowrap">
                <span style="color:{notesColor};font-weight:700">{notesOk ? '✓' : notesPartial ? '△' : '✗'}</span>
                {#if opp.note_entries > 0}<span style="color:var(--text-muted);margin-left:3px;font-size:10px">{opp.note_entries}</span>{/if}
              </td>
            </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  </div>
  {/if}

  <!-- Strategic / Expansion table -->
  {#if expOpps.length > 0}
  <div class="p5-panel" style="width:100%;margin-top:14px">
    <div style="padding:14px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px">
      <div class="p5-badge" style="font-size:9px;padding:2px 8px;background:rgba(var(--exp-rgb),0.12);color:var(--exp-color)">{expLabel} · TW Closed Won</div>
      <span style="font-size:10px;font-weight:700;color:var(--text-muted)">{expOpps.length} opp{expOpps.length !== 1 ? 's' : ''}</span>
    </div>
    <div style="padding:0 24px 20px">
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead>
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.12)">
            {#each [
              {key:'account',    label:'Account',       align:'left',  pad:'6px 8px 8px 0'},
              {key:'product',    label:'Product',       align:'left',  pad:'6px 8px 8px'},
              {key:'owner',      label:'AE',            align:'left',  pad:'6px 8px 8px'},
              {key:'icav',       label:'iACV',          align:'right', pad:'6px 8px 8px'},
              {key:'arr',        label:'Acct ARR',      align:'right', pad:'6px 8px 8px'},
              {key:'mrr_delta',  label:'Qtr MRR Δ',    align:'right', pad:'6px 8px 8px'},
              {key:'has_notes',  label:'Notes',         align:'right', pad:'6px 0 8px 8px'},
            ] as col}
            <th onclick={() => setExpSort(col.key)}
              style="text-align:{col.align};padding:{col.pad};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:{expSortKey===col.key?'var(--red)':'var(--text-muted)'};white-space:nowrap;cursor:pointer;user-select:none">
              {col.label}{expSortKey===col.key ? (expSortAsc ? ' ▲' : ' ▼') : ''}
            </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each expGrouped as group, gi}
          {@const isMulti = group.opps.length > 1}
          {#each group.opps as opp, oi}
          {@const isFirst = oi === 0}
          {@const isLastRow = oi === group.opps.length - 1}
          {@const isLastGroup = gi === expGrouped.length - 1}
          {@const notesOk = opp.has_notes && opp.has_history}
          {@const notesPartial = opp.has_notes || opp.has_history}
          {@const notesColor = notesOk ? ($theme==='twilio'?'#178742':'#10B981') : notesPartial ? ($theme==='twilio'?'#B45309':'#FFB800') : ($theme==='twilio'?'#DC2626':'#EF4444')}
          {@const trendUp = isFirst && (group.acctData?.mrr_delta ?? 0) > 0}
          {@const trendDown = isFirst && (group.acctData?.mrr_delta ?? 0) < 0}
          {@const trendColor = trendUp ? ($theme==='twilio'?'#178742':'#10B981') : trendDown ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'}
          {@const mrrPct = group.acctData?.mrr_pct ?? 0}
          {@const sfExpOppUrl = opp.id && sfInstanceUrl ? `${sfInstanceUrl}/${opp.id}` : null}
          <tr style="border-bottom:{isLastRow && isLastGroup ? 'none' : isLastRow ? '1px solid rgba(var(--red-rgb),0.1)' : '1px solid rgba(var(--exp-rgb),0.06)'};{isMulti ? `background:rgba(var(--exp-rgb),0.02)` : ''}">
            <td style="padding:8px 8px 8px 0;color:var(--text);font-weight:{isFirst?'600':'400'};max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title={group.acct}>
              {#if isFirst}
                {#if sfExpOppUrl}<a href={sfExpOppUrl} target="_blank" rel="noopener noreferrer" style="color:var(--text);text-decoration:none;border-bottom:1px solid rgba(var(--red-rgb),0.25)" onmouseenter={e => (e.currentTarget as HTMLElement).style.borderBottomColor='var(--red)'} onmouseleave={e => (e.currentTarget as HTMLElement).style.borderBottomColor='rgba(var(--red-rgb),0.25)'}>{group.acct}</a>
                {:else}{group.acct}{/if}
              {:else}<span style="padding-left:12px;color:var(--text-faint)">↳</span>{/if}
            </td>
            <td style="padding:8px;color:var(--text-muted);white-space:nowrap;vertical-align:top">{opp.product || '—'}</td>
            <td style="padding:8px;color:var(--text-muted);white-space:nowrap;vertical-align:top">{opp.owner}</td>
            <td style="padding:8px;font-weight:700;color:{opp.icav > 0 ? 'var(--exp-color)' : 'var(--text-muted)'};text-align:right;white-space:nowrap;vertical-align:top">{opp.icav > 0 ? fmt(opp.icav) : '$0'}</td>
            <td style="padding:8px;text-align:right;white-space:nowrap;vertical-align:top">
              {#if isFirst}
                {#if group.acctData?.arr > 0}<span style="font-weight:700;color:{$theme==='twilio'?'#178742':'#10B981'}">{fmt(group.acctData.arr)}</span>{:else}<span style="color:var(--text-faint)">—</span>{/if}
              {/if}
            </td>
            <td style="padding:8px;text-align:right;white-space:nowrap;vertical-align:top">
              {#if isFirst}
                {#if group.acctData}
                  {#if group.acctData.mrr_delta !== 0}
                  <span style="font-weight:700;color:{trendColor}">{trendUp ? '↑' : '↓'} {fmtMrr(Math.abs(group.acctData.mrr_delta))}/mo{#if mrrPct !== 0} <span style="font-size:10px;font-weight:600">({mrrPct > 0 ? '+' : ''}{mrrPct}%)</span>{/if}</span>
                  {:else}<span style="color:var(--text-faint)">→ flat</span>{/if}
                {:else}<span style="color:var(--text-faint)">—</span>{/if}
              {/if}
            </td>
            <td style="padding:8px 0 8px 8px;text-align:right;white-space:nowrap;vertical-align:top">
              <span style="color:{notesColor};font-weight:700">{notesOk ? '✓' : notesPartial ? '△' : '✗'}</span>
              {#if opp.note_entries > 0}<span style="color:var(--text-muted);margin-left:4px">{opp.note_entries}</span>{/if}
            </td>
          </tr>
          {/each}
          {/each}
        </tbody>
        </table>
      </div>
    </div>
  </div>
  {/if}

  {/if}
  {:else if selected}
  <div style="background:rgba(var(--red-rgb),0.08);border:1px solid rgba(var(--red-rgb),0.4);border-left:4px solid var(--red);padding:14px 18px;font-size:14px;color:var(--red);font-weight:700">
    ⚠ "{selected}" not found in report data.
  </div>
  {/if}
  </div><!-- end opacity wrapper -->

</div>

<style>
@keyframes loadFill {
  0%   { width: 0%  }
  12%  { width: 38% }
  30%  { width: 58% }
  52%  { width: 72% }
  70%  { width: 80% }
  85%  { width: 85% }
  100% { width: 88% }
}
@keyframes shimmer {
  0%   { filter: brightness(1)   }
  50%  { filter: brightness(1.3) }
  100% { filter: brightness(1)   }
}
@keyframes pulse {
  0%, 100% { opacity: 0.3; }
  50%       { opacity: 0.7; }
}
</style>
