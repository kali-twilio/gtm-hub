<script lang="ts">
  import { user } from '$lib/stores';

  interface Step { step: number; label: string; description: string; }
  interface Info  { wizard_url: string; steps: Step[]; }

  let info: Info | null = $state(null);

  $effect(async () => {
    const r = await fetch('/api/whatsapp-wizard/info');
    if (r.ok) info = await r.json();
  });
</script>

<div class="min-h-screen flex flex-col items-center px-4 py-14">

  <!-- Header -->
  <div class="text-center mb-10 w-full hub-container">
    <div class="p5-badge mb-3">WhatsApp Wizard</div>
    <div style="font-size:40px;margin-bottom:10px">💬</div>
    <h1 style="font-size:28px;font-weight:800;color:var(--text);letter-spacing:-0.02em">
      WhatsApp Business Onboarding
    </h1>
    <p style="font-size:14px;color:var(--text-muted);font-weight:500;margin-top:8px;line-height:1.6;max-width:480px;margin-inline:auto">
      A step-by-step wizard that guides your ISV customers through activating
      WhatsApp Business on Twilio — from WABA connection to approved message templates.
    </p>
    <div style="width:40px;height:3px;background:var(--red);border-radius:2px;margin:14px auto 0"></div>
  </div>

  <!-- Steps overview -->
  {#if info}
  <div class="w-full hub-container mb-8">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.18em;color:var(--text-muted);margin-bottom:12px">
      Onboarding Steps
    </div>
    <div style="display:flex;flex-direction:column;gap:8px">
      {#each info.steps as s}
      <div class="p5-panel" style="display:flex;align-items:flex-start;gap:14px;padding:14px 16px">
        <div style="width:28px;height:28px;border-radius:50%;background:rgba(var(--red-rgb),0.12);border:1px solid rgba(var(--red-rgb),0.3);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;color:var(--red);flex-shrink:0">
          {s.step}
        </div>
        <div>
          <div style="font-size:13px;font-weight:700;color:var(--text)">{s.label}</div>
          <div style="font-size:12px;color:var(--text-muted);font-weight:500;margin-top:2px">{s.description}</div>
        </div>
      </div>
      {/each}
    </div>
  </div>

  <!-- CTA -->
  <div class="w-full hub-container">
    <a
      href={info.wizard_url}
      target="_blank"
      rel="noopener noreferrer"
      class="p5-menu-btn"
      style="display:flex;align-items:center;justify-content:center;gap:10px;padding:16px;font-size:15px;font-weight:800;text-decoration:none;border-radius:10px;background:rgba(var(--red-rgb),0.12);border:1px solid rgba(var(--red-rgb),0.35);color:var(--red);letter-spacing:0.04em;transition:background 0.15s"
    >
      <span>Open WhatsApp Wizard</span>
      <span style="font-size:18px">↗</span>
    </a>
    <p style="font-size:11px;color:var(--text-muted);text-align:center;margin-top:10px">
      Opens in a new tab · Share this link with your ISV customers to start onboarding
    </p>
  </div>
  {/if}

</div>

<style>
.hub-container {
  max-width: 32rem;
}
@media (min-width: 768px) {
  .hub-container { max-width: 600px; }
}
</style>
