<script lang="ts">
  import { onMount } from 'svelte';
  import { getReport, fmt } from '$lib/api';
  import { theme } from '$lib/stores';
  import { tc, fc } from '$lib/colors';

  let data: any = $state(null);

  function bar(value: number, max: number, color: string) {
    const w = max ? Math.round(value / max * 100) : 0;
    return `<div style="min-width:80px;width:100%;background:${$theme==='twilio'?'rgba(13,18,43,0.08)':'rgba(255,255,255,0.08)'};border-radius:2px;height:5px"><div style="height:5px;border-radius:2px;background:${color};width:${w}%"></div></div>`;
  }

  onMount(async () => { data = await getReport(); });
</script>

{#if !data}
<div class="min-h-screen flex items-center justify-center">
  <div style="font-size:18px;font-weight:700;color:var(--text-muted)">Loading intel…</div>
</div>
{:else}

<div style="position:fixed;top:{$theme==='twilio'?'68px':'26px'};left:{$theme==='twilio'?'16px':'48px'};z-index:9999">
  <a href="/scorecard" class="p5-back-btn">◀ Back</a>
</div>

<div style="max-width:1200px;margin:0 auto;padding:60px 24px 40px">

  <!-- Header -->
  <div style="margin-bottom:28px">
    <div class="p5-badge" style="margin-bottom:10px">DSR Sales Engineering</div>
    <h1 style="font-size:36px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);{$theme==='p5'?'text-shadow:3px 3px 0 var(--red)':''}">SE Scorecard</h1>
    <p style="font-size:13px;color:var(--text-muted);font-weight:600;margin-top:4px">{data.total} SEs · Ranked across revenue, expansion quality, pipeline &amp; hygiene</p>
  </div>

  <!-- Summary -->
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px">
    {#each [{label:'Team Total iACV', val:fmt(data.team_icav)},{label:'Team Avg Owl %',val:data.avg_owl+'%'},{label:'SEs Analysed',val:String(data.total)}] as s}
    <div class="p5-panel" style="padding:18px 20px">
      <div style="font-size:10px;color:var(--red);font-weight:700;text-transform:uppercase;letter-spacing:0.18em;font-style:{$theme==='p5'?'italic':'normal'};margin-bottom:6px">{s.label}</div>
      <div style="font-size:28px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text);{$theme==='p5'?'text-shadow:2px 2px 0 var(--red)':''}">{s.val}</div>
    </div>
    {/each}
  </div>

  <!-- Overall Rankings -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)">
      <h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);margin-bottom:2px">Overall Rankings</h2>
      <p style="font-size:12px;color:var(--text-muted)">Total iACV 65% · Activate 10% · Expansion quality 10% · Future pipeline 8% · Owl% 7%</p>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)">
          <tr>{#each ['#','SE','Activate','Expansion','Total iACV','Owl%','Future Q%','Tier'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'};white-space:nowrap">{h}</th>{/each}</tr>
        </thead>
        <tbody>
          {#each data.ranked as se}
          {@const colors = tc(se.tier, $theme)}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;color:var(--text-muted);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'}">{se.rank}</td>
            <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
            <td style="padding:10px 16px;color:var(--act-color);font-weight:700">{fmt(se.act_icav)}</td>
            <td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{fmt(se.exp_icav)}</td>
            <td style="padding:10px 16px;color:var(--text);font-weight:900;font-style:{$theme==='p5'?'italic':'normal'}">{fmt(se.total_icav)}</td>
            <td style="padding:10px 16px;color:{se.owl_pct < 75 ? 'var(--red)' : 'var(--text-muted)'};font-weight:700">{se.owl_pct}%</td>
            <td style="padding:10px 16px;color:var(--text-muted)">{se.future_pct}%</td>
            <td style="padding:10px 16px"><span style="display:inline-block;padding:2px 10px 2px 8px;font-size:10px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.1em;background:{colors.bg};color:{colors.color};{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">{se.tier}</span></td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Activate + Expansion -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
    <div class="p5-panel">
      <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)">
        <h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);margin-bottom:2px">Activate — New Business</h2>
        <p style="font-size:12px;color:var(--text-muted)">New logos, no prior contract, deals &gt;$30K</p>
      </div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="background:rgba(var(--red-rgb),0.06)"><tr>{#each ['SE','Wins','iACV','Avg','Median','Vol'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'}">{h}</th>{/each}</tr></thead>
          <tbody>
            {#each data.act_sorted as se}
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
              <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
              <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.act_wins}</td>
              <td style="padding:10px 16px;color:var(--act-color);font-weight:700">{fmt(se.act_icav)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.act_avg)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.act_median)}</td>
              <td style="padding:10px 16px;min-width:80px">{@html bar(se.act_icav, data.max_act, $theme==='twilio'?'#006EFF':'#3B82F6')}</td>
            </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
    <div class="p5-panel">
      <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)">
        <h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);margin-bottom:2px">Expansion — Land &amp; Expand</h2>
        <p style="font-size:12px;color:var(--text-muted)">Existing customers · $0 median = flat retentions</p>
      </div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="background:rgba(var(--red-rgb),0.06)"><tr>{#each ['SE','Wins','iACV','Avg','Median','Status','Vol'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'}">{h}</th>{/each}</tr></thead>
          <tbody>
            {#each data.exp_sorted as se}
            <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
              <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
              <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.exp_wins}</td>
              <td style="padding:10px 16px;color:var(--exp-color);font-weight:700">{fmt(se.exp_icav)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.exp_avg)}</td>
              <td style="padding:10px 16px;color:var(--text-muted)">{fmt(se.exp_median)}</td>
              <td style="padding:10px 16px">
                {#if se.exp_growing}
                  <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};background:{$theme==='twilio'?'#F0FDF4':'rgba(0,232,122,0.12)'};color:var(--exp-color);border:1px solid rgba(var(--exp-rgb),0.3);{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">Growing</span>
                {:else}
                  <span style="display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};background:{$theme==='twilio'?'var(--dark)':'rgba(255,255,255,0.05)'};color:var(--text-muted);border:1px solid rgba(var(--red-rgb),0.1);{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">Retaining</span>
                {/if}
              </td>
              <td style="padding:10px 16px;min-width:80px">{@html bar(se.exp_icav, data.max_exp, $theme==='twilio'?'#178742':'#10B981')}</td>
            </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Pipeline -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)">
      <h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text);margin-bottom:2px">Pipeline Health</h2>
      <p style="font-size:12px;color:var(--text-muted)">Owl% = Salesforce hygiene · FutQ% = out-of-quarter emails</p>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)"><tr>{#each ['SE','Owl%','Act InQ','Act OutQ','Exp InQ','Exp OutQ','FutQ%','Investment'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'}">{h}</th>{/each}</tr></thead>
        <tbody>
          {#each data.pipe_sorted as se}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
            <td style="padding:10px 16px;color:{se.owl_pct < 75 ? 'var(--red)' : 'var(--text-muted)'};font-weight:700">{se.owl_pct}%</td>
            <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.email_act_inq}</td>
            <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.email_act_outq}</td>
            <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.email_exp_inq}</td>
            <td style="padding:10px 16px;color:var(--text-muted);text-align:center">{se.email_exp_outq}</td>
            <td style="padding:10px 16px;color:var(--text-muted)">{se.future_pct}%</td>
            <td style="padding:10px 16px;min-width:80px">{@html bar(se.future_emails, data.max_fut, $theme==='twilio'?'#7C3AED':'#8b5cf6')}</td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Deals -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)"><h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text)">Largest Deals</h2></div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead style="background:rgba(var(--red-rgb),0.06)"><tr>{#each ['SE','Value','DSR','Deal'] as h}<th style="padding:10px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--red);font-style:{$theme==='p5'?'italic':'normal'}">{h}</th>{/each}</tr></thead>
        <tbody>
          {#each data.deal_sorted as se}
          <tr style="border-bottom:1px solid rgba(var(--red-rgb),0.05)">
            <td style="padding:10px 16px;font-weight:700;color:var(--text)">{se.name}</td>
            <td style="padding:10px 16px;color:{$theme==='twilio'?'#B45309':'var(--yellow)'};font-weight:900;font-style:{$theme==='p5'?'italic':'normal'}">{fmt(se.largest_deal_value)}</td>
            <td style="padding:10px 16px;color:var(--text-muted)">{se.largest_deal_dsr}</td>
            <td style="padding:10px 16px;color:var(--text-muted);font-size:12px">{se.largest_deal.slice(0,60)}{se.largest_deal.length > 60 ? '…' : ''}</td>
          </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Trends & Flags -->
  <div class="p5-panel" style="margin-bottom:20px">
    <div style="padding:14px 20px;border-bottom:1px solid rgba(var(--red-rgb),0.12)"><h2 style="font-size:15px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text)">Trends &amp; Flags</h2></div>
    <div style="padding:16px;display:flex;flex-direction:column;gap:8px">
      {#each data.trends as [cat, msg]}
      {@const color = fc(cat, $theme)}
      <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 14px;border-left:4px solid {color};background:rgba(var(--red-rgb),0.03);{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;font-style:{$theme==='p5'?'italic':'normal'};color:{color};width:80px;flex-shrink:0">{cat}</span>
        <span style="font-size:13px;font-weight:500;color:var(--text-muted)">{msg}</span>
      </div>
      {/each}
    </div>
  </div>

  <!-- SE Profiles grid -->
  <div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
      <div class="p5-badge">SE Profiles</div>
      <div style="flex:1;height:1px;background:rgba(var(--red-rgb),0.15)"></div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
      {#each data.ranked as se}
      {@const colors = tc(se.tier, $theme)}
      <div class="p5-panel" style="padding:16px;display:flex;flex-direction:column;gap:10px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
              <span style="font-size:11px;color:var(--text-faint);font-style:{$theme==='p5'?'italic':'normal'}">#{se.rank}</span>
              <span style="font-size:14px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;color:var(--text)">{se.name}</span>
            </div>
            <span style="display:inline-block;background:{colors.bg};color:{colors.color};border:1px solid {colors.color}40;padding:2px 10px 2px 8px;font-size:10px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.12em;{$theme==='p5'?'clip-path:polygon(0 0,100% 0,calc(100% - 6px) 100%,0 100%)':'border-radius:4px'}">{se.tier}</span>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:18px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--text);{$theme==='p5'?'text-shadow:1px 1px 0 var(--red)':''}">{fmt(se.total_icav)}</div>
            <div style="font-size:10px;color:var(--text-faint);text-transform:uppercase;letter-spacing:0.12em">total iACV</div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
          <div style="background:rgba(var(--act-rgb),0.08);border:1px solid rgba(var(--act-rgb),0.2);border-left:3px solid var(--act-color);padding:10px;{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
            <div style="font-size:9px;color:var(--act-color);font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:4px">Activate</div>
            <div style="font-size:14px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--act-glow)">{fmt(se.act_icav)}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:2px">{se.act_wins} wins</div>
            {@html bar(se.act_icav, data.max_act_icav, $theme==='twilio'?'#006EFF':'#3B82F6')}
          </div>
          <div style="background:rgba(var(--exp-rgb),0.08);border:1px solid rgba(var(--exp-rgb),0.2);border-left:3px solid var(--exp-color);padding:10px;{$theme==='twilio'?'border-radius:0 6px 6px 0':''}">
            <div style="font-size:9px;color:var(--exp-color);font-weight:700;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:4px">Expansion</div>
            <div style="font-size:14px;font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};color:var(--exp-glow)">{fmt(se.exp_icav)}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:2px">{se.exp_wins} wins</div>
            {@html bar(se.exp_icav, data.max_exp_icav, $theme==='twilio'?'#178742':'#10B981')}
          </div>
        </div>
        <div style="display:flex;gap:14px;font-size:12px;color:var(--text-muted);border-top:1px solid rgba(var(--red-rgb),0.08);padding-top:8px">
          <span>Owl <strong style="color:{se.owl_pct < 75 ? 'var(--red)' : 'var(--text)'}">{se.owl_pct}%</strong></span>
          <span>FutQ <strong style="color:var(--text)">{se.future_pct}%</strong></span>
          <span>Fwd <strong style="color:var(--text)">{se.future_emails}</strong></span>
        </div>
        {#if se.flags?.length}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px">
          {#each se.flags as [cat, msg]}
          {@const color = fc(cat, $theme)}
          <div style="border-left:3px solid {color};background:rgba(var(--red-rgb),0.03);padding:6px 8px;min-height:44px;{$theme==='twilio'?'border-radius:0 4px 4px 0':''}">
            <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:{color};margin-bottom:2px">{cat}</div>
            <div style="font-size:10px;color:var(--text-muted);line-height:1.3">{msg}</div>
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
