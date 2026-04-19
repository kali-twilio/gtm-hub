<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { user, hasData, authReady, theme } from '$lib/stores';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import UserChip from '$lib/UserChip.svelte';

  // Dark-background pages where the chip should use the dark variant.
  const darkChip = $derived($page.url.pathname === '/');

  let { children, data } = $props();

  // Runs on every navigation (load function re-fetches /api/me each time).
  // This is what makes /simulate work: after the redirect, the load function
  // runs with the new session and $user updates here.
  $effect(() => {
    const me = data.me;
    if (me?.email) {
      user.set(me);
      hasData.set(me.has_data ?? false);
    } else {
      user.set(null);
    }
    authReady.set(true);
  });

  // Auth redirect — only on initial page load, not on every SPA nav
  onMount(() => {
    const me = data.me;
    if (!me?.email && $page.url.pathname !== '/') {
      goto('/');
    }
  });

  $effect(() => {
    document.body.setAttribute('data-theme', $theme);
  });
</script>

<UserChip dark={darkChip} />
{@render children()}
