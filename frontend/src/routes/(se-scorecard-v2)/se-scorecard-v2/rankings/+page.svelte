<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { getSFRankings, fmt } from '$lib/api';
  import { theme, sfTeam, sfPeriod, sfSubteam, user } from '$lib/stores';

  let data: any = $state(null);
  let ready = $state(false);
  let canvas: HTMLCanvasElement;
  let hoveredIdx: number | null = $state(null);
  let hoverCooldown = false;
  let loadingMsg = $state("Calculating who's the GOAT...");
  let rafId: number;

  const LOADING_MSGS = [
    "Calculating who's the GOAT...",
    "Pulling live Salesforce data...",
    "The numbers don't lie...",
    "Crunching the iACV...",
    "Crowning the champion...",
  ];

  const TIER_CFG_P5: Record<string, {color:string,bg:string,label:string}> = {
    Elite:   { color:'#FFB800', bg:'#1a1200', label:'🐐 GOAT TIER' },
    Strong:  { color:'#3B82F6', bg:'#0a1628', label:'🔥 ON FIRE' },
    Steady:  { color:'#10B981', bg:'#071a12', label:'😤 GRINDING' },
    Develop: { color:'#EF4444', bg:'#1a0a0a', label:'💀 SEND HELP' },
  };

  const TIER_CFG_TW: Record<string, {color:string,bg:string,label:string}> = {
    Elite:   { color:'#B45309', bg:'#FEF3C7', label:'🐐 GOAT TIER' },
    Strong:  { color:'#1D4ED8', bg:'#EFF6FF', label:'🔥 ON FIRE' },
    Steady:  { color:'#178742', bg:'#F0FDF4', label:'😤 GRINDING' },
    Develop: { color:'#DC2626', bg:'#FEF2F2', label:'💀 SEND HELP' },
  };

  function cfg(t: string) {
    return $theme === 'twilio' ? (TIER_CFG_TW[t] ?? TIER_CFG_TW.Steady) : (TIER_CFG_P5[t] ?? TIER_CFG_P5.Steady);
  }

  function colors() {
    return $theme === 'twilio'
      ? ['#F22F46','#006EFF','#178742','#B45309','#7C3AED','#F4F4F6']
      : ['#FFB800','#E8003D','#3B82F6','#10B981','#8b5cf6','#fff','#FFD600'];
  }

  const RAIN_COUNT = 45;

  function makeParticle(burst: boolean) {
    const c = colors();
    return {
      x: burst ? canvas.width * 0.1 + Math.random() * canvas.width * 0.8 : Math.random() * canvas.width,
      y: burst ? canvas.height * 0.4 + Math.random() * canvas.height * 0.2 : -20 - Math.random() * canvas.height * 0.5,
      vx: (Math.random() - 0.5) * (burst ? 10 : 2),
      vy: burst ? -11 - Math.random() * 9 : 0.6 + Math.random() * 1.2,
      w: 5 + Math.random() * 8, h: 3 + Math.random() * 4,
      rot: Math.random() * Math.PI * 2, vrot: (Math.random() - 0.5) * 0.14,
      color: c[Math.floor(Math.random() * c.length)],
      alpha: 1, burst,
    };
  }

  let pool: ReturnType<typeof makeParticle>[] = [];

  function startConfetti() {
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
    pool = Array.from({length: RAIN_COUNT}, () => makeParticle(false));

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let i = pool.length - 1; i >= 0; i--) {
        const p = pool[i];
        p.x += p.vx; p.y += p.vy; p.rot += p.vrot;
        p.vy += p.burst ? 0.32 : 0.018;
        if (p.burst) { p.alpha -= 0.005; if (p.alpha <= 0) { pool.splice(i, 1); continue; } }
        else if (p.y > canvas.height + 10) { pool[i] = makeParticle(false); continue; }
        ctx.save(); ctx.globalAlpha = Math.max(0, p.alpha);
        ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.fillStyle = p.color;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); ctx.restore();
      }
      while (pool.filter(p => !p.burst).length < RAIN_COUNT) pool.push(makeParticle(false));
      rafId = requestAnimationFrame(draw);
    }
    draw();
  }

  function burstConfetti() {
    if (!canvas || hoverCooldown) return;
    hoverCooldown = true;
    for (let i = 0; i < 260; i++) pool.push(makeParticle(true));
    setTimeout(() => hoverCooldown = false, 3200);
  }

  onMount(async () => {
    let msgIdx = 0;
    const msgTimer = setInterval(() => {
      msgIdx = (msgIdx + 1) % LOADING_MSGS.length;
      loadingMsg = LOADING_MSGS[msgIdx];
    }, 700);
    const [rankData] = await Promise.all([getSFRankings($sfTeam, $sfPeriod, 0, $sfSubteam), new Promise(r => setTimeout(r, 2200))]);
    clearInterval(msgTimer);
    if (!rankData || !rankData.ranked?.length) {
      loadingMsg = 'Failed to load data. Try refreshing.';
      return;
    }
    data = rankData;
    ready = true;
    setTimeout(startConfetti, 300);
  });

  onDestroy(() => { cancelAnimationFrame(rafId); });
</script>

<canvas bind:this={canvas} style="position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:998"></canvas>

{#if $user?.sf_access === 'se_restricted'}
<div class="min-h-screen flex items-center justify-center">
  <div style="max-width:420px;width:100%;padding:32px 24px;text-align:center">
    <div style="font-size:36px;margin-bottom:16px">🔒</div>
    <div style="font-size:18px;font-weight:800;color:var(--text);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px">Access Denied</div>
    <div style="font-size:13px;color:var(--text-muted);font-weight:500;margin-bottom:24px">Power Rankings are only available to SE managers and leaders.</div>
    <a href="/se-scorecard-v2/me" style="display:inline-block;padding:10px 24px;background:var(--red);color:white;font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;text-decoration:none;border-radius:4px">View My Stats instead</a>
  </div>
</div>
{:else if !ready}
<div class="min-h-screen flex items-center justify-center" style="background:{$theme==='twilio'?'#f0f0f2':'#06080f'}">
  <div style="text-align:center;padding:0 24px">
    <div style="margin-bottom:24px;display:flex;justify-content:center">
      {#if $theme === 'twilio'}
        <img src="/twilio-icon.svg" alt="Twilio" style="width:72px;height:72px;animation:breathe 1.6s ease-in-out infinite">
      {:else}
        <div style="font-size:72px;line-height:1;animation:breathe 1.6s ease-in-out infinite">🐐</div>
      {/if}
    </div>
    <div style="font-size:{$theme==='p5'?'clamp(2rem,8vw,3.5rem)':'clamp(1.8rem,6vw,3rem)'};font-weight:900;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:-0.02em;line-height:1;color:{$theme==='p5'?'white':'var(--text)'};{$theme==='p5'?'text-shadow:0 0 40px rgba(255,184,0,0.4)':''}">
      {$theme === 'p5' ? 'POWER' : 'Power'}<br>
      <span style="color:{$theme==='twilio'?'var(--red)':'#FFB800'}">{$theme === 'p5' ? 'RANKINGS' : 'Rankings'}</span>
    </div>
    <div style="margin-top:20px;font-size:{$theme==='p5'?'16px':'15px'};font-weight:{$theme==='p5'?'700':'600'};font-style:{$theme==='p5'?'italic':'normal'};color:{$theme==='p5'?'rgba(255,184,0,0.8)':'var(--text-muted)'};animation:fadeMsg 0.4s ease;min-height:24px">
      {loadingMsg}
    </div>
    <div style="margin-top:28px;width:240px;margin-left:auto;margin-right:auto">
      <div style="height:4px;background:{$theme==='twilio'?'rgba(13,18,43,0.1)':'rgba(255,255,255,0.1)'};border-radius:99px;overflow:hidden">
        <div style="height:100%;border-radius:99px;background:{$theme==='twilio'?'var(--red)':'#FFB800'};animation:loadBar 2.0s cubic-bezier(0.4,0,0.2,1) forwards"></div>
      </div>
    </div>
  </div>
</div>
{:else}

<div style="position:fixed;top:68px;left:16px;z-index:9999">
  <a href="/se-scorecard-v2" class="p5-back-btn">◀ Back</a>
</div>

<div style="position:fixed;bottom:{$theme==='p5'?'4px':'0'};left:0;right:0;height:52px;background:{$theme==='twilio'?'white':'#0d1117'};border-top:{$theme==='twilio'?'1px solid rgba(13,18,43,0.1)':'2px solid rgba(255,184,0,0.2)'};z-index:997;overflow:hidden;display:flex;align-items:center;{$theme==='twilio'?'box-shadow:0 -1px 8px rgba(13,18,43,0.06)':''}">
  <div style="display:flex;animation:tickerScroll 32s linear infinite;white-space:nowrap;will-change:transform">
    {#snippet tickerContent()}
      <span style="display:inline-flex;align-items:center;gap:0;padding-right:60px;font-size:13px;letter-spacing:0.07em;color:{$theme==='twilio'?'rgba(13,18,43,0.5)':'#94a3b8'}">
        {#each data.ranked as se, i}
          <span style="color:{$theme==='twilio'?'#B45309':'#FFB800'};font-weight:800;margin-right:4px">#{i+1}</span><span style="margin-right:4px">{se.name}</span><span style="color:{$theme==='twilio'?'#178742':'#10B981'};font-weight:700;margin-right:12px">{fmt(se.total)}</span><span style="opacity:0.3;margin-right:12px">·</span>
        {/each}
        <span style="color:{$theme==='twilio'?'#B45309':'#FFB800'};font-weight:800;margin-right:12px">🏆 {data.ranked[0].name}</span>
        <span style="opacity:0.3;margin-right:12px">·</span>
        <span style="color:{$theme==='twilio'?'#DC2626':'#EF4444'};font-weight:800;margin-right:12px">💀 {data.ranked[data.ranked.length-1].name}</span>
        <span style="opacity:0.3;margin-right:12px">·</span>
      </span>
    {/snippet}
    {@render tickerContent()}
    {@render tickerContent()}
  </div>
</div>

<style>
@keyframes breathe { 0%,100%{transform:scale(1);opacity:0.85} 50%{transform:scale(1.18);opacity:1} }
@keyframes fadeMsg { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
@keyframes loadBar { 0%{width:0%} 60%{width:75%} 85%{width:90%} 100%{width:100%} }
@keyframes tickerScroll { from{transform:translateX(0)} to{transform:translateX(-50%)} }
@keyframes slamDown { 0%{opacity:0;transform:translateY(-80px) scale(1.05)} 70%{transform:translateY(6px) scale(.99)} 100%{opacity:1;transform:translateY(0) scale(1)} }
@keyframes flipIn { 0%{opacity:0;transform:perspective(600px) rotateX(-35deg) translateY(30px)} 100%{opacity:1;transform:perspective(600px) rotateX(0) translateY(0)} }
@keyframes slideUp { from{opacity:0;transform:translateY(50px)} to{opacity:1;transform:translateY(0)} }
@keyframes barFill { to { width: var(--w) } }
@keyframes eliteGlowDark { 0%,100%{box-shadow:0 0 60px #FFB80040,0 0 120px #FFB80015} 50%{box-shadow:0 0 100px #FFB80070,0 0 200px #FFB80030} }
@keyframes eliteGlowLight { 0%,100%{box-shadow:0 4px 24px rgba(180,83,9,0.2),0 0 0 2px rgba(180,83,9,0.12)} 50%{box-shadow:0 8px 40px rgba(180,83,9,0.35),0 0 0 3px rgba(180,83,9,0.2)} }
@keyframes devWiggle { 0%,80%,100%{transform:rotate(0)} 82%{transform:rotate(-1.2deg)} 84%{transform:rotate(1.2deg)} 86%{transform:rotate(-.8deg)} 88%{transform:rotate(.8deg)} }
</style>

<div style="max-width:1100px;margin:0 auto;padding:80px 24px 80px">

  <div style="text-align:center;margin-bottom:32px">
    <div style="display:flex;justify-content:center;margin-bottom:18px">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:28px;width:auto;{$theme==='p5'?'filter:brightness(0) invert(1);opacity:0.5':''}">
    </div>
    {#if $theme === 'twilio'}
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.3em;color:var(--act-color);margin-bottom:10px">⚡ Live Salesforce · {data.quarter}</div>
      <h1 style="font-size:clamp(2.5rem,8vw,4rem);font-weight:800;letter-spacing:-0.03em;line-height:1;color:var(--text)">Power Rankings</h1>
      <div style="width:48px;height:3px;background:var(--red);margin:16px auto;border-radius:2px"></div>
      <p style="color:var(--text-muted);font-size:12px;letter-spacing:.1em;text-transform:uppercase">DSR Sales Engineering · {data.total} SEs</p>
    {:else}
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.3em;color:#3B82F6;margin-bottom:14px">⚡ Live Salesforce · {data.quarter}</div>
      <h1 style="font-size:clamp(3rem,12vw,6rem);font-weight:900;letter-spacing:-.04em;line-height:.9;text-transform:uppercase;background:linear-gradient(135deg,#fff 0%,#FFB800 40%,#fff 60%,#64748b 100%);background-size:300% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent">Power<br>Rankings</h1>
      <div style="width:80px;height:4px;background:linear-gradient(90deg,#3B82F6,#8b5cf6,#FFB800);margin:18px auto;border-radius:2px"></div>
      <p style="color:#334155;font-size:12px;letter-spacing:.1em;text-transform:uppercase">DSR Sales Engineering · {data.total} SEs</p>
    {/if}
  </div>

  <div style="display:flex;justify-content:center;gap:20px;flex-wrap:wrap;margin-bottom:28px">
    {#each [{val:fmt(data.team_total),lbl:'Team iACV',color:$theme==='twilio'?'#B45309':'#FFB800'},{val:String(data.total),lbl:'SEs Ranked',color:$theme==='twilio'?'#178742':'#10B981'}] as s}
    <div style="text-align:center;background:var(--panel);border:1px solid {$theme==='twilio'?'rgba(13,18,43,0.1)':'rgba(255,255,255,0.08)'};border-radius:12px;padding:14px 22px;{$theme==='twilio'?'box-shadow:0 1px 4px rgba(13,18,43,0.08)':''}">
      <div style="font-size:1.8rem;font-weight:900;color:{s.color}">{s.val}</div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--text-muted);margin-top:3px">{s.lbl}</div>
    </div>
    {/each}
  </div>

  <div style="display:flex;flex-direction:column;gap:14px">
    {#each data.ranked as se, idx}
    {@const i = idx + 1}
    {@const c = cfg(se._tier)}
    {@const isOne = i === 1}
    {@const isDev = se._tier === 'Develop'}
    {@const delay = idx * 180}
    {@const enter = isOne ? 'slamDown' : i <= 3 ? 'flipIn' : 'slideUp'}
    {@const glowAnim = $theme==='twilio' ? 'eliteGlowLight' : 'eliteGlowDark'}
    {@const isHovered = hoveredIdx === idx}
    {@const totalEmails = (se.email_act_inq ?? 0) + (se.email_exp_inq ?? 0) + (se.email_act_outq ?? 0) + (se.email_exp_outq ?? 0)}
    {@const notesCov = (se.note_hv_total ?? 0) > 0 ? Math.round((se.note_hv_covered ?? 0) / se.note_hv_total * 100) : null}
    <div
      style="animation:{enter} 0.6s cubic-bezier(.22,1,.36,1) {delay}ms both;transition:transform 0.2s cubic-bezier(.22,1,.36,1),box-shadow 0.2s;transform:{isHovered?'scale(1.04) translateY(-4px)':'scale(1) translateY(0)'}"
      onmouseenter={() => { hoveredIdx = idx; if (i === 1) burstConfetti(); }}
      onmouseleave={() => hoveredIdx = null}
      role="article"
    >
      {#if isOne}<div style="text-align:center;font-size:2.2rem;margin-bottom:4px">👑</div>{/if}
      <div style="border-radius:16px;background:{$theme==='twilio'?'white':'#0c1220'};overflow:hidden;position:relative;border:1px solid {c.color}40;cursor:default;{isOne?`animation:${glowAnim} 2.5s ease infinite`:isDev?'animation:devWiggle 3s ease infinite':''};{$theme==='twilio'?'box-shadow:'+( isHovered ? '0 8px 32px rgba(13,18,43,0.16)' : '0 2px 8px rgba(13,18,43,0.08)'):''}">
        <div style="position:absolute;right:-5px;top:-15px;font-size:8rem;font-weight:900;line-height:1;pointer-events:none;user-select:none;z-index:0;color:{c.color};opacity:{$theme==='twilio'?'.06':'.1'}">{i}</div>
        <div style="position:relative;z-index:1;padding:22px 26px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px">
            <div>
              <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.15em;color:{c.color};margin-bottom:6px">{['🥇','🥈','🥉'][i-1] ?? ''} {c.label}</div>
              <div style="font-size:clamp(1.1rem,3vw,1.4rem);font-weight:900;color:{$theme==='twilio'?'var(--text)':'#fff'};letter-spacing:-.02em">{se.name}</div>
              <div style="margin-top:7px">
                {#if se.exp_growing}
                  <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:800;letter-spacing:.08em;background:{$theme==='twilio'?'#F0FDF4':'#10B98118'};color:{$theme==='twilio'?'#178742':'#10B981'};border:1px solid {$theme==='twilio'?'#86EFAC':'#10B98140'}">📈 GROWING</span>
                {:else}
                  <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:800;letter-spacing:.08em;background:{$theme==='twilio'?'#F4F4F6':'#fff08'};color:{$theme==='twilio'?'#6B7280':'#6b7280'};border:1px solid {$theme==='twilio'?'rgba(13,18,43,0.15)':'#fff1'}">😐 RETAINING</span>
                {/if}
              </div>
            </div>
            <div style="text-align:right;flex-shrink:0">
              <div style="font-size:clamp(1.4rem,4vw,2rem);font-weight:900;color:{$theme==='twilio'?'var(--text)':'#fff'};line-height:1">{fmt(se.total)}</div>
              <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin-top:2px">total iACV</div>
            </div>
          </div>
          <div style="font-size:12px;color:color-mix(in srgb,{c.color} 70%,{$theme==='twilio'?'#374151':'#aaa'});font-style:italic;margin-bottom:14px;padding:8px 12px;border-radius:8px;border-left:2px solid {c.color}50;background:{c.bg}">{se._roast}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
            <div style="background:{$theme==='twilio'?'#F8FAFF':'rgba(255,255,255,0.04)'};border:1px solid {$theme==='twilio'?'rgba(0,110,255,0.15)':'rgba(255,255,255,0.06)'};border-radius:10px;padding:11px 13px">
              <div style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--text-muted);margin-bottom:4px">🎯 Activate</div>
              <div style="font-size:1.05rem;font-weight:800;color:var(--act-color);line-height:1.2">{fmt(se.act_icav)}</div>
              <div style="font-size:10px;color:var(--text-muted);margin-top:2px;margin-bottom:7px">{se.act_wins} wins · med {fmt(se.act_median)}</div>
              <div style="background:{$theme==='twilio'?'rgba(0,110,255,0.1)':'rgba(255,255,255,0.06)'};border-radius:99px;height:3px;overflow:hidden">
                <div style="height:3px;border-radius:99px;background:var(--act-color);width:0;animation:barFill .9s cubic-bezier(.34,1.56,.64,1) {delay+500}ms forwards;--w:{se._aw}%"></div>
              </div>
            </div>
            <div style="background:{$theme==='twilio'?'#F0FDF4':'rgba(255,255,255,0.04)'};border:1px solid {$theme==='twilio'?'rgba(23,135,66,0.15)':'rgba(255,255,255,0.06)'};border-radius:10px;padding:11px 13px">
              <div style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--text-muted);margin-bottom:4px">📈 Expansion</div>
              <div style="font-size:1.05rem;font-weight:800;color:var(--exp-color);line-height:1.2">{fmt(se.exp_icav)}</div>
              <div style="font-size:10px;color:var(--text-muted);margin-top:2px;margin-bottom:7px">{se.exp_wins} wins · med {fmt(se.exp_median)}</div>
              <div style="background:{$theme==='twilio'?'rgba(23,135,66,0.1)':'rgba(255,255,255,0.06)'};border-radius:99px;height:3px;overflow:hidden">
                <div style="height:3px;border-radius:99px;background:var(--exp-color);width:0;animation:barFill .9s cubic-bezier(.34,1.56,.64,1) {delay+600}ms forwards;--w:{se._ew}%"></div>
              </div>
            </div>
          </div>

          <!-- Emails + Notes hygiene -->
          {#if totalEmails > 0 || notesCov !== null}
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            {#if totalEmails > 0}
            <div style="display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:8px;background:{$theme==='twilio'?'#F4F4F6':'rgba(255,255,255,0.04)'};border:1px solid {$theme==='twilio'?'rgba(13,18,43,0.08)':'rgba(255,255,255,0.06)'}">
              <span style="font-size:11px;color:var(--text-muted)">✉</span>
              <span style="font-size:11px;font-weight:700;color:var(--text)">{totalEmails}</span>
              <span style="font-size:10px;color:var(--text-muted)">emails</span>
              {#if (se.email_act_outq ?? 0) + (se.email_exp_outq ?? 0) > 0}
              <span style="font-size:10px;color:var(--text-muted)">· {(se.email_act_outq ?? 0) + (se.email_exp_outq ?? 0)} pipe</span>
              {/if}
            </div>
            {/if}
            {#if notesCov !== null}
            {@const notesColor = notesCov === 100 ? ($theme==='twilio'?'#178742':'#10B981') : notesCov <= 50 ? ($theme==='twilio'?'#DC2626':'#EF4444') : 'var(--text)'}
            <div style="display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:8px;background:{$theme==='twilio'?'#F4F4F6':'rgba(255,255,255,0.04)'};border:1px solid {$theme==='twilio'?'rgba(13,18,43,0.08)':'rgba(255,255,255,0.06)'}">
              <span style="font-size:11px;color:var(--text-muted)">📝</span>
              <span style="font-size:11px;font-weight:700;color:{notesColor}">{se.note_hv_covered}/{se.note_hv_total}</span>
              <span style="font-size:10px;color:var(--text-muted)">notes · {se.note_hv_avg_entries} avg</span>
            </div>
            {/if}
          </div>
          {/if}
        </div>
      </div>
    </div>
    {/each}
  </div>

</div>
{/if}
