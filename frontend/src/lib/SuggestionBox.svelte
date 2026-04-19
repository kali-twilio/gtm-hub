<script lang="ts">
  import { getSuggestions, createSuggestion, deleteSuggestion, type Suggestion } from '$lib/api';
  import { theme } from '$lib/stores';

  let { app = '', dark = false }: { app?: string; dark?: boolean } = $props();

  let open       = $state(false);
  let tab        = $state<'view' | 'submit'>('view');
  let items      = $state<Suggestion[]>([]);
  let loading    = $state(false);
  let submitting = $state(false);
  let draft      = $state('');
  let error      = $state('');
  let success    = $state(false);
  let btnEl      = $state<HTMLButtonElement | null>(null);
  let panelLeft  = $state(0);

  const p5 = $derived(dark || $theme === 'p5');

  async function load() {
    loading = true;
    items   = await getSuggestions(app || undefined);
    loading = false;
  }

  async function openBox() {
    if (btnEl) panelLeft = btnEl.getBoundingClientRect().left;
    open = true;
    tab  = draft.trim() ? 'submit' : 'view';
    await load();
  }

  function closeBox() {
    open    = false;
    error   = '';
    success = false;
  }

  async function submit() {
    error = '';
    const text = draft.trim();
    if (!text) { error = 'Type something first.'; return; }
    submitting = true;
    const created = await createSuggestion(text, app || undefined);
    submitting = false;
    if (!created) { error = 'Failed to submit — try again.'; return; }
    items   = [created, ...items];
    draft   = '';
    success = true;

    tab     = 'view';
    setTimeout(() => success = false, 3000);
  }

  async function remove(id: string) {
    const ok = await deleteSuggestion(id);
    if (ok) items = items.filter(s => s.id !== id);
  }

  function fmtDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }
</script>

<!-- Trigger button -->
<button
  bind:this={btnEl}
  onclick={openBox}
  style="background:none;border:none;padding:4px 8px;cursor:pointer;font-size:12px;font-weight:600;color:{open?(p5?'rgba(255,255,255,0.7)':'rgba(13,18,43,0.65)'):(p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)')};border-radius:5px;transition:color 0.15s,background 0.15s;background:{open?(p5?'rgba(255,255,255,0.06)':'rgba(13,18,43,0.05)'):'none'};display:flex;align-items:center;gap:5px"
  onmouseenter={e => { const el = e.currentTarget as HTMLElement; el.style.color = p5?'rgba(255,255,255,0.7)':'rgba(13,18,43,0.65)'; el.style.background = p5?'rgba(255,255,255,0.06)':'rgba(13,18,43,0.05)'; }}
  onmouseleave={e => { if (!open) { const el = e.currentTarget as HTMLElement; el.style.color = p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'; el.style.background = 'none'; } }}
>
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style="opacity:0.8"><path d="M8 1C4.134 1 1 3.91 1 7.5c0 1.66.618 3.18 1.638 4.356L2 15l3.363-1.05A7.18 7.18 0 0 0 8 14c3.866 0 7-2.91 7-6.5S11.866 1 8 1Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>
  Feedback
</button>

<!-- Overlay backdrop -->
{#if open}
<button
  onclick={closeBox}
  aria-label="Close suggestions"
  style="position:fixed;inset:0;z-index:9998;background:rgba(0,0,0,0.35);backdrop-filter:blur(2px);border:none;cursor:default;padding:0"
></button>

<!-- Panel — anchored under the button -->
<div
  style="position:fixed;left:{panelLeft}px;top:64px;z-index:9999;width:380px;max-height:calc(100vh - 80px);display:flex;flex-direction:column;background:{p5?'#0d0d0d':'#fff'};border:1px solid {p5?'rgba(232,0,61,0.3)':'rgba(13,18,43,0.12)'};border-radius:10px;box-shadow:0 16px 48px rgba(0,0,0,0.25);overflow:hidden"
>
  <!-- Header -->
  <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px 12px;border-bottom:1px solid {p5?'rgba(232,0,61,0.15)':'rgba(13,18,43,0.08)'}">
    <div>
      <div style="font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;color:{p5?'#fff':'#0d122b'}">
        Suggestions
      </div>
      <div style="font-size:10px;color:{p5?'rgba(255,255,255,0.4)':'rgba(13,18,43,0.4)'};margin-top:1px;font-weight:500">
        Ideas, bugs, requests — read by the team
      </div>
    </div>
    <button onclick={closeBox} style="background:none;border:none;font-size:18px;cursor:pointer;color:{p5?'rgba(255,255,255,0.4)':'rgba(13,18,43,0.4)'};line-height:1;padding:4px">✕</button>
  </div>

  <!-- Tabs -->
  <div style="display:flex;border-bottom:1px solid {p5?'rgba(232,0,61,0.1)':'rgba(13,18,43,0.07)'}">
    {#each [{key:'view',label:'All ({n})'.replace('{n}',String(items.length))},{key:'submit',label:'Submit'}] as t}
    <button
      onclick={() => { tab = t.key as 'view' | 'submit'; if (t.key === 'view') load(); }}
      style="flex:1;padding:9px 0;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;border:none;cursor:pointer;background:{tab===t.key?(p5?'rgba(232,0,61,0.08)':'rgba(242,47,70,0.05)'):'transparent'};color:{tab===t.key?'var(--red)':(p5?'rgba(255,255,255,0.4)':'rgba(13,18,43,0.4)')};border-bottom:2px solid {tab===t.key?'var(--red)':'transparent'};transition:all 0.12s"
    >
      {t.label}
    </button>
    {/each}
  </div>

  <!-- Body -->
  <div style="flex:1;overflow-y:auto;padding:12px 16px 16px">

    {#if tab === 'view'}
      {#if loading}
        <div style="text-align:center;padding:32px 0;font-size:12px;color:{p5?'rgba(255,255,255,0.3)':'rgba(13,18,43,0.3)'}">Loading…</div>
      {:else if items.length === 0}
        <div style="text-align:center;padding:32px 0;font-size:13px;color:{p5?'rgba(255,255,255,0.3)':'rgba(13,18,43,0.3)'}">
          No suggestions yet — be the first!
        </div>
      {:else}
        <div style="display:flex;flex-direction:column;gap:8px">
          {#each items as s (s.id)}
          <div style="padding:10px 12px;background:{p5?'rgba(255,255,255,0.04)':'rgba(13,18,43,0.03)'};border-radius:6px;border:1px solid {p5?'rgba(255,255,255,0.07)':'rgba(13,18,43,0.07)'};position:relative">
            <div style="font-size:13px;color:{p5?'rgba(255,255,255,0.85)':'#0d122b'};line-height:1.5;margin-bottom:6px;padding-right:{s.is_mine?'24px':'0'}">{s.text}</div>
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
              <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <span style="display:flex;align-items:center;gap:4px;font-size:10px;font-weight:600;color:var(--red)">
                  {#if s.source === 'whatsapp'}
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="opacity:0.8;flex-shrink:0"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                  {:else if s.source === 'sms'}
                  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" style="opacity:0.7;flex-shrink:0"><rect x="1" y="2" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M4 14l2-2h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                  {/if}
                  {s.author}
                </span>
                {#if s.app && !app}
                <span style="font-size:9px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:{p5?'rgba(255,255,255,0.35)':'rgba(13,18,43,0.35)'};background:{p5?'rgba(255,255,255,0.06)':'rgba(13,18,43,0.06)'};border:1px solid {p5?'rgba(255,255,255,0.1)':'rgba(13,18,43,0.1)'};border-radius:3px;padding:1px 5px">{s.app}</span>
                {/if}
              </div>
              <span style="font-size:10px;color:{p5?'rgba(255,255,255,0.25)':'rgba(13,18,43,0.3)'}">{fmtDate(s.created_at)}</span>
            </div>
            {#if s.is_mine}
            <button
              onclick={() => remove(s.id)}
              title="Delete my suggestion"
              style="position:absolute;top:8px;right:8px;background:none;border:none;cursor:pointer;font-size:12px;color:{p5?'rgba(255,255,255,0.25)':'rgba(13,18,43,0.3)'};padding:2px;line-height:1;border-radius:3px"
              onmouseenter={e => (e.currentTarget as HTMLElement).style.color='var(--red)'}
              onmouseleave={e => (e.currentTarget as HTMLElement).style.color=p5?'rgba(255,255,255,0.25)':'rgba(13,18,43,0.3)'}
            >✕</button>
            {/if}
          </div>
          {/each}
        </div>
      {/if}

    {:else}
      {#if success}
      <div style="padding:10px 14px;background:{p5?'rgba(16,185,129,0.12)':'rgba(16,185,129,0.08)'};border:1px solid rgba(16,185,129,0.3);border-radius:6px;font-size:12px;font-weight:600;color:#10B981;margin-bottom:12px">
        Submitted — thanks!
      </div>
      {/if}

      <div style="margin-bottom:8px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;color:{p5?'rgba(255,255,255,0.4)':'rgba(13,18,43,0.4)'}">
        Your suggestion
      </div>
      <textarea
        bind:value={draft}
        placeholder="What would make this tool better?"
        maxlength={1000}
        rows={5}
        style="width:100%;resize:vertical;padding:10px 12px;font-size:13px;font-family:inherit;border-radius:6px;border:1px solid {error?'var(--red)':(p5?'rgba(232,0,61,0.25)':'rgba(13,18,43,0.18)')};background:{p5?'rgba(255,255,255,0.04)':'#f7f8fc'};color:{p5?'rgba(255,255,255,0.85)':'#0d122b'};outline:none;box-sizing:border-box;line-height:1.5"
      ></textarea>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px;margin-bottom:10px">
        {#if error}
        <span style="font-size:11px;color:var(--red);font-weight:600">{error}</span>
        {:else}
        <span></span>
        {/if}
        <span style="font-size:10px;color:{p5?'rgba(255,255,255,0.25)':'rgba(13,18,43,0.3)'}">{draft.length}/1000</span>
      </div>
      <button
        onclick={submit}
        disabled={submitting}
        style="width:100%;padding:9px 0;background:var(--red);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;cursor:{submitting?'not-allowed':'pointer'};opacity:{submitting?0.6:1};transition:opacity 0.12s"
      >
        {submitting ? 'Submitting…' : 'Submit'}
      </button>
      <div style="margin-top:8px;font-size:10px;color:{p5?'rgba(255,255,255,0.25)':'rgba(13,18,43,0.3)'};text-align:center">
        Visible to everyone · Your name shown as your email prefix
      </div>
    {/if}

  </div>
</div>
{/if}
