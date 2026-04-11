<script lang="ts">
  import { user, hasData } from '$lib/stores';

  let uploading = $state(false);
  let sheetUrl = $state('');
  let fileName = $state('');
  let fileInput: HTMLInputElement;
  let error = $state('');

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    uploading = true;
    error = '';
    const form = e.target as HTMLFormElement;
    const data = new FormData(form);
    const r = await fetch('/api/generate', { method: 'POST', body: data });
    const json = await r.json();
    if (json.ok) {
      hasData.set(true);
    } else {
      error = json.error || 'Failed to generate report.';
    }
    uploading = false;
  }

  function onFileChange(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) fileName = f.name;
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    const f = e.dataTransfer?.files[0];
    if (f?.name.endsWith('.csv')) {
      const dt = new DataTransfer();
      dt.items.add(f);
      fileInput.files = dt.files;
      fileName = f.name;
    }
  }
</script>

<div class="min-h-screen flex flex-col items-center px-4 py-16">

  <!-- Top bar -->
  {#if $user}
  <div class="w-full max-w-lg flex justify-between items-center mb-6 text-xs">
    <span style="color:rgba(255,255,255,0.3);font-weight:600;letter-spacing:0.08em">{$user.email}</span>
    <a href="/logout" style="color:rgba(232,0,61,0.7);font-weight:700;text-decoration:none;text-transform:uppercase;letter-spacing:0.1em;font-style:italic">Sign out ◆</a>
  </div>
  {/if}

  <!-- Header -->
  {#if !$user}
  <!-- Login state -->
  <div class="w-full max-w-sm">
    <div class="text-center mb-8">
      <div class="p5-badge mb-4">DSR Sales Engineering</div>
      <h1 style="font-size:52px;font-weight:900;font-style:italic;text-transform:uppercase;letter-spacing:-0.02em;line-height:0.9;text-shadow:4px 4px 0 var(--red)">
        SE<br>SCORE<span style="color:var(--red)">CARD</span>
      </h1>
      <div style="width:80px;height:4px;background:var(--red);transform:skewX(-20deg);margin:14px auto 0;box-shadow:0 0 8px var(--red)"></div>
    </div>
    <div class="p5-panel" style="padding:28px 24px">
      <div class="p5-badge" style="font-size:10px;margin-bottom:12px">Access Required</div>
      <p style="color:rgba(255,255,255,0.4);font-size:14px;font-weight:500;margin-bottom:20px">
        Sign in with your Twilio Google account to continue.
      </p>
      <a href="/auth" class="p5-btn" style="display:flex;align-items:center;justify-content:center;gap:10px;background:white;color:#111;box-shadow:none;clip-path:polygon(6px 0%,100% 0%,calc(100% - 6px) 100%,0% 100%)">
        <svg width="20" height="20" viewBox="0 0 48 48">
          <path fill="#EA4335" d="M24 9.5c3.14 0 5.95 1.08 8.17 2.85l6.09-6.09C34.46 3.05 29.52 1 24 1 14.82 1 7.07 6.48 3.58 14.18l7.09 5.51C12.28 13.36 17.67 9.5 24 9.5z"/>
          <path fill="#4285F4" d="M46.46 24.5c0-1.64-.15-3.22-.42-4.75H24v9h12.64c-.55 2.96-2.2 5.47-4.68 7.16l7.19 5.59C43.44 37.28 46.46 31.36 46.46 24.5z"/>
          <path fill="#FBBC05" d="M10.67 28.31A14.6 14.6 0 0 1 9.5 24c0-1.49.26-2.93.7-4.31l-7.09-5.51A23.94 23.94 0 0 0 0 24c0 3.87.93 7.53 2.58 10.76l8.09-6.45z"/>
          <path fill="#34A853" d="M24 47c5.52 0 10.15-1.83 13.53-4.96l-7.19-5.59C28.6 38.27 26.42 39 24 39c-6.33 0-11.72-3.86-13.33-9.19l-8.09 6.45C6.07 43.52 14.42 47 24 47z"/>
        </svg>
        <span style="font-style:italic;font-weight:700;text-transform:uppercase;letter-spacing:0.1em">Sign in with Google</span>
      </a>
      <p style="font-size:11px;color:rgba(255,255,255,0.2);text-align:center;margin-top:14px;letter-spacing:0.12em">◆ @TWILIO.COM ACCOUNTS ONLY ◆</p>
    </div>
  </div>

  {:else}

  <!-- Logged in: show menu + upload -->
  <div class="text-center mb-8 w-full max-w-lg">
    <div class="p5-badge mb-4">DSR Sales Engineering</div>
    <h1 style="font-size:48px;font-weight:900;font-style:italic;text-transform:uppercase;letter-spacing:-0.02em;line-height:0.9;text-shadow:3px 3px 0 var(--red)">
      SE <span style="color:var(--red)">SCORE</span>CARD
    </h1>
    <div style="width:80px;height:4px;background:var(--red);transform:skewX(-20deg);margin:12px auto 0;box-shadow:0 0 8px var(--red)"></div>
  </div>

  {#if error}
  <div class="w-full max-w-lg mb-4" style="background:rgba(232,0,61,0.12);border:1px solid rgba(232,0,61,0.5);border-left:4px solid var(--red);padding:12px 16px;font-size:14px;color:#ff7070;font-weight:700;font-style:italic">
    ⚠ {error}
  </div>
  {/if}

  {#if $hasData}
  <!-- Mission select -->
  <div class="w-full max-w-lg mb-2">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <div style="height:2px;flex:1;background:linear-gradient(90deg,transparent,rgba(232,0,61,0.4))"></div>
      <span style="font-size:10px;color:rgba(232,0,61,0.7);font-weight:700;font-style:italic;letter-spacing:0.2em;text-transform:uppercase">Select Mission</span>
      <div style="height:2px;flex:1;background:linear-gradient(90deg,rgba(232,0,61,0.4),transparent)"></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:6px">
      <a href="/report" class="p5-menu-btn">
        <span style="font-size:22px">📊</span>
        <div style="flex:1">
          <div style="font-size:16px;font-weight:700;font-style:italic;text-transform:uppercase;letter-spacing:0.06em">Full Report</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.35);font-weight:500">Complete SE performance analysis</div>
        </div>
        <span style="color:var(--red);font-size:18px">▶</span>
      </a>
      <a href="/rankings" class="p5-menu-btn">
        <span style="font-size:22px">🏆</span>
        <div style="flex:1">
          <div style="font-size:16px;font-weight:700;font-style:italic;text-transform:uppercase;letter-spacing:0.06em">Power Rankings</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.35);font-weight:500">Ranked leaderboard by performance</div>
        </div>
        <span style="color:var(--red);font-size:18px">▶</span>
      </a>
      <a href="/me" class="p5-menu-btn">
        <span style="font-size:22px">👤</span>
        <div style="flex:1">
          <div style="font-size:16px;font-weight:700;font-style:italic;text-transform:uppercase;letter-spacing:0.06em">My Stats</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.35);font-weight:500">Individual SE performance view</div>
        </div>
        <span style="color:var(--red);font-size:18px">▶</span>
      </a>
    </div>
  </div>

  <div class="w-full max-w-lg" style="display:flex;align-items:center;gap:10px;margin:20px 0">
    <div style="height:1px;flex:1;background:rgba(232,0,61,0.2)"></div>
    <span style="font-size:10px;color:rgba(255,255,255,0.2);font-weight:700;letter-spacing:0.2em;text-transform:uppercase">Update Intel</span>
    <div style="height:1px;flex:1;background:rgba(232,0,61,0.2)"></div>
  </div>
  {:else}
  <p style="font-size:14px;color:rgba(255,255,255,0.3);font-weight:600;font-style:italic;text-align:center;margin-bottom:14px;letter-spacing:0.05em">◆ Load a scorecard to begin ◆</p>
  {/if}

  <!-- Upload form -->
  <div class="w-full max-w-lg p5-panel" style="padding:24px">
    <form onsubmit={submit}>
      <div style="margin-bottom:16px">
        <div class="p5-badge" style="font-size:10px;margin-bottom:10px">Google Sheets URL</div>
        <input type="url" name="sheet_url" bind:value={sheetUrl}
          placeholder="https://docs.google.com/spreadsheets/d/…" />
        <p style="font-size:11px;color:rgba(255,255,255,0.2);margin-top:6px;font-weight:500">Share as "Anyone with the link can view"</p>
      </div>

      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
        <div style="flex:1;height:1px;background:rgba(255,255,255,0.08)"></div>
        <span style="font-size:10px;color:rgba(255,255,255,0.25);font-weight:700;letter-spacing:0.18em;text-transform:uppercase">or</span>
        <div style="flex:1;height:1px;background:rgba(255,255,255,0.08)"></div>
      </div>

      <!-- Drop zone -->
      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
      <div
        style="border:2px dashed rgba(232,0,61,0.3);padding:24px;text-align:center;cursor:pointer;margin-bottom:18px;background:rgba(0,0,0,0.3);transition:border-color .2s"
        onclick={() => fileInput.click()}
        ondragover={e => { e.preventDefault(); }}
        ondrop={onDrop}
      >
        <input bind:this={fileInput} type="file" name="csv_file" accept=".csv" style="display:none" onchange={onFileChange} />
        <div style="font-size:24px;margin-bottom:6px">{fileName ? '✅' : '📂'}</div>
        {#if fileName}
          <div style="font-size:13px;font-weight:700;color:#00e87a">{fileName}</div>
        {:else}
          <div style="font-size:13px;color:rgba(255,255,255,0.4);font-weight:600">
            Drag &amp; drop CSV or <span style="color:var(--red);font-weight:700">click to browse</span>
          </div>
        {/if}
      </div>

      <button type="submit" class="p5-btn" style="width:100%;text-align:center" disabled={uploading}>
        {uploading ? '⏳ Generating…' : '◆ Upload & Refresh All ◆'}
      </button>
    </form>
  </div>
  {/if}

</div>
