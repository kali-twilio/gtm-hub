<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  interface Email {
    id: number;
    subject: string;
    company_name: string | null;
    call_date: string | null;
    duration: string | null;
    parsed_data: any;
    status: string;
    received_at: string;
    created_at: string;
    uploaded_by_name: string | null;
    user_email: string;
  }

  interface Uploader { id: string; name: string; }

  let emails = $state<Email[]>([]);
  let total = $state(0);
  let loading = $state(true);
  let uploading = $state(false);
  let uploadStatus = $state('');
  let error = $state('');
  let dragOver = $state(false);
  let fileInput: HTMLInputElement;

  let uploaders = $state<Uploader[]>([]);
  let filterUser = $state('');

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
      const r = await fetch(`/api/se-assist/emails?${params}`);
      const data = await r.json();
      emails = data.emails;
      total = data.total;
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function loadUploaders() {
    try {
      const r = await fetch('/api/se-assist/emails/uploaders');
      uploaders = await r.json();
    } catch { /* ignore */ }
  }

  onMount(() => { load(); loadUploaders(); });

  $effect(() => { filterUser; load(); });

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    uploading = true;
    error = '';
    const fileArr = Array.from(files);
    const uploadedIds: number[] = [];

    for (const file of fileArr) {
      try {
        uploadStatus = 'Uploading...';
        const fd = new FormData();
        fd.append('file', file);
        const r = await fetch('/api/se-assist/emails/upload', { method: 'POST', body: fd });
        if (!r.ok) { const d = await r.json(); throw new Error(d.error || 'Upload failed'); }
        const res = await r.json();
        uploadedIds.push(res.email_id);
      } catch (e: any) {
        error = e.message;
      }
    }

    if (uploadedIds.length > 0) {
      uploadStatus = 'Analyzing...';
      for (const emailId of uploadedIds) {
        try {
          await fetch(`/api/se-assist/analysis/${emailId}`, { method: 'POST' });
        } catch (e: any) {
          error = e.message;
        }
      }
      if (uploadedIds.length === 1) {
        uploading = false;
        uploadStatus = '';
        goto(`/se-assist/emails/${uploadedIds[0]}`);
        return;
      }
      await load();
      await loadUploaders();
    }
    uploading = false;
    uploadStatus = '';
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragOver = false;
    handleFiles(e.dataTransfer?.files ?? null);
  }

  async function handleDelete(e: MouseEvent, emailId: number) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Delete this email and its analysis?')) return;
    try {
      await fetch(`/api/se-assist/emails/${emailId}`, { method: 'DELETE' });
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
    <h1 style="font-size:24px;font-weight:700;color:var(--c-text);margin-bottom:4px">Gong Emails</h1>
    <p style="font-size:14px;color:var(--c-text-weak)">Upload .eml files from Gong Call Summaries for AI analysis</p>
  </div>
  <div style="display:flex;gap:8px">
    <button class="sa-btn primary" onclick={() => fileInput?.click()} disabled={uploading}>
      {uploading ? (uploadStatus || 'Uploading...') : 'Upload'}
    </button>
    <input bind:this={fileInput} type="file" accept=".eml" multiple style="display:none"
      onchange={(e) => handleFiles((e.target as HTMLInputElement).files)} />
  </div>
</div>

<!-- Alert -->
{#if error}
  <div class="sa-alert warning" style="margin-bottom:16px">
    {error}
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
{:else if emails.length === 0}
  <!-- Empty state / drop zone -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="sa-card"
    style="text-align:center;padding:64px 32px;border:2px dashed {dragOver ? 'var(--c-primary)' : 'var(--c-border)'};background:{dragOver ? '#E5F0FF' : 'var(--c-surface)'};cursor:pointer;transition:border-color 0.15s, background 0.15s"
    ondragover={(e) => { e.preventDefault(); dragOver = true; }}
    ondragleave={() => dragOver = false}
    ondrop={handleDrop}
    onclick={() => fileInput?.click()}
  >
    <div style="width:48px;height:48px;border-radius:50%;background:#E5F0FF;display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0263E0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    </div>
    <h3 style="font-size:16px;font-weight:600;margin-bottom:8px">Drop .eml files here or click to upload</h3>
    <p style="font-size:14px;color:var(--c-text-weak);max-width:420px;margin:0 auto">
      Forward Gong call notification emails to yourself, save as .eml, and upload here.
    </p>
  </div>
{:else}
  <!-- Drop zone banner -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    style="border:2px dashed {dragOver ? 'var(--c-primary)' : 'var(--c-border)'};border-radius:var(--radius-sm);padding:16px 24px;text-align:center;margin-bottom:16px;background:{dragOver ? '#E5F0FF' : 'transparent'};cursor:pointer;font-size:14px;color:var(--c-text-weak);transition:border-color 0.15s,background 0.15s"
    ondragover={(e) => { e.preventDefault(); dragOver = true; }}
    ondragleave={() => dragOver = false}
    ondrop={handleDrop}
    onclick={() => fileInput?.click()}
  >
    Drop .eml files here or click to upload
  </div>

  <div style="display:flex;flex-direction:column;gap:8px">
    {#each emails as email}
      <a href="/se-assist/emails/{email.id}" style="text-decoration:none;color:inherit">
        <div class="sa-card sa-card-hover" style="padding:16px 24px;display:flex;justify-content:space-between;align-items:center;cursor:pointer">
          <div style="display:flex;align-items:center;gap:16px">
            <div style="width:40px;height:40px;border-radius:var(--radius-sm);background:#F4F4F6;display:flex;align-items:center;justify-content:center;flex-shrink:0">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#606B85" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
              </svg>
            </div>
            <div>
              <div style="font-weight:600;font-size:15px;margin-bottom:2px">{email.company_name || 'Unknown Company'}</div>
              <div style="font-size:13px;color:var(--c-text-weak)">
                {email.parsed_data?.call_date || 'Unknown date'}
                {#if email.duration}<span style="color:var(--c-text-weaker)"> &middot; {email.duration}</span>{/if}
                <span style="color:var(--c-text-weaker)"> &middot; Uploaded {formatDate(email.created_at)}</span>
                {#if email.uploaded_by_name}<span style="color:var(--c-text-weaker)"> by {email.uploaded_by_name}</span>{/if}
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="sa-badge {email.status}">{email.status}</span>
            <button class="sa-icon-btn" title="Delete email" onclick={(e) => handleDelete(e, email.id)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
            </button>
          </div>
        </div>
      </a>
    {/each}
    {#if total > emails.length}
      <p style="text-align:center;color:var(--c-text-weak);font-size:13px;padding:8px">Showing {emails.length} of {total}</p>
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
  .sa-badge.synced { background: #FFF4E5; color: #B54708; }
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
</style>
