<script lang="ts">
  import { onMount } from 'svelte';
  import { user, theme, sfTeam, sfPeriod } from '$lib/stores';
  import { getSFSEs, getSFPeriods, fmt } from '$lib/api';
  import { tc, fc } from '$lib/colors';

  interface Period { key: string; label: string; }

  let ses: any[] = $state([]);
  let periods: Period[] = $state([]);
  let selected = $state('');
  let se: any = $state(null);
  let loading = $state(false);
  let showLoading = $state(false);

  async function loadData(periodKey: string) {
    loading = true;
    const t = setTimeout(() => { if (loading) showLoading = true; }, 400);
    const data = await getSFSEs($sfTeam, periodKey);
    clearTimeout(t);
    loading = false;
    showLoading = false;
    if (!data) return;
    ses = [...data].sort((a, b) => a.name.localeCompare(b.name));
    // Maintain selection across period switches; auto-select SE ICs on first load
    const target = selected || ($user?.sf_is_se ? ($user.sf_se_name ?? '') : '');
    const found = target ? ses.find(s => s.name === target) : null;
    se = found ?? null;
    if (found) selected = target;
  }

  function onPeriodChange(key: string) {
    sfPeriod.set(key);
    loadData(key);
  }

  function onSelect(e: Event) {
    selected = (e.target as HTMLSelectElement).value;
    se = ses.find(s => s.name === selected) ?? null;
  }

  const isOwnProfile = () => $user?.sf_is_se ?? false;

  onMount(async () => {
    periods = await getSFPeriods();
    await loadData($sfPeriod);
  });
</script>

<div class="w-full mx-auto px-4 py-8" style="max-width:min(100%,900px)">

  <div style="margin-bottom:20px">
    <div class="p5-badge" style="margin-bottom:8px">SE Scorecard V2 · {periods.find(p => p.key === $sfPeriod)?.label ?? $sfPeriod}</div>
    <h1 style="font-size:32px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:2px 2px 0 var(--red)':''}">My Stats</h1>
    <div style="width:50px;height:3px;background:var(--red);{$theme==='p5'?'transform:skewX(-20deg);box-shadow:0 0 8px var(--red)':'border-radius:2px'};margin-top:8px"></div>
  </div>

  <!-- Period selector -->
  {#if periods.length > 0}
  <div style="margin-bottom:20px">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--text-muted);margin-bottom:8px">Period</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">
      {#each periods as p}
      <button
        onclick={() => onPeriodChange(p.key)}
        disabled={loading}
        style="padding:6px 14px;font-size:12px;font-weight:700;border-radius:6px;border:1px solid {$sfPeriod === p.key ? 'var(--red)' : 'rgba(var(--red-rgb),0.2)'};background:{$sfPeriod === p.key ? 'rgba(var(--red-rgb),0.12)' : 'transparent'};color:{$sfPeriod === p.key ? 'var(--red)' : 'var(--text-muted)'};cursor:{loading ? 'default' : 'pointer'};opacity:{loading && $sfPeriod !== p.key ? '0.5' : '1'};transition:all 0.15s;letter-spacing:0.04em"
      >{p.label}</button>
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
  <div class="p5-panel" style="padding:24px;width:100%">

    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px">
      <div>
        <div style="font-size:24px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:2px 2px 0 rgba(232,0,61,0.5)':''}">{se.name}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:36px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};line-height:1;color:var(--text);{$theme==='p5'?'text-shadow:3px 3px 0 var(--red)':''}">{fmt(se.total_icav)}</div>
        <div style="font-size:10px;color:var(--text-muted);letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin-top:2px">Total iACV</div>
      </div>
    </div>

    <div style="height:2px;background:linear-gradient(90deg,var(--red),transparent);{$theme==='p5'?'transform:skewX(-20deg);transform-origin:left':'border-radius:1px'};margin-bottom:20px"></div>

    <div style="display:grid;grid-template-columns:{showAct && showExp ? '1fr 1fr' : '1fr'};gap:8px;margin-bottom:20px">
      {#if showAct}
      {@const tm = se.team_medians ?? {}}
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
      {@const tm = se.team_medians ?? {}}
      <div style="background:rgba(var(--exp-rgb),0.08);border:1px solid rgba(var(--exp-rgb),0.2);border-left:4px solid var(--exp-color);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-color);margin-bottom:8px">{expLabel}{#if !isAE} · {se.exp_status ?? (se.exp_growing ? 'Growing' : 'Retaining')}{/if}</div>
        <div style="font-size:26px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-glow);line-height:1">{fmt(se.exp_icav)}</div>
        {#if tm.exp_icav}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px;margin-bottom:8px">{fmt(tm.exp_icav)}</div>{:else}<div style="margin-bottom:8px"></div>{/if}
        <div style="border-top:1px solid rgba(var(--exp-rgb),0.15);padding-top:8px">
          <div style="font-size:12px;color:var(--text-muted)">{se.exp_wins} wins · Med {fmt(se.exp_median)}</div>
          {#if tm.exp_wins != null}<div style="font-size:10px;color:var(--text-muted);opacity:0.55;margin-top:2px">{tm.exp_wins} wins · {fmt(tm.exp_median)}</div>{/if}
        </div>
      </div>
      {/if}
    </div>

    {#if se.largest_deal_value > 0}
    <div style="background:rgba(var(--red-rgb),0.04);border:1px solid rgba(var(--red-rgb),0.15);border-left:4px solid var(--red);padding:14px 16px;margin-bottom:20px;{$theme==='twilio'?'border-radius:8px':''}">
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

    {#if se.flags?.length}
    <div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <div class="p5-badge" style="font-size:10px">{$theme==='p5'?'Intel Report':'Performance Flags'}</div>
        <div style="flex:1;height:1px;background:rgba(var(--red-rgb),0.15)"></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        {#each se.flags as [cat, msg]}
        {@const color = fc(cat, $theme)}
        <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 14px;border-left:4px solid {color};background:rgba(var(--red-rgb),0.03);{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
          <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;font-style:{$theme==='p5'?'italic':'normal'};color:{color};width:72px;flex-shrink:0">{cat}</span>
          <span style="font-size:13px;font-weight:500;color:var(--text-muted)">{msg}</span>
        </div>
        {/each}
      </div>
    </div>
    {/if}

  </div>

  <!-- TW Closed Won opp detail tables -->
  {#if se.tw_opps_detail?.length}
  {@const actOpps = se.tw_opps_detail.filter((o: any) => isAE ? o.motion === 'nb' : o.motion === 'act')}
  {@const expOpps = se.tw_opps_detail.filter((o: any) => isAE ? o.motion === 'strat' : o.motion === 'exp')}

  <!-- Activate: compact table -->
  {#if actOpps.length > 0}
  <div class="p5-panel" style="padding:14px 20px;width:100%;margin-top:14px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <div class="p5-badge" style="font-size:9px;padding:2px 8px;background:rgba(var(--act-rgb),0.12);color:var(--act-color);border-color:rgba(var(--act-rgb),0.3)">{actLabel} · TW Closed Won</div>
      <div style="flex:1;height:1px;background:rgba(var(--act-rgb),0.15)"></div>
      <span style="font-size:10px;font-weight:700;color:var(--act-color)">{actOpps.length} opp{actOpps.length !== 1 ? 's' : ''}</span>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:11px">
        <thead>
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.1)">
            <th style="text-align:left;padding:4px 8px 6px 0;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">Opportunity</th>
            <th style="text-align:left;padding:4px 8px 6px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">AE</th>
            <th style="text-align:right;padding:4px 8px 6px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">Date</th>
            <th style="text-align:right;padding:4px 8px 6px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">iACV</th>
            <th style="text-align:right;padding:4px 0 6px 8px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">Notes</th>
          </tr>
        </thead>
        <tbody>
          {#each actOpps as opp, i}
          {@const notesOk = opp.has_notes && opp.has_history}
          {@const notesPartial = opp.has_notes || opp.has_history}
          {@const notesColor = notesOk ? ($theme==='twilio'?'#178742':'#10B981') : notesPartial ? ($theme==='twilio'?'#B45309':'#FFB800') : ($theme==='twilio'?'#DC2626':'#EF4444')}
          <tr style="border-bottom:{i < actOpps.length-1 ? '1px solid rgba(var(--red-rgb),0.05)' : 'none'}">
            <td style="padding:5px 8px 5px 0;color:var(--text);font-weight:600;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title={opp.name}>{opp.name}</td>
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
  {/if}

  <!-- Expansion: opps + account revenue combined -->
  {#if expOpps.length > 0}
  {@const acctMap = Object.fromEntries((se.exp_account_detail ?? []).map((a: any) => [a.opp_name, a]))}
  <div class="p5-panel" style="padding:20px 24px;width:100%;margin-top:14px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <div class="p5-badge" style="font-size:10px;background:rgba(var(--exp-rgb),0.12);color:var(--exp-color);border-color:rgba(var(--exp-rgb),0.3)">{expLabel} · TW Closed Won</div>
      <div style="flex:1;height:1px;background:rgba(var(--exp-rgb),0.2)"></div>
      <span style="font-size:11px;font-weight:700;color:var(--exp-color)">{expOpps.length} opp{expOpps.length !== 1 ? 's' : ''}</span>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead>
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.12)">
            <th style="text-align:left;padding:6px 8px 8px 0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">Opportunity · Account</th>
            <th style="text-align:left;padding:6px 8px 8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">AE</th>
            <th style="text-align:right;padding:6px 8px 8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">iACV</th>
            <th style="text-align:right;padding:6px 8px 8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">Acct ARR</th>
            <th style="text-align:right;padding:6px 8px 8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">Quarter MRR Δ</th>
            <th style="text-align:right;padding:6px 0 8px 8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);white-space:nowrap">Notes</th>
          </tr>
        </thead>
        <tbody>
          {#each expOpps as opp, i}
          {@const acct = acctMap[opp.name] ?? null}
          {@const notesOk = opp.has_notes && opp.has_history}
          {@const notesPartial = opp.has_notes || opp.has_history}
          {@const notesColor = notesOk ? ($theme==='twilio'?'#178742':'#10B981') : notesPartial ? ($theme==='twilio'?'#B45309':'#FFB800') : ($theme==='twilio'?'#DC2626':'#EF4444')}
          {@const trendUp = acct?.mrr_delta > 0}
          {@const trendDown = acct?.mrr_delta < 0}
          {@const trendColor = trendUp ? ($theme==='twilio'?'#178742':'#10B981') : trendDown ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text-muted)'}
          {@const mrrPct = acct?.mrr_pct ?? 0}
          <tr style="border-bottom:{i < expOpps.length-1 ? '1px solid rgba(var(--red-rgb),0.06)' : 'none'}">
            <td style="padding:8px 8px 8px 0;max-width:240px">
              <div style="color:var(--text);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title={opp.name}>{opp.name}</div>
              {#if acct?.acct_name && acct.acct_name !== opp.name}
              <div style="font-size:10px;color:var(--text-muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{acct.acct_name}</div>
              {/if}
            </td>
            <td style="padding:8px;color:var(--text-muted);white-space:nowrap;vertical-align:top">{opp.owner}</td>
            <td style="padding:8px;font-weight:700;color:{opp.icav > 0 ? 'var(--exp-color)' : 'var(--text-muted)'};text-align:right;white-space:nowrap;vertical-align:top">{opp.icav > 0 ? fmt(opp.icav) : '$0'}</td>
            <td style="padding:8px;text-align:right;white-space:nowrap;vertical-align:top">
              {#if acct?.arr > 0}<span style="font-weight:700;color:{$theme==='twilio'?'#178742':'#10B981'}">{fmt(acct.arr)}</span>{:else}<span style="color:var(--text-faint)">—</span>{/if}
            </td>
            <td style="padding:8px;text-align:right;white-space:nowrap;vertical-align:top">
              {#if acct}
                {#if acct.mrr_delta !== 0}
                <span style="font-weight:700;color:{trendColor}">{trendUp ? '↑' : '↓'} {fmt(Math.abs(acct.mrr_delta))}/mo{#if mrrPct !== 0} <span style="font-size:10px;font-weight:600">({mrrPct > 0 ? '+' : ''}{mrrPct}%)</span>{/if}</span>
                {:else}
                <span style="color:var(--text-faint)">→ flat{#if mrrPct === 0} (0%){/if}</span>
                {/if}
              {:else}<span style="color:var(--text-faint)">—</span>{/if}
            </td>
            <td style="padding:8px 0 8px 8px;text-align:right;white-space:nowrap;vertical-align:top">
              <span style="color:{notesColor};font-weight:700">{notesOk ? '✓' : notesPartial ? '△' : '✗'}</span>
              {#if opp.note_entries > 0}<span style="color:var(--text-muted);margin-left:4px">{opp.note_entries}</span>{/if}
            </td>
          </tr>
          {/each}
        </tbody>
      </table>
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
</style>
