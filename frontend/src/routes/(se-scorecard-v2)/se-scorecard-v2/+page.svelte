<script lang="ts">
  import { onMount } from 'svelte';
  import { user, sfTeam, sfPeriod, sfSubteam } from '$lib/stores';
  import { getSFPeriods, fmt } from '$lib/api';

  interface Criterion { label: string; detail: string; }
  interface Team { key: string; label: string; description: string; criteria: Criterion[]; }
  interface Period { key: string; label: string; }

  let teams: Team[] = $state([]);
  let periods: Period[] = $state([]);
  let summary: { total: number; team_icav: number; team_wins: number; team_label: string; quarter: string } | null = $state(null);
  let loading = $state(false);
  let error = $state('');

  let criteriaExpanded = $state(false);

  async function loadSummary(teamKey: string, periodKey: string, subteamKey = $sfSubteam) {
    loading = true;
    error = '';
    summary = null;
    const sub = subteamKey !== 'none' ? `&subteam=${subteamKey}` : '';
    const r = await fetch(`/api/se-scorecard-v2/data/report?team=${teamKey}&period=${periodKey}${sub}`);
    if (r.ok) {
      const d = await r.json();
      summary = { total: d.total, team_icav: d.team_icav, team_wins: d.team_wins, team_label: d.team_label, quarter: d.quarter };
    } else {
      const d = await r.json().catch(() => ({}));
      error = d.error || 'Failed to load data.';
    }
    loading = false;
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


  onMount(async () => {
    const [teamsRes, periodsData] = await Promise.all([
      fetch('/api/se-scorecard-v2/teams').then(r => r.ok ? r.json() : []),
      getSFPeriods(),
    ]);
    teams = teamsRes;
    periods = periodsData;
    loadSummary($sfTeam, $sfPeriod);
  });
</script>

<div class="min-h-screen flex flex-col items-center px-4 py-14">

  <!-- Top bar -->
  <div class="w-full max-w-lg flex justify-between items-center mb-8 text-xs">
    <a href="/" class="p5-back-btn" style="font-size:11px">◀ Apps</a>
    <div style="display:flex;align-items:center;gap:12px">
      <span style="color:var(--text-muted);font-weight:600;letter-spacing:0.08em">{$user?.email}</span>
      <a href="/logout" style="color:var(--red);font-weight:700;text-decoration:none;text-transform:uppercase;letter-spacing:0.1em">Sign out</a>
    </div>
  </div>

  <!-- Header -->
  <div class="text-center mb-8 w-full max-w-lg">
    <div class="p5-badge mb-3">SE Scorecard V2</div>
    <h1 style="font-size:28px;font-weight:800;color:var(--text);letter-spacing:-0.02em">SE Performance</h1>
    <div style="width:40px;height:3px;background:var(--red);border-radius:2px;margin:10px auto 0"></div>
  </div>

  <!-- Team selector -->
  <div class="w-full max-w-lg mb-5">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--text-muted);margin-bottom:8px">Team</div>
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
  </div>

  <!-- Subteam selector -->
  {#if (teams.find(t => t.key === $sfTeam)?.subteams ?? []).length > 0}
  <div class="w-full max-w-lg mb-5">
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

  <!-- Period selector -->
  {#if periods.length > 0}
  <div class="w-full max-w-lg mb-6">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--text-muted);margin-bottom:8px">Period</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">
      {#each periods as p}
      <button
        onclick={() => onPeriodChange(p.key)}
        style="padding:6px 12px;font-size:12px;font-weight:700;border-radius:6px;border:1px solid {$sfPeriod === p.key ? 'var(--red)' : 'rgba(var(--red-rgb),0.2)'};background:{$sfPeriod === p.key ? 'rgba(var(--red-rgb),0.12)' : 'transparent'};color:{$sfPeriod === p.key ? 'var(--red)' : 'var(--text-muted)'};cursor:pointer;transition:all 0.15s;letter-spacing:0.04em"
      >{p.label}</button>
      {/each}
    </div>
  </div>
  {/if}

  <!-- Membership criteria (collapsible) -->
  {#if teams.length > 0}
  {@const criteria = teams.find(t => t.key === $sfTeam)?.criteria ?? []}
  {#if criteria.length > 0}
  <div class="w-full max-w-lg mb-6">
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
  {#if loading}
  <div class="w-full max-w-lg p5-panel" style="padding:32px;text-align:center;margin-bottom:16px">
    <div style="font-size:13px;color:var(--text-muted);font-weight:600;letter-spacing:0.05em">Pulling live Salesforce data…</div>
    <div style="margin-top:14px;height:3px;background:rgba(var(--red-rgb),0.1);border-radius:99px;overflow:hidden">
      <div style="height:100%;border-radius:99px;background:var(--red);animation:loadPulse 1.4s ease-in-out infinite"></div>
    </div>
  </div>

  {:else if error}
  <div class="w-full max-w-lg mb-4" style="background:rgba(var(--red-rgb),0.08);border:1px solid rgba(var(--red-rgb),0.3);border-left:4px solid var(--red);padding:14px 16px;font-size:13px;color:var(--red);font-weight:700">
    ⚠ {error}
  </div>

  {:else if summary}
  <!-- Period label -->
  <div class="w-full max-w-lg mb-3">
    <div style="font-size:11px;color:var(--text-muted);font-weight:600;letter-spacing:0.08em">{summary.team_label} · {summary.quarter}</div>
  </div>

  <!-- Summary stats -->
  <div class="w-full max-w-lg" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:20px">
    {#each [
      { label: 'Team iACV',  val: fmt(summary.team_icav) },
      { label: 'TW Closed Won',  val: String(summary.team_wins) },
      { label: 'SEs',        val: String(summary.total)  },
    ] as s}
    <div class="p5-panel" style="padding:14px 16px;text-align:center">
      <div style="font-size:10px;color:var(--red);font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:6px">{s.label}</div>
      <div style="font-size:22px;font-weight:900;color:var(--text)">{s.val}</div>
    </div>
    {/each}
  </div>

  <!-- Nav -->
  <div class="w-full max-w-lg" style="display:flex;flex-direction:column;gap:6px;margin-bottom:24px">
    <a href="/se-scorecard-v2/report" class="p5-menu-btn">
      <span style="font-size:22px">📊</span>
      <div style="flex:1">
        <div style="font-size:16px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">Full Report</div>
        <div style="font-size:11px;color:var(--text-muted);font-weight:500">Complete SE performance analysis</div>
      </div>
      <span style="color:var(--red);font-size:18px">▶</span>
    </a>
    <a href="/se-scorecard-v2/rankings" class="p5-menu-btn">
      <span style="font-size:22px">🏆</span>
      <div style="flex:1">
        <div style="font-size:16px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">Power Rankings</div>
        <div style="font-size:11px;color:var(--text-muted);font-weight:500">Ranked leaderboard by performance</div>
      </div>
      <span style="color:var(--red);font-size:18px">▶</span>
    </a>
    <a href="/se-scorecard-v2/me" class="p5-menu-btn">
      <span style="font-size:22px">👤</span>
      <div style="flex:1">
        <div style="font-size:16px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">My Stats</div>
        <div style="font-size:11px;color:var(--text-muted);font-weight:500">Individual SE performance view</div>
      </div>
      <span style="color:var(--red);font-size:18px">▶</span>
    </a>
  </div>
  {/if}


</div>

<style>
@keyframes loadPulse {
  0%   { width: 0%;    margin-left: 0% }
  50%  { width: 60%;   margin-left: 20% }
  100% { width: 0%;    margin-left: 100% }
}
</style>
