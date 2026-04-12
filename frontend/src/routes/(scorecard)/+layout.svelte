<script lang="ts">
  import { theme } from '$lib/stores';

  let { children } = $props();
</script>

<!-- Theme toggle -->
<button class="theme-toggle" onclick={() => theme.toggle()}>
  {#if $theme === 'p5'}
    <span>🏢</span> Twilio
  {:else}
    <span>🎉</span> Fun Mode
  {/if}
</button>

<!-- Fun Mode (P5) chrome -->
{#if $theme === 'p5'}
<div style="position:fixed;top:0;left:0;right:0;height:4px;background:var(--red);z-index:100;box-shadow:0 0 12px var(--red)"></div>
<div style="position:fixed;bottom:0;left:0;right:0;height:4px;background:var(--red);z-index:100;box-shadow:0 0 12px var(--red)"></div>
<div style="position:fixed;top:16px;left:16px;width:22px;height:22px;border-top:3px solid var(--red);border-left:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;top:16px;right:16px;width:22px;height:22px;border-top:3px solid var(--red);border-right:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:16px;left:16px;width:22px;height:22px;border-bottom:3px solid var(--red);border-left:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:16px;right:16px;width:22px;height:22px;border-bottom:3px solid var(--red);border-right:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:-30px;right:-10px;font-size:280px;font-weight:900;font-style:italic;color:rgba(232,0,61,0.04);line-height:1;pointer-events:none;user-select:none;transform:skewX(-5deg);z-index:0">5</div>
{:else}
<!-- Twilio header bar -->
<div style="position:fixed;top:0;left:0;right:0;height:56px;background:white;border-bottom:1px solid rgba(13,18,43,0.1);z-index:100;display:flex;align-items:center;padding:0 24px;gap:16px;box-shadow:0 1px 8px rgba(13,18,43,0.06)">
  <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
  <div style="width:1px;height:22px;background:rgba(13,18,43,0.12)"></div>
  <span style="font-size:13px;color:rgba(13,18,43,0.45);font-weight:600;letter-spacing:-0.01em">SE Scorecard</span>
</div>
{/if}

<div style="padding-top:{$theme === 'twilio' ? '56px' : '0'}">
  {@render children()}
</div>
