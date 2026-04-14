<script lang="ts">
  import { onMount } from 'svelte';

  interface StepState { status: 'pending' | 'complete' | 'failed'; data: Record<string, any>; completed_at?: number; }
  interface WizardState {
    current_step: number;
    steps: Record<string, StepState>;
    dev_bypass: boolean;
    sandbox_number: string;
    meta_app_id: string;
    meta_config_id: string;
  }

  let state = $state<WizardState | null>(null);
  let loading = $state(true);
  let activeStep = $state(1);

  // Step 1
  let s1Sid   = $state('');
  let s1Token = $state('');
  let s1Busy  = $state(false);
  let s1Error = $state('');

  // Step 2
  let s2Busy  = $state(false);
  let s2Error = $state('');

  // Step 3
  let s3Numbers  = $state<{sid:string;phone_number:string;friendly_name:string}[]>([]);
  let s3Selected = $state('');
  let s3SelNum   = $state('');
  let s3Busy     = $state(false);
  let s3Error    = $state('');
  let s3Loaded   = $state(false);

  // Step 4
  let s4DisplayName = $state('');
  let s4Description = $state('');
  let s4Address     = $state('');
  let s4ProfileBusy = $state(false);
  let s4ProfileErr  = $state('');
  let s4ProfileDone = $state(false);

  let s4TmplName     = $state('');
  let s4TmplCategory = $state('UTILITY');
  let s4TmplLang     = $state('en_US');
  let s4TmplBody     = $state('');
  let s4TmplBusy     = $state(false);
  let s4TmplErr      = $state('');
  let s4TmplDone     = $state(false);

  async function loadState() {
    loading = true;
    const r = await fetch('/api/whatsapp-wizard/state');
    if (r.ok) {
      state = await r.json();
      activeStep = Math.min(state!.current_step, 4);
      // Pre-fill step 4 if already saved
      const p4 = state!.steps['4']?.data?.profile;
      if (p4) { s4DisplayName = p4.display_name || ''; s4Description = p4.description || ''; s4Address = p4.address || ''; s4ProfileDone = !!p4.saved; }
      const t4 = state!.steps['4']?.data?.template;
      if (t4) { s4TmplName = t4.name || ''; s4TmplBody = t4.body || ''; s4TmplDone = !!t4.saved; }
    }
    loading = false;
  }

  onMount(loadState);

  async function loadNumbers() {
    s3Error = ''; s3Loaded = false;
    const r = await fetch('/api/whatsapp-wizard/step3/numbers');
    const d = await r.json();
    if (!r.ok) { s3Error = d.error || 'Failed to load numbers'; return; }
    s3Numbers = d.numbers || [];
    s3Loaded = true;
  }

  $effect(() => {
    if (state && activeStep === 3 && !s3Loaded && state.steps['2']?.status === 'complete') {
      loadNumbers();
    }
  });

  async function submitStep1() {
    s1Error = ''; s1Busy = true;
    const r = await fetch('/api/whatsapp-wizard/step1', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ account_sid: s1Sid, auth_token: s1Token }),
    });
    const d = await r.json();
    s1Busy = false;
    if (!r.ok) { s1Error = d.error || 'Unknown error'; return; }
    await loadState();
  }

  async function step2Bypass() {
    s2Error = ''; s2Busy = true;
    const r = await fetch('/api/whatsapp-wizard/step2/bypass', { method: 'POST' });
    const d = await r.json();
    s2Busy = false;
    if (!r.ok) { s2Error = d.error || 'Unknown error'; return; }
    await loadState();
  }

  async function step3Sandbox() {
    s3Error = ''; s3Busy = true;
    const r = await fetch('/api/whatsapp-wizard/step3/sandbox', { method: 'POST' });
    const d = await r.json();
    s3Busy = false;
    if (!r.ok) { s3Error = d.error || 'Unknown error'; return; }
    await loadState();
  }

  async function step3Register() {
    if (!s3Selected) { s3Error = 'Select a phone number first.'; return; }
    s3Error = ''; s3Busy = true;
    const r = await fetch('/api/whatsapp-wizard/step3/register', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ phone_number_sid: s3Selected, phone_number: s3SelNum }),
    });
    const d = await r.json();
    s3Busy = false;
    if (!r.ok) { s3Error = d.error || 'Unknown error'; return; }
    await loadState();
  }

  async function step4Profile() {
    s4ProfileErr = ''; s4ProfileBusy = true;
    const r = await fetch('/api/whatsapp-wizard/step4/profile', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ display_name: s4DisplayName, description: s4Description, address: s4Address }),
    });
    const d = await r.json();
    s4ProfileBusy = false;
    if (!r.ok) { s4ProfileErr = d.error || 'Unknown error'; return; }
    s4ProfileDone = true;
    await loadState();
  }

  async function step4Template() {
    s4TmplErr = ''; s4TmplBusy = true;
    const r = await fetch('/api/whatsapp-wizard/step4/template', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ name: s4TmplName, category: s4TmplCategory, language: s4TmplLang, body: s4TmplBody }),
    });
    const d = await r.json();
    s4TmplBusy = false;
    if (!r.ok) { s4TmplErr = d.error || 'Unknown error'; return; }
    s4TmplDone = true;
    await loadState();
  }

  async function resetWizard() {
    await fetch('/api/whatsapp-wizard/reset', { method: 'POST' });
    s1Sid=''; s1Token=''; s1Error='';
    s2Error='';
    s3Numbers=[]; s3Selected=''; s3SelNum=''; s3Error=''; s3Loaded=false;
    s4DisplayName=''; s4Description=''; s4Address=''; s4ProfileDone=false; s4ProfileErr='';
    s4TmplName=''; s4TmplBody=''; s4TmplDone=false; s4TmplErr='';
    await loadState();
  }

  const stepLabels = ['Connect Twilio Account','Meta Embedded Signup','Register Phone Number','Business Profile & Templates'];

  function stepDone(n: number) { return state?.steps[String(n)]?.status === 'complete'; }
  function stepActive(n: number) { return !stepDone(n) && activeStep === n; }
</script>

<div class="min-h-screen flex flex-col items-center px-4 py-14">

  <!-- Header -->
  <div class="text-center mb-8 w-full hub-container">
    <div class="p5-badge mb-3">WhatsApp Wizard</div>
    <div style="font-size:36px;margin-bottom:8px">💬</div>
    <h1 style="font-size:26px;font-weight:800;color:var(--text);letter-spacing:-0.02em">
      WhatsApp Business Onboarding
    </h1>
    <p style="font-size:13px;color:var(--text-muted);margin-top:6px;line-height:1.6;max-width:460px;margin-inline:auto">
      A guided 4-step wizard to activate WhatsApp Business on your Twilio account.
    </p>
    <div style="width:36px;height:3px;background:var(--red);border-radius:2px;margin:12px auto 0"></div>
  </div>

  {#if loading}
    <div style="color:var(--text-muted);font-size:14px;font-weight:600">Loading…</div>
  {:else if state}

    <!-- Progress bar -->
    <div class="w-full hub-container mb-8">
      <div style="display:flex;gap:6px;align-items:center">
        {#each [1,2,3,4] as n}
          <div style="flex:1">
            <div
              style="height:4px;border-radius:2px;background:{stepDone(n)?'var(--red)':activeStep===n?'rgba(var(--red-rgb),0.4)':'rgba(var(--red-rgb),0.12)'};transition:background 0.3s"
            ></div>
            <div style="font-size:10px;font-weight:700;color:{stepDone(n)?'var(--red)':activeStep===n?'var(--text)':'var(--text-muted)'};margin-top:5px;text-align:center;text-transform:uppercase;letter-spacing:0.06em">
              {stepDone(n) ? '✓' : n}
            </div>
          </div>
          {#if n < 4}<div style="width:6px;height:4px;flex-shrink:0"></div>{/if}
        {/each}
      </div>
    </div>

    <!-- Steps -->
    {#each [1,2,3,4] as n}
      {@const done  = stepDone(n)}
      {@const active = stepActive(n)}
      {@const locked = !done && !active}

      <div class="w-full hub-container mb-4">
        <!-- Step header (clickable if done or active) -->
        <button
          onclick={() => { if (!locked) activeStep = n; }}
          style="width:100%;display:flex;align-items:center;gap:14px;padding:14px 16px;background:{active?'rgba(var(--red-rgb),0.06)':'transparent'};border:1px solid {active?'rgba(var(--red-rgb),0.3)':done?'rgba(var(--red-rgb),0.18)':'rgba(var(--text-muted-rgb,128,128,128),0.12)'};border-radius:10px;cursor:{locked?'default':'pointer'};text-align:left"
        >
          <div style="width:32px;height:32px;border-radius:50%;background:{done?'var(--red)':active?'rgba(var(--red-rgb),0.15)':'rgba(128,128,128,0.1)'};border:1px solid {done?'var(--red)':active?'rgba(var(--red-rgb),0.4)':'rgba(128,128,128,0.2)'};display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;color:{done?'#fff':active?'var(--red)':'var(--text-muted)'};flex-shrink:0">
            {done ? '✓' : n}
          </div>
          <div style="flex:1">
            <div style="font-size:13px;font-weight:700;color:{locked?'var(--text-muted)':'var(--text)'}">
              {stepLabels[n-1]}
            </div>
            {#if done}
              {#if n === 1}
                <div style="font-size:11px;color:var(--text-muted);margin-top:2px">{state.steps['1'].data?.friendly_name || 'Connected'}</div>
              {:else if n === 2}
                <div style="font-size:11px;color:var(--text-muted);margin-top:2px">
                  {state.steps['2'].data?.sandbox ? 'Sandbox mode (dev)' : `WABA: ${state.steps['2'].data?.waba_id}`}
                </div>
              {:else if n === 3}
                <div style="font-size:11px;color:var(--text-muted);margin-top:2px">
                  {state.steps['3'].data?.sandbox ? `Sandbox: ${state.steps['3'].data?.phone_number}` : state.steps['3'].data?.phone_number}
                </div>
              {:else if n === 4}
                <div style="font-size:11px;color:var(--text-muted);margin-top:2px">Profile &amp; template saved</div>
              {/if}
            {:else if locked}
              <div style="font-size:11px;color:var(--text-muted);margin-top:2px">Complete previous steps first</div>
            {/if}
          </div>
        </button>

        <!-- Step body -->
        {#if active}
          <div style="padding:16px;border:1px solid rgba(var(--red-rgb),0.2);border-top:none;border-radius:0 0 10px 10px;background:rgba(var(--red-rgb),0.03)">

            <!-- ── Step 1 ── -->
            {#if n === 1}
              <p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;line-height:1.5">
                Enter your Twilio Account SID and Auth Token. Find them in the
                <strong style="color:var(--text)">Twilio Console → Account → General Settings</strong>.
              </p>
              <label class="ww-label">Account SID
                <input class="ww-input" bind:value={s1Sid} placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" spellcheck="false" />
              </label>
              <label class="ww-label" style="margin-top:10px">Auth Token
                <input class="ww-input" type="password" bind:value={s1Token} placeholder="32+ character token" />
              </label>
              {#if s1Error}<div class="ww-error">{s1Error}</div>{/if}
              <button class="ww-btn" onclick={submitStep1} disabled={s1Busy || !s1Sid || !s1Token}>
                {s1Busy ? 'Validating…' : 'Validate & Connect'}
              </button>

            <!-- ── Step 2 ── -->
            {:else if n === 2}
              {#if state.dev_bypass}
                <div class="ww-notice">
                  <strong>Dev mode active.</strong> Skip Meta OAuth and use a sandbox WABA placeholder.
                </div>
                {#if s2Error}<div class="ww-error">{s2Error}</div>{/if}
                <button class="ww-btn" onclick={step2Bypass} disabled={s2Busy}>
                  {s2Busy ? 'Setting up…' : 'Use Sandbox WABA (Dev Bypass)'}
                </button>
              {:else}
                <p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;line-height:1.5">
                  Click the button below to open the Meta Embedded Signup flow. You'll be asked to log in
                  to Facebook and connect your WhatsApp Business Account.
                </p>
                {#if s2Error}<div class="ww-error">{s2Error}</div>{/if}
                <!-- Facebook JS SDK embedded signup — loaded inline -->
                <div id="meta-signup-container">
                  <button class="ww-btn" onclick={() => {
                    s2Error = '';
                    // @ts-ignore
                    if (typeof FB !== 'undefined') {
                      // @ts-ignore
                      FB.login(async (resp: any) => {
                        if (resp.authResponse?.code) {
                          s2Busy = true;
                          const r = await fetch('/api/whatsapp-wizard/step2/callback', {
                            method: 'POST', headers: {'Content-Type':'application/json'},
                            body: JSON.stringify({ code: resp.authResponse.code }),
                          });
                          const d = await r.json();
                          s2Busy = false;
                          if (!r.ok) { s2Error = d.error || 'Meta error'; return; }
                          await loadState();
                        } else {
                          s2Error = 'Meta signup cancelled or failed.';
                        }
                      }, {
                        config_id: state!.meta_config_id,
                        response_type: 'code',
                        override_default_response_type: true,
                        extras: { setup: {}, featureType: '', sessionInfoVersion: '3' },
                      });
                    } else {
                      s2Error = 'Facebook SDK not loaded. Refresh and try again.';
                    }
                  }} disabled={s2Busy}>
                    {s2Busy ? 'Connecting…' : 'Connect WhatsApp Business Account'}
                  </button>
                </div>
                <p style="font-size:11px;color:var(--text-muted);margin-top:8px">
                  Meta App ID: {state.meta_app_id || '(not configured)'}
                </p>
              {/if}

            <!-- ── Step 3 ── -->
            {:else if n === 3}
              {@const isSandboxWaba = state.steps['2']?.data?.waba_id === 'sandbox-waba-dev'}
              {#if state.dev_bypass && isSandboxWaba}
                <div class="ww-notice">
                  <strong>Dev mode + Sandbox WABA.</strong> Use the Twilio test sandbox number instead of registering a real number.
                </div>
                {#if s3Error}<div class="ww-error">{s3Error}</div>{/if}
                <button class="ww-btn" onclick={step3Sandbox} disabled={s3Busy}>
                  {s3Busy ? 'Setting up…' : `Use Sandbox Number (${state.sandbox_number})`}
                </button>
                <div style="margin-top:12px;border-top:1px solid rgba(var(--red-rgb),0.1);padding-top:12px">
                  <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-muted);margin-bottom:8px">Or choose a real number from your account</div>
                {/if}
              {/if}
              {#if !state.dev_bypass || !isSandboxWaba || true}
                {#if s3Error && !(state.dev_bypass && isSandboxWaba)}<div class="ww-error">{s3Error}</div>{/if}
                {#if s3Loaded}
                  {#if s3Numbers.length === 0}
                    <div class="ww-notice">No incoming phone numbers found on this Twilio account. Purchase a number first.</div>
                  {:else}
                    <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px">
                      {#each s3Numbers as num}
                        <button
                          onclick={() => { s3Selected = num.sid; s3SelNum = num.phone_number; }}
                          style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-radius:8px;border:1px solid {s3Selected===num.sid?'var(--red)':'rgba(var(--red-rgb),0.2)'};background:{s3Selected===num.sid?'rgba(var(--red-rgb),0.08)':'transparent'};cursor:pointer;text-align:left"
                        >
                          <span style="font-size:13px;font-weight:700;color:var(--text)">{num.phone_number}</span>
                          <span style="font-size:11px;color:var(--text-muted)">{num.friendly_name}</span>
                        </button>
                      {/each}
                    </div>
                    <button class="ww-btn" onclick={step3Register} disabled={s3Busy || !s3Selected}>
                      {s3Busy ? 'Registering…' : 'Register for WhatsApp'}
                    </button>
                  {/if}
                {:else}
                  <button class="ww-btn ww-btn-secondary" onclick={loadNumbers}>Load My Phone Numbers</button>
                {/if}
              {/if}
              {#if state.dev_bypass && isSandboxWaba}
                </div>
              {/if}

            <!-- ── Step 4 ── -->
            {:else if n === 4}
              <!-- Business Profile -->
              <div style="margin-bottom:18px">
                <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-muted);margin-bottom:10px">
                  Business Profile {s4ProfileDone ? '✓' : ''}
                </div>
                <label class="ww-label">Display Name *
                  <input class="ww-input" bind:value={s4DisplayName} placeholder="Your Business Name" />
                </label>
                <label class="ww-label" style="margin-top:8px">Description
                  <textarea class="ww-input" bind:value={s4Description} rows="2" placeholder="What does your business do?"></textarea>
                </label>
                <label class="ww-label" style="margin-top:8px">Address
                  <input class="ww-input" bind:value={s4Address} placeholder="123 Main St, City, Country" />
                </label>
                {#if s4ProfileErr}<div class="ww-error">{s4ProfileErr}</div>{/if}
                <button class="ww-btn" style="margin-top:10px" onclick={step4Profile} disabled={s4ProfileBusy || !s4DisplayName}>
                  {s4ProfileBusy ? 'Saving…' : s4ProfileDone ? 'Update Profile' : 'Save Profile'}
                </button>
              </div>

              <div style="border-top:1px solid rgba(var(--red-rgb),0.12);padding-top:18px">
                <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:var(--text-muted);margin-bottom:10px">
                  Message Template {s4TmplDone ? '✓' : ''}
                </div>
                <label class="ww-label">Template Name * <span style="font-size:10px;color:var(--text-muted)">(lowercase, underscores only)</span>
                  <input class="ww-input" bind:value={s4TmplName} placeholder="welcome_message" spellcheck="false" />
                </label>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
                  <label class="ww-label">Category
                    <select class="ww-input" bind:value={s4TmplCategory}>
                      <option value="UTILITY">Utility</option>
                      <option value="MARKETING">Marketing</option>
                      <option value="AUTHENTICATION">Authentication</option>
                    </select>
                  </label>
                  <label class="ww-label">Language
                    <select class="ww-input" bind:value={s4TmplLang}>
                      <option value="en_US">English (US)</option>
                      <option value="en_GB">English (UK)</option>
                      <option value="pt_BR">Portuguese (BR)</option>
                      <option value="es">Spanish</option>
                      <option value="fr">French</option>
                    </select>
                  </label>
                </div>
                <label class="ww-label" style="margin-top:8px">Template Body *
                  <textarea class="ww-input" bind:value={s4TmplBody} rows="3" placeholder="Hello {"{{"}}1{{"}}"}}, your order {"{{"}}2{{"}}"} is ready."></textarea>
                </label>
                {#if s4TmplErr}<div class="ww-error">{s4TmplErr}</div>{/if}
                <button class="ww-btn" style="margin-top:10px" onclick={step4Template} disabled={s4TmplBusy || !s4TmplName || !s4TmplBody}>
                  {s4TmplBusy ? 'Submitting…' : s4TmplDone ? 'Submit Another Template' : 'Submit Template for Approval'}
                </button>
              </div>
            {/if}

          </div>
        {/if}
      </div>
    {/each}

    <!-- All done banner -->
    {#if state.current_step > 4}
      <div class="w-full hub-container">
        <div class="p5-panel" style="padding:24px;text-align:center;border-color:rgba(var(--red-rgb),0.3);background:rgba(var(--red-rgb),0.06)">
          <div style="font-size:32px;margin-bottom:10px">🎉</div>
          <div style="font-size:16px;font-weight:800;color:var(--text);margin-bottom:6px">Onboarding Complete!</div>
          <p style="font-size:12px;color:var(--text-muted);line-height:1.6">
            Your WhatsApp Business account is set up. Templates are pending Meta approval —
            you'll receive a notification once approved.
          </p>
        </div>
      </div>
    {/if}

    <!-- Dev reset -->
    {#if state.dev_bypass}
      <div class="w-full hub-container" style="margin-top:24px;text-align:center">
        <button
          onclick={resetWizard}
          style="font-size:11px;color:var(--text-muted);background:none;border:none;cursor:pointer;text-decoration:underline;padding:4px"
        >Reset wizard (dev only)</button>
      </div>
    {/if}

  {/if}
</div>

<!-- Facebook JS SDK (loaded only in production / when meta_app_id is set) -->
{#if state && !state.dev_bypass && state.meta_app_id}
  <svelte:head>
    <script>
      window.fbAsyncInit = function() {
        FB.init({ version: 'v21.0', xfbml: false, cookie: false });
      };
    </script>
    <!-- svelte-ignore -->
    <script async defer src="https://connect.facebook.net/en_US/sdk.js"></script>
  </svelte:head>
{/if}

<style>
.hub-container { max-width: 32rem; }
@media (min-width: 768px) { .hub-container { max-width: 600px; } }

:global(.ww-label) {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-muted);
}
:global(.ww-input) {
  padding: 9px 12px;
  border-radius: 7px;
  border: 1px solid rgba(var(--red-rgb), 0.25);
  background: transparent;
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  width: 100%;
  box-sizing: border-box;
  outline: none;
}
:global(.ww-input:focus) {
  border-color: var(--red);
}
:global(.ww-btn) {
  margin-top: 12px;
  width: 100%;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid rgba(var(--red-rgb), 0.35);
  background: rgba(var(--red-rgb), 0.1);
  color: var(--red);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.03em;
  cursor: pointer;
  transition: background 0.15s;
}
:global(.ww-btn:hover:not(:disabled)) { background: rgba(var(--red-rgb), 0.18); }
:global(.ww-btn:disabled) { opacity: 0.45; cursor: not-allowed; }
:global(.ww-btn-secondary) {
  background: transparent;
  border-color: rgba(var(--red-rgb), 0.2);
  color: var(--text-muted);
}
:global(.ww-error) {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(220, 50, 50, 0.08);
  border: 1px solid rgba(220, 50, 50, 0.25);
  color: #e05555;
  font-size: 12px;
  font-weight: 600;
}
:global(.ww-notice) {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 7px;
  background: rgba(var(--red-rgb), 0.06);
  border: 1px solid rgba(var(--red-rgb), 0.2);
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}
</style>
