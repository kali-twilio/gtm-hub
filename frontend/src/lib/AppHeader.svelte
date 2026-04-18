<script lang="ts">
  import { theme, msgChannel } from '$lib/stores';
  import SuggestionBox from '$lib/SuggestionBox.svelte';
  import { chatWithAI } from '$lib/api';

  let {
    appName    = '',
    appId      = '',
    showAskAI  = false,
    chatOpen   = $bindable(false),
  }: {
    appName?:   string;
    appId?:     string;
    showAskAI?: boolean;
    chatOpen?:  boolean;
  } = $props();

  const p5 = $derived($theme === 'p5');

  const PHONE = '+18446990268';
  function contactHref(channel: string) {
    if (channel === 'whatsapp') return `https://wa.me/${PHONE.replace('+', '')}`;
    return `sms:${PHONE}`;
  }

  // ── Ask AI panel ────────────────────────────────────────────────────────────
  let chatInput   = $state('');
  let chatLoading = $state(false);
  interface ChatMsg { role: 'user' | 'assistant'; text: string; }
  let chatMessages: ChatMsg[] = $state([]);
  let chatEndEl: HTMLElement | null = $state(null);

  const SUGGESTED_PROMPTS: Record<string, string[]> = {
    'se-forecast': [
      "What's our total pipeline iACV this quarter?",
      "Which SEs have the most deals without a TW?",
      "List all deals in Commit without a Technical Win",
      "How many unassigned deals are there?",
    ],
    'gtm-hub': [
      "How many closed won deals this quarter?",
      "Who are the top 5 SEs by iACV closed this year?",
      "Show me pipeline deals closing this month",
      "What's the team's win rate this quarter?",
    ],
  };

  const prompts = $derived(SUGGESTED_PROMPTS[appId] ?? SUGGESTED_PROMPTS['gtm-hub']);

  async function sendChat() {
    const msg = chatInput.trim();
    if (!msg || chatLoading) return;
    chatMessages = [...chatMessages, { role: 'user', text: msg }];
    chatInput = '';
    chatLoading = true;
    setTimeout(() => chatEndEl?.scrollIntoView({ behavior: 'smooth' }), 50);
    const res = await chatWithAI(msg, appId);
    chatLoading = false;
    chatMessages = [...chatMessages, { role: 'assistant', text: res.answer ?? res.error ?? 'No response.' }];
    setTimeout(() => chatEndEl?.scrollIntoView({ behavior: 'smooth' }), 50);
  }

  function onChatKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  }
</script>

<!-- Fixed nav header -->
<div
  style="position:fixed;top:0;left:0;right:0;height:56px;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:0 24px;
    {p5
      ? 'background:#0d0d0d;border-bottom:1px solid rgba(232,0,61,0.35);box-shadow:0 0 20px rgba(232,0,61,0.08);'
      : 'background:white;border-bottom:1px solid rgba(13,18,43,0.1);box-shadow:0 1px 8px rgba(13,18,43,0.06);'}"
>
  <div style="display:flex;align-items:center;gap:16px">
    <a href="/" style="display:flex;align-items:center;text-decoration:none">
      <img src="/Twilio-logo-red.svg.png" alt="Twilio" style="height:22px;width:auto">
    </a>
    <div style="width:1px;height:22px;background:{p5 ? 'rgba(232,0,61,0.3)' : 'rgba(13,18,43,0.12)'}"></div>
    <span style="font-size:13px;font-weight:600;letter-spacing:-0.01em;color:{p5 ? 'rgba(255,255,255,0.5)' : 'rgba(13,18,43,0.45)'}">{appName}</span>

    {#if showAskAI}
    <button
      onclick={() => chatOpen = !chatOpen}
      style="display:flex;align-items:center;gap:6px;background:{chatOpen?(p5?'rgba(232,0,61,0.15)':'rgba(242,47,70,0.1)'):'none'};border:1px solid {chatOpen?'var(--red)':(p5?'rgba(255,255,255,0.12)':'rgba(13,18,43,0.12)')};border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;font-weight:700;letter-spacing:0.02em;color:{chatOpen?'var(--red)':(p5?'rgba(255,255,255,0.6)':'rgba(13,18,43,0.5)')};transition:all 0.15s;white-space:nowrap"
      onmouseenter={e => { if (!chatOpen) { const el = e.currentTarget as HTMLElement; el.style.color='var(--red)'; el.style.borderColor='var(--red)'; el.style.background=p5?'rgba(232,0,61,0.08)':'rgba(242,47,70,0.06)'; }}}
      onmouseleave={e => { if (!chatOpen) { const el = e.currentTarget as HTMLElement; el.style.color=p5?'rgba(255,255,255,0.6)':'rgba(13,18,43,0.5)'; el.style.borderColor=p5?'rgba(255,255,255,0.12)':'rgba(13,18,43,0.12)'; el.style.background='none'; }}}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
      Ask AI
    </button>
    {/if}

    <!-- Feedback group -->
    <div style="display:flex;align-items:center;gap:4px;{showAskAI?'margin-left:16px;':''}padding:4px 6px;border-radius:8px;background:{p5?'rgba(255,255,255,0.03)':'rgba(13,18,43,0.03)'};border:1px solid {p5?'rgba(255,255,255,0.07)':'rgba(13,18,43,0.07)'}">
      <SuggestionBox app={appId} />
      <div style="width:1px;height:18px;background:{p5?'rgba(255,255,255,0.1)':'rgba(13,18,43,0.1)'}"></div>
      <div style="display:flex;align-items:center;border-radius:5px;overflow:hidden;border:1px solid {p5?'rgba(255,255,255,0.12)':'rgba(13,18,43,0.12)'}">
        {#each [{id:'sms',label:'SMS'},{id:'whatsapp',label:'WA'}] as ch}
          <button
            onclick={() => msgChannel.set(ch.id)}
            style="background:{$msgChannel===ch.id?(p5?'rgba(255,255,255,0.1)':'rgba(13,18,43,0.08)'):'none'};border:none;padding:2px 7px;cursor:pointer;font-size:11px;font-weight:700;letter-spacing:0.02em;color:{$msgChannel===ch.id?(p5?'rgba(255,255,255,0.85)':'rgba(13,18,43,0.75)'):(p5?'rgba(255,255,255,0.3)':'rgba(13,18,43,0.3)')};transition:color 0.15s,background 0.15s;line-height:1.8"
          >{ch.label}</button>
        {/each}
      </div>
      <a
        href={contactHref($msgChannel)}
        target={$msgChannel === 'whatsapp' ? '_blank' : undefined}
        rel={$msgChannel === 'whatsapp' ? 'noopener noreferrer' : undefined}
        title="{$msgChannel === 'whatsapp' ? 'WhatsApp' : 'Text'} us feedback"
        style="display:flex;align-items:center;gap:6px;text-decoration:none;padding:3px 8px;border-radius:5px;transition:color 0.15s,background 0.15s;color:{p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'}"
        onmouseenter={e => { const el = e.currentTarget as HTMLElement; el.style.color='var(--red)'; el.style.background=p5?'rgba(232,0,61,0.1)':'rgba(242,47,70,0.07)'; }}
        onmouseleave={e => { const el = e.currentTarget as HTMLElement; el.style.color=p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'; el.style.background='none'; }}
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

<!-- Ask AI slide-in panel -->
{#if showAskAI && chatOpen}
<div style="position:fixed;top:56px;left:0;bottom:0;width:min(420px,100vw);z-index:10000;display:flex;flex-direction:column;
  {p5?'background:#111;border-right:1px solid rgba(232,0,61,0.25);':'background:white;border-right:1px solid rgba(13,18,43,0.1);box-shadow:4px 0 24px rgba(13,18,43,0.08);'}">

  <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid {p5?'rgba(232,0,61,0.2)':'rgba(13,18,43,0.08)'}">
    <div style="font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.12em;color:var(--red)">Ask AI</div>
    <button onclick={() => chatOpen = false} style="background:none;border:none;cursor:pointer;font-size:18px;color:{p5?'rgba(255,255,255,0.4)':'rgba(13,18,43,0.35)'};line-height:1;padding:2px 4px" aria-label="Close">✕</button>
  </div>

  <div style="flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px">
    {#if chatMessages.length === 0}
      <div style="color:{p5?'rgba(255,255,255,0.3)':'rgba(13,18,43,0.35)'};font-size:13px;text-align:center;margin-top:24px">
        Ask anything about Salesforce data.
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">
        {#each prompts as prompt}
        <button onclick={() => { chatInput = prompt; sendChat(); }}
          style="text-align:left;background:{p5?'rgba(255,255,255,0.04)':'rgba(13,18,43,0.03)'};border:1px solid {p5?'rgba(255,255,255,0.08)':'rgba(13,18,43,0.08)'};border-radius:6px;padding:8px 12px;cursor:pointer;font-size:12px;color:{p5?'rgba(255,255,255,0.5)':'rgba(13,18,43,0.5)'};transition:all 0.15s"
          onmouseenter={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor='var(--red)'; el.style.color='var(--red)'; }}
          onmouseleave={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor=p5?'rgba(255,255,255,0.08)':'rgba(13,18,43,0.08)'; el.style.color=p5?'rgba(255,255,255,0.5)':'rgba(13,18,43,0.5)'; }}
        >{prompt}</button>
        {/each}
      </div>
    {/if}
    {#each chatMessages as msg}
    <div style="display:flex;flex-direction:column;align-items:{msg.role==='user'?'flex-end':'flex-start'}">
      <div style="max-width:85%;padding:10px 13px;border-radius:10px;font-size:13px;line-height:1.5;white-space:pre-wrap;
        {msg.role==='user'
          ? 'background:var(--red);color:white;border-bottom-right-radius:3px;'
          : p5?'background:rgba(255,255,255,0.07);color:rgba(255,255,255,0.85);border-bottom-left-radius:3px;':'background:rgba(13,18,43,0.05);color:rgba(13,18,43,0.85);border-bottom-left-radius:3px;'}"
      >{msg.text}</div>
    </div>
    {/each}
    {#if chatLoading}
    <div style="display:flex;align-items:flex-start">
      <div style="padding:10px 14px;border-radius:10px;border-bottom-left-radius:3px;background:{p5?'rgba(255,255,255,0.07)':'rgba(13,18,43,0.05)'}">
        <span style="display:inline-flex;gap:4px">{#each [0,1,2] as i}<span style="width:6px;height:6px;border-radius:50%;background:var(--red);animation:bounce 1.2s ease-in-out {i*0.2}s infinite"></span>{/each}</span>
      </div>
    </div>
    {/if}
    <div bind:this={chatEndEl}></div>
  </div>

  <div style="padding:12px 16px;border-top:1px solid {p5?'rgba(232,0,61,0.2)':'rgba(13,18,43,0.08)'}">
    <div style="display:flex;gap:8px;align-items:flex-end">
      <textarea
        bind:value={chatInput}
        onkeydown={onChatKey}
        placeholder="Ask about Salesforce data…"
        rows="2"
        style="flex:1;resize:none;border:1px solid {p5?'rgba(255,255,255,0.12)':'rgba(13,18,43,0.15)'};border-radius:8px;padding:8px 12px;font-size:13px;background:{p5?'rgba(255,255,255,0.05)':'white'};color:{p5?'rgba(255,255,255,0.85)':'rgba(13,18,43,0.85)'};outline:none;font-family:inherit;line-height:1.4"
      ></textarea>
      <button onclick={sendChat} disabled={chatLoading || !chatInput.trim()}
        style="background:var(--red);border:none;border-radius:8px;padding:8px 14px;cursor:pointer;color:white;font-size:13px;font-weight:700;opacity:{chatLoading||!chatInput.trim()?'0.4':'1'};transition:opacity 0.15s;white-space:nowrap"
      >Send</button>
    </div>
    <div style="font-size:10px;color:{p5?'rgba(255,255,255,0.2)':'rgba(13,18,43,0.25)'};margin-top:6px">Enter to send · Shift+Enter for newline · Read-only Salesforce access</div>
  </div>
</div>
{/if}

<style>
@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40%            { transform: translateY(-6px); opacity: 1; }
}
</style>
