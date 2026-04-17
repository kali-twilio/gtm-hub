<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  let { children } = $props();
  let prevTheme = '';

  onMount(() => {
    prevTheme = document.body.getAttribute('data-theme') ?? '';
    document.body.setAttribute('data-theme', 'twilio');
  });

  onDestroy(() => {
    if (prevTheme) {
      document.body.setAttribute('data-theme', prevTheme);
    } else {
      document.body.removeAttribute('data-theme');
    }
  });
</script>

<!-- Header -->
<div style="position:fixed;top:0;left:0;right:0;height:56px;z-index:100;display:flex;align-items:center;padding:0 24px;background:white;border-bottom:1px solid rgba(13,18,43,0.1);box-shadow:0 1px 8px rgba(13,18,43,0.06)">
  <div style="display:flex;align-items:center;gap:16px">
    <a href="/" style="display:flex;align-items:center;text-decoration:none">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
    </a>
    <div style="width:1px;height:22px;background:rgba(13,18,43,0.12)"></div>
    <span style="font-size:13px;font-weight:600;letter-spacing:-0.01em;color:rgba(13,18,43,0.45)">SE Forecast</span>
  </div>
</div>

<div style="padding-top:56px;min-height:100vh;background:#F4F4F6">
  {@render children()}
</div>
