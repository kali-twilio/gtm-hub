<script lang="ts">
  import { onMount } from 'svelte';
  import { user } from '$lib/stores';
  import { goto } from '$app/navigation';

  let clients: any[] = $state([]);
  let selected: any = $state(null);
  let loading = $state(true);
  let detailLoading = $state(false);

  const isAdmin = $derived($user?.sf_access === 'full');

  onMount(async () => {
    if (!isAdmin) { goto('/whatsapp-wizard'); return; }
    const r = await fetch('/api/whatsapp-wizard/admin/clients');
    if (r.ok) clients = (await r.json()).clients ?? [];
    loading = false;
  });

  async function loadDetail(email: string) {
    detailLoading = true;
    const r = await fetch(`/api/whatsapp-wizard/admin/clients/${encodeURIComponent(email)}`);
    if (r.ok) selected = await r.json();
    detailLoading = false;
  }

  const STEP_LABELS: Record<number, string> = {
    1: 'Twilio Account',
    2: 'WABA',
    3: 'Phone Number',
    4: 'Profile & Template',
  };

  function stepStatus(steps: Record<string, any>, n: number) {
    return steps?.[String(n)]?.status ?? 'pending';
  }
</script>

<div style="min-height:100vh;padding:40px 16px">
<div style="max-width:1100px;margin:0 auto">

  <div style="display:flex;align-items:center;gap:12px;margin-bottom:28px">
    <a href="/whatsapp-wizard" style="font-size:12px;color:rgba(13,18,43,0.4);text-decoration:none;font-weight:600">◀ Hub</a>
    <div style="width:1px;height:14px;background:rgba(13,18,43,0.15)"></div>
    <h1 style="font-size:20px;font-weight:800;color:#0D122B;margin:0">Admin — All Clients</h1>
    <span style="margin-left:auto;font-size:12px;color:rgba(13,18,43,0.4);font-weight:600">{clients.length} users</span>
  </div>

  <div style="display:grid;grid-template-columns:{selected ? '1fr 380px' : '1fr'};gap:20px;align-items:start">

    <!-- Client list -->
    <div style="background:white;border:1px solid rgba(13,18,43,0.08);border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(13,18,43,0.06)">
      {#if loading}
      <div style="padding:48px;text-align:center;color:rgba(13,18,43,0.4);font-size:14px">Loading…</div>
      {:else if clients.length === 0}
      <div style="padding:48px;text-align:center;color:rgba(13,18,43,0.4);font-size:14px">No clients yet.</div>
      {:else}
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead>
          <tr style="border-bottom:1px solid rgba(13,18,43,0.08)">
            <th style="padding:12px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.4)">User</th>
            <th style="padding:12px 16px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.4)">Twilio Account</th>
            <th style="padding:12px 16px;text-align:center;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.4)">Progress</th>
            <th style="padding:12px 16px;text-align:right;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.4)">Started</th>
          </tr>
        </thead>
        <tbody>
          {#each clients as client}
          {@const pct = (client.completed_steps / 4) * 100}
          <tr
            onclick={() => loadDetail(client.email)}
            style="border-bottom:1px solid rgba(13,18,43,0.05);cursor:pointer;background:{selected?.email === client.email ? 'rgba(232,0,61,0.03)' : 'white'};transition:background 0.1s"
            onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = selected?.email === client.email ? 'rgba(232,0,61,0.05)' : 'rgba(13,18,43,0.02)'}
            onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = selected?.email === client.email ? 'rgba(232,0,61,0.03)' : 'white'}
          >
            <td style="padding:14px 16px">
              <div style="font-weight:600;color:#0D122B">{client.friendly_name ?? client.email.split('@')[0]}</div>
              <div style="font-size:11px;color:rgba(13,18,43,0.4);margin-top:2px">{client.email}</div>
            </td>
            <td style="padding:14px 16px;color:rgba(13,18,43,0.6);font-family:monospace;font-size:12px">{client.friendly_name ?? '—'}</td>
            <td style="padding:14px 16px;text-align:center">
              <div style="font-size:11px;font-weight:700;color:{pct === 100 ? '#178742' : '#E8003D'};margin-bottom:4px">{client.completed_steps}/4</div>
              <div style="height:4px;background:rgba(13,18,43,0.08);border-radius:99px;overflow:hidden;width:80px;margin:0 auto">
                <div style="height:100%;background:{pct === 100 ? '#178742' : '#E8003D'};border-radius:99px;width:{pct}%"></div>
              </div>
            </td>
            <td style="padding:14px 16px;text-align:right;font-size:11px;color:rgba(13,18,43,0.4)">{client.connected_at ? new Date(client.connected_at).toLocaleDateString() : '—'}</td>
          </tr>
          {/each}
        </tbody>
      </table>
      {/if}
    </div>

    <!-- Detail panel -->
    {#if selected}
    <div style="background:white;border:1px solid rgba(13,18,43,0.08);border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(13,18,43,0.06);position:sticky;top:76px">
      {#if detailLoading}
      <div style="padding:32px;text-align:center;color:rgba(13,18,43,0.4);font-size:13px">Loading…</div>
      {:else}
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <div>
          <div style="font-size:14px;font-weight:800;color:#0D122B">{selected.account?.friendly_name ?? selected.email.split('@')[0]}</div>
          <div style="font-size:11px;color:rgba(13,18,43,0.4);margin-top:2px">{selected.email}</div>
        </div>
        <button onclick={() => selected = null} style="font-size:16px;background:none;border:none;cursor:pointer;color:rgba(13,18,43,0.3)">✕</button>
      </div>

      {#if selected.account}
      <div style="font-size:11px;color:rgba(13,18,43,0.4);font-family:monospace;margin-bottom:16px;padding:8px 12px;background:rgba(13,18,43,0.03);border-radius:6px">{selected.account.sid}</div>
      {/if}

      <!-- Steps -->
      <div style="margin-bottom:16px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.4);margin-bottom:8px">Steps</div>
        <div style="display:flex;flex-direction:column;gap:6px">
          {#each [1, 2, 3, 4] as n}
          {@const s = stepStatus(selected.steps, n)}
          <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:{s === 'complete' ? 'rgba(23,135,66,0.06)' : 'rgba(13,18,43,0.03)'};border-radius:6px">
            <span style="font-size:14px">{s === 'complete' ? '✅' : '○'}</span>
            <span style="font-size:12px;font-weight:600;color:{s === 'complete' ? '#178742' : 'rgba(13,18,43,0.5)'}">{STEP_LABELS[n]}</span>
            {#if selected.steps?.[String(n)]?.completed_at}
            <span style="margin-left:auto;font-size:10px;color:rgba(13,18,43,0.3)">{new Date(selected.steps[String(n)].completed_at).toLocaleDateString()}</span>
            {/if}
          </div>
          {/each}
        </div>
      </div>

      <!-- Senders -->
      {#if selected.senders?.length}
      <div style="margin-bottom:16px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.4);margin-bottom:8px">Phone Numbers</div>
        {#each selected.senders as s}
        <div style="font-size:12px;font-weight:600;color:#0D122B;font-family:monospace;padding:6px 12px;background:rgba(13,18,43,0.03);border-radius:6px;margin-bottom:4px">
          {s.phone_number} <span style="font-weight:400;color:rgba(13,18,43,0.4)">· {s.status}</span>
        </div>
        {/each}
      </div>
      {/if}

      <!-- Templates -->
      {#if selected.templates?.length}
      <div>
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:rgba(13,18,43,0.4);margin-bottom:8px">Templates</div>
        {#each selected.templates as t}
        {@const statusColor = t.meta_status === 'approved' ? '#178742' : t.meta_status === 'rejected' ? '#E8003D' : '#B45309'}
        <div style="padding:10px 12px;background:rgba(13,18,43,0.03);border-radius:6px;margin-bottom:6px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
            <span style="font-size:12px;font-weight:700;color:#0D122B;font-family:monospace">{t.name}</span>
            <span style="font-size:10px;font-weight:700;color:{statusColor};text-transform:uppercase">{t.meta_status}</span>
          </div>
          <div style="font-size:11px;color:rgba(13,18,43,0.5)">{t.body}</div>
        </div>
        {/each}
      </div>
      {/if}
      {/if}
    </div>
    {/if}

  </div>
</div>
</div>
