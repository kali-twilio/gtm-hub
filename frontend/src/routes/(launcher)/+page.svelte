<script lang="ts">
  import { user, authReady } from '$lib/stores';
  import { getApps, type AppManifest } from '$lib/api';

  let apps: AppManifest[] = $state([]);

  $effect(() => {
    if ($authReady && $user) {
      getApps().then(a => { apps = a; });
    }
  });
</script>

<!--
  Platform launcher — always neutral/clean regardless of theme.
  Each app has its own branding. This is just the shell.
-->
<style>
  .launcher {
    min-height: 100vh;
    background: #0f1117;
    color: #e2e8f0;
    font-family: Inter, ui-sans-serif, system-ui, sans-serif;
    padding: 0 0 60px;
  }

  /* Override any body data-theme styles for this page */
  :global(body[data-theme="p5"]) .launcher,
  :global(body[data-theme="twilio"]) .launcher {
    background: #0f1117;
    color: #e2e8f0;
    font-family: Inter, ui-sans-serif, system-ui, sans-serif;
  }

  .top-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    padding: 0 24px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    background: #090c12;
  }

  .app-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
    padding: 32px 28px;
    max-width: 900px;
    margin: 0 auto;
  }

  .app-card {
    background: #171c26;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 24px 22px;
    text-decoration: none;
    display: flex;
    flex-direction: column;
    transition: transform 0.18s cubic-bezier(.22,1,.36,1), box-shadow 0.18s, border-color 0.18s;
    cursor: pointer;
  }
  .app-card:hover {
    transform: translateY(-4px) scale(1.02);
    box-shadow: 0 12px 32px rgba(0,0,0,0.4);
    border-color: rgba(255,255,255,0.15);
  }
  .app-card.disabled {
    opacity: 0.42;
    cursor: default;
    pointer-events: none;
  }

  .card-icon {
    font-size: 36px;
    margin-bottom: 14px;
    line-height: 1;
  }
  .card-name {
    font-size: 15px;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 6px;
    letter-spacing: -0.01em;
  }
  .card-desc {
    font-size: 12px;
    color: #64748b;
    line-height: 1.55;
    flex: 1;
    margin-bottom: 16px;
  }
  .card-open {
    font-size: 11px;
    font-weight: 700;
    color: #F22F46;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .card-soon {
    font-size: 10px;
    font-weight: 700;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 4px;
    padding: 2px 8px;
    display: inline-block;
  }

  /* Accent strip on active cards */
  .app-card.active {
    border-top: 2px solid #F22F46;
  }

  .login-wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0f1117;
  }
  .login-box {
    width: 100%;
    max-width: 360px;
    padding: 0 24px;
  }
  .google-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    width: 100%;
    padding: 13px 20px;
    background: white;
    color: #111;
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
    text-decoration: none;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    transition: box-shadow 0.15s;
  }
  .google-btn:hover {
    box-shadow: 0 4px 16px rgba(255,255,255,0.15);
  }

  .section-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: #475569;
    padding: 0 28px;
    margin-bottom: 0;
    max-width: 900px;
    margin-left: auto;
    margin-right: auto;
  }
</style>

{#if !$authReady}
<div style="min-height:100vh;background:#0f1117"></div>
{:else if !$user}

<div class="login-wrap">
  <div class="login-box">
    <div style="text-align:center;margin-bottom:32px">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:26px;width:auto;margin:0 auto 20px;display:block">
      <h1 style="font-size:28px;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;margin-bottom:8px">GTM Hub</h1>
      <p style="font-size:14px;color:#64748b;font-weight:500">Tools that accelerate sales innovation</p>
      <div style="width:32px;height:2px;background:#F22F46;border-radius:1px;margin:14px auto 0"></div>
    </div>
    <div style="background:#171c26;border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:28px 24px">
      <p style="font-size:13px;color:#64748b;font-weight:500;margin-bottom:20px;text-align:center">
        Sign in with your Twilio Google account to access the platform.
      </p>
      <a href="/auth" class="google-btn">
        <svg width="18" height="18" viewBox="0 0 48 48">
          <path fill="#EA4335" d="M24 9.5c3.14 0 5.95 1.08 8.17 2.85l6.09-6.09C34.46 3.05 29.52 1 24 1 14.82 1 7.07 6.48 3.58 14.18l7.09 5.51C12.28 13.36 17.67 9.5 24 9.5z"/>
          <path fill="#4285F4" d="M46.46 24.5c0-1.64-.15-3.22-.42-4.75H24v9h12.64c-.55 2.96-2.2 5.47-4.68 7.16l7.19 5.59C43.44 37.28 46.46 31.36 46.46 24.5z"/>
          <path fill="#FBBC05" d="M10.67 28.31A14.6 14.6 0 0 1 9.5 24c0-1.49.26-2.93.7-4.31l-7.09-5.51A23.94 23.94 0 0 0 0 24c0 3.87.93 7.53 2.58 10.76l8.09-6.45z"/>
          <path fill="#34A853" d="M24 47c5.52 0 10.15-1.83 13.53-4.96l-7.19-5.59C28.6 38.27 26.42 39 24 39c-6.33 0-11.72-3.86-13.33-9.19l-8.09 6.45C6.07 43.52 14.42 47 24 47z"/>
        </svg>
        Sign in with Google
      </a>
      <p style="font-size:11px;color:#334155;text-align:center;margin-top:14px;letter-spacing:0.1em">@TWILIO.COM ACCOUNTS ONLY</p>
    </div>
  </div>
</div>

{:else}

<div class="launcher">
  <!-- Top bar -->
  <div class="top-bar">
    <div style="display:flex;align-items:center;gap:14px">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto;opacity:0.9">
      <div style="width:1px;height:18px;background:rgba(255,255,255,0.1)"></div>
      <span style="font-size:13px;font-weight:600;color:#94a3b8;letter-spacing:-0.01em">GTM Hub</span>
    </div>
  </div>

  <!-- Page heading -->
  <div style="padding:32px 28px 8px;max-width:900px;margin:0 auto">
    <h2 style="font-size:22px;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;margin-bottom:4px">Your Apps</h2>
    <p style="font-size:13px;color:#475569">Select an app to get started.</p>
  </div>

  <!-- App grid -->
  <div class="app-grid">
    {#each apps as app}
      {#if app.status === 'live'}
        <a href={app.path} class="app-card active" style="color:inherit">
          <div class="card-icon">{app.icon}</div>
          <div class="card-name">{app.name}</div>
          <div class="card-desc">{app.description}</div>
          <div class="card-open">Open <span>→</span></div>
        </a>
      {:else}
        <div class="app-card disabled">
          <div class="card-icon">{app.icon}</div>
          <div class="card-name">{app.name}</div>
          <div class="card-desc">{app.description}</div>
          <div class="card-soon">Coming Soon</div>
        </div>
      {/if}
    {/each}
  </div>
</div>

{/if}
