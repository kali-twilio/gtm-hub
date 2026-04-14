<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import {
    getEmail, getAnalysis, runAnalysis, updateAnalysis, rerunAnalysis, deleteEmail,
    type EmailResponse, type AnalysisResponse,
  } from '$lib/se-assist/api';

  const PRESALES_STAGES = ['1 - Qualified','2 - Discovery','3 - Technical Evaluation','4 - Technical Win Achieved','5 - Technical Loss'];
  const USE_CASE_OPTIONS = ['Alerts & Notifications','Identity & Verification','Asset Management','Promotions','Customer Loyalty','Lead Conversion','Contact Center','IVR & Bots','Field Service & Conversations','Other'];

  let emailData: EmailResponse | null = $state(null);
  let analysis: AnalysisResponse | null = $state(null);
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
      emailData = await getEmail(id);
      try {
        const a = await getAnalysis(id);
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
      const res = analysis ? await rerunAnalysis(id) : await runAnalysis(id);
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
      const res = await updateAnalysis(analysis.id, editFields);
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
    if (!confirm('Delete this email and its analysis?')) return;
    deleting = true;
    try { await deleteEmail(Number($page.params.id)); goto('/se-assist/emails'); }
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
{:else if !emailData}
  <p>Email not found</p>
{:else}
  {@const parsed = emailData.parsed_data}
  <div>
    <!-- Breadcrumb -->
    <a href="/se-assist/emails" class="sa-breadcrumb">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
      Emails
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
        <h1 style="font-size:24px;font-weight:700;margin:0 0 4px;color:#0D122B">{parsed.company_name}</h1>
        <div style="display:flex;align-items:center;gap:8px;font-size:14px;color:#606B85">
          <span>{parsed.call_date}</span>
          {#if parsed.duration}<span style="color:#CACDD8">&middot;</span><span>{parsed.duration}</span>{/if}
          <span class="sa-badge sa-badge-{emailData.status}">{emailData.status}</span>
        </div>
      </div>
      <button class="sa-btn sa-btn-destructive" onclick={handleDelete} disabled={deleting}>
        {deleting ? 'Deleting...' : 'Delete'}
      </button>
    </div>

    <!-- Two column layout -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start">
      <!-- Left: Gong notes -->
      <div style="display:flex;flex-direction:column;gap:24px">
        <div class="sa-card">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:20px">
            <div>
              <h3 class="sa-section-label">Twilio</h3>
              {#each parsed.twilio_participants || [] as p}
                <div style="font-size:14px;margin-bottom:4px">
                  <span style="font-weight:500">{p.name}</span>
                  {#if p.title}<span style="color:#606B85;font-size:13px"> &middot; {p.title}</span>{/if}
                </div>
              {/each}
            </div>
            <div>
              <h3 class="sa-section-label">Customer</h3>
              {#each parsed.customer_participants || [] as p}
                <div style="font-size:14px;margin-bottom:4px">
                  <span style="font-weight:500">{p.name}</span>
                  {#if p.title}<span style="color:#606B85;font-size:13px"> &middot; {p.title}</span>{/if}
                </div>
              {/each}
            </div>
          </div>
          {#if parsed.associated_deals?.length > 0}
            <div style="background:#F4F4F6;border-radius:6px;padding:12px 16px">
              <h3 class="sa-section-label" style="margin-bottom:6px">Associated Deal</h3>
              {#each parsed.associated_deals as deal}
                <div style="font-size:14px">
                  <span style="font-weight:600">{deal.name}</span>
                  <div style="color:#606B85;font-size:13px;margin-top:2px">
                    {#if deal.amount}<span>{deal.amount}</span>{/if}
                    {#if deal.stage}<span> &middot; {deal.stage}</span>{/if}
                    {#if deal.close_date}<span> &middot; Close: {deal.close_date}</span>{/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <div class="sa-card">
          <h2 style="font-size:16px;font-weight:700;margin:0 0 12px">Key Points</h2>
          <ol style="padding-left:20px;margin:0">
            {#each parsed.key_points || [] as point}
              <li style="font-size:14px;margin-bottom:8px;line-height:1.6;color:#0D122B">{point}</li>
            {/each}
          </ol>
        </div>

        <div class="sa-card">
          <h2 style="font-size:16px;font-weight:700;margin:0 0 12px">Next Steps</h2>
          <ol style="padding-left:20px;margin:0">
            {#each parsed.next_steps || [] as step}
              <li style="font-size:14px;margin-bottom:8px;line-height:1.6;color:#0D122B">{step}</li>
            {/each}
          </ol>
        </div>
      </div>

      <!-- Right: AI Analysis -->
      <div class="sa-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
          <h2 style="font-size:16px;font-weight:700;margin:0">AI Analysis</h2>
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
  .sa-section-label { font-size:11px; font-weight:700; color:#8891AA; text-transform:uppercase; letter-spacing:0.08em; margin:0 0 8px; }

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
