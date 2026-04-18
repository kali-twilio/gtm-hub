<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import AppHeader from '$lib/AppHeader.svelte';

  let { children } = $props();
  let prevTheme = '';
  let chatOpen  = $state(false);

  onMount(() => {
    prevTheme = document.body.getAttribute('data-theme') ?? '';
    document.body.setAttribute('data-theme', 'twilio');
  });

  onDestroy(() => {
    if (prevTheme) {
      document.body.setAttribute('data-theme', prevTheme);
    } else {
      document.body.removeAttribute('data-theme');
    }
  });
</script>

<AppHeader appName="SE Forecast" appId="se-forecast" showAskAI={true} bind:chatOpen />

<div style="padding-top:56px;min-height:100vh;background:#F4F4F6;transition:margin-left 0.2s;margin-left:{chatOpen?'min(420px,100vw)':'0'}">
  {@render children()}
</div>
