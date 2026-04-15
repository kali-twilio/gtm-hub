<script lang="ts">
  import { page } from '$app/stores';
  import { theme } from '$lib/stores';
  import { onMount } from 'svelte';

  let { children } = $props();

  onMount(() => {
    if (!localStorage.getItem('theme')) theme.set('twilio');
  });

  const navItems = [
    { href: '/se-assist/emails', label: 'Emails' },
    { href: '/se-assist/transcripts', label: 'Transcripts' },
  ];
</script>

<!-- Header -->
<div class="sa-header">
  <div style="display:flex;align-items:center;gap:16px">
    <a href="/" style="display:flex;align-items:center;text-decoration:none">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
    </a>
    <div style="width:1px;height:22px;background:rgba(13,18,43,0.12)"></div>
    <span style="font-size:13px;font-weight:600;letter-spacing:-0.01em;color:rgba(13,18,43,0.45)">SE Assist</span>
  </div>
  <nav style="display:flex;gap:4px;margin-left:32px">
    {#each navItems as item}
      <a
        href={item.href}
        class="sa-nav-link"
        class:active={$page.url.pathname.startsWith(item.href)}
      >
        {item.label}
      </a>
    {/each}
  </nav>
</div>

<div style="padding:72px 32px 32px">
  {@render children()}
</div>

<style>
  .sa-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 56px;
    z-index: 100;
    display: flex;
    align-items: center;
    padding: 0 24px;
    background: white;
    border-bottom: 1px solid rgba(13,18,43,0.1);
    box-shadow: 0 1px 8px rgba(13,18,43,0.06);
  }
  .sa-nav-link {
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    color: rgba(13,18,43,0.55);
    text-decoration: none;
    transition: background 0.15s, color 0.15s;
  }
  .sa-nav-link:hover { background: rgba(13,18,43,0.05); }
  .sa-nav-link.active {
    background: rgba(2,99,224,0.08);
    color: #0263E0;
  }

  /* App-scoped styles */
  :global([data-theme]) {
    --c-primary: #0263E0;
    --c-link: #0263E0;
    --c-text: #0D122B;
    --c-text-weak: rgba(13,18,43,0.55);
    --c-text-weaker: rgba(13,18,43,0.35);
    --c-border: #CACDD8;
    --c-border-strong: #A0A4B0;
    --c-surface: #F4F4F6;
    --c-success: #027A48;
    --c-danger: #D92D20;
    --radius-sm: 4px;
    --radius-md: 8px;
    --shadow-card: 0 1px 3px rgba(0,0,0,0.08);
  }
</style>
