<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import {
    getTranscript, getTranscriptAnalysis, runTranscriptAnalysis,
    updateTranscriptAnalysis, rerunTranscriptAnalysis, deleteTranscript,
    type TranscriptResponse, type TranscriptAnalysisResponse,
  } from '$lib/se-assist/api';

  const PRESALES_STAGES = ['1 - Qualified','2 - Discovery','3 - Technical Evaluation','4 - Technical Win Achieved','5 - Technical Loss'];
  const USE_CASE_OPTIONS = ['Alerts & Notifications','Identity & Verification','Asset Management','Promotions','Customer Loyalty','Lead Conversion','Contact Center','IVR & Bots','Field Service & Conversations','Other'];

  let transcript: TranscriptResponse | null = $state(null);
  let analysis: TranscriptAnalysisResponse | null = $state(null);
  let loading = $state(true);
  let analyzing = $state(false);
  let analysisDuration: number | null = $state(null);
  let deleting = $state(false);
  let error = $state('');
  let success = $state('');

  let editFields = $state({
    use_case_category: '', presales_stage: '',
    sfdc_use_case_description: '', sfdc_solutions_notes: '', sfdc_technical_risks: '',
  });

  async function loadData() {
    loading = true;
    const id = Number($page.params.id);
    try {
      transcript = await getTranscript(id);
      try {
        const a = await getTranscriptAnalysis(id);
        analysis = a;
        editFields = {
          use_case_category: a.use_case_category || '',
          presales_stage: a.presales_stage || '',
          sfdc_use_case_description: a.sfdc_use_case_description || '',
          sfdc_solutions_notes: a.sfdc_solutions_notes || '',
          sfdc_technical_risks: a.sfdc_technical_risks || '',
        };
      } catch {}
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  onMount(loadData);

  async function handleAnalyze() {
    analyzing = true; error = '';
    const id = Number($page.params.id);
    const start = Date.now();
    try {
      const res = analysis ? await rerunTranscriptAnalysis(id) : await runTranscriptAnalysis(id);
      analysisDuration = (Date.now() - start) / 1000;
      analysis = res;
      editFields = {
        use_case_category: res.use_case_category || '',
        presales_stage: res.presales_stage || '',
        sfdc_use_case_description: res.sfdc_use_case_description || '',
        sfdc_solutions_notes: res.sfdc_solutions_notes || '',
        sfdc_technical_risks: res.sfdc_technical_risks || '',
      };
      success = 'Analysis complete';
      setTimeout(() => { success = ''; }, 4000);
    } catch (e: any) { error = e.message; }
    finally { analyzing = false; }
  }

  async function handleSaveEdits() {
    if (!analysis) return;
    try {
      const res = await updateTranscriptAnalysis(analysis.id, editFields);
      analysis = res;
      success = 'Changes saved';
      setTimeout(() => { success = ''; }, 3000);
    } catch (e: any) { error = e.message; }
  }

  function copyToClipboard(text: string, label: string) {
    navigator.clipboard.writeText(text);
    success = `${label} copied to clipboard`;
    setTimeout(() => { success = ''; }, 2000);
  }

  async function handleDelete() {
    if (!confirm('Delete this transcript and its analysis?')) return;
    deleting = true;
    try { await deleteTranscript(Number($page.params.id)); goto('/se-assist/transcripts'); }
    catch (e: any) { error = e.message; deleting = false; }
  }

  function autoResize(el: HTMLTextAreaElement) {
    const resize = () => { el.style.height = 'auto'; el.style.height = Math.max(el.scrollHeight, 66) + 'px'; };
    resize();
    el.addEventListener('input', resize);
    return { destroy() { el.removeEventListener('input', resize); } };
  }
</script>

{#if loading}
  <p style="color:#606B85;padding:24px">Loading...</p>
{:else if !transcript}
  <p>Transcript not found</p>
{:else}
  <div>
    <!-- Breadcrumb -->
    <a href="/se-assist/transcripts" class="sa-breadcrumb">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
      Transcripts
    </a>

    <!-- Alerts -->
    {#if error}
      <div class="sa-alert sa-alert-error">
        {error}
        <button onclick={() => { error = ''; }} class="sa-alert-close">&times;</button>
      </div>
    {/if}
    {#if success}
      <div class="sa-alert sa-alert-success">{success}</div>
    {/if}

    <!-- Header -->
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px">
      <div>
        <h1 style="font-size:24px;font-weight:700;margin:0 0 4px;color:#0D122B">{transcript.company_name}</h1>
        <div style="display:flex;align-items:center;gap:8px;font-size:14px;color:#606B85">
          {#if transcript.call_date}
            <span>{new Date(transcript.call_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
          {/if}
          {#if transcript.duration}
            <span style="color:#CACDD8">&middot;</span><span>{transcript.duration}</span>
          {/if}
          <span class="sa-badge sa-badge-{transcript.status}">{transcript.status}</span>
        </div>
      </div>
      <button class="sa-btn sa-btn-destructive" onclick={handleDelete} disabled={deleting}>
        {deleting ? 'Deleting...' : 'Delete'}
      </button>
    </div>

    <!-- Two column layout -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start">
      <!-- Left: Transcript text -->
      <div class="sa-card">
        <h2 style="font-size:16px;font-weight:700;margin:0 0 12px;color:#0D122B">Call Transcript</h2>
        <div style="font-size:14px;line-height:1.7;color:#0D122B;white-space:pre-wrap;max-height:600px;overflow-y:auto;padding:12px 16px;background:#F4F4F6;border-radius:6px">
          {transcript.transcript_text}
        </div>
      </div>

      <!-- Right: AI Analysis -->
      <div class="sa-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
          <h2 style="font-size:16px;font-weight:700;margin:0;color:#0D122B">AI Analysis</h2>
          <button class="sa-btn sa-btn-primary" onclick={handleAnalyze} disabled={analyzing} style="font-size:13px;padding:6px 14px">
            {analyzing ? 'Analyzing...' : analysis ? 'Re-run' : 'Analyze'}
          </button>
        </div>

        {#if analysis}
          <div style="display:flex;flex-direction:column;gap:16px">
            <div class="sa-field">
              <label class="sa-label">Use Case (SE)</label>
              <select bind:value={editFields.use_case_category} class="sa-select">
                <option value="">Select...</option>
                {#each USE_CASE_OPTIONS as opt}<option value={opt}>{opt}</option>{/each}
              </select>
            </div>

            <div class="sa-field">
              <label class="sa-label">Presales Stage</label>
              <select bind:value={editFields.presales_stage} class="sa-select">
                <option value="">Select...</option>
                {#each PRESALES_STAGES as opt}<option value={opt}>{opt}</option>{/each}
              </select>
            </div>

            <div class="sa-field">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <label class="sa-label" style="margin:0">Use Case Description</label>
                <button class="sa-copy-btn" onclick={() => copyToClipboard(editFields.sfdc_use_case_description, 'Use Case Description')} disabled={!editFields.sfdc_use_case_description}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
                  Copy
                </button>
              </div>
              <textarea bind:value={editFields.sfdc_use_case_description} use:autoResize class="sa-textarea"></textarea>
            </div>

            <div class="sa-field">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <label class="sa-label" style="margin:0">Solutions Team Notes</label>
                <button class="sa-copy-btn" onclick={() => copyToClipboard(editFields.sfdc_solutions_notes, 'Solutions Team Notes')} disabled={!editFields.sfdc_solutions_notes}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
                  Copy
                </button>
              </div>
              <textarea bind:value={editFields.sfdc_solutions_notes} use:autoResize class="sa-textarea"></textarea>
            </div>

            <div class="sa-field">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <label class="sa-label" style="margin:0">Technical Risks & Challenges</label>
                <button class="sa-copy-btn" onclick={() => copyToClipboard(editFields.sfdc_technical_risks, 'Technical Risks & Challenges')} disabled={!editFields.sfdc_technical_risks}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
                  Copy
                </button>
              </div>
              <textarea bind:value={editFields.sfdc_technical_risks} use:autoResize class="sa-textarea"></textarea>
            </div>

            <div style="display:flex;justify-content:flex-end">
              <button class="sa-btn sa-btn-secondary" onclick={handleSaveEdits} style="font-size:13px;padding:6px 14px">Save Edits</button>
            </div>

            {#if analysis.model_used}
              <div class="sa-meta">
                Model: {analysis.model_used}
                {#if analysis.input_tokens != null} &middot; {analysis.input_tokens.toLocaleString()} input tokens{/if}
                {#if analysis.output_tokens != null} &middot; {analysis.output_tokens.toLocaleString()} output tokens{/if}
                {#if analysis.cost_usd != null} &middot; ${analysis.cost_usd.toFixed(4)}{/if}
                {#if analysisDuration != null} &middot; {analysisDuration.toFixed(1)}s{/if}
              </div>
            {/if}
          </div>
        {:else}
          <p style="color:#606B85;font-size:14px;margin:0">Run AI analysis to generate SFDC field recommendations.</p>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .sa-breadcrumb { color:#0263E0; text-decoration:none; font-size:13px; font-weight:500; margin-bottom:20px; display:inline-flex; align-items:center; gap:4px; }
  .sa-alert { padding:12px 16px; border-radius:6px; margin-bottom:16px; font-size:14px; display:flex; align-items:center; gap:8px; }
  .sa-alert-error { background:#FDE8EA; border:1px solid #DB132A; color:#991B1B; }
  .sa-alert-success { background:#E1F5E9; border:1px solid #14B053; color:#0A6130; }
  .sa-alert-close { margin-left:auto; background:none; border:none; padding:4px; color:inherit; font-size:16px; cursor:pointer; }

  .sa-btn { border:none; border-radius:6px; padding:8px 16px; font-size:14px; font-weight:600; cursor:pointer; }
  .sa-btn-primary { background:#0263E0; color:#fff; }
  .sa-btn-primary:hover { background:#0150B5; }
  .sa-btn-primary:disabled { opacity:0.6; cursor:not-allowed; }
  .sa-btn-secondary { background:#F4F4F6; color:#0D122B; border:1px solid #CACDD8; }
  .sa-btn-secondary:hover { background:#E8E8EC; }
  .sa-btn-destructive { background:#FDE8EA; color:#DB132A; border:1px solid #DB132A; }
  .sa-btn-destructive:hover { background:#FBCDD1; }
  .sa-btn-destructive:disabled { opacity:0.6; cursor:not-allowed; }

  .sa-card { background:#fff; border:1px solid #CACDD8; border-radius:8px; padding:20px 24px; }

  .sa-badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px; font-weight:600; text-transform:capitalize; }
  .sa-badge-uploaded { background:#E5F0FF; color:#0263E0; }
  .sa-badge-analyzed { background:#E1F5E9; color:#0A6130; }
  .sa-badge-pending { background:#F4F4F6; color:#606B85; }

  .sa-field { display:flex; flex-direction:column; }
  .sa-label { font-size:13px; font-weight:600; color:#606B85; margin-bottom:4px; }
  .sa-select { width:100%; padding:8px 12px; font-size:14px; border:1px solid #CACDD8; border-radius:6px; background:#fff; color:#0D122B; }
  .sa-textarea { width:100%; padding:8px 12px; font-size:14px; border:1px solid #CACDD8; border-radius:6px; background:#fff; color:#0D122B; font-family:inherit; overflow:hidden; resize:none; line-height:1.6; }
  .sa-copy-btn { background:none; border:none; padding:4px; cursor:pointer; color:#606B85; display:flex; align-items:center; gap:4px; font-size:12px; font-weight:500; }
  .sa-copy-btn:disabled { color:#CACDD8; cursor:default; }

  .sa-meta { font-size:12px; color:#8891AA; border-top:1px solid #CACDD8; padding-top:12px; }
</style>
