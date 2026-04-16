<script lang="ts">
  import { onMount } from 'svelte';
  import { getSFForecast, fmt } from '$lib/api';
  import { theme, sfTeam, sfSubteam, user, authReady } from '$lib/stores';
  import { goto } from '$app/navigation';

  let data: any = $state(null);
  let loading = $state(false);
  let showLoading = $state(false);
  let error = $state('');
  // key of expanded quarter panel (for pipeline drill-down)
  let expandedQ = $state<string | null>(null);
  // within an expanded quarter, which SE row is drilled in
  let expandedSe = $state<string | null>(null);

  const p5 = $derived($theme === 'p5');
  const restricted = $derived($user?.sf_access === 'se_restricted');

  $effect(() => {
    if ($authReady && restricted) goto('/se-scorecard-v2/me');
  });

  async function load(team: string, subteam: string) {
    loading = true;
    error = '';
    data = null;
    expandedQ = null;
    expandedSe = null;
    const t = setTimeout(() => { if (loading) showLoading = true; }, 400);
    const res = await getSFForecast(team, subteam === 'none' ? '' : subteam);
    clearTimeout(t);
    showLoading = false;
    loading = false;
    if (res) {
      data = res;
    } else {
      error = 'Failed to load forecast data.';
    }
  }

  onMount(() => {
    load($sfTeam, $sfSubteam);
  });

  function toggleQ(key: string) {
    expandedQ = expandedQ === key ? null : key;
    expandedSe = null;
  }

  function toggleSe(se: string) {
    expandedSe = expandedSe === se ? null : se;
  }

  // Total pipeline iACV across all future quarters
  const totalPipeIcav = $derived(
    data ? data.quarters.reduce((s: number, q: any) => s + q.pipe.total_icav, 0) : 0
  );
  const totalPipeTwIcav = $derived(
    data ? data.quarters.reduce((s: number, q: any) => s + q.pipe.tw_icav, 0) : 0
  );
  const totalPipeCount = $derived(
    data ? data.quarters.reduce((s: number, q: any) => s + q.pipe.count, 0) : 0
  );

  // Bar width helper — % of max iACV
  function barWidth(val: number, max: number): number {
    return max > 0 ? Math.round((val / max) * 100) : 0;
  }

  const maxPipeIcav = $derived(
    data ? Math.max(...data.quarters.map((q: any) => q.pipe.total_icav), 1) : 1
  );
  const maxClosedIcav = $derived(
    data ? Math.max(...data.quarters.map((q: any) => q.closed.total_icav), 1) : 1
  );
  const combinedMax = $derived(Math.max(maxPipeIcav, maxClosedIcav, 1));
</script>

<div style="min-height:100vh;padding:24px 16px 48px">
  <div class="fc-container">

    <!-- Page title -->
    <div style="margin-bottom:20px">
      <h1 style="font-size:32px;font-weight:800;color:var(--text);letter-spacing:-0.02em;margin:0">
        Pipeline Forecast
      </h1>
      <div style="width:36px;height:3px;background:var(--red);border-radius:2px;margin:8px 0 0"></div>
      {#if data}
      <div style="font-size:12px;color:var(--text-muted);font-weight:600;margin-top:6px">
        {data.team_label} · open pipeline vs. closed won by quarter
      </div>
      {/if}
    </div>

    <!-- Loading -->
    {#if showLoading}
    <div class="p5-panel" style="padding:28px;text-align:center;margin-bottom:16px">
      <div style="font-size:13px;color:var(--text-muted);font-weight:600;letter-spacing:0.05em">Pulling live Salesforce pipeline…</div>
      <div style="margin-top:12px;height:4px;background:rgba(var(--red-rgb),0.12);border-radius:99px;overflow:hidden">
        <div style="height:100%;border-radius:99px;background:var(--red);animation:loadFill 10s linear forwards"></div>
      </div>
    </div>
    {/if}

    {#if error}
    <div style="background:rgba(var(--red-rgb),0.08);border:1px solid rgba(var(--red-rgb),0.3);border-left:4px solid var(--red);padding:14px 16px;font-size:13px;color:var(--red);font-weight:700;border-radius:4px;margin-bottom:16px">
      ⚠ {error}
    </div>
    {/if}

    {#if data && data.quarters.length === 0}
    <div class="p5-panel" style="padding:32px;text-align:center;color:var(--text-muted);font-size:14px">
      No open pipeline or recent closed won data found for this team.
    </div>
    {/if}

    {#if data && data.quarters.length > 0}

    <!-- Summary chips -->
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:20px">
      <div class="p5-stat-chip" style="text-align:center">
        <div style="font-size:9px;color:var(--red);font-weight:800;text-transform:uppercase;letter-spacing:0.2em;margin-bottom:4px">Open Pipeline</div>
        <div style="font-size:22px;font-weight:900;color:var(--text);line-height:1">{fmt(totalPipeIcav)}</div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:2px">{totalPipeCount} opp{totalPipeCount !== 1 ? 's' : ''}</div>
      </div>
      <div class="p5-stat-chip" style="text-align:center">
        <div style="font-size:9px;color:var(--red);font-weight:800;text-transform:uppercase;letter-spacing:0.2em;margin-bottom:4px">TW Pipeline</div>
        <div style="font-size:22px;font-weight:900;color:var(--text);line-height:1">{fmt(totalPipeTwIcav)}</div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:2px">
          {totalPipeIcav > 0 ? Math.round(totalPipeTwIcav / totalPipeIcav * 100) : 0}% TW rate
        </div>
      </div>
      <div class="p5-stat-chip" style="text-align:center">
        <div style="font-size:9px;color:var(--red);font-weight:800;text-transform:uppercase;letter-spacing:0.2em;margin-bottom:4px">Quarters</div>
        <div style="font-size:22px;font-weight:900;color:var(--text);line-height:1">{data.quarters.length}</div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:2px">tracked</div>
      </div>
    </div>

    <!-- Quarter rows -->
    {#each data.quarters as q (q.key)}
    {@const isExpanded = expandedQ === q.key}
    {@const hasPipe = q.pipe.count > 0}
    {@const hasClosed = q.closed.count > 0}
    <div style="margin-bottom:10px;border:1px solid {isExpanded ? 'rgba(var(--red-rgb),0.35)' : 'rgba(var(--red-rgb),0.12)'};border-radius:8px;overflow:hidden;transition:border-color 0.15s">

      <!-- Quarter header row — click to expand pipeline detail -->
      <button
        onclick={() => hasPipe && toggleQ(q.key)}
        style="width:100%;background:{isExpanded ? (p5?'rgba(232,0,61,0.06)':'rgba(242,47,70,0.04)') : 'transparent'};border:none;padding:14px 16px;cursor:{hasPipe?'pointer':'default'};text-align:left;display:flex;flex-direction:column;gap:10px"
      >
        <!-- Quarter label + count badges -->
        <div style="display:flex;align-items:center;justify-content:space-between;width:100%">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:15px;font-weight:800;color:var(--text);letter-spacing:-0.01em">{q.label}</span>
            {#if hasPipe}
            <span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;background:rgba(var(--red-rgb),0.1);color:var(--red)">{q.pipe.count} open</span>
            {/if}
            {#if hasClosed}
            <span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;background:rgba(16,185,129,0.12);color:#10B981">{q.closed.count} won</span>
            {/if}
          </div>
          {#if hasPipe}
          <span style="font-size:11px;color:{isExpanded?'var(--red)':'var(--text-muted)'};transition:transform 0.2s;display:inline-block;transform:{isExpanded?'rotate(180deg)':'rotate(0)'}">▼</span>
          {/if}
        </div>

        <!-- Dual bar: pipeline (red) vs closed (green) -->
        <div style="width:100%;display:flex;flex-direction:column;gap:5px">
          {#if hasPipe}
          <div style="display:flex;align-items:center;gap:8px">
            <div style="font-size:10px;color:var(--text-muted);width:56px;text-align:right;flex-shrink:0">Pipeline</div>
            <div style="flex:1;height:10px;background:rgba(var(--red-rgb),0.1);border-radius:99px;overflow:hidden">
              <div style="height:100%;border-radius:99px;background:var(--red);width:{barWidth(q.pipe.total_icav, combinedMax)}%;transition:width 0.4s"></div>
            </div>
            <div style="font-size:11px;font-weight:700;color:var(--text);min-width:54px">{fmt(q.pipe.total_icav)}</div>
            {#if q.pipe.tw_icav > 0}
            <div style="font-size:10px;color:var(--text-muted)">{fmt(q.pipe.tw_icav)} TW</div>
            {/if}
          </div>
          {/if}
          {#if hasClosed}
          <div style="display:flex;align-items:center;gap:8px">
            <div style="font-size:10px;color:var(--text-muted);width:56px;text-align:right;flex-shrink:0">Closed</div>
            <div style="flex:1;height:10px;background:rgba(16,185,129,0.1);border-radius:99px;overflow:hidden">
              <div style="height:100%;border-radius:99px;background:#10B981;width:{barWidth(q.closed.total_icav, combinedMax)}%;transition:width 0.4s"></div>
            </div>
            <div style="font-size:11px;font-weight:700;color:var(--text);min-width:54px">{fmt(q.closed.total_icav)}</div>
            {#if q.closed.tw_icav > 0}
            <div style="font-size:10px;color:var(--text-muted)">{fmt(q.closed.tw_icav)} TW</div>
            {/if}
          </div>
          {/if}
        </div>
      </button>

      <!-- Expanded: pipeline detail by SE -->
      {#if isExpanded && hasPipe}
      <div style="border-top:1px solid rgba(var(--red-rgb),0.12);background:{p5?'rgba(255,255,255,0.01)':'rgba(13,18,43,0.01)'}">
        {#each q.pipe.ses as se, i (se.se)}
        {@const seExpanded = expandedSe === (q.key + '/' + se.se)}
        <div style="border-top:{i > 0 ? '1px solid rgba(var(--red-rgb),0.07)' : 'none'}">

          <!-- SE row -->
          <button
            onclick={() => toggleSe(q.key + '/' + se.se)}
            style="width:100%;background:none;border:none;padding:10px 16px 10px 24px;cursor:pointer;text-align:left;display:flex;align-items:center;gap:10px"
          >
            <div style="flex:1;min-width:0">
              <div style="font-size:13px;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{se.se}</div>
              <div style="font-size:10px;color:var(--text-muted);margin-top:1px">{se.count} opp{se.count !== 1 ? 's' : ''}{se.tw_count > 0 ? ` · ${se.tw_count} TW` : ''}</div>
            </div>
            <div style="text-align:right;flex-shrink:0">
              <div style="font-size:14px;font-weight:800;color:var(--text)">{fmt(se.icav)}</div>
              {#if se.tw_icav > 0 && se.tw_icav !== se.icav}
              <div style="font-size:10px;color:var(--red)">{fmt(se.tw_icav)} TW</div>
              {/if}
            </div>
            <span style="font-size:10px;color:var(--text-muted);flex-shrink:0;transition:transform 0.2s;display:inline-block;transform:{seExpanded?'rotate(180deg)':'rotate(0)'}">▼</span>
          </button>

          <!-- SE opp detail -->
          {#if seExpanded}
          <div style="padding:0 16px 10px 32px;display:flex;flex-direction:column;gap:4px">
            {#each se.opps as opp (opp.id)}
            <div style="padding:8px 10px;border-radius:5px;background:{p5?'rgba(255,255,255,0.03)':'rgba(13,18,43,0.03)'};border:1px solid rgba(var(--red-rgb),0.08)">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">
                <div style="min-width:0;flex:1">
                  <div style="font-size:12px;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{opp.name}</div>
                  {#if opp.account}
                  <div style="font-size:10px;color:var(--text-muted);margin-top:1px">{opp.account}</div>
                  {/if}
                  <div style="display:flex;gap:6px;margin-top:4px;flex-wrap:wrap">
                    <span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;background:rgba(var(--red-rgb),0.08);color:var(--text-muted)">{opp.stage}</span>
                    {#if opp.is_tw}
                    <span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;background:rgba(232,0,61,0.15);color:var(--red)">TW</span>
                    {/if}
                    <span style="font-size:9px;color:var(--text-muted)">Close: {opp.close}</span>
                  </div>
                </div>
                <div style="font-size:13px;font-weight:800;color:var(--text);flex-shrink:0">{fmt(opp.icav)}</div>
              </div>
            </div>
            {/each}
          </div>
          {/if}

        </div>
        {/each}
      </div>
      {/if}

    </div>
    {/each}

    {/if}

  </div>
</div>

<style>
.fc-container {
  max-width: 32rem;
  margin: 0 auto;
}
@media (min-width: 768px) {
  .fc-container { max-width: 720px; }
}
@media (min-width: 1024px) {
  .fc-container { max-width: 860px; }
}

@keyframes loadFill {
  0%   { width: 0% }
  30%  { width: 55% }
  70%  { width: 78% }
  100% { width: 88% }
}
</style>
