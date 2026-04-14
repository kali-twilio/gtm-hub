<script lang="ts">
  import { onMount } from 'svelte';

  let status: any = $state(null);
  let currentStep = $state(1);
  let loading = $state(true);
  let saving = $state(false);
  let error = $state('');
  let success = $state('');

  // Step 1
  let accountSid = $state('');
  let authToken = $state('');

  // Step 3
  let phoneNumbers: any[] = $state([]);
  let selectedSid = $state('');
  let numbersLoading = $state(false);

  // Step 4
  let displayName = $state('');
  let description = $state('');
  let address = $state('');
  let logoUrl = $state('');
  let profileSaved = $state(false);
  let templateName = $state('');
  let templateCategory = $state('UTILITY');
  let templateLanguage = $state('en_US');
  let templateBody = $state('');
  let templateSaved = $state(false);

  async function loadStatus() {
    const r = await fetch('/api/whatsapp-wizard/status');
    if (r.ok) {
      status = await r.json();
      currentStep = status.current_step;
      if (status.profile) {
        displayName = status.profile.display_name ?? '';
        description = status.profile.description ?? '';
        address = status.profile.address ?? '';
        logoUrl = status.profile.logo_url ?? '';
      }
      if (status.completed_steps.includes(4) || status.completed_steps.includes(5)) {
        profileSaved = true; templateSaved = true;
      }
    }
    loading = false;
  }

  async function loadNumbers() {
    numbersLoading = true;
    const r = await fetch('/api/whatsapp-wizard/step/3/numbers');
    if (r.ok) phoneNumbers = (await r.json()).numbers ?? [];
    numbersLoading = false;
  }

  function goToStep(n: number) {
    error = ''; success = '';
    currentStep = n;
    if (n === 3 && phoneNumbers.length === 0) loadNumbers();
  }

  async function post(url: string, body: object) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return { ok: r.ok, data: await r.json() };
  }

  async function submitStep1() {
    saving = true; error = '';
    const { ok, data } = await post('/api/whatsapp-wizard/step/1', { account_sid: accountSid, auth_token: authToken });
    saving = false;
    if (!ok) { error = data.error; return; }
    success = `Connected: ${data.friendly_name}`;
    await loadStatus();
    setTimeout(() => { success = ''; goToStep(2); }, 900);
  }

  async function submitStep2Meta(code: string) {
    saving = true; error = '';
    const { ok, data } = await post('/api/whatsapp-wizard/step/2/meta-callback', { code });
    saving = false;
    if (!ok) { error = data.error; return; }
    success = `WABA connected: ${data.waba_id}`;
    await loadStatus();
    setTimeout(() => { success = ''; goToStep(3); loadNumbers(); }, 900);
  }

  async function bypassStep2() {
    saving = true; error = '';
    const { ok, data } = await post('/api/whatsapp-wizard/step/2/bypass', {});
    saving = false;
    if (!ok) { error = data.error; return; }
    success = 'Sandbox WABA applied';
    await loadStatus();
    setTimeout(() => { success = ''; goToStep(3); loadNumbers(); }, 900);
  }

  async function submitStep3() {
    if (!selectedSid) { error = 'Select a phone number.'; return; }
    saving = true; error = '';
    const { ok, data } = await post('/api/whatsapp-wizard/step/3/register', { phone_sid: selectedSid });
    saving = false;
    if (!ok) { error = data.error; return; }
    success = `Registered: ${data.phone_number}`;
    await loadStatus();
    setTimeout(() => { success = ''; goToStep(4); }, 900);
  }

  async function bypassStep3() {
    saving = true; error = '';
    const { ok, data } = await post('/api/whatsapp-wizard/step/3/bypass', {});
    saving = false;
    if (!ok) { error = data.error; return; }
    success = `Using sandbox: ${data.phone_number}`;
    await loadStatus();
    setTimeout(() => { success = ''; goToStep(4); }, 900);
  }

  async function submitProfile() {
    if (!displayName.trim()) { error = 'Display name is required.'; return; }
    saving = true; error = '';
    const { ok, data } = await post('/api/whatsapp-wizard/step/4/profile', { display_name: displayName, description, address, logo_url: logoUrl });
    saving = false;
    if (!ok) { error = data.error; return; }
    profileSaved = true;
    await loadStatus();
  }

  async function submitTemplate() {
    if (!templateName.trim() || !templateBody.trim()) { error = 'Template name and body are required.'; return; }
    saving = true; error = '';
    const { ok, data } = await post('/api/whatsapp-wizard/step/4/template', { name: templateName, category: templateCategory, language: templateLanguage, body: templateBody });
    saving = false;
    if (!ok) { error = data.error; return; }
    templateSaved = true;
    success = `Template submitted — status: ${data.status}`;
    await loadStatus();
  }

  // Facebook Embedded Signup SDK
  function initFacebookSDK(appId: string, configId: string) {
    (window as any).fbAsyncInit = function () {
      (window as any).FB.init({ appId, cookie: true, xfbml: true, version: 'v21.0' });
    };
    (function (d, s, id) {
      if (d.getElementById(id)) return;
      const js = d.createElement(s) as HTMLScriptElement;
      js.id = id;
      js.src = 'https://connect.facebook.net/en_US/sdk.js';
      d.head.appendChild(js);
    })(document, 'script', 'facebook-jssdk');
  }

  function launchFacebookLogin(configId: string) {
    (window as any).FB.login(
      (response: any) => {
        if (response.authResponse?.code) {
          submitStep2Meta(response.authResponse.code);
        } else {
          error = 'Facebook login was cancelled or failed.';
        }
      },
      { config_id: configId, response_type: 'code', override_default_response_type: true }
    );
  }

  onMount(async () => {
    await loadStatus();
    if (status?.meta_app_id) initFacebookSDK(status.meta_app_id, status.meta_config_id);
  });

  const STEP_LABELS = ['Connect Twilio', 'Link WABA', 'Phone Number', 'Profile & Template'];
</script>

<div style="min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:40px 16px">
<div style="width:100%;max-width:640px">

  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
    <a href="/whatsapp-wizard" style="font-size:12px;color:rgba(13,18,43,0.4);text-decoration:none;font-weight:600">◀ Hub</a>
  </div>

  {#if loading}
  <div style="text-align:center;padding:64px;color:rgba(13,18,43,0.4)">Loading…</div>
  {:else}

  <!-- Step progress bar -->
  <div style="display:flex;gap:0;margin-bottom:32px">
    {#each STEP_LABELS as label, i}
    {@const n = i + 1}
    {@const done = status?.completed_steps?.includes(n)}
    {@const active = currentStep === n}
    <button
      onclick={() => goToStep(n)}
      style="flex:1;padding:10px 4px;text-align:center;font-size:11px;font-weight:700;cursor:pointer;background:{active ? '#E8003D' : done ? 'rgba(23,135,66,0.08)' : 'rgba(13,18,43,0.04)'};color:{active ? 'white' : done ? '#178742' : 'rgba(13,18,43,0.4)'};border:none;border-right:{i < 3 ? '1px solid rgba(13,18,43,0.08)' : 'none'};border-radius:{i === 0 ? '8px 0 0 8px' : i === 3 ? '0 8px 8px 0' : '0'};letter-spacing:0.04em"
    >{done ? '✓ ' : ''}{n}. {label}</button>
    {/each}
  </div>

  <!-- Error / success -->
  {#if error}
  <div style="background:rgba(232,0,61,0.08);border:1px solid rgba(232,0,61,0.3);border-left:4px solid #E8003D;padding:12px 16px;border-radius:6px;font-size:13px;color:#E8003D;font-weight:600;margin-bottom:20px">⚠ {error}</div>
  {/if}
  {#if success}
  <div style="background:rgba(23,135,66,0.08);border:1px solid rgba(23,135,66,0.3);border-left:4px solid #178742;padding:12px 16px;border-radius:6px;font-size:13px;color:#178742;font-weight:600;margin-bottom:20px">✓ {success}</div>
  {/if}

  <!-- ── Step 1 ── -->
  {#if currentStep === 1}
  <div style="background:white;border:1px solid rgba(13,18,43,0.08);border-radius:12px;padding:28px;box-shadow:0 1px 4px rgba(13,18,43,0.06)">
    <h2 style="font-size:18px;font-weight:800;color:#0D122B;margin:0 0 6px">Connect Twilio Account</h2>
    <p style="font-size:13px;color:rgba(13,18,43,0.5);margin:0 0 24px">Enter the ISV's Twilio Account SID and Auth Token from their Twilio Console.</p>

    {#if status?.account}
    <div style="background:rgba(23,135,66,0.06);border:1px solid rgba(23,135,66,0.2);border-radius:8px;padding:14px 16px;margin-bottom:20px;font-size:13px;color:#178742;font-weight:600">
      ✅ Connected: <strong>{status.account.friendly_name}</strong> ({status.account.sid})
    </div>
    {/if}

    <div style="display:flex;flex-direction:column;gap:14px">
      <div>
        <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Account SID</label>
        <input bind:value={accountSid} placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;font-family:monospace;box-sizing:border-box" />
      </div>
      <div>
        <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Auth Token</label>
        <input bind:value={authToken} type="password" placeholder="••••••••••••••••••••••••••••••••" style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;font-family:monospace;box-sizing:border-box" />
      </div>
      <button onclick={submitStep1} disabled={saving || !accountSid || !authToken} style="padding:12px 24px;background:#E8003D;color:white;font-weight:700;font-size:14px;border:none;border-radius:8px;cursor:{saving ? 'wait' : 'pointer'};opacity:{saving || !accountSid || !authToken ? 0.6 : 1}">
        {saving ? 'Validating…' : 'Validate & Connect'}
      </button>
    </div>
  </div>

  <!-- ── Step 2 ── -->
  {:else if currentStep === 2}
  <div style="background:white;border:1px solid rgba(13,18,43,0.08);border-radius:12px;padding:28px;box-shadow:0 1px 4px rgba(13,18,43,0.06)">
    <h2 style="font-size:18px;font-weight:800;color:#0D122B;margin:0 0 6px">Link WhatsApp Business Account</h2>
    <p style="font-size:13px;color:rgba(13,18,43,0.5);margin:0 0 24px">The ISV must authorize via Facebook to connect their WhatsApp Business Account (WABA).</p>

    {#if status?.completed_steps?.includes(2)}
    <div style="background:rgba(23,135,66,0.06);border:1px solid rgba(23,135,66,0.2);border-radius:8px;padding:14px 16px;margin-bottom:20px;font-size:13px;color:#178742;font-weight:600">
      ✅ WABA linked
    </div>
    {/if}

    <div style="display:flex;flex-direction:column;gap:12px">
      <button
        onclick={() => launchFacebookLogin(status?.meta_config_id)}
        disabled={saving || !status?.meta_app_id}
        style="display:flex;align-items:center;justify-content:center;gap:10px;padding:13px 24px;background:#1877F2;color:white;font-weight:700;font-size:14px;border:none;border-radius:8px;cursor:pointer;opacity:{!status?.meta_app_id ? 0.5 : 1}"
      >
        <span style="font-size:20px">f</span> Continue with Facebook
      </button>

      {#if status?.dev_bypass}
      <div style="border-top:1px solid rgba(13,18,43,0.08);padding-top:12px">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.3);margin-bottom:8px">Dev Mode</div>
        <button onclick={bypassStep2} disabled={saving} style="padding:10px 20px;background:rgba(13,18,43,0.06);color:rgba(13,18,43,0.6);font-weight:600;font-size:13px;border:1px solid rgba(13,18,43,0.12);border-radius:6px;cursor:pointer">
          Use Sandbox WABA
        </button>
      </div>
      {/if}
    </div>
  </div>

  <!-- ── Step 3 ── -->
  {:else if currentStep === 3}
  <div style="background:white;border:1px solid rgba(13,18,43,0.08);border-radius:12px;padding:28px;box-shadow:0 1px 4px rgba(13,18,43,0.06)">
    <h2 style="font-size:18px;font-weight:800;color:#0D122B;margin:0 0 6px">Register Phone Number</h2>
    <p style="font-size:13px;color:rgba(13,18,43,0.5);margin:0 0 24px">Select a phone number from the ISV's Twilio account to register for WhatsApp.</p>

    {#if status?.completed_steps?.includes(3)}
    <div style="background:rgba(23,135,66,0.06);border:1px solid rgba(23,135,66,0.2);border-radius:8px;padding:14px 16px;margin-bottom:20px;font-size:13px;color:#178742;font-weight:600">
      ✅ Registered: {status?.senders?.[0]?.phone_number}
    </div>
    {/if}

    {#if numbersLoading}
    <div style="padding:24px;text-align:center;color:rgba(13,18,43,0.4);font-size:13px">Loading numbers…</div>
    {:else if phoneNumbers.length === 0}
    <div style="padding:16px;background:rgba(232,0,61,0.05);border:1px solid rgba(232,0,61,0.15);border-radius:8px;font-size:13px;color:rgba(13,18,43,0.6);margin-bottom:16px">No phone numbers found on the connected account.</div>
    {:else}
    <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:20px">
      {#each phoneNumbers as num}
      <label style="display:flex;align-items:center;gap:12px;padding:12px 16px;border:1px solid {selectedSid === num.sid ? '#E8003D' : 'rgba(13,18,43,0.1)'};border-radius:8px;cursor:pointer;background:{selectedSid === num.sid ? 'rgba(232,0,61,0.04)' : 'white'}">
        <input type="radio" bind:group={selectedSid} value={num.sid} style="accent-color:#E8003D" />
        <div>
          <div style="font-size:14px;font-weight:600;color:#0D122B;font-family:monospace">{num.phone_number}</div>
          <div style="font-size:11px;color:rgba(13,18,43,0.4)">{num.friendly_name}</div>
        </div>
      </label>
      {/each}
    </div>
    {/if}

    <div style="display:flex;flex-direction:column;gap:12px">
      <button onclick={submitStep3} disabled={saving || !selectedSid} style="padding:12px 24px;background:#E8003D;color:white;font-weight:700;font-size:14px;border:none;border-radius:8px;cursor:{!selectedSid ? 'default' : 'pointer'};opacity:{saving || !selectedSid ? 0.6 : 1}">
        {saving ? 'Registering…' : 'Register for WhatsApp'}
      </button>

      {#if status?.dev_bypass}
      <div style="border-top:1px solid rgba(13,18,43,0.08);padding-top:12px">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.3);margin-bottom:8px">Dev Mode</div>
        <button onclick={bypassStep3} disabled={saving} style="padding:10px 20px;background:rgba(13,18,43,0.06);color:rgba(13,18,43,0.6);font-weight:600;font-size:13px;border:1px solid rgba(13,18,43,0.12);border-radius:6px;cursor:pointer">
          Use Twilio Sandbox (+14155238886)
        </button>
      </div>
      {/if}
    </div>
  </div>

  <!-- ── Step 4 ── -->
  {:else if currentStep === 4}
  <div style="display:flex;flex-direction:column;gap:16px">

    <!-- Business profile -->
    <div style="background:white;border:1px solid rgba(13,18,43,0.08);border-radius:12px;padding:24px;box-shadow:0 1px 4px rgba(13,18,43,0.06)">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
        <h2 style="font-size:16px;font-weight:800;color:#0D122B;margin:0">Business Profile</h2>
        {#if profileSaved}<span style="font-size:12px;color:#178742;font-weight:600">✅ Saved</span>{/if}
      </div>
      <div style="display:flex;flex-direction:column;gap:14px">
        <div>
          <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Display Name *</label>
          <input bind:value={displayName} placeholder="Acme Corp" style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;box-sizing:border-box" />
        </div>
        <div>
          <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Description</label>
          <textarea bind:value={description} placeholder="Brief description of the business…" rows="3" style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;resize:vertical;box-sizing:border-box"></textarea>
        </div>
        <div>
          <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Address</label>
          <input bind:value={address} placeholder="123 Main St, City, Country" style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;box-sizing:border-box" />
        </div>
        <div>
          <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Logo URL</label>
          <input bind:value={logoUrl} placeholder="https://…/logo.png" style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;box-sizing:border-box" />
        </div>
        <button onclick={submitProfile} disabled={saving || !displayName.trim()} style="padding:11px 24px;background:{profileSaved ? 'rgba(23,135,66,0.1)' : '#E8003D'};color:{profileSaved ? '#178742' : 'white'};font-weight:700;font-size:13px;border:none;border-radius:8px;cursor:pointer;opacity:{saving || !displayName.trim() ? 0.6 : 1}">
          {saving ? 'Saving…' : profileSaved ? '✓ Profile Saved' : 'Save Profile'}
        </button>
      </div>
    </div>

    <!-- Message template -->
    <div style="background:white;border:1px solid rgba(13,18,43,0.08);border-radius:12px;padding:24px;box-shadow:0 1px 4px rgba(13,18,43,0.06)">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
        <h2 style="font-size:16px;font-weight:800;color:#0D122B;margin:0">First Message Template</h2>
        {#if templateSaved}<span style="font-size:12px;color:#178742;font-weight:600">✅ Submitted</span>{/if}
      </div>
      <div style="display:flex;flex-direction:column;gap:14px">
        <div>
          <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Template Name *</label>
          <input bind:value={templateName} placeholder="welcome_message" style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;font-family:monospace;box-sizing:border-box" />
          <div style="font-size:11px;color:rgba(13,18,43,0.35);margin-top:4px">Lowercase letters, numbers, underscores only</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div>
            <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Category</label>
            <select bind:value={templateCategory} style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;box-sizing:border-box">
              <option value="UTILITY">Utility</option>
              <option value="MARKETING">Marketing</option>
              <option value="AUTHENTICATION">Authentication</option>
            </select>
          </div>
          <div>
            <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Language</label>
            <select bind:value={templateLanguage} style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;box-sizing:border-box">
              <option value="en_US">English (US)</option>
              <option value="en_GB">English (UK)</option>
              <option value="es">Spanish</option>
              <option value="pt_BR">Portuguese (BR)</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="it">Italian</option>
              <option value="ja">Japanese</option>
            </select>
          </div>
        </div>
        <div>
          <label style="display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.5);margin-bottom:6px">Body *</label>
          <textarea bind:value={templateBody} placeholder={"Hello {{1}}, welcome to our service!"} rows="4" style="width:100%;padding:10px 14px;border:1px solid rgba(13,18,43,0.15);border-radius:6px;font-size:13px;resize:vertical;box-sizing:border-box"></textarea>
          <div style="font-size:11px;color:rgba(13,18,43,0.35);margin-top:4px">Use {`{{1}}`}, {`{{2}}`} etc. for variables · Max 1024 chars</div>
        </div>
        <button onclick={submitTemplate} disabled={saving || !templateName.trim() || !templateBody.trim()} style="padding:11px 24px;background:{templateSaved ? 'rgba(23,135,66,0.1)' : '#E8003D'};color:{templateSaved ? '#178742' : 'white'};font-weight:700;font-size:13px;border:none;border-radius:8px;cursor:pointer;opacity:{saving || !templateName.trim() || !templateBody.trim() ? 0.6 : 1}">
          {saving ? 'Submitting…' : templateSaved ? '✓ Template Submitted' : 'Submit for Approval'}
        </button>
      </div>
    </div>

    {#if profileSaved && templateSaved}
    <div style="background:rgba(23,135,66,0.08);border:1px solid rgba(23,135,66,0.25);border-radius:12px;padding:20px;text-align:center">
      <div style="font-size:28px;margin-bottom:8px">🎉</div>
      <div style="font-size:16px;font-weight:800;color:#178742">Onboarding Complete!</div>
      <div style="font-size:13px;color:rgba(13,18,43,0.5);margin-top:4px">All 4 steps finished. Template approval can take up to 24 hours.</div>
      <a href="/whatsapp-wizard" style="display:inline-block;margin-top:16px;padding:10px 20px;background:#178742;color:white;font-weight:700;font-size:13px;border-radius:8px;text-decoration:none">Back to Hub</a>
    </div>
    {/if}

  {/if}

  {/if}
</div>
</div>
