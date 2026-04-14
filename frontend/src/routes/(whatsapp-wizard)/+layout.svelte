<script lang="ts">
  import { user } from '$lib/stores';
  let { children } = $props();
</script>

<div style="min-height:100vh;background:#0f1117;color:#e2e8f0;font-family:Inter,ui-sans-serif,system-ui,sans-serif">
  <!-- Same header style as GTM Hub launcher -->
  <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 28px;border-bottom:1px solid rgba(255,255,255,0.06);background:#090c12">
    <div style="display:flex;align-items:center;gap:14px">
      <a href="/">
        <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:18px;width:auto;opacity:0.9">
      </a>
      <div style="width:1px;height:18px;background:rgba(255,255,255,0.1)"></div>
      <span style="font-size:13px;font-weight:600;color:#94a3b8;letter-spacing:-0.01em">WhatsApp Wizard</span>
    </div>
    {#if $user}
    <div style="display:flex;align-items:center;gap:16px">
      <span style="font-size:12px;color:#475569">{$user.email}</span>
      <a href="/logout" style="font-size:12px;font-weight:700;color:#F22F46;text-decoration:none;text-transform:uppercase;letter-spacing:0.08em">Sign out</a>
    </div>
    {/if}
  </div>

  {@render children()}
</div>
