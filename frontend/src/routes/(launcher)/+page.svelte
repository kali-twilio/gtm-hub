<script lang="ts">
  import { user, authReady, msgChannel } from '$lib/stores';
  import { getApps, type AppManifest, chatWithAI } from '$lib/api';
  import SuggestionBox from '$lib/SuggestionBox.svelte';

  const PHONE = '+18446990268';
  function contactHref(channel: string) {
    if (channel === 'whatsapp') return `https://wa.me/${PHONE.replace('+', '')}`;
    return `sms:${PHONE}`;
  }

  let apps: AppManifest[] = $state([]);

  $effect(() => {
    if ($authReady && $user) {
      getApps().then(a => { apps = a; });
    }
  });

  // Ask AI
  let chatOpen    = $state(false);
  let chatInput   = $state('');
  let chatLoading = $state(false);
  interface ChatMsg { role: 'user' | 'assistant'; text: string; }
  let chatMessages: ChatMsg[] = $state([]);
  let chatEndEl: HTMLElement | null = $state(null);

  const PROMPTS = [
    "How many closed won deals this quarter?",
    "Who are the top 5 SEs by iACV closed this year?",
    "Show me pipeline deals closing this month",
    "What's the total pipeline iACV for Self Service?",
  ];

  async function sendChat() {
    const msg = chatInput.trim();
    if (!msg || chatLoading) return;
    chatMessages = [...chatMessages, { role: 'user', text: msg }];
    chatInput = '';
    chatLoading = true;
    setTimeout(() => chatEndEl?.scrollIntoView({ behavior: 'smooth' }), 50);
    const res = await chatWithAI(msg, 'gtm-hub');
    chatLoading = false;
    chatMessages = [...chatMessages, { role: 'assistant', text: res.answer ?? res.error ?? 'No response.' }];
    setTimeout(() => chatEndEl?.scrollIntoView({ behavior: 'smooth' }), 50);
  }

  function onChatKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  }
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
    padding: 56px 0 60px;
  }

  /* Override any body data-theme styles for this page */
  :global(body[data-theme="p5"]) .launcher,
  :global(body[data-theme="twilio"]) .launcher {
    background: #0f1117;
    color: #e2e8f0;
    font-family: Inter, ui-sans-serif, system-ui, sans-serif;
  }

  .top-bar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    padding: 0 24px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    background: #090c12;
    gap: 16px;
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

  @keyframes bounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
    40%            { transform: translateY(-6px); opacity: 1; }
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

<!-- Ask AI slide-in panel (dark theme, always — launcher is always dark) -->
{#if $user && chatOpen}
<div style="position:fixed;top:56px;left:0;bottom:0;width:min(420px,100vw);z-index:10000;display:flex;flex-direction:column;background:#111;border-right:1px solid rgba(242,47,70,0.25);">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid rgba(242,47,70,0.2)">
    <div style="font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.12em;color:#F22F46">Ask AI</div>
    <button onclick={() => chatOpen = false} style="background:none;border:none;cursor:pointer;font-size:18px;color:rgba(255,255,255,0.4);line-height:1;padding:2px 4px" aria-label="Close">✕</button>
  </div>
  <div style="flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px">
    {#if chatMessages.length === 0}
      <div style="color:rgba(255,255,255,0.3);font-size:13px;text-align:center;margin-top:24px">Ask anything about Salesforce data.</div>
      <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">
        {#each PROMPTS as prompt}
        <button onclick={() => { chatInput = prompt; sendChat(); }}
          style="text-align:left;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:8px 12px;cursor:pointer;font-size:12px;color:rgba(255,255,255,0.5);transition:all 0.15s"
          onmouseenter={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor='#F22F46'; el.style.color='#F22F46'; }}
          onmouseleave={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor='rgba(255,255,255,0.08)'; el.style.color='rgba(255,255,255,0.5)'; }}
        >{prompt}</button>
        {/each}
      </div>
    {/if}
    {#each chatMessages as msg}
    <div style="display:flex;flex-direction:column;align-items:{msg.role==='user'?'flex-end':'flex-start'}">
      <div style="max-width:85%;padding:10px 13px;border-radius:10px;font-size:13px;line-height:1.5;white-space:pre-wrap;
        {msg.role==='user'?'background:#F22F46;color:white;border-bottom-right-radius:3px;':'background:rgba(255,255,255,0.07);color:rgba(255,255,255,0.85);border-bottom-left-radius:3px;'}"
      >{msg.text}</div>
    </div>
    {/each}
    {#if chatLoading}
    <div style="display:flex;align-items:flex-start">
      <div style="padding:10px 14px;border-radius:10px;border-bottom-left-radius:3px;background:rgba(255,255,255,0.07)">
        <span style="display:inline-flex;gap:4px">{#each [0,1,2] as i}<span style="width:6px;height:6px;border-radius:50%;background:#F22F46;animation:bounce 1.2s ease-in-out {i*0.2}s infinite"></span>{/each}</span>
      </div>
    </div>
    {/if}
    <div bind:this={chatEndEl}></div>
  </div>
  <div style="padding:12px 16px;border-top:1px solid rgba(242,47,70,0.2)">
    <div style="display:flex;gap:8px;align-items:flex-end">
      <textarea bind:value={chatInput} onkeydown={onChatKey} placeholder="Ask about Salesforce data…" rows="2"
        style="flex:1;resize:none;border:1px solid rgba(255,255,255,0.12);border-radius:8px;padding:8px 12px;font-size:13px;background:rgba(255,255,255,0.05);color:rgba(255,255,255,0.85);outline:none;font-family:inherit;line-height:1.4"
      ></textarea>
      <button onclick={sendChat} disabled={chatLoading || !chatInput.trim()}
        style="background:#F22F46;border:none;border-radius:8px;padding:8px 14px;cursor:pointer;color:white;font-size:13px;font-weight:700;opacity:{chatLoading||!chatInput.trim()?0.4:1};transition:opacity 0.15s;white-space:nowrap"
      >Send</button>
    </div>
    <div style="font-size:10px;color:rgba(255,255,255,0.2);margin-top:6px">Enter to send · Shift+Enter for newline · Read-only Salesforce access</div>
  </div>
</div>
{/if}

<div class="launcher" style="transition:margin-left 0.2s;margin-left:{$user && chatOpen?'min(420px,100vw)':'0'}">
  <!-- Top bar -->
  <div class="top-bar">
    <div style="display:flex;align-items:center;gap:16px">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto;opacity:0.9">
      <div style="width:1px;height:22px;background:rgba(255,255,255,0.1)"></div>
      <span style="font-size:13px;font-weight:600;color:#94a3b8;letter-spacing:-0.01em">GTM Hub</span>
      <!-- Ask AI button -->
      <button
        onclick={() => chatOpen = !chatOpen}
        style="display:flex;align-items:center;gap:6px;background:{chatOpen?'rgba(242,47,70,0.15)':'none'};border:1px solid {chatOpen?'#F22F46':'rgba(255,255,255,0.12)'};border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;font-weight:700;letter-spacing:0.02em;color:{chatOpen?'#F22F46':'rgba(255,255,255,0.6)'};transition:all 0.15s;white-space:nowrap"
        onmouseenter={e => { if (!chatOpen) { const el = e.currentTarget as HTMLElement; el.style.color='#F22F46'; el.style.borderColor='#F22F46'; el.style.background='rgba(242,47,70,0.08)'; }}}
        onmouseleave={e => { if (!chatOpen) { const el = e.currentTarget as HTMLElement; el.style.color='rgba(255,255,255,0.6)'; el.style.borderColor='rgba(255,255,255,0.12)'; el.style.background='none'; }}}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        Ask AI
      </button>
      <!-- Feedback group -->
      <div style="display:flex;align-items:center;gap:4px;margin-left:16px;padding:4px 6px;border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07)">
      <SuggestionBox app="gtm-hub" dark={true} />
      <div style="width:1px;height:18px;background:rgba(255,255,255,0.1)"></div>
      <div style="display:flex;align-items:center;border-radius:5px;overflow:hidden;border:1px solid rgba(255,255,255,0.12)">
        {#each [{id:'sms',label:'SMS'},{id:'whatsapp',label:'WA'}] as ch}
          <button
            onclick={() => msgChannel.set(ch.id)}
            style="background:{$msgChannel===ch.id?'rgba(255,255,255,0.1)':'none'};border:none;padding:2px 7px;cursor:pointer;font-size:11px;font-weight:700;letter-spacing:0.02em;color:{$msgChannel===ch.id?'rgba(255,255,255,0.85)':'rgba(255,255,255,0.3)'};transition:color 0.15s,background 0.15s;line-height:1.8"
          >{ch.label}</button>
        {/each}
      </div>
      <a
        href={contactHref($msgChannel)}
        target={$msgChannel === 'whatsapp' ? '_blank' : undefined}
        rel={$msgChannel === 'whatsapp' ? 'noopener noreferrer' : undefined}
        title="{$msgChannel === 'whatsapp' ? 'WhatsApp' : 'Text'} us feedback"
        style="display:flex;align-items:center;gap:6px;text-decoration:none;padding:3px 8px;border-radius:5px;transition:color 0.15s,background 0.15s;color:rgba(255,255,255,0.35)"
        onmouseenter={e => { const el = e.currentTarget as HTMLElement; el.style.color='#F22F46'; el.style.background='rgba(242,47,70,0.1)'; }}
        onmouseleave={e => { const el = e.currentTarget as HTMLElement; el.style.color='rgba(255,255,255,0.35)'; el.style.background='none'; }}
      >
        {#if $msgChannel === 'whatsapp'}
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" style="opacity:0.8;flex-shrink:0"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
        {:else}
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="opacity:0.8;flex-shrink:0"><rect x="1" y="2" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.4"/><path d="M4 14l2-2h6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        {/if}
        <span style="font-size:17px;font-weight:800;letter-spacing:-0.01em;line-height:1">(844) 699-0268</span>
      </a>
    </div>
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
      {#if app.status === 'live' && app.id !== 'se-forecast'}
        <a href={app.path} class="app-card active" style="color:inherit">
          <div class="card-icon">{app.icon}</div>
          <div class="card-name">{app.name}</div>
          <div class="card-desc">{app.description}</div>
          <div class="card-open">Open <span>→</span></div>
        </a>
      {:else if app.id === 'se-forecast'}
        <a href={app.path} class="app-card active" style="color:inherit;position:relative;overflow:hidden;border-color:#f5a623;border-top-color:#f5a623">
          <div style="position:absolute;inset:0;background:repeating-linear-gradient(-45deg,rgba(245,166,35,0.07),rgba(245,166,35,0.07) 10px,transparent 10px,transparent 20px);pointer-events:none;z-index:0"></div>
          <div style="position:relative;z-index:1">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
              <span style="font-size:36px;line-height:1">{app.icon}</span>
              <span style="font-size:10px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#f5a623;background:rgba(245,166,35,0.12);border:1px solid rgba(245,166,35,0.3);border-radius:4px;padding:2px 7px">🚧 WIP</span>
            </div>
            <div class="card-name">{app.name}</div>
            <div class="card-desc">{app.description}</div>
            <div class="card-open" style="color:#f5a623">Open <span>→</span></div>
          </div>
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
