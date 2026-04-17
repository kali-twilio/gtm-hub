<script lang="ts">
  import { getSFGhostWork } from '$lib/api';
  import { theme, sfTeam, sfPeriod, sfSubteam } from '$lib/stores';

  function textColor(isDark: boolean) {
    return isDark ? 'rgba(255,255,255,0.88)' : 'rgba(13,18,43,0.88)';
  }

  let data: any      = $state(null);
  let loading        = $state(false);
  let showLoading    = $state(false);
  let error          = $state('');
  let expanded       = $state<Record<string, boolean>>({});

  const p5 = $derived($theme === 'p5');

  async function load(team: string, period: string, subteam: string) {
    loading = true;
    error   = '';
    data    = null;
    const t = setTimeout(() => { if (loading) showLoading = true; }, 400);
    const result = await getSFGhostWork(team, period, subteam !== 'none' ? subteam : '');
    clearTimeout(t);
    loading     = false;
    showLoading = false;
    if (result && !result.error) {
      data = result;
    } else {
      error = result?.error || 'Failed to load ghost work data.';
    }
  }

  $effect(() => {
    const team    = $sfTeam;
    const period  = $sfPeriod;
    const subteam = $sfSubteam;
    load(team, period, subteam !== 'none' ? subteam : '');
  });

  function toggleSE(name: string) {
    expanded[name] = !expanded[name];
  }

  function ghostColor(count: number): string {
    if (count >= 10) return p5 ? '#ef4444' : '#dc2626';
    if (count >= 5)  return p5 ? '#f97316' : '#ea580c';
    if (count >= 2)  return p5 ? '#eab308' : '#ca8a04';
    return p5 ? 'rgba(255,255,255,0.4)' : 'rgba(13,18,43,0.4)';
  }
</script>

<a href="/se-scorecard-v2" class="p5-back-btn">◀ Back</a>

<div style="max-width:1100px;margin:0 auto;padding:32px 24px 64px">

  <!-- Title -->
  <div style="margin-bottom:28px">
    <h1 style="font-size:22px;font-weight:700;color:{textColor(p5)};margin:0 0 6px">
      Ghost Work Detector
    </h1>
    <p style="font-size:14px;color:{p5?'rgba(255,255,255,0.45)':'rgba(13,18,43,0.45)'};margin:0">
      Activity on accounts with no open opportunity closing this quarter or next.
      {#if data}
        &nbsp;·&nbsp;<span style="font-weight:600;color:{textColor(p5)}">{data.quarter}</span>
        &nbsp;·&nbsp;<span style="font-weight:600;color:{textColor(p5)}">{data.team_label}</span>
      {/if}
    </p>
  </div>

  <!-- Loading -->
  {#if showLoading}
    <div style="color:{p5?'rgba(255,255,255,0.4)':'rgba(13,18,43,0.4)'};font-size:14px;padding:48px 0;text-align:center">
      Loading…
    </div>
  {/if}

  <!-- Error -->
  {#if error}
    <div style="background:{p5?'rgba(239,68,68,0.1)':'#fef2f2'};border:1px solid {p5?'rgba(239,68,68,0.3)':'#fca5a5'};border-radius:8px;padding:16px 20px;color:{p5?'#f87171':'#dc2626'};font-size:14px">
      {error}
    </div>
  {/if}

  {#if data && !showLoading}

    <!-- Insights banner -->
    {#if data.insights && data.insights.length}
      <div style="background:{p5?'rgba(255,255,255,0.04)':'#f8f9fc'};border:1px solid {p5?'rgba(255,255,255,0.08)':'rgba(13,18,43,0.1)'};border-radius:10px;padding:18px 20px;margin-bottom:28px">
        <div style="font-size:11px;font-weight:700;letter-spacing:0.08em;color:{p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'};text-transform:uppercase;margin-bottom:10px">
          Insights
        </div>
        {#each data.insights as insight}
          <div style="font-size:14px;color:{textColor(p5)};line-height:1.55;margin-bottom:6px;display:flex;gap:8px;align-items:flex-start">
            <span style="color:var(--red);flex-shrink:0;margin-top:1px">●</span>
            <span>{insight}</span>
          </div>
        {/each}
      </div>
    {/if}

    <!-- Summary chips -->
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:28px">
      {#each [
        { label: 'SEs with ghost work',    value: data.by_se?.length ?? 0 },
        { label: 'Ghost accounts',          value: data.total_ghost_accounts ?? 0 },
        { label: 'Total ghost activities',  value: data.total_ghost_activity ?? 0 },
      ] as chip}
        <div style="background:{p5?'rgba(255,255,255,0.05)':'white'};border:1px solid {p5?'rgba(255,255,255,0.1)':'rgba(13,18,43,0.1)'};border-radius:8px;padding:12px 18px;min-width:140px">
          <div style="font-size:22px;font-weight:700;color:{textColor(p5)}">{chip.value}</div>
          <div style="font-size:12px;color:{p5?'rgba(255,255,255,0.4)':'rgba(13,18,43,0.4)'};margin-top:2px">{chip.label}</div>
        </div>
      {/each}
    </div>

    <!-- No ghost work -->
    {#if !data.by_se || data.by_se.length === 0}
      <div style="text-align:center;padding:64px 0;color:{p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'};font-size:15px">
        No ghost work detected this period. All activity is tied to open pipeline.
      </div>

    {:else}

      <!-- Per-SE cards -->
      {#each data.by_se as se}
        <div style="background:{p5?'rgba(255,255,255,0.03)':'white'};border:1px solid {p5?'rgba(255,255,255,0.08)':'rgba(13,18,43,0.09)'};border-radius:10px;margin-bottom:12px;overflow:hidden">

          <!-- SE header row -->
          <button
            onclick={() => toggleSE(se.se_name)}
            style="width:100%;display:flex;align-items:center;justify-content:space-between;padding:14px 18px;background:none;border:none;cursor:pointer;text-align:left;gap:12px"
          >
            <div style="display:flex;align-items:center;gap:12px;flex:1;min-width:0">
              <span style="font-size:15px;font-weight:600;color:{textColor(p5)};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                {se.se_name}
              </span>
              <span style="font-size:12px;color:{p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'};flex-shrink:0">
                {se.ghost_account_count} account{se.ghost_account_count !== 1 ? 's' : ''}
              </span>
            </div>
            <div style="display:flex;align-items:center;gap:16px;flex-shrink:0">
              <span style="font-size:13px;font-weight:600;color:{ghostColor(se.total_ghost_activity)}">
                {se.total_ghost_activity} activit{se.total_ghost_activity !== 1 ? 'ies' : 'y'}
              </span>
              <span style="color:{p5?'rgba(255,255,255,0.3)':'rgba(13,18,43,0.3)'};font-size:11px;transform:{expanded[se.se_name]?'rotate(90deg)':'rotate(0deg)'};transition:transform 0.15s">
                ▶
              </span>
            </div>
          </button>

          <!-- Ghost accounts table -->
          {#if expanded[se.se_name]}
            <div style="border-top:1px solid {p5?'rgba(255,255,255,0.06)':'rgba(13,18,43,0.06)'}">
              <table style="width:100%;border-collapse:collapse;font-size:13px">
                <thead>
                  <tr style="color:{p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'};font-size:11px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase">
                    <th style="padding:8px 18px;text-align:left;font-weight:600">Account</th>
                    <th style="padding:8px 12px;text-align:center;font-weight:600">Emails</th>
                    <th style="padding:8px 12px;text-align:center;font-weight:600">Meetings</th>
                    <th style="padding:8px 12px;text-align:center;font-weight:600">Total</th>
                    <th style="padding:8px 18px;text-align:left;font-weight:600">Last Activity</th>
                  </tr>
                </thead>
                <tbody>
                  {#each se.ghost_accounts as acct}
                    <tr style="border-top:1px solid {p5?'rgba(255,255,255,0.04)':'rgba(13,18,43,0.04)'}">
                      <td style="padding:9px 18px;color:{textColor(p5)};max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                        {acct.account_name || '—'}
                      </td>
                      <td style="padding:9px 12px;text-align:center;color:{acct.email_count>0?tc(p5):p5?'rgba(255,255,255,0.2)':'rgba(13,18,43,0.2)'}">
                        {acct.email_count}
                      </td>
                      <td style="padding:9px 12px;text-align:center;color:{acct.meeting_count>0?tc(p5):p5?'rgba(255,255,255,0.2)':'rgba(13,18,43,0.2)'}">
                        {acct.meeting_count}
                      </td>
                      <td style="padding:9px 12px;text-align:center;font-weight:600;color:{ghostColor(acct.total_activity)}">
                        {acct.total_activity}
                      </td>
                      <td style="padding:9px 18px;color:{p5?'rgba(255,255,255,0.4)':'rgba(13,18,43,0.4)'}">
                        {acct.last_activity || '—'}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}

        </div>
      {/each}
    {/if}
  {/if}
</div>
