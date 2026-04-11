<script lang="ts">
  import { onMount } from 'svelte';
  import { getRankings, fmt } from '$lib/api';

  let data: any = $state(null);

  const TIER_CFG: Record<string, {color:string,bg:string,label:string}> = {
    Elite:   { color:'#FFB800', bg:'#1a1200', label:'🐐 GOAT TIER' },
    Strong:  { color:'#3B82F6', bg:'#0a1628', label:'🔥 ON FIRE' },
    Steady:  { color:'#10B981', bg:'#071a12', label:'😤 GRINDING' },
    Develop: { color:'#EF4444', bg:'#1a0a0a', label:'💀 SEND HELP' },
  };

  onMount(async () => { data = await getRankings(); });
</script>

{#if !data}
<div class="min-h-screen flex items-center justify-center" style="background:#06080f">
  <div style="font-size:18px;font-weight:700;font-style:italic;color:rgba(255,255,255,0.4)">Loading rankings…</div>
</div>
{:else}

<div style="position:fixed;top:14px;left:16px;z-index:9999">
  <a href="/" class="p5-back-btn">◀ Back</a>
</div>

<!-- Ticker -->
<div style="position:fixed;bottom:4px;left:0;right:0;height:52px;background:#0d1117;border-top:2px solid rgba(255,184,0,0.2);z-index:997;overflow:hidden;display:flex;align-items:center">
  <div style="white-space:nowrap;animation:tickerScroll 60s linear infinite;font-size:13px;letter-spacing:0.07em;color:#94a3b8;padding-left:100%">
    {#each data.ranked as se, i}
      <span style="color:#FFB800;font-weight:800">#{i+1}</span> {se.name} {fmt(se.total)} &nbsp;·&nbsp;
    {/each}
    <span style="color:#FFB800">🏆 GOAT: {data.ranked[0].name}</span> &nbsp;·&nbsp;
    <span style="color:#EF4444">💀 PRAYERS: {data.ranked[data.ranked.length-1].name}</span>
  </div>
</div>

<style>
@keyframes tickerScroll { from { transform: translateX(0) } to { transform: translateX(-50%) } }
@keyframes slamDown { 0%{opacity:0;transform:translateY(-80px) scale(1.05)} 70%{transform:translateY(6px) scale(.99)} 100%{opacity:1;transform:translateY(0) scale(1)} }
@keyframes flipIn { 0%{opacity:0;transform:perspective(600px) rotateX(-35deg) translateY(30px)} 100%{opacity:1;transform:perspective(600px) rotateX(0) translateY(0)} }
@keyframes slideUp { from{opacity:0;transform:translateY(50px)} to{opacity:1;transform:translateY(0)} }
@keyframes barFill { to { width: var(--w) } }
@keyframes eliteGlow { 0%,100%{box-shadow:0 0 60px #FFB80040,0 0 120px #FFB80015} 50%{box-shadow:0 0 100px #FFB80070,0 0 200px #FFB80030} }
@keyframes devWiggle { 0%,80%,100%{transform:rotate(0)} 82%{transform:rotate(-1.2deg)} 84%{transform:rotate(1.2deg)} 86%{transform:rotate(-.8deg)} 88%{transform:rotate(.8deg)} }
</style>

<div style="max-width:820px;margin:0 auto;padding:80px 20px 80px;padding-bottom:80px">

  <!-- Hero -->
  <div style="text-align:center;margin-bottom:32px">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.3em;color:#3B82F6;margin-bottom:14px">🏆 Official Results</div>
    <h1 style="font-size:clamp(3rem,12vw,6rem);font-weight:900;letter-spacing:-.04em;line-height:.9;text-transform:uppercase;background:linear-gradient(135deg,#fff 0%,#FFB800 40%,#fff 60%,#64748b 100%);background-size:300% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent">Power<br>Rankings</h1>
    <div style="width:80px;height:4px;background:linear-gradient(90deg,#3B82F6,#8b5cf6,#FFB800);margin:18px auto;border-radius:2px"></div>
    <p style="color:#334155;font-size:12px;letter-spacing:.1em;text-transform:uppercase">DSR Sales Engineering · {data.total} SEs</p>
  </div>

  <!-- Summary -->
  <div style="display:flex;justify-content:center;gap:20px;flex-wrap:wrap;margin-bottom:28px">
    {#each [{val:fmt(data.team_total),lbl:'Team iACV',color:'#FFB800'},{val:data.team_owl+'%',lbl:'Avg Owl %',color:'#3B82F6'},{val:String(data.total),lbl:'SEs Ranked',color:'#10B981'}] as s}
    <div style="text-align:center;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:14px 22px">
      <div style="font-size:1.8rem;font-weight:900;color:{s.color}">{s.val}</div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#475569;margin-top:3px">{s.lbl}</div>
    </div>
    {/each}
  </div>

  <!-- Cards -->
  <div style="display:flex;flex-direction:column;gap:14px">
    {#each data.ranked as se, idx}
    {@const i = idx + 1}
    {@const cfg = TIER_CFG[se._tier]}
    {@const isOne = i === 1}
    {@const isDev = se._tier === 'Develop'}
    {@const delay = idx * 180}
    {@const enter = isOne ? 'slamDown' : i <= 3 ? 'flipIn' : 'slideUp'}
    {@const owlCol = se.owl < 75 ? '#EF4444' : se.owl === 100 ? '#FFB800' : '#9ca3af'}
    <div style="animation:{enter} 0.6s cubic-bezier(.22,1,.36,1) {delay}ms both">
      {#if isOne}<div style="text-align:center;font-size:2.2rem;margin-bottom:4px">👑</div>{/if}
      <div style="border-radius:16px;background:#0c1220;overflow:hidden;position:relative;border:1px solid {cfg.color}40;{isOne ? 'animation:eliteGlow 2.5s ease infinite' : isDev ? 'animation:devWiggle 3s ease infinite' : ''}">
        <!-- Big rank number watermark -->
        <div style="position:absolute;right:-5px;top:-15px;font-size:8rem;font-weight:900;line-height:1;pointer-events:none;user-select:none;z-index:0;color:{cfg.color};opacity:.1">{i}</div>
        <div style="position:relative;z-index:1;padding:22px 26px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px">
            <div>
              <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.15em;color:{cfg.color};margin-bottom:6px">{['🥇','🥈','🥉'][i-1] ?? ''} {cfg.label}</div>
              <div style="font-size:clamp(1.1rem,3vw,1.4rem);font-weight:900;color:#fff;letter-spacing:-.02em">{se.name}</div>
              <div style="margin-top:7px">
                {#if se.exp_growing}
                  <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:800;letter-spacing:.08em;background:#10B98118;color:#10B981;border:1px solid #10B98140">📈 GROWING</span>
                {:else}
                  <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:800;letter-spacing:.08em;background:#fff08;color:#6b7280;border:1px solid #fff1">😐 RETAINING</span>
                {/if}
              </div>
            </div>
            <div style="text-align:right;flex-shrink:0">
              <div style="font-size:clamp(1.4rem,4vw,2rem);font-weight:900;color:#fff;line-height:1">{fmt(se.total)}</div>
              <div style="font-size:10px;color:#4b5563;text-transform:uppercase;letter-spacing:.08em;margin-top:2px">total iACV</div>
            </div>
          </div>
          <!-- Roast -->
          <div style="font-size:12px;color:color-mix(in srgb,{cfg.color} 70%,#aaa);font-style:italic;margin-bottom:14px;padding:8px 12px;border-radius:8px;border-left:2px solid {cfg.color}50;background:{cfg.bg}">{se._roast}</div>
          <!-- Stats 2-grid -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:11px 13px">
              <div style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#374151;margin-bottom:4px">🎯 Activate</div>
              <div style="font-size:1.05rem;font-weight:800;color:#60a5fa;line-height:1.2">{fmt(se.act_icav)}</div>
              <div style="font-size:10px;color:#374151;margin-top:2px;margin-bottom:7px">{se.act_wins} wins · med {fmt(se.act_median)}</div>
              <div style="background:rgba(255,255,255,0.06);border-radius:99px;height:3px;overflow:hidden">
                <div style="height:3px;border-radius:99px;background:#3B82F6;width:0;animation:barFill .9s cubic-bezier(.34,1.56,.64,1) {delay+500}ms forwards;--w:{se._aw}%"></div>
              </div>
            </div>
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:11px 13px">
              <div style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#374151;margin-bottom:4px">📈 Expansion</div>
              <div style="font-size:1.05rem;font-weight:800;color:#34d399;line-height:1.2">{fmt(se.exp_icav)}</div>
              <div style="font-size:10px;color:#374151;margin-top:2px;margin-bottom:7px">{se.exp_wins} wins · med {fmt(se.exp_median)}</div>
              <div style="background:rgba(255,255,255,0.06);border-radius:99px;height:3px;overflow:hidden">
                <div style="height:3px;border-radius:99px;background:#10B981;width:0;animation:barFill .9s cubic-bezier(.34,1.56,.64,1) {delay+600}ms forwards;--w:{se._ew}%"></div>
              </div>
            </div>
          </div>
          <!-- Stats 3-grid -->
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:11px 13px">
              <div style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#374151;margin-bottom:4px">🦉 Owl%</div>
              <div style="font-size:1rem;font-weight:800;color:{owlCol}">{se.owl}%</div>
              <div style="background:rgba(255,255,255,0.06);border-radius:99px;height:3px;overflow:hidden;margin-top:6px">
                <div style="height:3px;border-radius:99px;background:{owlCol};width:0;animation:barFill .9s cubic-bezier(.34,1.56,.64,1) {delay+700}ms forwards;--w:{se.owl}%"></div>
              </div>
            </div>
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:11px 13px">
              <div style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#374151;margin-bottom:4px">🔮 Future Q%</div>
              <div style="font-size:1rem;font-weight:800;color:#a78bfa">{se.future_pct}%</div>
              <div style="background:rgba(255,255,255,0.06);border-radius:99px;height:3px;overflow:hidden;margin-top:6px">
                <div style="height:3px;border-radius:99px;background:#8b5cf6;width:0;animation:barFill .9s cubic-bezier(.34,1.56,.64,1) {delay+800}ms forwards;--w:{se._fw}%"></div>
              </div>
            </div>
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:11px 13px">
              <div style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#374151;margin-bottom:4px">✉️ Fut. Emails</div>
              <div style="font-size:1rem;font-weight:800;color:#f9a8d4">{se.future}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    {/each}
  </div>

</div>
{/if}
