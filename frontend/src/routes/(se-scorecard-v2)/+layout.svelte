<script lang="ts">
  import { onMount } from 'svelte';
  import { theme } from '$lib/stores';

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
    <span style="font-size:13px;font-weight:600;letter-spacing:-0.01em;color:{p5 ? 'rgba(255,255,255,0.5)' : 'rgba(13,18,43,0.45)'}">SE Scorecard V2</span>
    {#if p5}
    <button onclick={() => theme.toggle()} style="background:rgba(232,0,61,0.12);border:1px solid rgba(232,0,61,0.25);border-radius:6px;padding:5px 10px;font-size:11px;font-weight:700;color:var(--red);cursor:pointer;display:flex;align-items:center;gap:5px;letter-spacing:0.03em;text-transform:uppercase"><span>🏢</span> Exit Fun Mode</button>
    {:else}
    <button onclick={() => theme.toggle()} style="background:rgba(242,47,70,0.07);border:none;border-radius:6px;padding:5px 10px;font-size:11px;font-weight:700;color:#F22F46;cursor:pointer;display:flex;align-items:center;gap:5px;letter-spacing:0.03em;text-transform:uppercase"><span>🎉</span> Fun Mode</button>
    {/if}
  </div>
</div>

<div style="padding-top:56px">
  {@render children()}
</div>
