<script lang="ts">
  import { onMount } from 'svelte';
  import { theme, user } from '$lib/stores';

  let { children } = $props();

  onMount(() => theme.set('twilio'));
</script>

<div style="position:fixed;top:0;left:0;right:0;height:56px;background:white;border-bottom:1px solid rgba(13,18,43,0.1);z-index:100;display:flex;align-items:center;justify-content:space-between;padding:0 24px;box-shadow:0 1px 8px rgba(13,18,43,0.06)">
  <div style="display:flex;align-items:center;gap:16px">
    <a href="/" style="display:flex;align-items:center;text-decoration:none">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
    </a>
    <div style="width:1px;height:22px;background:rgba(13,18,43,0.12)"></div>
    <span style="font-size:13px;color:rgba(13,18,43,0.45);font-weight:600;letter-spacing:-0.01em">SE Scorecard V2</span>
  </div>
  {#if $user?.email}
  <div style="display:flex;align-items:center;gap:16px">
    <span style="font-size:12px;color:rgba(13,18,43,0.45);font-weight:500">{$user.email}</span>
    <a href="/logout" style="font-size:12px;font-weight:700;color:#F22F46;text-decoration:none;text-transform:uppercase;letter-spacing:0.08em">Sign out</a>
  </div>
  {/if}
</div>

<div style="padding-top:56px">
  {@render children()}
</div>
