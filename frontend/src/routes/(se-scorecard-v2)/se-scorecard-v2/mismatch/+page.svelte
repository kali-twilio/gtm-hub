<script lang="ts">
  import { onMount } from 'svelte';
  import { getSFMismatch, getSFPeriods, fmt } from '$lib/api';
  import { theme, sfTeam, sfPeriod, sfSubteam } from '$lib/stores';
  import { tc, fc } from '$lib/colors';

  let data: any = $state(null);
  let loading = $state(false);
  let showLoading = $state(false);
  let error = $state('');
  let periods: { key: string; label: string }[] = $state([]);
  let teams: any[] = $state([]);

  const p5 = $derived($theme === 'p5');

  const RULES = [
    { fc: 'Pipeline',    allowed: ['Qualified', 'Discovery'] },
    { fc: 'Best Case',   allowed: ['Discovery', 'Technical Evaluation', 'Technical Win Achieved'] },
    { fc: 'Most Likely', allowed: ['Technical Win Achieved'] },
    { fc: 'Commit',      allowed: ['Technical Win Achieved'] },
  ];

  const STAGE_COLORS: Record<string, string> = {
    'Qualified':              '#6366f1',
    'Discovery':              '#3b82f6',
    'Technical Evaluation':   '#f59e0b',
    'Technical Win Achieved': '#10b981',
    'Not Set':                '#6b7280',
  };

  const FC_COLORS: Record<string, string> = {
    'Pipeline':    '#6366f1',
    'Best Case':   '#3b82f6',
    'Most Likely': '#f59e0b',
    'Commit':      '#ef4444',
    'Omitted':     '#6b7280',
  };

  async function load() {
    loading = true;
    error = '';
    data = null;
    const t = setTimeout(() => { if (loading) showLoading = true; }, 400);
    const result = await getSFMismatch($sfTeam, $sfPeriod, $sfSubteam !== 'none' ? $sfSubteam : '');
    clearTimeout(t);
    loading = false;
    showLoading = false;
    if (result && !result.error) {
      data = result;
    } else {
      error = result?.error || 'Failed to load mismatch data.';
    }
  }

  function onTeamChange(e: Event) {
    sfTeam.set((e.target as HTMLSelectElement).value);
    sfSubteam.set('none');
    load();
  }

  function onSubteamChange(e: Event) {
    sfSubteam.set((e.target as HTMLSelectElement).value);
    load();
  }

  function onPeriodChange(e: Event) {
    sfPeriod.set((e.target as HTMLSelectElement).value);
    load();
  }

  const currentTeam = $derived(teams.find(t => t.key === $sfTeam));
  const subteams = $derived(currentTeam?.subteams ?? []);

  onMount(async () => {
    const [p, t] = await Promise.all([
      getSFPeriods(),
      fetch('/api/se-scorecard-v2/teams').then(r => r.ok ? r.json() : []),
    ]);
    periods = p;
    teams = t;
    load();
  });

  const bg    = $derived(p5 ? '#0d0d0d' : '#f8f9fb');
  const card  = $derived(p5 ? '#141414' : '#ffffff');
  const text  = $derived(p5 ? 'rgba(255,255,255,0.9)' : 'rgba(13,18,43,0.9)');
  const sub   = $derived(p5 ? 'rgba(255,255,255,0.45)' : 'rgba(13,18,43,0.45)');
  const bdr   = $derived(p5 ? 'rgba(255,255,255,0.08)' : 'rgba(13,18,43,0.08)');
  const red   = '#e8003d';

  function stageChip(stage: string) {
    const c = STAGE_COLORS[stage] || '#6b7280';
    return `display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:${c}22;color:${c};border:1px solid ${c}44`;
  }

  function fcChip(fcat: string) {
    const c = FC_COLORS[fcat] || '#6b7280';
    return `display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:${c}22;color:${c};border:1px solid ${c}44`;
  }

  const mismatchPct = $derived(data && data.total_icav_all > 0
    ? Math.round(data.total_icav_mismatched / data.total_icav_all * 100)
    : 0);
</script>

<div style="min-height:100vh;background:{bg};padding:32px 24px 64px;color:{text};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">

  <!-- Page header -->
  <div style="max-width:1100px;margin:0 auto">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:28px">
      <div>
        <h1 style="font-size:22px;font-weight:700;margin:0 0 4px;letter-spacing:-0.02em">Stage Mismatch Report</h1>
        <p style="margin:0;font-size:13px;color:{sub}">
          Compares Forecast Category against Presales Stage for open pipeline deals.
          {#if data}· {data.team_label} · {data.quarter}{/if}
        </p>
      </div>

      <!-- Controls -->
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
        <select onchange={onTeamChange} style="background:{card};color:{text};border:1px solid {bdr};border-radius:6px;padding:6px 10px;font-size:13px;cursor:pointer">
          {#each teams as t}
            <option value={t.key} selected={t.key === $sfTeam}>{t.label}</option>
          {/each}
        </select>

        {#if subteams.length > 0}
          <select onchange={onSubteamChange} style="background:{card};color:{text};border:1px solid {bdr};border-radius:6px;padding:6px 10px;font-size:13px;cursor:pointer">
            <option value="none" selected={$sfSubteam === 'none'}>All</option>
            {#each subteams as s}
              <option value={s.key} selected={s.key === $sfSubteam}>{s.label}</option>
            {/each}
          </select>
        {/if}

        <select onchange={onPeriodChange} style="background:{card};color:{text};border:1px solid {bdr};border-radius:6px;padding:6px 10px;font-size:13px;cursor:pointer">
          {#each periods as p}
            <option value={p.key} selected={p.key === $sfPeriod}>{p.label}</option>
          {/each}
        </select>

        <button
          onclick={load}
          style="background:{red};color:white;border:none;border-radius:6px;padding:6px 14px;font-size:13px;font-weight:600;cursor:pointer"
        >Refresh</button>
      </div>
    </div>

    <!-- Loading / error -->
    {#if showLoading}
      <div style="text-align:center;padding:60px 0;color:{sub}">Loading pipeline data…</div>
    {:else if error}
      <div style="background:#ef444422;border:1px solid #ef444444;border-radius:8px;padding:16px;color:#ef4444">{error}</div>
    {:else if data}

      <!-- Summary cards -->
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:28px">

        <div style="background:{card};border:1px solid {bdr};border-radius:10px;padding:20px">
          <div style="font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px">Total Pipeline iACV</div>
          <div style="font-size:26px;font-weight:800;letter-spacing:-0.03em">{fmt(data.total_icav_all)}</div>
          <div style="font-size:12px;color:{sub};margin-top:4px">{data.total_count} open deals</div>
        </div>

        <div style="background:{card};border:1px solid {bdr};border-radius:10px;padding:20px">
          <div style="font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px">Mismatched iACV</div>
          <div style="font-size:26px;font-weight:800;letter-spacing:-0.03em;color:{red}">{fmt(data.total_icav_mismatched)}</div>
          <div style="font-size:12px;color:{sub};margin-top:4px">{data.mismatch_count} deals · {mismatchPct}% of total</div>
        </div>

        <div style="background:{card};border:1px solid {bdr};border-radius:10px;padding:20px">
          <div style="font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px">Aligned iACV</div>
          <div style="font-size:26px;font-weight:800;letter-spacing:-0.03em;color:#10b981">{fmt(data.total_icav_all - data.total_icav_mismatched)}</div>
          <div style="font-size:12px;color:{sub};margin-top:4px">{data.total_count - data.mismatch_count} deals · {100 - mismatchPct}% of total</div>
        </div>

      </div>

      <!-- Insights -->
      {#if data.insights?.length > 0}
        <div style="background:{p5?'rgba(232,0,61,0.07)':'rgba(239,68,68,0.06)'};border:1px solid {p5?'rgba(232,0,61,0.2)':'rgba(239,68,68,0.15)'};border-radius:10px;padding:20px;margin-bottom:28px">
          <div style="font-size:12px;font-weight:700;color:{red};text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px">Insights</div>
          <ul style="margin:0;padding:0 0 0 18px;display:flex;flex-direction:column;gap:8px">
            {#each data.insights as insight}
              <li style="font-size:14px;color:{text}">{insight}</li>
            {/each}
          </ul>
        </div>
      {/if}

      <!-- Rules reference -->
      <div style="background:{card};border:1px solid {bdr};border-radius:10px;padding:20px;margin-bottom:28px">
        <div style="font-size:12px;font-weight:700;color:{sub};text-transform:uppercase;letter-spacing:0.08em;margin-bottom:14px">Stage Alignment Rules</div>
        <div style="display:flex;flex-wrap:wrap;gap:12px">
          {#each RULES as rule}
            <div style="display:flex;align-items:flex-start;gap:8px;min-width:200px">
              <span style={fcChip(rule.fc)}>{rule.fc}</span>
              <span style="font-size:12px;color:{sub};padding-top:3px">→ {rule.allowed.join(' or ')}</span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Mismatch table -->
      {#if data.mismatched.length === 0}
        <div style="text-align:center;padding:48px;color:{sub};background:{card};border:1px solid {bdr};border-radius:10px">
          No stage mismatches found — all pipeline deals are aligned.
        </div>
      {:else}
        <div style="background:{card};border:1px solid {bdr};border-radius:10px;overflow:hidden">
          <table style="width:100%;border-collapse:collapse;font-size:13px">
            <thead>
              <tr style="border-bottom:1px solid {bdr}">
                <th style="text-align:left;padding:12px 16px;font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em">Opportunity</th>
                <th style="text-align:right;padding:12px 16px;font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em">iACV</th>
                <th style="text-align:left;padding:12px 16px;font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em">Forecast Cat.</th>
                <th style="text-align:left;padding:12px 16px;font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em">Presales Stage</th>
                <th style="text-align:left;padding:12px 16px;font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em">SE</th>
                <th style="text-align:left;padding:12px 16px;font-size:11px;font-weight:600;color:{sub};text-transform:uppercase;letter-spacing:0.06em">Mismatch Reason</th>
              </tr>
            </thead>
            <tbody>
              {#each data.mismatched as opp, i}
                <tr style="border-bottom:1px solid {bdr};{i % 2 === 1 ? `background:${p5?'rgba(255,255,255,0.02)':'rgba(13,18,43,0.02)'}` : ''}">
                  <td style="padding:12px 16px">
                    <div style="font-weight:600;margin-bottom:2px">{opp.account || opp.name}</div>
                    <div style="font-size:11px;color:{sub}">{opp.name}</div>
                    <div style="font-size:11px;color:{sub}">Close: {opp.close_date}</div>
                  </td>
                  <td style="padding:12px 16px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums;color:{red}">
                    {fmt(opp.icav)}
                  </td>
                  <td style="padding:12px 16px">
                    <span style={fcChip(opp.forecast_cat)}>{opp.forecast_cat || '—'}</span>
                  </td>
                  <td style="padding:12px 16px">
                    <span style={stageChip(opp.presales_stage)}>{opp.presales_stage}</span>
                  </td>
                  <td style="padding:12px 16px;color:{sub};white-space:nowrap">
                    {opp.se_name || '—'}
                  </td>
                  <td style="padding:12px 16px">
                    {#each opp.mismatches as reason}
                      <div style="font-size:12px;color:{p5?'rgba(251,191,36,0.9)':'rgba(180,83,9,0.9)'};margin-bottom:4px">⚠ {reason}</div>
                    {/each}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}

    {/if}
  </div>
</div>
