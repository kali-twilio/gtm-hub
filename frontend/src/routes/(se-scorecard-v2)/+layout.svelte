<script lang="ts">
  import { onMount } from 'svelte';
  import { theme, user } from '$lib/stores';

  let { children } = $props();

  onMount(() => {
    if (!localStorage.getItem('theme')) theme.set('twilio');
  });
</script>

<!-- Fun Mode (P5) chrome -->
{#if $theme === 'p5'}
<div style="position:fixed;top:0;left:0;right:0;height:4px;background:var(--red);z-index:100;box-shadow:0 0 12px var(--red)"></div>
<div style="position:fixed;bottom:0;left:0;right:0;height:4px;background:var(--red);z-index:100;box-shadow:0 0 12px var(--red)"></div>
<div style="position:fixed;top:16px;left:16px;width:22px;height:22px;border-top:3px solid var(--red);border-left:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;top:16px;right:16px;width:22px;height:22px;border-top:3px solid var(--red);border-right:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:16px;left:16px;width:22px;height:22px;border-bottom:3px solid var(--red);border-left:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:16px;right:16px;width:22px;height:22px;border-bottom:3px solid var(--red);border-right:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:-30px;right:-10px;font-size:280px;font-weight:900;font-style:italic;color:rgba(232,0,61,0.04);line-height:1;pointer-events:none;user-select:none;transform:skewX(-5deg);z-index:0">5</div>
<!-- Floating toggle to get back to Twilio mode -->
<button class="theme-toggle" onclick={() => theme.toggle()}><span>🏢</span> Twilio</button>
{:else}
<!-- Twilio header bar -->
<div style="position:fixed;top:0;left:0;right:0;height:56px;background:white;border-bottom:1px solid rgba(13,18,43,0.1);z-index:100;display:flex;align-items:center;justify-content:space-between;padding:0 24px;box-shadow:0 1px 8px rgba(13,18,43,0.06)">
  <div style="display:flex;align-items:center;gap:16px">
    <a href="/" style="display:flex;align-items:center;text-decoration:none">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
    </a>
    <div style="width:1px;height:22px;background:rgba(13,18,43,0.12)"></div>
    <span style="font-size:13px;color:rgba(13,18,43,0.45);font-weight:600;letter-spacing:-0.01em">SE Scorecard V2</span>
  </div>
  <div style="display:flex;align-items:center;gap:16px">
    <button onclick={() => theme.toggle()} style="background:rgba(242,47,70,0.07);border:none;border-radius:6px;padding:5px 10px;font-size:11px;font-weight:700;color:#F22F46;cursor:pointer;display:flex;align-items:center;gap:5px;letter-spacing:0.03em;text-transform:uppercase"><span>🎉</span> Fun Mode</button>
    {#if $user?.email}
    <span style="font-size:12px;color:rgba(13,18,43,0.45);font-weight:500">{$user.email}</span>
    <a href="/logout" style="font-size:12px;font-weight:700;color:#F22F46;text-decoration:none;text-transform:uppercase;letter-spacing:0.08em">Sign out</a>
    {/if}
  </div>
</div>
{/if}

<div style="padding-top:{$theme === 'twilio' ? '56px' : '0'}">
  {@render children()}
</div>
