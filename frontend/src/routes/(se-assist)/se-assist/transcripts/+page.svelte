<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import {
    listTranscripts, createTranscript, deleteTranscript,
    listTranscriptUploaders, runTranscriptAnalysis,
    type TranscriptResponse, type Uploader,
  } from '$lib/se-assist/api';

  let transcripts: TranscriptResponse[] = $state([]);
  let total = $state(0);
  let loading = $state(true);
  let submitting = $state(false);
  let submitStatus = $state('');
  let error = $state('');
  let showForm = $state(false);

  let uploaders: Uploader[] = $state([]);
  let filterUser: number | undefined = $state(undefined);

  // Form fields
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

  async function load(uploadedBy?: number) {
    loading = true;
    try {
      const res = await listTranscripts(0, 20, uploadedBy);
      transcripts = res.transcripts;
      total = res.total;
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  async function loadUploaders() {
    try { uploaders = await listTranscriptUploaders(); } catch {}
  }

  onMount(() => { load(filterUser); loadUploaders(); });
  $effect(() => { load(filterUser); });

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    if (!companyName.trim() || !transcriptText.trim()) return;
    submitting = true; error = '';
    try {
      submitStatus = 'Submitting...';
      const transcript = await createTranscript({
        company_name: companyName.trim(),
        call_date: callDate.trim() || undefined,
        transcript_text: transcriptText.trim(),
      });
      submitStatus = 'Analyzing...';
      await runTranscriptAnalysis(transcript.id);
      submitting = false; submitStatus = '';
      goto(`/se-assist/transcripts/${transcript.id}`);
    } catch (e: any) {
      error = e.message;
      submitting = false; submitStatus = '';
    }
  }

  async function handleDelete(e: MouseEvent, id: number) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Delete this transcript and its analysis?')) return;
    try {
      await deleteTranscript(id);
      await load(filterUser);
      await loadUploaders();
    } catch (err: any) { error = err.message; }
  }
</script>

<div>
  <!-- Page header -->
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px">
    <div>
      <h1 style="font-size:24px;font-weight:700;color:#0D122B;margin:0 0 4px">Transcripts</h1>
      <p style="font-size:14px;color:#606B85;margin:0">Paste Gong call transcripts for AI analysis</p>
    </div>
    <button class="sa-btn sa-btn-primary" onclick={() => { showForm = !showForm; }}>
      {showForm ? 'Cancel' : 'New Transcript'}
    </button>
  </div>

  <!-- Alert -->
  {#if error}
    <div class="sa-alert sa-alert-warn">{error}</div>
  {/if}

  <!-- Paste form -->
  {#if showForm}
    <div class="sa-card" style="margin-bottom:24px">
      <h2 style="font-size:16px;font-weight:700;margin:0 0 16px;color:#0D122B">Paste Transcript</h2>
      <form onsubmit={handleSubmit} style="display:flex;flex-direction:column;gap:12px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div>
            <label class="sa-label">Company Name *</label>
            <input type="text" bind:value={companyName} placeholder="e.g. Acme Corp" required class="sa-input" />
          </div>
          <div>
            <label class="sa-label">Call Date</label>
            <input type="text" bind:value={callDate} placeholder="e.g. Apr 10, 2026" class="sa-input" />
          </div>
        </div>
        <div>
          <label class="sa-label">Transcript *</label>
          <textarea bind:value={transcriptText} placeholder="Paste the full Gong call transcript here..." required class="sa-textarea" style="min-height:200px"></textarea>
        </div>
        <div style="display:flex;justify-content:flex-end">
          <button class="sa-btn sa-btn-primary" type="submit" disabled={submitting}>
            {submitting ? (submitStatus || 'Submitting...') : 'Submit Transcript'}
          </button>
        </div>
      </form>
    </div>
  {/if}

  <!-- Filter -->
  {#if uploaders.length > 0}
    <div style="margin-bottom:16px;display:flex;align-items:center;gap:8px">
      <label style="font-size:13px;font-weight:600;color:#606B85">Uploaded by:</label>
      <select style="width:auto;padding:4px 8px;font-size:13px;border:1px solid #CACDD8;border-radius:4px;background:#fff"
        onchange={(e) => { const v = (e.target as HTMLSelectElement).value; filterUser = v ? Number(v) : undefined; }}>
        <option value="">All</option>
        {#each uploaders as u}
          <option value={u.id}>{u.name}</option>
        {/each}
      </select>
    </div>
  {/if}

  <!-- Content -->
  {#if loading}
    <p style="color:#606B85;padding:24px">Loading...</p>
  {:else if transcripts.length === 0 && !showForm}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="sa-card sa-empty-state" onclick={() => { showForm = true; }}>
      <div class="sa-drop-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0263E0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
        </svg>
      </div>
      <h3 style="font-size:16px;font-weight:600;margin:0 0 8px">No transcripts yet</h3>
      <p style="font-size:14px;color:#606B85;max-width:420px;margin:0 auto">
        Click "New Transcript" to paste a Gong call transcript for AI analysis.
      </p>
    </div>
  {:else}
    <div style="display:flex;flex-direction:column;gap:8px">
      {#each transcripts as t (t.id)}
        <a href="/se-assist/transcripts/{t.id}" class="sa-card sa-card-row">
          <div style="display:flex;align-items:center;gap:16px">
            <div class="sa-icon-box">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#606B85" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            </div>
            <div>
              <div style="font-weight:600;font-size:15px;margin-bottom:2px">{t.company_name}</div>
              <div style="font-size:13px;color:#606B85">
                {t.call_date ? new Date(t.call_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'No date'}
                {#if t.duration}<span style="color:#8891AA"> &middot; {t.duration}</span>{/if}
                <span style="color:#8891AA"> &middot; Uploaded {formatDate(t.created_at)}</span>
                {#if t.uploaded_by_name}<span style="color:#8891AA"> by {t.uploaded_by_name}</span>{/if}
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="sa-badge sa-badge-{t.status}">{t.status}</span>
            <button class="sa-btn-icon" title="Delete transcript"
              onclick={(e) => handleDelete(e, t.id)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
            </button>
          </div>
        </a>
      {/each}
      {#if total > transcripts.length}
        <p style="text-align:center;color:#606B85;font-size:13px;padding:8px">Showing {transcripts.length} of {total}</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .sa-btn { border:none; border-radius:6px; padding:8px 16px; font-size:14px; font-weight:600; cursor:pointer; transition:background 0.15s; }
  .sa-btn-primary { background:#0263E0; color:#fff; }
  .sa-btn-primary:hover { background:#0150B5; }
  .sa-btn-primary:disabled { opacity:0.6; cursor:not-allowed; }
  .sa-btn-icon { background:none; border:none; padding:4px; color:#8891AA; cursor:pointer; display:flex; align-items:center; }
  .sa-btn-icon:hover { color:#0D122B; }

  .sa-alert-warn { background:#FFF4E5; border:1px solid #F47C22; padding:12px 16px; border-radius:6px; margin-bottom:16px; font-size:14px; color:#8A5200; }

  .sa-card { background:#fff; border:1px solid #CACDD8; border-radius:8px; padding:20px 24px; }
  .sa-card-row { padding:16px 24px; display:flex; justify-content:space-between; align-items:center; cursor:pointer; text-decoration:none; color:inherit; transition:border-color 0.15s, box-shadow 0.15s; }
  .sa-card-row:hover { border-color:#0263E0; box-shadow:0 2px 8px rgba(2,99,224,0.1); }

  .sa-icon-box { width:40px; height:40px; border-radius:6px; background:#F4F4F6; display:flex; align-items:center; justify-content:center; flex-shrink:0; }

  .sa-badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px; font-weight:600; text-transform:capitalize; }
  .sa-badge-uploaded { background:#E5F0FF; color:#0263E0; }
  .sa-badge-analyzed { background:#E1F5E9; color:#0A6130; }
  .sa-badge-pending { background:#F4F4F6; color:#606B85; }

  .sa-empty-state { text-align:center; padding:64px 32px; border:2px dashed #CACDD8; cursor:pointer; }
  .sa-drop-icon { width:48px; height:48px; border-radius:50%; background:#E5F0FF; display:inline-flex; align-items:center; justify-content:center; margin-bottom:16px; }

  .sa-label { display:block; font-size:13px; font-weight:600; color:#606B85; margin-bottom:4px; }
  .sa-input { width:100%; padding:8px 12px; font-size:14px; border:1px solid #CACDD8; border-radius:6px; background:#fff; color:#0D122B; }
  .sa-textarea { width:100%; padding:8px 12px; font-size:14px; border:1px solid #CACDD8; border-radius:6px; background:#fff; color:#0D122B; font-family:inherit; line-height:1.6; }
</style>
