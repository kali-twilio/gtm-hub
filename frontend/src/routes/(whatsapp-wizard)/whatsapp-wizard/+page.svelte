<script lang="ts">
  import { onMount } from 'svelte';
  import { user } from '$lib/stores';
  import { goto } from '$app/navigation';

  let status: any = $state(null);
  let loading = $state(true);

  const isAdmin = $derived($user?.sf_access === 'full');

  onMount(async () => {
    const r = await fetch('/api/whatsapp-wizard/status');
    if (r.ok) status = await r.json();
    loading = false;
  });

  const STEPS = [
    { n: 1, label: 'Connect Twilio Account', icon: '🔑' },
    { n: 2, label: 'Link WhatsApp Business Account', icon: '📘' },
    { n: 3, label: 'Register Phone Number', icon: '📱' },
    { n: 4, label: 'Business Profile & Template', icon: '🏢' },
  ];
</script>

<div style="min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:48px 16px">
  <div style="width:100%;max-width:720px">

    <!-- Header -->
    <div style="margin-bottom:36px">
      <div style="display:inline-block;padding:3px 10px;font-size:10px;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;border:1px solid rgba(232,0,61,0.3);color:#E8003D;border-radius:4px;margin-bottom:12px">WhatsApp Wizard</div>
      <h1 style="font-size:28px;font-weight:800;color:#0D122B;letter-spacing:-0.02em;margin:0 0 6px">ISV Onboarding</h1>
      <p style="font-size:14px;color:rgba(13,18,43,0.5);margin:0">Guide an ISV through setting up WhatsApp Business messaging on Twilio.</p>
    </div>

    {#if loading}
    <div style="text-align:center;padding:48px;color:rgba(13,18,43,0.4);font-size:14px">Loading…</div>
    {:else if status}

    <!-- Progress summary -->
    <div style="background:white;border:1px solid rgba(13,18,43,0.08);border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 1px 4px rgba(13,18,43,0.06)">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <div style="font-size:13px;font-weight:700;color:#0D122B;letter-spacing:0.02em">ONBOARDING PROGRESS</div>
        <div style="font-size:12px;font-weight:600;color:#E8003D">{status.completed_steps.length}/4 steps complete</div>
      </div>
      <div style="height:6px;background:rgba(232,0,61,0.1);border-radius:99px;overflow:hidden;margin-bottom:20px">
        <div style="height:100%;background:#E8003D;border-radius:99px;transition:width 0.4s;width:{(status.completed_steps.length / 4) * 100}%"></div>
      </div>
      <div style="display:grid;gap:10px">
        {#each STEPS as step}
        {@const done = status.completed_steps.includes(step.n)}
        {@const active = status.current_step === step.n}
        <div style="display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:8px;background:{done ? 'rgba(23,135,66,0.06)' : active ? 'rgba(232,0,61,0.05)' : 'rgba(13,18,43,0.03)'};border:1px solid {done ? 'rgba(23,135,66,0.2)' : active ? 'rgba(232,0,61,0.2)' : 'rgba(13,18,43,0.08)'}">
          <div style="font-size:20px;width:32px;text-align:center">{step.icon}</div>
          <div style="flex:1">
            <div style="font-size:13px;font-weight:600;color:{done ? '#178742' : active ? '#E8003D' : '#0D122B'}">{step.label}</div>
            {#if active && !done}<div style="font-size:11px;color:rgba(232,0,61,0.7);margin-top:2px">Current step</div>{/if}
          </div>
          <div style="font-size:16px">{done ? '✅' : active ? '▶' : '○'}</div>
        </div>
        {/each}
      </div>
    </div>

    <!-- CTA -->
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <a href="/whatsapp-wizard/wizard" style="flex:1;min-width:200px;display:flex;align-items:center;justify-content:center;gap:8px;padding:14px 24px;background:#E8003D;color:white;font-weight:700;font-size:14px;border-radius:8px;text-decoration:none;letter-spacing:0.02em">
        {status.completed_steps.length === 4 ? '🔄 Review Setup' : status.completed_steps.length === 0 ? '🚀 Start Wizard' : '▶ Continue Wizard'}
      </a>
      {#if isAdmin}
      <a href="/whatsapp-wizard/admin" style="display:flex;align-items:center;gap:8px;padding:14px 24px;background:white;color:#0D122B;font-weight:600;font-size:14px;border-radius:8px;text-decoration:none;border:1px solid rgba(13,18,43,0.15)">
        🛡️ Admin View
      </a>
      {/if}
    </div>

    {/if}
  </div>
</div>
