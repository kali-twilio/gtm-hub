<script lang="ts">
  import { marked } from 'marked';

  // ── Marked config ────────────────────────────────────────────────────────
  marked.use({ breaks: true });

  // ── Form state ───────────────────────────────────────────────────────────
  let companyName   = $state('');
  let websiteUrl    = $state('');
  let industry      = $state('');
  let location      = $state('');
  let companySize   = $state('');
  let existingTwilio = $state('');
  let phoneNumbers  = $state('');
  let linkedinUrl   = $state('');
  let socialMedia   = $state('');
  let notes         = $state('');

  // ── Analysis state ───────────────────────────────────────────────────────
  type Phase = 'idle' | 'analyzing' | 'done' | 'error';
  let phase        = $state<Phase>('idle');
  let progressMsgs = $state<string[]>([]);
  let reportText   = $state('');
  let errorMsg     = $state('');
  let copied       = $state(false);

  // ── Send to team state ───────────────────────────────────────────────────
  let sendTo       = $state('');
  let sendChannel  = $state<'sms' | 'whatsapp'>('sms');
  let sending      = $state(false);
  let sendResult   = $state<{ ok: boolean; message: string } | null>(null);

  async function sendReport() {
    if (!sendTo.trim() || !reportText) return;
    sending    = true;
    sendResult = null;
    try {
      const resp = await fetch('/api/customer-profiler/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to:           sendTo.trim(),
          channel:      sendChannel,
          report_text:  reportText,
          company_name: companyName,
        }),
      });
      const data = await resp.json();
      if (resp.ok && data.ok) {
        sendResult = { ok: true, message: `✅ Sent via ${sendChannel === 'sms' ? 'SMS' : 'WhatsApp'} to ${sendTo}` };
        sendTo = '';
      } else {
        sendResult = { ok: false, message: `⚠️ ${data.error || 'Send failed'}` };
      }
    } catch (err) {
      sendResult = { ok: false, message: `⚠️ Network error` };
    } finally {
      sending = false;
    }
  }

  let reportHtml   = $derived(marked.parse(reportText) as string);

  // ── Submit ───────────────────────────────────────────────────────────────
  async function analyze() {
    if (!companyName.trim()) return;

    phase        = 'analyzing';
    progressMsgs = [];
    reportText   = '';
    errorMsg     = '';

    const payload = {
      company_name:     companyName.trim(),
      website_url:      websiteUrl.trim(),
      industry:         industry.trim(),
      location:         location.trim(),
      company_size:     companySize,
      existing_twilio:  existingTwilio.trim(),
      phone_numbers:    phoneNumbers.trim(),
      linkedin_url:     linkedinUrl.trim(),
      social_media:     socialMedia.trim(),
      notes:            notes.trim(),
    };

    try {
      const resp = await fetch('/api/customer-profiler/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE events are delimited by \n\n
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          for (const line of part.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            try {
              const ev = JSON.parse(line.slice(6));
              if (ev.type === 'progress') {
                progressMsgs = [...progressMsgs, ev.message];
              } else if (ev.type === 'delta') {
                reportText += ev.text;
              } else if (ev.type === 'done') {
                phase = 'done';
              } else if (ev.type === 'error') {
                errorMsg = ev.message;
                phase    = 'error';
              }
            } catch { /* ignore parse errors */ }
          }
        }
      }

      if (phase === 'analyzing') phase = 'done';

    } catch (err: unknown) {
      errorMsg = err instanceof Error ? err.message : String(err);
      phase    = 'error';
    }
  }

  function reset() {
    phase        = 'idle';
    progressMsgs = [];
    reportText   = '';
    errorMsg     = '';
  }

  async function copyReport() {
    if (!reportText) return;
    await navigator.clipboard.writeText(reportText);
    copied = true;
    setTimeout(() => (copied = false), 2000);
  }

  const COMPANY_SIZES = [
    { value: '',         label: 'Unknown' },
    { value: '1-50',     label: '1–50 employees' },
    { value: '51-200',   label: '51–200 employees' },
    { value: '201-500',  label: '201–500 employees' },
    { value: '501-1000', label: '501–1,000 employees' },
    { value: '1001-5000',label: '1,001–5,000 employees' },
    { value: '5001+',    label: '5,001+ employees' },
  ];
</script>

<div class="min-h-screen flex flex-col items-center px-4 py-12">

  <!-- ── Header ──────────────────────────────────────────────────────────── -->
  <div class="text-center mb-8 w-full hub-container">
    <div class="p5-badge mb-3">DSR Intelligence</div>
    <div style="font-size:36px;margin-bottom:8px">🔍</div>
    <h1 style="font-size:26px;font-weight:800;color:var(--text);letter-spacing:-0.02em">
      Customer Profiler
    </h1>
    <p style="font-size:13px;color:var(--text-muted);margin-top:6px;line-height:1.6;max-width:500px;margin-inline:auto">
      Enter what you know about a prospect and get an AI-powered report covering
      their communication stack, Twilio opportunities, and your ideal sales approach.
    </p>
    <div style="width:36px;height:3px;background:var(--red);border-radius:2px;margin:12px auto 0"></div>
  </div>

  <!-- ── Input Form ──────────────────────────────────────────────────────── -->
  {#if phase === 'idle' || phase === 'done' || phase === 'error'}
    <div class="w-full hub-container mb-6">
      <div class="p5-panel">

        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-muted);margin-bottom:14px">
          Customer Information
        </div>

        <!-- Row 1 -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
          <label class="cp-label">
            Company Name <span style="color:var(--red)">*</span>
            <input class="cp-input" bind:value={companyName}
              placeholder="Acme Corp" />
          </label>
          <label class="cp-label">
            Website URL
            <input class="cp-input" bind:value={websiteUrl}
              placeholder="https://acme.com" />
          </label>
        </div>

        <!-- Row 2 -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
          <label class="cp-label">
            Industry / Vertical
            <input class="cp-input" bind:value={industry}
              placeholder="e.g. FinTech, Healthcare, Retail" />
          </label>
          <label class="cp-label">
            HQ Location
            <input class="cp-input" bind:value={location}
              placeholder="e.g. San Francisco, CA" />
          </label>
        </div>

        <!-- Row 3 -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
          <label class="cp-label">
            Company Size
            <select class="cp-input" bind:value={companySize}>
              {#each COMPANY_SIZES as opt}
                <option value={opt.value}>{opt.label}</option>
              {/each}
            </select>
          </label>
          <label class="cp-label">
            Currently Using Twilio?
            <input class="cp-input" bind:value={existingTwilio}
              placeholder="e.g. SMS, Voice, WhatsApp, None" />
          </label>
        </div>

        <!-- Row 4 -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
          <label class="cp-label">
            Phone Numbers (toll-free / company)
            <input class="cp-input" bind:value={phoneNumbers}
              placeholder="e.g. 1-800-555-0100, +1 415 555 0100" />
          </label>
          <label class="cp-label">
            LinkedIn URL
            <input class="cp-input" bind:value={linkedinUrl}
              placeholder="https://linkedin.com/company/acme" />
          </label>
        </div>

        <!-- Row 5 -->
        <label class="cp-label" style="margin-bottom:10px">
          Social Media & Other Channels
          <input class="cp-input" bind:value={socialMedia}
            placeholder="e.g. @acmecorp (Twitter), facebook.com/acme, WhatsApp Business active" />
        </label>

        <!-- Notes -->
        <label class="cp-label" style="margin-bottom:14px">
          DSR Notes & Context
          <textarea class="cp-input" bind:value={notes} rows="3"
            placeholder="Any additional context: recent interactions, known pain points, deal stage, relevant news...">
          </textarea>
        </label>

        <!-- Error display -->
        {#if phase === 'error' && errorMsg}
          <div class="cp-error" style="margin-bottom:12px">⚠️ {errorMsg}</div>
        {/if}

        <!-- Actions -->
        <div style="display:flex;justify-content:flex-end;gap:10px">
          {#if phase === 'done' || phase === 'error'}
            <button class="cp-btn" onclick={reset}>New Search</button>
          {/if}
          <button
            class="cp-btn cp-btn-primary"
            onclick={analyze}
            disabled={!companyName.trim()}
          >
            Analyze Customer →
          </button>
        </div>

      </div>
    </div>
  {/if}

  <!-- ── Analyzing: Progress + partial report ────────────────────────────── -->
  {#if phase === 'analyzing' || (phase === 'done' && reportText)}

    <!-- Progress log (shown only while analyzing) -->
    {#if phase === 'analyzing'}
      <div class="w-full hub-container mb-4">
        <div class="p5-panel" style="padding:16px">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-muted);margin-bottom:10px">
            Research Progress
          </div>
          {#each progressMsgs as msg}
            <div style="font-size:12px;color:var(--text-muted);padding:3px 0;line-height:1.5">
              {msg}
            </div>
          {/each}
          {#if progressMsgs.length === 0}
            <div style="font-size:12px;color:var(--text-muted)">Starting…</div>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Report output -->
    {#if reportText}
      <div class="w-full hub-container mb-6">
        <div class="p5-panel" style="padding:24px">

          <!-- Report header -->
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px">
            <div>
              <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-muted)">
                Intelligence Report
              </div>
              <div style="font-size:14px;font-weight:800;color:var(--text);margin-top:2px">
                {companyName}
                {#if phase === 'analyzing'}
                  <span style="font-size:11px;color:var(--text-muted);font-weight:400;margin-left:8px">generating…</span>
                {/if}
              </div>
            </div>
            <div style="display:flex;gap:8px">
              {#if phase === 'done'}
                <button class="cp-btn" onclick={copyReport} style="font-size:11px;padding:7px 14px">
                  {copied ? '✓ Copied' : '📋 Copy Report'}
                </button>
                <button class="cp-btn" onclick={reset} style="font-size:11px;padding:7px 14px">
                  New Search
                </button>
              {/if}
            </div>
          </div>

          <!-- Divider -->
          <div style="height:1px;background:var(--border);margin-bottom:16px"></div>

          <!-- Rendered markdown -->
          <!-- eslint-disable-next-line svelte/no-at-html-tags -->
          <div class="report-body">{@html reportHtml}</div>

          <!-- Streaming cursor -->
          {#if phase === 'analyzing'}
            <span style="display:inline-block;width:8px;height:14px;background:var(--red);border-radius:2px;animation:blink 1s step-end infinite;vertical-align:middle;margin-left:2px"></span>
          {/if}

        </div>
      </div>

      <!-- ── Send to Team panel (shown only when report is ready) ───────── -->
      {#if phase === 'done'}
        <div class="w-full hub-container mb-6">
          <div class="p5-panel" style="padding:20px">

            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-muted);margin-bottom:14px">
              📲 Send to Team
            </div>

            <div style="display:grid;grid-template-columns:1fr auto auto;gap:10px;align-items:flex-end">

              <!-- Phone number input -->
              <label class="cp-label">
                Phone Number
                <input
                  class="cp-input"
                  bind:value={sendTo}
                  placeholder="+1 415 555 0100"
                  type="tel"
                />
              </label>

              <!-- Channel toggle -->
              <div style="display:flex;gap:0;border-radius:8px;overflow:hidden;border:1px solid rgba(var(--red-rgb),0.3);height:38px;align-self:flex-end">
                <button
                  onclick={() => sendChannel = 'sms'}
                  style="padding:0 16px;font-size:12px;font-weight:700;font-family:var(--font);border:none;cursor:pointer;background:{sendChannel==='sms'?'var(--red)':'transparent'};color:{sendChannel==='sms'?'white':'var(--text-muted)'};transition:background 0.15s"
                >
                  SMS
                </button>
                <button
                  onclick={() => sendChannel = 'whatsapp'}
                  style="padding:0 16px;font-size:12px;font-weight:700;font-family:var(--font);border:none;border-left:1px solid rgba(var(--red-rgb),0.3);cursor:pointer;background:{sendChannel==='whatsapp'?'var(--red)':'transparent'};color:{sendChannel==='whatsapp'?'white':'var(--text-muted)'};transition:background 0.15s"
                >
                  WhatsApp
                </button>
              </div>

              <!-- Send button -->
              <button
                class="cp-btn cp-btn-primary"
                onclick={sendReport}
                disabled={sending || !sendTo.trim()}
                style="height:38px;padding:0 20px;font-size:12px;align-self:flex-end"
              >
                {sending ? 'Sending…' : 'Send →'}
              </button>

            </div>

            <!-- Channel hint -->
            <div style="font-size:11px;color:var(--text-muted);margin-top:8px">
              {#if sendChannel === 'whatsapp'}
                💬 LATAM team — recipient must have joined the WhatsApp sandbox first
                (<strong style="color:var(--text)">send "join &lt;your-sandbox-word&gt;" to +1 415 523 8886</strong>)
              {:else}
                📱 US team — standard SMS, no setup required
              {/if}
            </div>

            <!-- Result feedback -->
            {#if sendResult}
              <div style="margin-top:10px;padding:10px 14px;border-radius:7px;font-size:13px;font-weight:600;
                background:{sendResult.ok ? 'rgba(0,200,100,0.08)' : 'rgba(220,50,50,0.08)'};
                border:1px solid {sendResult.ok ? 'rgba(0,200,100,0.25)' : 'rgba(220,50,50,0.25)'};
                color:{sendResult.ok ? '#00c864' : '#e05555'}">
                {sendResult.message}
              </div>
            {/if}

          </div>
        </div>
      {/if}
    {/if}

    <!-- Cancel / new search while analyzing -->
    {#if phase === 'analyzing'}
      <div class="w-full hub-container" style="text-align:center">
        <button
          onclick={reset}
          style="font-size:11px;color:var(--text-muted);background:none;border:none;cursor:pointer;text-decoration:underline;padding:4px"
        >Cancel</button>
      </div>
    {/if}

  {/if}

</div>

<style>
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0; }
  }

  select.cp-input option {
    background: var(--panel);
    color: var(--text);
  }
</style>
