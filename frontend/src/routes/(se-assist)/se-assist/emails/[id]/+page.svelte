<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';

  const PRESALES_STAGES = [
    '1 - Qualified', '2 - Discovery', '3 - Technical Evaluation',
    '4 - Technical Win Achieved', '5 - Technical Loss',
  ];
  const USE_CASE_OPTIONS = [
    'Alerts & Notifications', 'Identity & Verification', 'Asset Management',
    'Promotions', 'Customer Loyalty', 'Lead Conversion',
    'Contact Center', 'IVR & Bots', 'Field Service & Conversations', 'Other',
  ];

  let email = $state<any>(null);
  let analysis = $state<any>(null);
  let loading = $state(true);
  let analyzing = $state(false);
  let analysisDuration = $state<number | null>(null);
  let deleting = $state(false);
  let error = $state('');
  let success = $state('');

  let editFields = $state({
    use_case_category: '',
    presales_stage: '',
    sfdc_use_case_description: '',
    sfdc_solutions_notes: '',
    sfdc_technical_risks: '',
  });

  const id = $derived($page.params.id);

  async function loadData() {
    loading = true;
    try {
      const r = await fetch(`/api/se-assist/emails/${id}`);
      if (!r.ok) throw new Error('Email not found');
      email = await r.json();
      try {
        const ar = await fetch(`/api/se-assist/analysis/${id}`);
        if (ar.ok) {
          analysis = await ar.json();
          editFields = {
            use_case_category: analysis.use_case_category || '',
            presales_stage: analysis.presales_stage || '',
            sfdc_use_case_description: analysis.sfdc_use_case_description || '',
            sfdc_solutions_notes: analysis.sfdc_solutions_notes || '',
            sfdc_technical_risks: analysis.sfdc_technical_risks || '',
          };
        }
      } catch { /* no analysis yet */ }
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  onMount(loadData);

  async function handleAnalyze() {
    analyzing = true;
    error = '';
    const start = Date.now();
    try {
      const endpoint = analysis
        ? `/api/se-assist/analysis/${id}/rerun`
        : `/api/se-assist/analysis/${id}`;
      const r = await fetch(endpoint, { method: 'POST' });
      if (!r.ok) { const d = await r.json(); throw new Error(d.error || 'Analysis failed'); }
      analysisDuration = (Date.now() - start) / 1000;
      analysis = await r.json();
      editFields = {
        use_case_category: analysis.use_case_category || '',
        presales_stage: analysis.presales_stage || '',
        sfdc_use_case_description: analysis.sfdc_use_case_description || '',
        sfdc_solutions_notes: analysis.sfdc_solutions_notes || '',
        sfdc_technical_risks: analysis.sfdc_technical_risks || '',
      };
      success = 'Analysis complete';
      setTimeout(() => success = '', 4000);
    } catch (e: any) {
      error = e.message;
    } finally {
      analyzing = false;
    }
  }

  async function handleSaveEdits() {
    if (!analysis) return;
    try {
      const r = await fetch(`/api/se-assist/analysis/${analysis.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editFields),
      });
      if (!r.ok) throw new Error('Save failed');
      analysis = await r.json();
      success = 'Changes saved';
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    }
  }

  function copyToClipboard(text: string, label: string) {
    navigator.clipboard.writeText(text);
    success = `${label} copied to clipboard`;
    setTimeout(() => success = '', 2000);
  }

  async function handleDelete() {
    if (!confirm('Delete this email and its analysis?')) return;
    deleting = true;
    try {
      await fetch(`/api/se-assist/emails/${id}`, { method: 'DELETE' });
      goto('/se-assist/emails');
    } catch (e: any) {
      error = e.message;
      deleting = false;
    }
  }

  function autoResize(el: HTMLTextAreaElement) {
    el.style.height = 'auto';
    el.style.height = Math.max(el.scrollHeight, 66) + 'px';
  }

  function autoResizeAction(el: HTMLTextAreaElement) {
    const tick = () => requestAnimationFrame(() => autoResize(el));
    tick();
    return { update: tick };
  }
</script>

{#if loading}
  <p style="color:var(--c-text-weak);padding:24px">Loading...</p>
{:else if !email}
  <p>Email not found</p>
{:else}
  <!-- Breadcrumb -->
  <a href="/se-assist/emails" class="sa-breadcrumb">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
    Emails
  </a>

  <!-- Alerts -->
  {#if error}
    <div class="sa-alert error" style="margin-bottom:16px">
      {error}
      <button onclick={() => error = ''} style="margin-left:auto;background:none;border:none;padding:4px;color:#991B1B;font-size:16px;cursor:pointer">&times;</button>
    </div>
  {/if}
  {#if success}
    <div class="sa-alert success" style="margin-bottom:16px">{success}</div>
  {/if}

  <!-- Page header -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px">
    <div>
      <h1 style="font-size:24px;font-weight:700;margin-bottom:4px">{email.parsed_data?.company_name || email.company_name}</h1>
      <div style="display:flex;align-items:center;gap:8px;font-size:14px;color:var(--c-text-weak)">
        <span>{email.parsed_data?.call_date || ''}</span>
        {#if email.parsed_data?.duration}<span style="color:var(--c-border-strong)">&middot;</span><span>{email.parsed_data.duration}</span>{/if}
        <span class="sa-badge {email.status}">{email.status}</span>
      </div>
    </div>
    <button class="sa-btn destructive" onclick={handleDelete} disabled={deleting}>
      {deleting ? 'Deleting...' : 'Delete'}
    </button>
  </div>

  <!-- Two column layout -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start">
    <!-- Left: Gong notes -->
    <div style="display:flex;flex-direction:column;gap:24px">
      <!-- Participants + Deal -->
      <div class="sa-card">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:20px">
          <div>
            <h3 class="sa-section-label">Twilio</h3>
            {#each email.parsed_data?.twilio_participants || [] as p}
              <div style="font-size:14px;margin-bottom:4px">
                <span style="font-weight:500">{p.name}</span>
                {#if p.title}<span style="color:var(--c-text-weak);font-size:13px"> &middot; {p.title}</span>{/if}
              </div>
            {/each}
          </div>
          <div>
            <h3 class="sa-section-label">Customer</h3>
            {#each email.parsed_data?.customer_participants || [] as p}
              <div style="font-size:14px;margin-bottom:4px">
                <span style="font-weight:500">{p.name}</span>
                {#if p.title}<span style="color:var(--c-text-weak);font-size:13px"> &middot; {p.title}</span>{/if}
              </div>
            {/each}
          </div>
        </div>

        {#if email.parsed_data?.associated_deals?.length}
          <div style="background:#F4F4F6;border-radius:var(--radius-sm);padding:12px 16px">
            <h3 class="sa-section-label" style="margin-bottom:6px">Associated Deal</h3>
            {#each email.parsed_data.associated_deals as deal}
              <div style="font-size:14px">
                <span style="font-weight:600">{deal.name}</span>
                <div style="color:var(--c-text-weak);font-size:13px;margin-top:2px">
                  {#if deal.amount}<span>{deal.amount}</span>{/if}
                  {#if deal.stage}<span> &middot; {deal.stage}</span>{/if}
                  {#if deal.close_date}<span> &middot; Close: {deal.close_date}</span>{/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Key points -->
      <div class="sa-card">
        <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Key Points</h2>
        <ol style="padding-left:20px">
          {#each email.parsed_data?.key_points || [] as point}
            <li style="font-size:14px;margin-bottom:8px;line-height:1.6;color:var(--c-text)">{point}</li>
          {/each}
        </ol>
      </div>

      <!-- Next steps -->
      <div class="sa-card">
        <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Next Steps</h2>
        <ol style="padding-left:20px">
          {#each email.parsed_data?.next_steps || [] as step}
            <li style="font-size:14px;margin-bottom:8px;line-height:1.6;color:var(--c-text)">{step}</li>
          {/each}
        </ol>
      </div>
    </div>

    <!-- Right: AI Analysis -->
    <div style="display:flex;flex-direction:column;gap:24px">
      <div class="sa-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
          <h2 style="font-size:16px;font-weight:700">AI Analysis</h2>
          <button class="sa-btn primary" onclick={handleAnalyze} disabled={analyzing} style="font-size:13px;padding:6px 14px">
            {analyzing ? 'Analyzing...' : analysis ? 'Re-run' : 'Analyze'}
          </button>
        </div>

        {#if analysis}
          <div style="display:flex;flex-direction:column;gap:16px">
            <!-- Use Case -->
            <div>
              <label class="sa-field-label">Use Case (SE)</label>
              <select bind:value={editFields.use_case_category} class="sa-select">
                <option value="">Select...</option>
                {#each USE_CASE_OPTIONS as opt}<option value={opt}>{opt}</option>{/each}
              </select>
            </div>

            <!-- Presales Stage -->
            <div>
              <label class="sa-field-label">Presales Stage</label>
              <select bind:value={editFields.presales_stage} class="sa-select">
                <option value="">Select...</option>
                {#each PRESALES_STAGES as opt}<option value={opt}>{opt}</option>{/each}
              </select>
            </div>

            <!-- Use Case Description -->
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <label class="sa-field-label" style="margin-bottom:0">Use Case Description</label>
                <button class="sa-copy-btn" onclick={() => copyToClipboard(editFields.sfdc_use_case_description, 'Use Case Description')} disabled={!editFields.sfdc_use_case_description}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
                  Copy
                </button>
              </div>
              <textarea class="sa-textarea" bind:value={editFields.sfdc_use_case_description}
                oninput={(e) => autoResize(e.currentTarget as HTMLTextAreaElement)}
                use:autoResizeAction={editFields.sfdc_use_case_description}></textarea>
            </div>

            <!-- Solutions Notes -->
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <label class="sa-field-label" style="margin-bottom:0">Solutions Team Notes</label>
                <button class="sa-copy-btn" onclick={() => copyToClipboard(editFields.sfdc_solutions_notes, 'Solutions Team Notes')} disabled={!editFields.sfdc_solutions_notes}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
                  Copy
                </button>
              </div>
              <textarea class="sa-textarea" bind:value={editFields.sfdc_solutions_notes} style="min-height:88px"
                oninput={(e) => autoResize(e.currentTarget as HTMLTextAreaElement)}
                use:autoResizeAction={editFields.sfdc_solutions_notes}></textarea>
            </div>

            <!-- Technical Risks -->
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <label class="sa-field-label" style="margin-bottom:0">Technical Risks & Challenges</label>
                <button class="sa-copy-btn" onclick={() => copyToClipboard(editFields.sfdc_technical_risks, 'Technical Risks')} disabled={!editFields.sfdc_technical_risks}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
                  Copy
                </button>
              </div>
              <textarea class="sa-textarea" bind:value={editFields.sfdc_technical_risks}
                oninput={(e) => autoResize(e.currentTarget as HTMLTextAreaElement)}
                use:autoResizeAction={editFields.sfdc_technical_risks}></textarea>
            </div>

            <div style="display:flex;justify-content:flex-end">
              <button class="sa-btn secondary" onclick={handleSaveEdits} style="font-size:13px;padding:6px 14px">Save Edits</button>
            </div>

            {#if analysis.model_used}
              <div style="font-size:12px;color:var(--c-text-weaker);border-top:1px solid var(--c-border);padding-top:12px">
                Model: {analysis.model_used}
                {#if analysis.input_tokens != null} &middot; {analysis.input_tokens.toLocaleString()} input tokens{/if}
                {#if analysis.output_tokens != null} &middot; {analysis.output_tokens.toLocaleString()} output tokens{/if}
                {#if analysis.cost_usd != null} &middot; ${analysis.cost_usd.toFixed(4)}{/if}
                {#if analysisDuration != null} &middot; {analysisDuration.toFixed(1)}s{/if}
              </div>
            {/if}
          </div>
        {:else}
          <p style="color:var(--c-text-weak);font-size:14px">Run AI analysis to generate SFDC field recommendations.</p>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .sa-card {
    background: white;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-md);
    padding: 24px;
  }
  .sa-breadcrumb {
    color: var(--c-link);
    text-decoration: none;
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 20px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
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
  .sa-btn.secondary { background: white; color: var(--c-text); border: 1px solid var(--c-border); }
  .sa-btn.secondary:hover { background: #F4F4F6; }
  .sa-btn.destructive { background: #FDE8EA; color: #D92D20; }
  .sa-btn.destructive:hover { background: #FDD3D6; }
  .sa-btn:disabled { opacity: 0.6; cursor: not-allowed; }
  .sa-alert {
    padding: 12px 16px;
    border-radius: var(--radius-sm);
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .sa-alert.error { background: #FDE8EA; border: 1px solid var(--c-danger); color: #991B1B; }
  .sa-alert.success { background: #E1F5E9; border: 1px solid var(--c-success); color: #0A6130; }
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
  .sa-section-label {
    font-size: 11px;
    font-weight: 700;
    color: var(--c-text-weaker);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }
  .sa-field-label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--c-text-weak);
    margin-bottom: 4px;
  }
  .sa-select {
    width: 100%;
    padding: 8px 12px;
    font-size: 14px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    background: white;
    color: var(--c-text);
  }
  .sa-select:focus { outline: none; border-color: #0263E0; box-shadow: 0 0 0 2px rgba(2,99,224,0.15); }
  .sa-textarea {
    width: 100%;
    padding: 8px 12px;
    font-size: 14px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    font-family: inherit;
    color: var(--c-text);
    min-height: 66px;
    overflow: hidden;
    resize: none;
  }
  .sa-textarea:focus { outline: none; border-color: #0263E0; box-shadow: 0 0 0 2px rgba(2,99,224,0.15); }
  .sa-copy-btn {
    background: none;
    border: none;
    padding: 4px;
    cursor: pointer;
    color: var(--c-text-weak);
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    font-weight: 500;
  }
  .sa-copy-btn:disabled { color: var(--c-border); cursor: default; }
</style>
