<script lang="ts">
  import { onMount } from 'svelte';
  import { theme } from '$lib/stores';

  let { children } = $props();

  // SE Scorecard V2 is always Twilio mode — no fun mode
  onMount(() => theme.set('twilio'));
</script>

<div style="position:fixed;top:0;left:0;right:0;height:56px;background:white;border-bottom:1px solid rgba(13,18,43,0.1);z-index:100;display:flex;align-items:center;padding:0 24px;gap:16px;box-shadow:0 1px 8px rgba(13,18,43,0.06)">
  <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
  <div style="width:1px;height:22px;background:rgba(13,18,43,0.12)"></div>
  <span style="font-size:13px;color:rgba(13,18,43,0.45);font-weight:600;letter-spacing:-0.01em">SE Scorecard V2</span>
</div>

<div style="padding-top:56px">
  {@render children()}
</div>
