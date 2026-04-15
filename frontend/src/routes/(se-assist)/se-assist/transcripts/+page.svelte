<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  interface Transcript {
    id: number;
    company_name: string;
    call_date: string | null;
    duration: string | null;
    transcript_text: string;
    status: string;
    created_at: string;
    uploaded_by_name: string | null;
    user_email: string;
  }

  interface Uploader { id: string; name: string; }

  let transcripts = $state<Transcript[]>([]);
  let total = $state(0);
  let loading = $state(true);
  let submitting = $state(false);
  let submitStatus = $state('');
  let error = $state('');
  let showForm = $state(false);

  let uploaders = $state<Uploader[]>([]);
  let filterUser = $state('');

  let companyName = $state('');
  let callDate = $state('');
  let transcriptText = $state('');

  function formatDate(iso: string) {
    const utcIso = iso.endsWith('Z') ? iso : iso + 'Z';
    return new Date(utcIso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
    });
  }

  async function load() {
    loading = true;
    try {
      const params = new URLSearchParams({ skip: '0', limit: '20' });
      if (filterUser) params.set('uploaded_by', filterUser);
      const r = await fetch(`/api/se-assist/transcripts?${params}`);
      const data = await r.json();
      transcripts = data.transcripts;
      total = data.total;
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function loadUploaders() {
    try {
      const r = await fetch('/api/se-assist/transcripts/uploaders');
      uploaders = await r.json();
    } catch { /* ignore */ }
  }

  onMount(() => { load(); loadUploaders(); });

  $effect(() => { filterUser; load(); });

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    if (!companyName.trim() || !transcriptText.trim()) return;
    submitting = true;
    error = '';
    try {
      submitStatus = 'Submitting...';
      const r = await fetch('/api/se-assist/transcripts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: companyName.trim(),
          call_date: callDate.trim() || undefined,
          transcript_text: transcriptText.trim(),
        }),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.error || 'Submit failed'); }
      const transcript = await r.json();
      submitStatus = 'Analyzing...';
      await fetch(`/api/se-assist/transcripts/${transcript.id}/analyze`, { method: 'POST' });
      submitting = false;
      submitStatus = '';
      goto(`/se-assist/transcripts/${transcript.id}`);
    } catch (e: any) {
      error = e.message;
      submitting = false;
      submitStatus = '';
    }
  }

  async function handleDelete(e: MouseEvent, id: number) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Delete this transcript and its analysis?')) return;
    try {
      await fetch(`/api/se-assist/transcripts/${id}`, { method: 'DELETE' });
      await load();
      await loadUploaders();
    } catch (err: any) {
      error = err.message;
    }
  }
</script>

<!-- Page header -->
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px">
  <div>
    <h1 style="font-size:24px;font-weight:700;color:var(--c-text);margin-bottom:4px">Transcripts</h1>
    <p style="font-size:14px;color:var(--c-text-weak)">Paste Gong call transcripts for AI analysis</p>
  </div>
  <button class="sa-btn primary" onclick={() => showForm = !showForm}>
    {showForm ? 'Cancel' : 'New Transcript'}
  </button>
</div>

<!-- Alert -->
{#if error}
  <div class="sa-alert warning" style="margin-bottom:16px">{error}</div>
{/if}

<!-- Paste form -->
{#if showForm}
  <div class="sa-card" style="margin-bottom:24px">
    <h2 style="font-size:16px;font-weight:700;margin-bottom:16px">Paste Transcript</h2>
    <form onsubmit={handleSubmit} style="display:flex;flex-direction:column;gap:12px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div>
          <label class="sa-field-label">Company Name *</label>
          <input type="text" bind:value={companyName} placeholder="e.g. Acme Corp" required class="sa-input" />
        </div>
        <div>
          <label class="sa-field-label">Call Date</label>
          <input type="text" bind:value={callDate} placeholder="e.g. Apr 10, 2026" class="sa-input" />
        </div>
      </div>
      <div>
        <label class="sa-field-label">Transcript *</label>
        <textarea bind:value={transcriptText} placeholder="Paste the full Gong call transcript here..." required class="sa-textarea" style="min-height:200px;resize:vertical;overflow:auto"></textarea>
      </div>
      <div style="display:flex;justify-content:flex-end">
        <button class="sa-btn primary" type="submit" disabled={submitting}>
          {submitting ? (submitStatus || 'Submitting...') : 'Submit Transcript'}
        </button>
      </div>
    </form>
  </div>
{/if}

<!-- Filter bar -->
{#if uploaders.length > 0}
  <div style="margin-bottom:16px;display:flex;align-items:center;gap:8px">
    <label style="font-size:13px;font-weight:600;color:var(--c-text-weak)">Uploaded by:</label>
    <select bind:value={filterUser} style="width:auto;padding:4px 8px;font-size:13px;border:1px solid var(--c-border);border-radius:var(--radius-sm)">
      <option value="">All</option>
      {#each uploaders as u}
        <option value={u.id}>{u.name}</option>
      {/each}
    </select>
  </div>
{/if}

<!-- Content -->
{#if loading}
  <p style="color:var(--c-text-weak);padding:24px">Loading...</p>
{:else if transcripts.length === 0 && !showForm}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="sa-card" style="text-align:center;padding:64px 32px;border:2px dashed var(--c-border);background:var(--c-surface);cursor:pointer" onclick={() => showForm = true}>
    <div style="width:48px;height:48px;border-radius:50%;background:#E5F0FF;display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0263E0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    </div>
    <h3 style="font-size:16px;font-weight:600;margin-bottom:8px">No transcripts yet</h3>
    <p style="font-size:14px;color:var(--c-text-weak);max-width:420px;margin:0 auto">
      Click "New Transcript" to paste a Gong call transcript for AI analysis.
    </p>
  </div>
{:else}
  <div style="display:flex;flex-direction:column;gap:8px">
    {#each transcripts as t}
      <a href="/se-assist/transcripts/{t.id}" style="text-decoration:none;color:inherit">
        <div class="sa-card sa-card-hover" style="padding:16px 24px;display:flex;justify-content:space-between;align-items:center;cursor:pointer">
          <div style="display:flex;align-items:center;gap:16px">
            <div style="width:40px;height:40px;border-radius:var(--radius-sm);background:#F4F4F6;display:flex;align-items:center;justify-content:center;flex-shrink:0">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#606B85" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            </div>
            <div>
              <div style="font-weight:600;font-size:15px;margin-bottom:2px">{t.company_name}</div>
              <div style="font-size:13px;color:var(--c-text-weak)">
                {#if t.call_date}
                  {new Date(t.call_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                {:else}
                  No date
                {/if}
                {#if t.duration}<span style="color:var(--c-text-weaker)"> &middot; {t.duration}</span>{/if}
                <span style="color:var(--c-text-weaker)"> &middot; Uploaded {formatDate(t.created_at)}</span>
                {#if t.uploaded_by_name}<span style="color:var(--c-text-weaker)"> by {t.uploaded_by_name}</span>{/if}
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="sa-badge {t.status}">{t.status}</span>
            <button class="sa-icon-btn" title="Delete transcript" onclick={(e) => handleDelete(e, t.id)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
            </button>
          </div>
        </div>
      </a>
    {/each}
    {#if total > transcripts.length}
      <p style="text-align:center;color:var(--c-text-weak);font-size:13px;padding:8px">Showing {transcripts.length} of {total}</p>
    {/if}
  </div>
{/if}

<style>
  .sa-card {
    background: white;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-md);
    padding: 24px;
  }
  .sa-card-hover { transition: border-color 0.15s, box-shadow 0.15s; }
  .sa-card-hover:hover { border-color: #0263E0; box-shadow: var(--shadow-card); }
  .sa-btn {
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: background 0.15s;
  }
  .sa-btn.primary { background: #0263E0; color: white; }
  .sa-btn.primary:hover { background: #0150B5; }
  .sa-btn:disabled { opacity: 0.6; cursor: not-allowed; }
  .sa-alert.warning {
    background: #FFF4E5;
    border: 1px solid #F47C22;
    padding: 12px 16px;
    border-radius: var(--radius-sm);
    font-size: 14px;
    color: #8A5200;
  }
  .sa-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 100px;
    font-size: 12px;
    font-weight: 600;
    text-transform: capitalize;
  }
  .sa-badge.uploaded { background: #E5F0FF; color: #0263E0; }
  .sa-badge.analyzed { background: #E1F5E9; color: #027A48; }
  .sa-badge.pending { background: #F4F4F6; color: #606B85; }
  .sa-icon-btn {
    background: none;
    border: none;
    padding: 4px;
    color: var(--c-text-weaker);
    cursor: pointer;
    display: flex;
    align-items: center;
  }
  .sa-icon-btn:hover { color: var(--c-danger); }
  .sa-field-label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--c-text-weak);
    margin-bottom: 4px;
  }
  .sa-input {
    width: 100%;
    padding: 8px 12px;
    font-size: 14px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    color: var(--c-text);
    background: white;
  }
  .sa-input:focus { outline: none; border-color: #0263E0; box-shadow: 0 0 0 2px rgba(2,99,224,0.15); }
  .sa-textarea {
    width: 100%;
    padding: 8px 12px;
    font-size: 14px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    font-family: inherit;
    color: var(--c-text);
  }
  .sa-textarea:focus { outline: none; border-color: #0263E0; box-shadow: 0 0 0 2px rgba(2,99,224,0.15); }
</style>
