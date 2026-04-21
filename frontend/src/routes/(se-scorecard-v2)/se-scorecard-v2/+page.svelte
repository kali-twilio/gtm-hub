<script lang="ts">
  import { onMount } from 'svelte';
  import { user, sfTeam, sfPeriod, sfSubteam, authReady } from '$lib/stores';
  import { getSFPeriods, fmt } from '$lib/api';
  import { goto } from '$app/navigation';

  interface Criterion { label: string; detail: string; }
  interface Subteam { key: string; label: string; }
  interface Team { key: string; label: string; description: string; motion: string; criteria: Criterion[]; subteams?: Subteam[]; }
  interface Period { key: string; label: string; }

  let teams: Team[] = $state([]);
  let periods: Period[] = $state([]);
  interface TrendPoint { period: string; period_key: string; is_current: boolean; team_act_icav: number; team_exp_icav: number; team_total_icav: number; }
  let summary: { total: number; team_icav: number; team_earr: number; team_wins: number; team_arr: number; team_label: string; quarter: string; se_icav_pct: number | null; team_total_icav: number | null; team_total_wins: number | null; team_total_earr: number | null; se_earr_pct: number | null; ae_dsr_count: number | null; ae_to_se_ratio: number | null; motion: string | null; exp_trend: TrendPoint[] } | null = $state(null);
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
      summary = { total: d.total, team_icav: d.team_icav, team_earr: d.team_earr ?? 0, team_wins: d.team_wins, team_arr: d.team_arr ?? 0, team_label: d.team_label, quarter: d.quarter, se_icav_pct: d.se_icav_pct ?? null, team_total_icav: d.team_total_icav ?? null, team_total_wins: d.team_total_wins ?? null, team_total_earr: d.team_total_earr ?? null, se_earr_pct: d.se_earr_pct ?? null, ae_dsr_count: d.ae_dsr_count ?? null, ae_to_se_ratio: d.ae_to_se_ratio ?? null, motion: d.motion ?? null, exp_trend: d.exp_trend ?? [] };
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
    <h1 style="font-size:40px;font-weight:800;color:var(--text);letter-spacing:-0.02em">SE Scorecard</h1>
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
      <button onclick={() => onPeriodChange(p.key)} class="p5-ctrl {$sfPeriod === p.key ? 'active' : ''}">{p.label}</button>
      {/each}
    </div>
  </div>
  {/if}

  <!-- Methodology (collapsible) -->
  {#if teams.length > 0}
  {@const criteria = teams.find(t => t.key === $sfTeam)?.criteria ?? []}
  {@const teamMotion = teams.find(t => t.key === $sfTeam)?.motion ?? 'ae'}
  {#if criteria.length > 0}
  <div class="w-full hub-container mb-6">
    <button
      onclick={() => criteriaExpanded = !criteriaExpanded}
      style="width:100%;display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:transparent;border:1px solid rgba(var(--red-rgb),0.15);border-radius:{criteriaExpanded ? '6px 6px 0 0' : '6px'};cursor:pointer;color:var(--text-muted);font-size:12px;font-weight:600;letter-spacing:0.05em"
    >
      <span>ℹ How these numbers are calculated</span>
      <span style="font-size:10px;transition:transform 0.2s;transform:{criteriaExpanded ? 'rotate(180deg)' : 'rotate(0)'}">▼</span>
    </button>
    {#if criteriaExpanded}
    <div style="border:1px solid rgba(var(--red-rgb),0.15);border-top:none;border-radius:0 0 6px 6px;overflow:hidden">

      <!-- SEs counted -->
      <div style="padding:10px 14px">
        <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.14em;color:var(--red);margin-bottom:6px">Who counts as an SE</div>
        <div style="display:flex;flex-direction:column;gap:6px">
          {#each criteria as c}
          <div>
            <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--text)">{c.label} — </span><span style="font-size:12px;color:var(--text-muted);line-height:1.5">{c.detail}</span>
          </div>
          {/each}
        </div>
      </div>

      <!-- iACV -->
      <div style="padding:10px 14px;border-top:1px solid rgba(var(--red-rgb),0.08)">
        <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.14em;color:var(--red);margin-bottom:6px">iACV</div>
        {#if teamMotion === 'dsr'}
        <div style="font-size:12px;color:var(--text-muted);line-height:1.5">
          <strong style="color:var(--text)">SE iACV</strong> — <code style="font-size:11px">SUM(Comms_Segment_Combined_iACV__c)</code> on Closed Won opps where the opp is DSR-tagged <em>and</em> the SE is tagged as Technical Lead.<br>
          <strong style="color:var(--text)">Team total iACV</strong> — same field on all DSR opps regardless of SE tag; SE iACV ÷ team total = the SE coverage % shown.<br>
          <strong style="color:var(--text)">Activate / Expansion split</strong> — Expansion = opp where AE's current role or FY_16 stamp contains "Expansion"; Activate = everything else.
        </div>
        {:else}
        <div style="font-size:12px;color:var(--text-muted);line-height:1.5">
          <strong style="color:var(--text)">SE iACV</strong> — <code style="font-size:11px">SUM(Comms_Segment_Combined_iACV__c)</code> on Closed Won opps where <code style="font-size:11px">Technical_Lead__r.UserRole.Name LIKE 'SE - {$sfTeam === 'emea' ? 'EMEA' : 'NAMER'}%'</code>.<br>
          <strong style="color:var(--text)">NB / Strat split</strong> — NB = AE role contains " NB"; Strat = AE role or FY_16 stamp contains "Strat". NB + Strat = team total exactly.<br>
          <strong style="color:var(--text)">Team total iACV</strong> — scoped to NB + Strat opps only so the split always sums to 100%.
        </div>
        {/if}
      </div>

      <!-- ARR -->
      <div style="padding:10px 14px;border-top:1px solid rgba(var(--red-rgb),0.08)">
        <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.14em;color:var(--red);margin-bottom:6px">ARR</div>
        <div style="font-size:12px;color:var(--text-muted);line-height:1.5">
          <strong style="color:var(--text)">eARR (expected ARR)</strong> — <code style="font-size:11px">SUM(Expected_ARR__c)</code> on the same SE-tagged Closed Won opps.<br>
          <strong style="color:var(--text)">Acct ARR</strong> — <code style="font-size:11px">SUM(Account.ARR__c)</code> pulled from accounts linked to those opps; represents the install base each SE is selling into.
        </div>
      </div>

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
    ...(summary.team_earr > 0 ? [{ label: 'Team eARR', val: fmt(summary.team_earr), sub: (summary.se_earr_pct !== null && summary.team_total_earr !== null) ? `${summary.se_earr_pct}% · ${fmt(summary.team_total_earr)} total` : null }] : []),
    ...(summary.team_arr > 0 ? [{ label: 'Acct ARR', val: fmt(summary.team_arr), sub: null }] : []),
    { label: 'TW Closed Won', val: String(summary.team_wins), sub: (summary.team_total_wins != null) ? `${Math.round(summary.team_wins / summary.team_total_wins * 100)}% · ${summary.team_total_wins} total` : null },
    { label: 'SEs', val: String(summary.total), sub: (summary.ae_dsr_count != null && summary.ae_to_se_ratio != null) ? `${summary.ae_dsr_count} ${summary.motion === 'dsr' ? 'DSRs' : 'AEs'} · ${summary.ae_to_se_ratio}:1` : null },
  ]}
  <div class="w-full hub-container" style="display:grid;grid-template-columns:repeat({summaryStats.length + 1}, 1fr);gap:8px;margin-bottom:20px">
    <div class="p5-stat-chip" style="text-align:center">
      <div style="font-size:9px;color:var(--red);font-weight:800;text-transform:uppercase;letter-spacing:0.2em;margin-bottom:6px">Total SE iACV</div>
      <div style="font-size:26px;font-weight:900;color:var(--text);line-height:1">{fmt(summary.team_icav)}</div>
      {#if summary.se_icav_pct !== null && summary.team_total_icav !== null}
      <div style="font-size:11px;color:var(--text-muted);font-weight:600;margin-top:5px">{summary.se_icav_pct}% · {fmt(summary.team_total_icav)} total</div>
      {/if}
    </div>
    {#each summaryStats as s}
    <div class="p5-stat-chip" style="text-align:center">
      <div style="font-size:9px;color:var(--red);font-weight:800;text-transform:uppercase;letter-spacing:0.2em;margin-bottom:6px">{s.label}</div>
      <div style="font-size:26px;font-weight:900;color:var(--text);line-height:1">{s.val}</div>
      {#if s.sub}<div style="font-size:11px;color:var(--text-muted);font-weight:600;margin-top:5px">{s.sub}</div>{/if}
    </div>
    {/each}
  </div>

  <!-- iACV Trend Chart -->
  {#if summary.exp_trend && summary.exp_trend.length >= 2}
  {@const trend = summary.exp_trend}
  {@const W = 600}
  {@const H = 140}
  {@const PAD_L = 52}
  {@const PAD_R = 16}
  {@const PAD_T = 16}
  {@const PAD_B = 36}
  {@const cW = W - PAD_L - PAD_R}
  {@const cH = H - PAD_T - PAD_B}
  {@const maxV = Math.max(...trend.map(p => p.team_total_icav)) || 1}
  {@const xOf = (i: number) => trend.length === 1 ? PAD_L + cW / 2 : PAD_L + (i / (trend.length - 1)) * cW}
  {@const yOf = (v: number) => PAD_T + cH - (v / maxV) * cH}
  {@const pts = (key: 'team_total_icav' | 'team_act_icav' | 'team_exp_icav') => trend.map((p, i) => `${xOf(i)},${yOf(p[key])}`).join(' ')}
  {@const fmtM = (v: number) => v >= 1_000_000 ? `$${(v/1_000_000).toFixed(1)}M` : v >= 1_000 ? `$${Math.round(v/1_000)}K` : `$${v}`}
  {@const actLabel = summary.motion === 'ae' ? 'New Business' : 'Activate'}
  {@const expLabel = summary.motion === 'ae' ? 'Strategic' : 'Expansion'}
  <div class="w-full hub-container mb-6">
    <div class="p5-panel" style="padding:16px 18px">
      <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);margin-bottom:12px">Team iACV Trend</div>
      <svg viewBox="0 0 {W} {H}" style="width:100%;display:block;overflow:visible" aria-hidden="true">
        <!-- Y gridlines + labels -->
        {#each [0, 0.5, 1] as frac}
        {@const yg = PAD_T + cH - frac * cH}
        <line x1={PAD_L} y1={yg} x2={W - PAD_R} y2={yg} stroke="rgba(var(--red-rgb),0.08)" stroke-width="1"/>
        <text x={PAD_L - 6} y={yg + 4} text-anchor="end" font-size="9" fill="var(--text-muted)" font-family="inherit">{fmtM(frac * maxV)}</text>
        {/each}
        <!-- Area fills -->
        <polygon points="{trend.map((p,i) => `${xOf(i)},${yOf(p.team_act_icav)}`).join(' ')} {xOf(trend.length-1)},{PAD_T+cH} {xOf(0)},{PAD_T+cH}" fill="rgba(var(--red-rgb),0.10)"/>
        <polygon points="{trend.map((p,i) => `${xOf(i)},${yOf(p.team_exp_icav)}`).join(' ')} {xOf(trend.length-1)},{PAD_T+cH} {xOf(0)},{PAD_T+cH}" fill="rgba(100,160,255,0.10)"/>
        <!-- Lines -->
        <polyline points={pts('team_total_icav')} fill="none" stroke="var(--red)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
        <polyline points={pts('team_act_icav')} fill="none" stroke="rgba(var(--red-rgb),0.55)" stroke-width="1.5" stroke-dasharray="4 3" stroke-linejoin="round" stroke-linecap="round"/>
        <polyline points={pts('team_exp_icav')} fill="none" stroke="rgba(100,160,255,0.75)" stroke-width="1.5" stroke-dasharray="4 3" stroke-linejoin="round" stroke-linecap="round"/>
        <!-- Data points + labels -->
        {#each trend as p, i}
        {@const x = xOf(i)}
        {@const yT = yOf(p.team_total_icav)}
        <circle cx={x} cy={yT} r={p.is_current ? 4.5 : 3} fill={p.is_current ? 'var(--red)' : 'var(--bg)'} stroke="var(--red)" stroke-width="2"/>
        {#if p.is_current}
        <text x={x} y={yT - 9} text-anchor="middle" font-size="9" font-weight="700" fill="var(--red)" font-family="inherit">{fmtM(p.team_total_icav)}</text>
        {:else if i === 0 || i === trend.length - 2}
        <text x={x} y={yT - 8} text-anchor="middle" font-size="9" fill="var(--text-muted)" font-family="inherit">{fmtM(p.team_total_icav)}</text>
        {/if}
        <!-- X axis label -->
        <text x={x} y={H - 4} text-anchor="middle" font-size="9" fill={p.is_current ? 'var(--text)' : 'var(--text-muted)'} font-weight={p.is_current ? '700' : '400'} font-family="inherit">{p.period}</text>
        {/each}
      </svg>
      <!-- Legend -->
      <div style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap">
        <div style="display:flex;align-items:center;gap:5px">
          <svg width="18" height="4"><line x1="0" y1="2" x2="18" y2="2" stroke="var(--red)" stroke-width="2.5"/></svg>
          <span style="font-size:10px;color:var(--text-muted);font-weight:600">Total</span>
        </div>
        <div style="display:flex;align-items:center;gap:5px">
          <svg width="18" height="4"><line x1="0" y1="2" x2="18" y2="2" stroke="rgba(var(--red-rgb),0.55)" stroke-width="1.5" stroke-dasharray="4 3"/></svg>
          <span style="font-size:10px;color:var(--text-muted);font-weight:600">{actLabel}</span>
        </div>
        <div style="display:flex;align-items:center;gap:5px">
          <svg width="18" height="4"><line x1="0" y1="2" x2="18" y2="2" stroke="rgba(100,160,255,0.75)" stroke-width="1.5" stroke-dasharray="4 3"/></svg>
          <span style="font-size:10px;color:var(--text-muted);font-weight:600">{expLabel}</span>
        </div>
      </div>
    </div>
  </div>
  {/if}

  <!-- Nav — single column on mobile, 3-column on desktop -->
  <div class="w-full hub-container nav-grid" style="margin-bottom:24px">
    {#if !restricted}
    <a href="/se-scorecard-v2/report" class="p5-menu-btn nav-card">
      <span style="font-size:24px">📊</span>
      <div style="flex:1">
        <div style="font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">Full Report</div>
        <div style="font-size:11px;color:var(--text-muted);font-weight:500;margin-top:2px">Complete SE impact analysis</div>
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
        <div style="font-size:11px;color:var(--text-muted);font-weight:500;margin-top:2px">Individual SE impact view</div>
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
