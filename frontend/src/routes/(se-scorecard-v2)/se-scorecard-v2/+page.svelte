<script lang="ts">
  import { onMount } from 'svelte';
  import { user, sfTeam, sfPeriod, sfSubteam, authReady } from '$lib/stores';
  import { getSFPeriods, fmt } from '$lib/api';
  import { goto } from '$app/navigation';

  interface Criterion { label: string; detail: string; }
  interface Team { key: string; label: string; description: string; criteria: Criterion[]; }
  interface Period { key: string; label: string; }

  let teams: Team[] = $state([]);
  let periods: Period[] = $state([]);
  let summary: { total: number; team_icav: number; team_wins: number; team_arr: number; team_label: string; quarter: string } | null = $state(null);
  let loading = $state(false);
  let showLoading = $state(false);
  let error = $state('');

  let criteriaExpanded = $state(false);

  async function loadSummary(teamKey: string, periodKey: string, subteamKey = $sfSubteam) {
    loading = true;
    error = '';
    summary = null;
    const t = setTimeout(() => { if (loading) showLoading = true; }, 400);
    const sub = subteamKey !== 'none' ? `&subteam=${subteamKey}` : '';
    const r = await fetch(`/api/se-scorecard-v2/data/report?team=${teamKey}&period=${periodKey}${sub}`);
    if (r.ok) {
      const d = await r.json();
      summary = { total: d.total, team_icav: d.team_icav, team_wins: d.team_wins, team_arr: d.team_arr ?? 0, team_label: d.team_label, quarter: d.quarter };
    } else {
      const d = await r.json().catch(() => ({}));
      error = d.error || 'Failed to load data.';
    }
    clearTimeout(t);
    loading = false;
    showLoading = false;
  }

  function onTeamChange(e: Event) {
    const val = (e.target as HTMLSelectElement).value;
    sfTeam.set(val);
    sfSubteam.set('none');
    loadSummary(val, $sfPeriod, 'none');
  }

  function onSubteamChange(e: Event) {
    const val = (e.target as HTMLSelectElement).value;
    sfSubteam.set(val);
    loadSummary($sfTeam, $sfPeriod, val);
  }

  function onPeriodChange(key: string) {
    sfPeriod.set(key);
    loadSummary($sfTeam, key);
  }


  const restricted = $derived($user?.sf_access === 'se_restricted');

  // Auto-send SE ICs straight to their personal stats page
  $effect(() => {
    if ($authReady && restricted) goto('/se-scorecard-v2/me');
  });

  onMount(async () => {
    const [teamsRes, periodsData] = await Promise.all([
      fetch('/api/se-scorecard-v2/teams').then(r => r.ok ? r.json() : []),
      getSFPeriods(),
    ]);
    teams = teamsRes;
    periods = periodsData;
    // For restricted SEs, force their team and subteam from their SF role
    if (restricted && $user?.sf_team) {
      sfTeam.set($user.sf_team);
      if ($user.sf_subteam) sfSubteam.set($user.sf_subteam);
    }
    loadSummary($sfTeam, $sfPeriod, $sfSubteam);
  });
</script>

<div class="min-h-screen flex flex-col items-center px-4 py-14">

  <!-- Header -->
  <div class="text-center mb-8 w-full hub-container">
    <div class="p5-badge mb-3">SE Scorecard V2</div>
    <h1 style="font-size:28px;font-weight:800;color:var(--text);letter-spacing:-0.02em">SE Performance</h1>
    <div style="width:40px;height:3px;background:var(--red);border-radius:2px;margin:10px auto 0"></div>
  </div>

  <!-- Selectors row: team + subteam side-by-side on desktop -->
  <div class="w-full hub-container mb-5 selectors-row">
    <div style="flex:1;min-width:0">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--text-muted);margin-bottom:8px">Team</div>
      {#if restricted}
      <div style="padding:10px 14px;border:1px solid rgba(var(--red-rgb),0.15);border-radius:6px;font-size:13px;font-weight:600;color:var(--text);background:rgba(var(--red-rgb),0.03)">
        {teams.find(t => t.key === $sfTeam)?.label ?? $sfTeam}
      </div>
      {:else}
      <div style="position:relative">
        <select onchange={onTeamChange} value={$sfTeam} style="padding-right:36px">
          {#each teams as t}
            <option value={t.key} selected={t.key === $sfTeam}>{t.label}</option>
          {/each}
          {#if teams.length === 0}
            <option value={$sfTeam}>Loading…</option>
          {/if}
        </select>
        <div style="position:absolute;right:14px;top:50%;transform:translateY(-50%);color:var(--red);font-size:12px;pointer-events:none">▼</div>
      </div>
      {/if}
    </div>

    {#if (teams.find(t => t.key === $sfTeam)?.subteams ?? []).length > 0}
    <div style="flex:1;min-width:0">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--text-muted);margin-bottom:8px">Subteam</div>
      <div style="position:relative">
        <select onchange={onSubteamChange} value={$sfSubteam} style="padding-right:36px">
          <option value="none">None</option>
          {#each (teams.find(t => t.key === $sfTeam)?.subteams ?? []) as s}
            <option value={s.key} selected={s.key === $sfSubteam}>{s.label}</option>
          {/each}
        </select>
        <div style="position:absolute;right:14px;top:50%;transform:translateY(-50%);color:var(--red);font-size:12px;pointer-events:none">▼</div>
      </div>
    </div>
    {/if}
  </div>

  <!-- Period selector -->
  {#if periods.length > 0}
  <div class="w-full hub-container mb-6">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--text-muted);margin-bottom:8px">Period</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">
      {#each periods as p}
      <button
        onclick={() => onPeriodChange(p.key)}
        style="padding:6px 14px;font-size:12px;font-weight:700;border-radius:6px;border:1px solid {$sfPeriod === p.key ? 'var(--red)' : 'rgba(var(--red-rgb),0.2)'};background:{$sfPeriod === p.key ? 'rgba(var(--red-rgb),0.12)' : 'transparent'};color:{$sfPeriod === p.key ? 'var(--red)' : 'var(--text-muted)'};cursor:pointer;transition:all 0.15s;letter-spacing:0.04em"
      >{p.label}</button>
      {/each}
    </div>
  </div>
  {/if}

  <!-- Membership criteria (collapsible) -->
  {#if teams.length > 0}
  {@const criteria = teams.find(t => t.key === $sfTeam)?.criteria ?? []}
  {#if criteria.length > 0}
  <div class="w-full hub-container mb-6">
    <button
      onclick={() => criteriaExpanded = !criteriaExpanded}
      style="width:100%;display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:transparent;border:1px solid rgba(var(--red-rgb),0.15);border-radius:{criteriaExpanded ? '6px 6px 0 0' : '6px'};cursor:pointer;color:var(--text-muted);font-size:12px;font-weight:600;letter-spacing:0.05em"
    >
      <span>📋 Who counts as a team member?</span>
      <span style="font-size:10px;transition:transform 0.2s;transform:{criteriaExpanded ? 'rotate(180deg)' : 'rotate(0)'}">▼</span>
    </button>
    {#if criteriaExpanded}
    <div style="border:1px solid rgba(var(--red-rgb),0.15);border-top:none;border-radius:0 0 6px 6px;overflow:hidden">
      {#each criteria as c, i}
      <div style="padding:8px 14px;{i > 0 ? 'border-top:1px solid rgba(var(--red-rgb),0.08)' : ''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--red);margin-bottom:2px">{c.label}</div>
        <div style="font-size:12px;color:var(--text-muted);font-weight:500;line-height:1.4">{c.detail}</div>
      </div>
      {/each}
    </div>
    {/if}
  </div>
  {/if}
  {/if}

  <!-- Loading / error / summary -->
  {#if showLoading}
  <div class="w-full hub-container p5-panel" style="padding:32px;text-align:center;margin-bottom:16px">
    <div style="font-size:13px;color:var(--text-muted);font-weight:600;letter-spacing:0.05em">Pulling live Salesforce data…</div>
    <div style="margin-top:14px;height:4px;background:rgba(var(--red-rgb),0.12);border-radius:99px;overflow:hidden">
      <div style="height:100%;border-radius:99px;background:var(--red);animation:loadFill 10s linear forwards,shimmer 1.8s ease-in-out infinite"></div>
    </div>
  </div>
  {/if}

  {#if error}
  <div class="w-full hub-container mb-4" style="background:rgba(var(--red-rgb),0.08);border:1px solid rgba(var(--red-rgb),0.3);border-left:4px solid var(--red);padding:14px 16px;font-size:13px;color:var(--red);font-weight:700">
    ⚠ {error}
  </div>

  {:else if summary}
  <!-- Period label -->
  <div class="w-full hub-container mb-3">
    <div style="font-size:11px;color:var(--text-muted);font-weight:600;letter-spacing:0.08em">{summary.team_label} · {summary.quarter}</div>
  </div>

  <!-- Summary stats -->
  {@const summaryStats = [
    { label: 'Team iACV',    val: fmt(summary.team_icav) },
    ...(summary.team_arr > 0 ? [{ label: 'Acct ARR', val: fmt(summary.team_arr) }] : []),
    { label: 'TW Closed Won', val: String(summary.team_wins) },
    { label: 'SEs',           val: String(summary.total) },
  ]}
  <div class="w-full hub-container" style="display:grid;grid-template-columns:repeat({summaryStats.length}, 1fr);gap:10px;margin-bottom:20px">
    {#each summaryStats as s}
    <div class="p5-panel" style="padding:18px 20px;text-align:center">
      <div style="font-size:10px;color:var(--red);font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:8px">{s.label}</div>
      <div style="font-size:26px;font-weight:900;color:var(--text)">{s.val}</div>
    </div>
    {/each}
  </div>

  <!-- Nav — single column on mobile, 3-column on desktop -->
  <div class="w-full hub-container nav-grid" style="margin-bottom:24px">
    {#if !restricted}
    <a href="/se-scorecard-v2/report" class="p5-menu-btn nav-card">
      <span style="font-size:24px">📊</span>
      <div style="flex:1">
        <div style="font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">Full Report</div>
        <div style="font-size:11px;color:var(--text-muted);font-weight:500;margin-top:2px">Complete SE performance analysis</div>
      </div>
      <span style="color:var(--red);font-size:18px">▶</span>
    </a>
    <a href="/se-scorecard-v2/rankings" class="p5-menu-btn nav-card">
      <span style="font-size:24px">🏆</span>
      <div style="flex:1">
        <div style="font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">Power Rankings</div>
        <div style="font-size:11px;color:var(--text-muted);font-weight:500;margin-top:2px">Ranked leaderboard by performance</div>
      </div>
      <span style="color:var(--red);font-size:18px">▶</span>
    </a>
    {/if}
    <a href="/se-scorecard-v2/me" class="p5-menu-btn nav-card">
      <span style="font-size:24px">👤</span>
      <div style="flex:1">
        <div style="font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">My Stats</div>
        <div style="font-size:11px;color:var(--text-muted);font-weight:500;margin-top:2px">Individual SE performance view</div>
      </div>
      <span style="color:var(--red);font-size:18px">▶</span>
    </a>
  </div>
  {/if}


</div>

<style>
/* Responsive container — narrow on mobile, wider on desktop */
.hub-container {
  max-width: 32rem; /* 512px — mobile */
}
@media (min-width: 768px) {
  .hub-container { max-width: 720px; }
}
@media (min-width: 1024px) {
  .hub-container { max-width: 860px; }
}

/* Selectors: stacked on mobile, side-by-side on desktop */
.selectors-row {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
@media (min-width: 768px) {
  .selectors-row { flex-direction: row; gap: 16px; }
}

/* Nav cards: column on mobile, 3-column grid on desktop */
.nav-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
@media (min-width: 768px) {
  .nav-grid { grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .nav-card { flex-direction: column; align-items: flex-start; gap: 12px; padding: 20px; }
  .nav-card span:last-child { display: none; } /* hide ▶ arrow in card layout */
}

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
