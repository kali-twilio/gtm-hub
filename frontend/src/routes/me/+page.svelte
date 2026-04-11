<script lang="ts">
  import { onMount } from 'svelte';
  import { user } from '$lib/stores';
  import { getSEs, fmt } from '$lib/api';
  import { goto } from '$app/navigation';

  let ses: any[] = $state([]);
  let selected = $state('');
  let se: any = $state(null);

  const tierColors: Record<string, {color: string, bg: string}> = {
    Elite:   { color: '#FFD600', bg: 'rgba(255,214,0,0.15)' },
    Strong:  { color: '#4da6ff', bg: 'rgba(77,166,255,0.15)' },
    Steady:  { color: '#00e87a', bg: 'rgba(0,232,122,0.12)' },
    Develop: { color: '#ff6b6b', bg: 'rgba(255,107,107,0.12)' },
  };

  const flagColors: Record<string, string> = {
    PIPELINE: '#4da6ff', EXPANSION: '#00e87a', HYGIENE: '#ff6b6b',
    ACTIVATE: '#ffaa44', RISK: '#ff4466', MOTION: '#b87cff', STRENGTH: '#00d4ff',
  };

  onMount(async () => {
    const data = await getSEs();
    if (!data) return;
    ses = data;
    if ($user?.is_se && $user.se_name) {
      selected = $user.se_name;
      se = ses.find(s => s.name === selected) ?? null;
    }
  });

  function onSelect(e: Event) {
    selected = (e.target as HTMLSelectElement).value;
    se = ses.find(s => s.name === selected) ?? null;
  }

  function isOwnProfile() { return $user?.is_se ?? false; }
</script>

<div class="w-full max-w-2xl mx-auto px-4 py-8">

  <!-- Header -->
  <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:28px">
    <div>
      <div class="p5-badge" style="margin-bottom:8px">DSR Sales Engineering</div>
      <h1 style="font-size:32px;font-weight:900;font-style:italic;text-transform:uppercase;text-shadow:2px 2px 0 var(--red)">My Stats</h1>
      <div style="width:50px;height:3px;background:var(--red);transform:skewX(-20deg);margin-top:8px;box-shadow:0 0 8px var(--red)"></div>
    </div>
    <div style="text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:8px">
      <span style="font-size:11px;color:rgba(255,255,255,0.25);font-weight:600">{$user?.email}</span>
      {#if isOwnProfile()}
        <a href="/logout" style="font-size:12px;color:rgba(232,0,61,0.7);font-weight:700;text-decoration:none;font-style:italic;text-transform:uppercase;letter-spacing:0.1em">Sign out ◆</a>
      {/if}
    </div>
  </div>

  <!-- Fixed back button (managers only) -->
  {#if !isOwnProfile()}
  <div style="position:fixed;top:14px;left:16px;z-index:9999">
    <a href="/" class="p5-back-btn">◀ Back</a>
  </div>
  {/if}

  <!-- SE Selector (managers only) -->
  {#if !isOwnProfile()}
  <div style="margin-bottom:24px">
    <div class="p5-badge" style="font-size:10px;margin-bottom:10px">Select Operative</div>
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
  {@const tc = tierColors[se.tier] ?? tierColors.Steady}
  <div class="p5-panel" style="padding:24px;width:100%">

    <!-- Name + total -->
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px">
      <div>
        <div style="font-size:24px;font-weight:900;font-style:italic;text-transform:uppercase;text-shadow:2px 2px 0 rgba(232,0,61,0.5)">{se.name}</div>
        <span style="display:inline-block;background:{tc.bg};color:{tc.color};border:1px solid {tc.color}40;padding:2px 12px 2px 8px;font-size:10px;font-weight:700;font-style:italic;text-transform:uppercase;letter-spacing:0.18em;clip-path:polygon(0 0,100% 0,calc(100% - 8px) 100%,0 100%);margin-top:4px">{se.tier}</span>
      </div>
      <div style="text-align:right">
        <div style="font-size:36px;font-weight:900;font-style:italic;line-height:1;text-shadow:3px 3px 0 var(--red)">{fmt(se.total_icav)}</div>
        <div style="font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin-top:2px">Total iACV</div>
      </div>
    </div>

    <div style="height:2px;background:linear-gradient(90deg,var(--red),transparent);transform:skewX(-20deg);transform-origin:left;margin-bottom:20px"></div>

    <!-- 2×2 stats -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:20px">
      <div style="background:var(--panel);border:1px solid rgba(77,166,255,0.15);border-left:4px solid #4da6ff;padding:14px 16px;position:relative;overflow:hidden">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:italic;color:#4da6ff;margin-bottom:6px">Activate</div>
        <div style="font-size:26px;font-weight:900;font-style:italic;color:#7dc4ff;line-height:1;margin-bottom:6px">{fmt(se.act_icav)}</div>
        <div style="font-size:12px;color:rgba(255,255,255,0.4)">{se.act_wins} wins<br>Avg {fmt(se.act_avg)} · Med {fmt(se.act_median)}</div>
      </div>
      <div style="background:var(--panel);border:1px solid rgba(0,232,122,0.15);border-left:4px solid #00e87a;padding:14px 16px;position:relative;overflow:hidden">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:italic;color:#00e87a;margin-bottom:6px">
          Expansion · {se.exp_growing ? 'Growing' : 'Retaining'}
        </div>
        <div style="font-size:26px;font-weight:900;font-style:italic;color:#4dffa0;line-height:1;margin-bottom:6px">{fmt(se.exp_icav)}</div>
        <div style="font-size:12px;color:rgba(255,255,255,0.4)">{se.exp_wins} wins<br>Avg {fmt(se.exp_avg)} · Med {fmt(se.exp_median)}</div>
      </div>
      <div style="background:var(--panel);border:1px solid {se.owl_pct < 75 ? 'rgba(232,0,61,0.3)' : 'rgba(255,255,255,0.08)'};border-left:4px solid {se.owl_pct < 75 ? 'var(--red)' : 'rgba(255,255,255,0.2)'};padding:14px 16px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:italic;color:rgba(255,255,255,0.5);margin-bottom:6px">Owl %</div>
        <div style="font-size:26px;font-weight:900;font-style:italic;color:{se.owl_pct < 75 ? '#ff6b6b' : 'white'};line-height:1;margin-bottom:6px">{se.owl_pct}%</div>
        <div style="font-size:12px;color:rgba(255,255,255,0.4)">{se.owl_pct < 75 ? '⚠ Below 75% threshold' : '◆ Hygiene on track'}</div>
      </div>
      <div style="background:var(--panel);border:1px solid rgba(184,124,255,0.15);border-left:4px solid #b87cff;padding:14px 16px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:italic;color:#b87cff;margin-bottom:6px">Future Pipeline</div>
        <div style="font-size:26px;font-weight:900;font-style:italic;color:#d4aaff;line-height:1;margin-bottom:6px">{se.future_emails} <span style="font-size:16px">emails</span></div>
        <div style="font-size:12px;color:rgba(255,255,255,0.4)">{se.future_pct}% of activity out-of-quarter</div>
      </div>
    </div>

    <!-- Largest deal -->
    {#if se.largest_deal_value > 0}
    <div style="background:rgba(0,0,0,0.3);border:1px solid rgba(232,0,61,0.15);border-left:4px solid var(--red);padding:14px 16px;margin-bottom:20px">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.2em;font-style:italic;color:rgba(255,255,255,0.4);margin-bottom:8px">◆ Largest Deal</div>
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
        <div style="font-size:14px;color:rgba(255,255,255,0.75);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{se.largest_deal}</div>
        <div style="font-size:16px;font-weight:900;font-style:italic;color:var(--yellow);white-space:nowrap">{fmt(se.largest_deal_value)}</div>
      </div>
      {#if se.largest_deal_dsr}<div style="font-size:11px;color:rgba(255,255,255,0.25);margin-top:4px">{se.largest_deal_dsr}</div>{/if}
    </div>
    {/if}

    <!-- Flags -->
    {#if se.flags?.length}
    <div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <div class="p5-badge" style="font-size:10px">Intel Report</div>
        <div style="flex:1;height:1px;background:rgba(232,0,61,0.2)"></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        {#each se.flags as [cat, msg]}
        {@const fc = flagColors[cat] ?? '#aaaaaa'}
        <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 14px;border-left:4px solid {fc};background:rgba(0,0,0,0.2)">
          <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;font-style:italic;color:{fc};width:72px;flex-shrink:0">{cat}</span>
          <span style="font-size:13px;font-weight:500;color:rgba(255,255,255,0.75)">{msg}</span>
        </div>
        {/each}
      </div>
    </div>
    {/if}

  </div>
  {:else if selected}
  <div style="background:rgba(232,0,61,0.1);border:1px solid rgba(232,0,61,0.4);border-left:4px solid var(--red);padding:14px 18px;font-size:14px;color:#ff7070;font-weight:700;font-style:italic">
    ⚠ Operative "{selected}" not found in report data.
  </div>
  {/if}

</div>
