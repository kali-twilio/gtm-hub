<script lang="ts">
  import { theme } from '$lib/stores';
  import UserChip from '$lib/UserChip.svelte';
  let { children } = $props();
</script>

<!-- Header bar (always Twilio style) -->
<div style="position:fixed;top:0;left:0;right:0;height:56px;background:white;border-bottom:1px solid rgba(13,18,43,0.1);z-index:100;display:flex;align-items:center;justify-content:space-between;padding:0 24px;box-shadow:0 1px 8px rgba(13,18,43,0.06)">
  <div style="display:flex;align-items:center;gap:16px">
    <a href="/" style="display:flex;align-items:center;text-decoration:none">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
    </a>
    <div style="width:1px;height:22px;background:rgba(13,18,43,0.12)"></div>
    <span style="font-size:13px;color:rgba(13,18,43,0.45);font-weight:600;letter-spacing:-0.01em">WhatsApp Wizard</span>
  </div>
  <UserChip inline={true} sfProfile={false} />
</div>

<div style="padding-top:56px">
  {@render children()}
</div>
