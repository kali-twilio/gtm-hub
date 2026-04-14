<script lang="ts">
  import { page } from '$app/stores';
  import UserChip from '$lib/UserChip.svelte';

  let { children } = $props();

  const isActive = (path: string) => $page.url.pathname.startsWith(path);
</script>

<div class="se-assist-shell">
  <!-- Sidebar -->
  <nav class="se-assist-sidebar">
    <div class="se-assist-sidebar-inner">
      <div class="se-assist-brand">
        <a href="/" class="se-assist-home-link">
          <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:18px;width:auto;filter:brightness(10)" />
        </a>
        <div class="se-assist-brand-divider"></div>
        <span class="se-assist-brand-label">SE Assist</span>
      </div>

      <div class="se-assist-nav">
        <a
          href="/se-assist/emails"
          class="se-assist-nav-item"
          class:active={isActive('/se-assist/emails')}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
          </svg>
          Emails
        </a>
        <a
          href="/se-assist/transcripts"
          class="se-assist-nav-item"
          class:active={isActive('/se-assist/transcripts')}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          Transcripts
        </a>
      </div>

      <div class="se-assist-sidebar-bottom">
        <UserChip inline={true} dark={true} />
      </div>
    </div>
  </nav>

  <!-- Main content -->
  <main class="se-assist-main">
    {@render children()}
  </main>
</div>

<style>
  .se-assist-shell {
    display: flex;
    min-height: 100vh;
    background: #F4F4F6;
  }
  .se-assist-sidebar {
    width: 240px;
    background: #121C2D;
    color: #fff;
    flex-shrink: 0;
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 50;
  }
  .se-assist-sidebar-inner {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 20px 16px;
  }
  .se-assist-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-bottom: 24px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    margin-bottom: 24px;
  }
  .se-assist-home-link { display: flex; align-items: center; }
  .se-assist-brand-divider { width: 1px; height: 18px; background: rgba(255,255,255,0.2); }
  .se-assist-brand-label { font-size: 14px; font-weight: 600; color: rgba(255,255,255,0.9); }

  .se-assist-nav { display: flex; flex-direction: column; gap: 4px; }
  .se-assist-nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    color: rgba(255,255,255,0.65);
    text-decoration: none;
    transition: background 0.15s, color 0.15s;
  }
  .se-assist-nav-item:hover { background: rgba(255,255,255,0.08); color: #fff; }
  .se-assist-nav-item.active { background: rgba(255,255,255,0.12); color: #fff; font-weight: 600; }

  .se-assist-sidebar-bottom { margin-top: auto; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1); }

  .se-assist-main {
    flex: 1;
    margin-left: 240px;
    padding: 32px 40px;
  }
</style>
