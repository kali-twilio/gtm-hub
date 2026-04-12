<script lang="ts">
  import { user, hasData, theme } from '$lib/stores';

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
  <div class="w-full max-w-lg flex justify-between items-center mb-6 text-xs">
    <a href="/" class="p5-back-btn" style="font-size:11px">◀ Apps</a>
    <div style="display:flex;align-items:center;gap:12px">
      <span style="color:var(--text-muted);font-weight:600;letter-spacing:0.08em">{$user?.email}</span>
      <a href="/logout" style="color:var(--red);font-weight:700;text-decoration:none;text-transform:uppercase;letter-spacing:0.1em;font-style:{$theme==='p5'?'italic':'normal'}">Sign out</a>
    </div>
  </div>

  <!-- Header -->
  <div class="text-center mb-8 w-full max-w-lg">
    {#if $theme === 'twilio'}
      <div class="p5-badge mb-3">SE Scorecard</div>
      <h1 style="font-size:28px;font-weight:800;color:var(--text);letter-spacing:-0.02em">Data &amp; Reports</h1>
      <div style="width:40px;height:3px;background:var(--red);border-radius:2px;margin:10px auto 0"></div>
    {:else}
      <div class="p5-badge mb-4">SE Scorecard</div>
      <h1 style="font-size:48px;font-weight:900;font-style:italic;text-transform:uppercase;letter-spacing:-0.02em;line-height:0.9;text-shadow:3px 3px 0 var(--red)">
        SE <span style="color:var(--red)">SCORE</span>CARD
      </h1>
      <div style="width:80px;height:4px;background:var(--red);transform:skewX(-20deg);margin:12px auto 0;box-shadow:0 0 8px var(--red)"></div>
    {/if}
  </div>

  {#if error}
  <div class="w-full max-w-lg mb-4" style="background:rgba(var(--red-rgb),0.1);border:1px solid rgba(var(--red-rgb),0.4);border-left:4px solid var(--red);padding:12px 16px;font-size:14px;color:var(--red);font-weight:700">
    ⚠ {error}
  </div>
  {/if}

  {#if $hasData}
  <!-- Navigation -->
  <div class="w-full max-w-lg mb-2">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <div style="height:{$theme==='twilio'?'1px':'2px'};flex:1;background:linear-gradient(90deg,transparent,rgba(var(--red-rgb),0.3))"></div>
      <span style="font-size:10px;color:rgba(var(--red-rgb),0.7);font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};letter-spacing:0.2em;text-transform:uppercase">{$theme==='p5'?'Select Mission':'Navigation'}</span>
      <div style="height:{$theme==='twilio'?'1px':'2px'};flex:1;background:linear-gradient(90deg,rgba(var(--red-rgb),0.3),transparent)"></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:6px">
      <a href="/report" class="p5-menu-btn">
        <span style="font-size:22px">📊</span>
        <div style="flex:1">
          <div style="font-size:16px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">Full Report</div>
          <div style="font-size:11px;color:var(--text-muted);font-weight:500">Complete SE performance analysis</div>
        </div>
        <span style="color:var(--red);font-size:18px">▶</span>
      </a>
      <a href="/rankings" class="p5-menu-btn">
        <span style="font-size:22px">🏆</span>
        <div style="flex:1">
          <div style="font-size:16px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">Power Rankings</div>
          <div style="font-size:11px;color:var(--text-muted);font-weight:500">Ranked leaderboard by performance</div>
        </div>
        <span style="color:var(--red);font-size:18px">▶</span>
      </a>
      <a href="/me" class="p5-menu-btn">
        <span style="font-size:22px">👤</span>
        <div style="flex:1">
          <div style="font-size:16px;font-weight:700;font-style:{$theme==='p5'?'italic':'normal'};text-transform:uppercase;letter-spacing:0.06em;color:var(--text)">My Stats</div>
          <div style="font-size:11px;color:var(--text-muted);font-weight:500">Individual SE performance view</div>
        </div>
        <span style="color:var(--red);font-size:18px">▶</span>
      </a>
    </div>
  </div>

  <div class="w-full max-w-lg" style="display:flex;align-items:center;gap:10px;margin:20px 0">
    <div style="height:1px;flex:1;background:rgba(var(--red-rgb),0.15)"></div>
    <span style="font-size:10px;color:var(--text-faint);font-weight:700;letter-spacing:0.2em;text-transform:uppercase">Update Data</span>
    <div style="height:1px;flex:1;background:rgba(var(--red-rgb),0.15)"></div>
  </div>
  {:else}
  <p style="font-size:14px;color:var(--text-muted);font-weight:600;font-style:{$theme==='p5'?'italic':'normal'};text-align:center;margin-bottom:14px;letter-spacing:0.05em">{$theme==='p5'?'◆ Load a scorecard to begin ◆':'Load a scorecard to get started'}</p>
  {/if}

  <!-- Upload form -->
  <div class="w-full max-w-lg p5-panel" style="padding:24px">
    <form onsubmit={submit}>
      <div style="margin-bottom:16px">
        <div class="p5-badge" style="font-size:10px;margin-bottom:10px">Google Sheets URL</div>
        <input type="url" name="sheet_url" bind:value={sheetUrl}
          placeholder="https://docs.google.com/spreadsheets/d/…" />
        <p style="font-size:11px;color:var(--text-faint);margin-top:6px;font-weight:500">Share as "Anyone with the link can view"</p>
      </div>

      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
        <div style="flex:1;height:1px;background:rgba(var(--red-rgb),0.1)"></div>
        <span style="font-size:10px;color:var(--text-faint);font-weight:700;letter-spacing:0.18em;text-transform:uppercase">or</span>
        <div style="flex:1;height:1px;background:rgba(var(--red-rgb),0.1)"></div>
      </div>

      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
      <div
        style="border:2px dashed rgba(var(--red-rgb),0.25);padding:24px;text-align:center;cursor:pointer;margin-bottom:18px;background:rgba(var(--red-rgb),0.03);transition:border-color .2s;border-radius:{$theme==='twilio'?'8px':'0'}"
        onclick={() => fileInput.click()}
        ondragover={e => { e.preventDefault(); }}
        ondrop={onDrop}
      >
        <input bind:this={fileInput} type="file" name="csv_file" accept=".csv" style="display:none" onchange={onFileChange} />
        <div style="font-size:24px;margin-bottom:6px">{fileName ? '✅' : '📂'}</div>
        {#if fileName}
          <div style="font-size:13px;font-weight:700;color:#00a854">{fileName}</div>
        {:else}
          <div style="font-size:13px;color:var(--text-muted);font-weight:600">
            Drag &amp; drop CSV or <span style="color:var(--red);font-weight:700">click to browse</span>
          </div>
        {/if}
      </div>

      <button type="submit" class="p5-btn" style="width:100%;text-align:center" disabled={uploading}>
        {uploading ? '⏳ Generating…' : $theme==='p5'?'◆ Upload & Refresh All ◆':'Upload & Refresh Data'}
      </button>
    </form>
  </div>

</div>
