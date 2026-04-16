<script lang="ts">
  import { onMount } from 'svelte';
  import { theme } from '$lib/stores';
  import SuggestionBox from '$lib/SuggestionBox.svelte';

  let { children } = $props();

  onMount(() => {
    if (!localStorage.getItem('theme')) theme.set('twilio');
  });

  const p5 = $derived($theme === 'p5');
</script>

<!-- P5 decorative chrome (corner brackets + edge bars) -->
{#if p5}
<div style="position:fixed;top:0;left:0;right:0;height:4px;background:var(--red);z-index:200;box-shadow:0 0 12px var(--red)"></div>
<div style="position:fixed;bottom:0;left:0;right:0;height:4px;background:var(--red);z-index:200;box-shadow:0 0 12px var(--red)"></div>
<div style="position:fixed;bottom:-30px;right:-10px;font-size:280px;font-weight:900;font-style:italic;color:rgba(232,0,61,0.04);line-height:1;pointer-events:none;user-select:none;transform:skewX(-5deg);z-index:0">5</div>
{/if}

<!-- Header — always present, theme-aware -->
<div
  style="position:fixed;top:0;left:0;right:0;height:56px;z-index:100;display:flex;align-items:center;padding:0 24px;
    {p5
      ? 'background:#0d0d0d;border-bottom:1px solid rgba(232,0,61,0.35);box-shadow:0 0 20px rgba(232,0,61,0.08);'
      : 'background:white;border-bottom:1px solid rgba(13,18,43,0.1);box-shadow:0 1px 8px rgba(13,18,43,0.06);'}"
>
  <div style="display:flex;align-items:center;gap:16px">
    <a href="/" style="display:flex;align-items:center;text-decoration:none">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
    </a>
    <div style="width:1px;height:22px;background:{p5 ? 'rgba(232,0,61,0.3)' : 'rgba(13,18,43,0.12)'}"></div>
    <button
      onclick={() => theme.toggle()}
      style="background:none;border:none;padding:2px 4px;margin:-2px -4px;cursor:pointer;font-size:13px;font-weight:600;letter-spacing:-0.01em;color:{p5 ? 'rgba(255,255,255,0.5)' : 'rgba(13,18,43,0.45)'};border-radius:4px;transition:color 0.15s,background 0.15s"
      onmouseenter={e => { const el = e.currentTarget as HTMLElement; el.style.color = 'var(--red)'; el.style.background = p5 ? 'rgba(232,0,61,0.1)' : 'rgba(242,47,70,0.07)'; }}
      onmouseleave={e => { const el = e.currentTarget as HTMLElement; el.style.color = p5 ? 'rgba(255,255,255,0.5)' : 'rgba(13,18,43,0.45)'; el.style.background = 'none'; }}
      title="Click for a surprise"
    >SE Scorecard</button>
    <SuggestionBox />
    <a
      href="sms:+18446990268"
      title="Text us feedback"
      style="display:flex;align-items:center;gap:5px;text-decoration:none;padding:4px 8px;border-radius:5px;transition:color 0.15s,background 0.15s;font-size:12px;font-weight:600;color:{p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'}"
      onmouseenter={e => { const el = e.currentTarget as HTMLElement; el.style.color='var(--red)'; el.style.background=p5?'rgba(232,0,61,0.1)':'rgba(242,47,70,0.07)'; }}
      onmouseleave={e => { const el = e.currentTarget as HTMLElement; el.style.color=p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'; el.style.background='none'; }}
    >
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style="opacity:0.8"><rect x="1" y="2" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.4"/><path d="M4 14l2-2h6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
      <span style="font-size:15px;font-weight:700;letter-spacing:0.01em">(844) 699-0268</span>
    </a>
  </div>
</div>

<div style="padding-top:56px">
  {@render children()}
</div>
