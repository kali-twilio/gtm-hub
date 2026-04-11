<script lang="ts">
  import { onMount } from 'svelte';
  import { getReport, fmt } from '$lib/api';

  let data: any = $state(null);

  const tierColors: Record<string, {color:string,bg:string}> = {
    Elite:   { color:'#FFD600', bg:'rgba(255,214,0,0.15)' },
    Strong:  { color:'#4da6ff', bg:'rgba(77,166,255,0.15)' },
    Steady:  { color:'#00e87a', bg:'rgba(0,232,122,0.12)' },
    Develop: { color:'#ff6b6b', bg:'rgba(255,107,107,0.12)' },
  };
  const flagColors: Record<string,string> = {
    PIPELINE:'#4da6ff', EXPANSION:'#00e87a', HYGIENE:'#ff6b6b',
    ACTIVATE:'#ffaa44', RISK:'#ff4466', MOTION:'#b87cff', STRENGTH:'#00d4ff',
  };

  function bar(value: number, max: number, color: string) {
    const w = max ? Math.round(value / max * 100) : 0;
    return `<div style="min-width:80px;width:100%;background:rgba(255,255,255,0.08);border-radius:2px;height:5px"><div style="height:5px;border-radius:2px;background:${color};width:${w}%"></div></div>`;
  }

  onMount(async () => { data = await getReport(); });
</script>

{#if !data}
<div class="min-h-screen flex items-center justify-center">
  <div style="font-size:18px;font-weight:700;font-style:italic;color:rgba(255,255,255,0.4)">Loading intel…</div>
</div>
{:else}

<div style="position:fixed;top:14px;left:16px;z-index:9999">
  <a href="/" class="p5-back-btn">◀ Back</a>
</div>

<div style="max-width:1200px;margin:0 auto;padding:60px 24px 40px">

  <!-- Header -->
  <div style="margin-bottom:28px">
    <div class="p5-badge" style="margin-bottom:10px">DSR Sales Engineering</div>
    <h1 style="font-size:36px;font-weight:900;font-style:italic;text-transform:uppercase;text-shadow:3px 3px 0 var(--red)">SE Scorecard</h1>
    <p style="font-size:13px;color:rgba(255,255,255,0.3);font-weight:600;margin-top:4px">{data.total} SEs · Ranked across revenue, expansion quality, pipeline &amp; hygiene</p>
  </div>

  <!-- Summary -->
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px">
    {#each [{label:'Team Total iACV', val:fmt(data.team_icav)},{label:'Team Avg Owl %',val:data.avg_owl+'%'},{label:'SEs Analysed',val:String(data.total)}] as s}
    <div class="p5-panel" style="padding:18px 20px">
      <div style="font-size:10px;color:rgba(232,0,61,0.8);font-weight:700;text-transform:uppercase;letter-spacing:0.18em;font-style:italic;margin-bottom:6px">{s.label}</div>
      <div style="font-size:28px;font-weight:900;font-style:italic;text-shadow:2px 2px 0 var(--red)">{s.val}</div>
    </div>
    {/each}
  </div>

  <!-- Overall Rankings -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(232,0,61,0.15)">
      <h2 style="font-size:15px;font-weight:700;font-style:italic;text-transform:uppercase;margin-bottom:2px">Overall Rankings</h2>
      <p style="font-size:12px;color:rgba(255,255,255,0.35)">Total iACV 65% · Activate 10% · Expansion quality 10% · Future pipeline 8% · Owl% 7%</p>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(232,0,61,0.08)">
          <tr>{#each ['#','SE','Activate','Expansion','Total iACV','Owl%','Future Q%','Tier'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:rgba(232,0,61,0.8);font-style:italic;white-space:nowrap">{h}</th>{/each}</tr>
        </thead>
        <tbody>
          {#each data.ranked as se}
          {@const tc = tierColors[se.tier] ?? tierColors.Steady}
          <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
            <td style="padding:10px 16px;color:rgba(255,255,255,0.3);font-weight:700;font-style:italic">{se.rank}</td>
            <td style="padding:10px 16px;font-weight:700;color:white">{se.name}</td>
            <td style="padding:10px 16px;color:#7dc4ff;font-weight:700">{fmt(se.act_icav)}</td>
            <td style="padding:10px 16px;color:#4dffa0;font-weight:700">{fmt(se.exp_icav)}</td>
            <td style="padding:10px 16px;color:white;font-weight:900;font-style:italic">{fmt(se.total_icav)}</td>
            <td style="padding:10px 16px;color:{se.owl_pct < 75 ? '#ff6b6b' : 'rgba(255,255,255,0.6)'};font-weight:700">{se.owl_pct}%</td>
            <td style="padding:10px 16px;color:rgba(255,255,255,0.6)">{se.future_pct}%</td>
            <td style="padding:10px 16px"><span style="display:inline-block;padding:2px 10px 2px 8px;font-size:10px;font-weight:700;font-style:italic;text-transform:uppercase;letter-spacing:0.1em;background:{tc.bg};color:{tc.color};clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)">{se.tier}</span></td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Activate + Expansion -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
    <div class="p5-panel">
      <div style="padding:14px 20px;border-bottom:1px solid rgba(232,0,61,0.15)">
        <h2 style="font-size:15px;font-weight:700;font-style:italic;text-transform:uppercase;margin-bottom:2px">Activate — New Business</h2>
        <p style="font-size:12px;color:rgba(255,255,255,0.35)">New logos, no prior contract, deals &gt;$30K</p>
      </div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="background:rgba(232,0,61,0.08)"><tr>{#each ['SE','Wins','iACV','Avg','Median','Vol'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:rgba(232,0,61,0.8);font-style:italic">{h}</th>{/each}</tr></thead>
          <tbody>
            {#each data.act_sorted as se}
            <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
              <td style="padding:10px 16px;font-weight:700;color:white">{se.name}</td>
              <td style="padding:10px 16px;color:rgba(255,255,255,0.5);text-align:center">{se.act_wins}</td>
              <td style="padding:10px 16px;color:#7dc4ff;font-weight:700">{fmt(se.act_icav)}</td>
              <td style="padding:10px 16px;color:rgba(255,255,255,0.5)">{fmt(se.act_avg)}</td>
              <td style="padding:10px 16px;color:rgba(255,255,255,0.5)">{fmt(se.act_median)}</td>
              <td style="padding:10px 16px;min-width:80px">{@html bar(se.act_icav, data.max_act, '#3B82F6')}</td>
            </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
    <div class="p5-panel">
      <div style="padding:14px 20px;border-bottom:1px solid rgba(232,0,61,0.15)">
        <h2 style="font-size:15px;font-weight:700;font-style:italic;text-transform:uppercase;margin-bottom:2px">Expansion — Land &amp; Expand</h2>
        <p style="font-size:12px;color:rgba(255,255,255,0.35)">Existing customers · $0 median = flat retentions</p>
      </div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="background:rgba(232,0,61,0.08)"><tr>{#each ['SE','Wins','iACV','Avg','Median','Status','Vol'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:rgba(232,0,61,0.8);font-style:italic">{h}</th>{/each}</tr></thead>
          <tbody>
            {#each data.exp_sorted as se}
            <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
              <td style="padding:10px 16px;font-weight:700;color:white">{se.name}</td>
              <td style="padding:10px 16px;color:rgba(255,255,255,0.5);text-align:center">{se.exp_wins}</td>
              <td style="padding:10px 16px;color:#4dffa0;font-weight:700">{fmt(se.exp_icav)}</td>
              <td style="padding:10px 16px;color:rgba(255,255,255,0.5)">{fmt(se.exp_avg)}</td>
              <td style="padding:10px 16px;color:rgba(255,255,255,0.5)">{fmt(se.exp_median)}</td>
              <td style="padding:10px 16px">
                {#if se.exp_growing}
                  <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;font-style:italic;background:rgba(0,232,122,0.12);color:#00e87a;border:1px solid rgba(0,232,122,0.3);clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)">Growing</span>
                {:else}
                  <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;font-style:italic;background:rgba(255,255,255,0.05);color:rgba(255,255,255,0.35);border:1px solid rgba(255,255,255,0.1);clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)">Retaining</span>
                {/if}
              </td>
              <td style="padding:10px 16px;min-width:80px">{@html bar(se.exp_icav, data.max_exp, '#10B981')}</td>
            </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Pipeline, Deals, Trends, Profiles (condensed) -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(232,0,61,0.15)">
      <h2 style="font-size:15px;font-weight:700;font-style:italic;text-transform:uppercase;margin-bottom:2px">Pipeline Health</h2>
      <p style="font-size:12px;color:rgba(255,255,255,0.35)">Owl% = Salesforce hygiene · FutQ% = out-of-quarter emails</p>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(232,0,61,0.08)"><tr>{#each ['SE','Owl%','Act InQ','Act OutQ','Exp InQ','Exp OutQ','FutQ%','Investment'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:rgba(232,0,61,0.8);font-style:italic">{h}</th>{/each}</tr></thead>
        <tbody>
          {#each data.pipe_sorted as se}
          <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
            <td style="padding:10px 16px;font-weight:700;color:white">{se.name}</td>
            <td style="padding:10px 16px;color:{se.owl_pct < 75 ? '#ff6b6b' : 'rgba(255,255,255,0.6)'};font-weight:700">{se.owl_pct}%</td>
            <td style="padding:10px 16px;color:rgba(255,255,255,0.5);text-align:center">{se.email_act_inq}</td>
            <td style="padding:10px 16px;color:rgba(255,255,255,0.5);text-align:center">{se.email_act_outq}</td>
            <td style="padding:10px 16px;color:rgba(255,255,255,0.5);text-align:center">{se.email_exp_inq}</td>
            <td style="padding:10px 16px;color:rgba(255,255,255,0.5);text-align:center">{se.email_exp_outq}</td>
            <td style="padding:10px 16px;color:rgba(255,255,255,0.6)">{se.future_pct}%</td>
            <td style="padding:10px 16px;min-width:80px">{@html bar(se.future_emails, data.max_fut, '#8b5cf6')}</td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(232,0,61,0.15)"><h2 style="font-size:15px;font-weight:700;font-style:italic;text-transform:uppercase">Largest Deals</h2></div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(232,0,61,0.08)"><tr>{#each ['SE','Value','DSR','Deal'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:rgba(232,0,61,0.8);font-style:italic">{h}</th>{/each}</tr></thead>
        <tbody>
          {#each data.deal_sorted as se}
          <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
            <td style="padding:10px 16px;font-weight:700;color:white">{se.name}</td>
            <td style="padding:10px 16px;color:var(--yellow);font-weight:900;font-style:italic">{fmt(se.largest_deal_value)}</td>
            <td style="padding:10px 16px;color:rgba(255,255,255,0.4)">{se.largest_deal_dsr}</td>
            <td style="padding:10px 16px;color:rgba(255,255,255,0.65);font-size:12px">{se.largest_deal.slice(0,60)}{se.largest_deal.length > 60 ? '…' : ''}</td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(232,0,61,0.15)"><h2 style="font-size:15px;font-weight:700;font-style:italic;text-transform:uppercase">Trends &amp; Flags</h2></div>
    <div style="padding:16px;display:flex;flex-direction:column;gap:8px">
      {#each data.trends as [cat, msg]}
      {@const fc = flagColors[cat] ?? '#aaaaaa'}
      <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 14px;border-left:4px solid {fc};background:rgba(0,0,0,0.2)">
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;font-style:italic;color:{fc};width:80px;flex-shrink:0">{cat}</span>
        <span style="font-size:13px;font-weight:500;color:rgba(255,255,255,0.7)">{msg}</span>
      </div>
      {/each}
    </div>
  </div>

  <!-- SE Profiles grid -->
  <div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
      <div class="p5-badge">SE Profiles</div>
      <div style="flex:1;height:1px;background:rgba(232,0,61,0.2)"></div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
      {#each data.ranked as se}
      {@const tc = tierColors[se.tier] ?? tierColors.Steady}
      <div class="p5-panel" style="padding:16px;display:flex;flex-direction:column;gap:10px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
              <span style="font-size:11px;color:rgba(255,255,255,0.25);font-style:italic">#{se.rank}</span>
              <span style="font-size:14px;font-weight:700;font-style:italic;text-transform:uppercase">{se.name}</span>
            </div>
            <span style="display:inline-block;background:{tc.bg};color:{tc.color};border:1px solid {tc.color}40;padding:2px 10px 2px 8px;font-size:10px;font-weight:700;font-style:italic;text-transform:uppercase;letter-spacing:0.12em;clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)">{se.tier}</span>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:18px;font-weight:900;font-style:italic;text-shadow:1px 1px 0 var(--red)">{fmt(se.total_icav)}</div>
            <div style="font-size:10px;color:rgba(255,255,255,0.25);text-transform:uppercase;letter-spacing:0.12em">total iACV</div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
          <div style="background:rgba(77,166,255,0.08);border:1px solid rgba(77,166,255,0.2);border-left:3px solid #4da6ff;padding:10px">
            <div style="font-size:9px;color:#4da6ff;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:4px">Activate</div>
            <div style="font-size:14px;font-weight:900;font-style:italic;color:#7dc4ff">{fmt(se.act_icav)}</div>
            <div style="font-size:11px;color:rgba(255,255,255,0.3);margin-top:2px">{se.act_wins} wins</div>
            {@html bar(se.act_icav, data.max_act_icav, '#3B82F6')}
          </div>
          <div style="background:rgba(0,232,122,0.08);border:1px solid rgba(0,232,122,0.2);border-left:3px solid #00e87a;padding:10px">
            <div style="font-size:9px;color:#00e87a;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:4px">Expansion</div>
            <div style="font-size:14px;font-weight:900;font-style:italic;color:#4dffa0">{fmt(se.exp_icav)}</div>
            <div style="font-size:11px;color:rgba(255,255,255,0.3);margin-top:2px">{se.exp_wins} wins</div>
            {@html bar(se.exp_icav, data.max_exp_icav, '#10B981')}
          </div>
        </div>
        <div style="display:flex;gap:14px;font-size:12px;color:rgba(255,255,255,0.35);border-top:1px solid rgba(232,0,61,0.1);padding-top:8px">
          <span>Owl <strong style="color:{se.owl_pct < 75 ? '#ff6b6b' : 'white'}">{se.owl_pct}%</strong></span>
          <span>FutQ <strong style="color:white">{se.future_pct}%</strong></span>
          <span>Fwd <strong style="color:white">{se.future_emails}</strong></span>
        </div>
        {#if se.flags?.length}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px">
          {#each se.flags as [cat, msg]}
          {@const fc = flagColors[cat] ?? '#aaaaaa'}
          <div style="border-left:3px solid {fc};background:rgba(0,0,0,0.2);padding:6px 8px;min-height:44px">
            <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:{fc};margin-bottom:2px">{cat}</div>
            <div style="font-size:10px;color:rgba(255,255,255,0.6);line-height:1.3">{msg}</div>
          </div>
          {/each}
        </div>
        {/if}
      </div>
      {/each}
    </div>
  </div>

</div>
{/if}
