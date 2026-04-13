<script lang="ts">
  import { onMount } from 'svelte';
  import { user, theme, sfTeam, sfPeriod } from '$lib/stores';
  import { getSFSEs, fmt } from '$lib/api';
  import { tc, fc } from '$lib/colors';

  let ses: any[] = $state([]);
  let selected = $state('');
  let se: any = $state(null);
  let periodLabel = $state('');

  onMount(async () => {
    const [data, periodsData] = await Promise.all([
      getSFSEs($sfTeam, $sfPeriod),
      fetch('/api/sfscorecard/periods').then(r => r.ok ? r.json() : []),
    ]);
    if (!data) return;
    const found = periodsData.find((p: any) => p.key === $sfPeriod);
    periodLabel = found ? found.label : $sfPeriod;
    ses = [...data].sort((a, b) => a.name.localeCompare(b.name));
    if ($user?.sf_is_se && $user.sf_se_name) {
      selected = $user.sf_se_name;
      se = ses.find(s => s.name === selected) ?? null;
    }
  });

  function onSelect(e: Event) {
    selected = (e.target as HTMLSelectElement).value;
    se = ses.find(s => s.name === selected) ?? null;
  }

  const isOwnProfile = () => $user?.sf_is_se ?? false;
</script>

<div class="w-full max-w-2xl mx-auto px-4 py-8">

  <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:28px">
    <div>
      <div class="p5-badge" style="margin-bottom:8px">SF Scorecard · {periodLabel}</div>
      <h1 style="font-size:32px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:2px 2px 0 var(--red)':''}">My Stats</h1>
      <div style="width:50px;height:3px;background:var(--red);{$theme==='p5'?'transform:skewX(-20deg);box-shadow:0 0 8px var(--red)':'border-radius:2px'};margin-top:8px"></div>
    </div>
    <div style="text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:8px">
      <span style="font-size:11px;color:var(--text-muted);font-weight:600">{$user?.email}</span>
      {#if isOwnProfile()}
        <a href="/logout" style="font-size:12px;color:var(--red);font-weight:700;text-decoration:none;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.1em">Sign out {$theme==='p5'?'◆':''}</a>
      {/if}
    </div>
  </div>

  {#if !isOwnProfile()}
  <div style="position:fixed;top:{$theme==='twilio'?'68px':'26px'};left:{$theme==='twilio'?'16px':'48px'};z-index:9999">
    <a href="/sfscorecard" class="p5-back-btn">◀ Back</a>
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

  {#if se}
  {@const colors = tc(se.tier, $theme)}
  <div class="p5-panel" style="padding:24px;width:100%">

    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px">
      <div>
        <div style="font-size:24px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:2px 2px 0 rgba(232,0,61,0.5)':''}">{se.name}</div>
        <span style="display:inline-block;background:{colors.bg};color:{colors.color};border:1px solid {colors.color}40;padding:2px 12px 2px 8px;font-size:10px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.18em;{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 8px) 100%,0 100%)':'border-radius:4px'};margin-top:4px">{se.tier}</span>
      </div>
      <div style="text-align:right">
        <div style="font-size:36px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};line-height:1;color:var(--text);{$theme==='p5'?'text-shadow:3px 3px 0 var(--red)':''}">{fmt(se.total_icav)}</div>
        <div style="font-size:10px;color:var(--text-muted);letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin-top:2px">Total iACV</div>
      </div>
    </div>

    <div style="height:2px;background:linear-gradient(90deg,var(--red),transparent);{$theme==='p5'?'transform:skewX(-20deg);transform-origin:left':'border-radius:1px'};margin-bottom:20px"></div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:20px">
      <div style="background:rgba(var(--act-rgb),0.08);border:1px solid rgba(var(--act-rgb),0.2);border-left:4px solid var(--act-color);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--act-color);margin-bottom:6px">Activate</div>
        <div style="font-size:26px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--act-glow);line-height:1;margin-bottom:6px">{fmt(se.act_icav)}</div>
        <div style="font-size:12px;color:var(--text-muted)">{se.act_wins} wins<br>Avg {fmt(se.act_avg)} · Med {fmt(se.act_median)}</div>
      </div>
      <div style="background:rgba(var(--exp-rgb),0.08);border:1px solid rgba(var(--exp-rgb),0.2);border-left:4px solid var(--exp-color);padding:14px 16px;{$theme==='twilio'?'border-radius:8px':''}">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-color);margin-bottom:6px">
          Expansion · {se.exp_growing ? 'Growing' : 'Retaining'}
        </div>
        <div style="font-size:26px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-glow);line-height:1;margin-bottom:6px">{fmt(se.exp_icav)}</div>
        <div style="font-size:12px;color:var(--text-muted)">{se.exp_wins} wins<br>Avg {fmt(se.exp_avg)} · Med {fmt(se.exp_median)}</div>
      </div>
    </div>

    {#if se.largest_deal_value > 0}
    <div style="background:rgba(var(--red-rgb),0.04);border:1px solid rgba(var(--red-rgb),0.15);border-left:4px solid var(--red);padding:14px 16px;margin-bottom:20px;{$theme==='twilio'?'border-radius:8px':''}">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text-muted);margin-bottom:8px">{$theme==='p5'?'◆ ':''}Largest Deal</div>
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
  {:else if selected}
  <div style="background:rgba(var(--red-rgb),0.08);border:1px solid rgba(var(--red-rgb),0.4);border-left:4px solid var(--red);padding:14px 18px;font-size:14px;color:var(--red);font-weight:700">
    ⚠ "{selected}" not found in report data.
  </div>
  {/if}

</div>
