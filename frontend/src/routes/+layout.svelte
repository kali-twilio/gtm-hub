<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { user, hasData, authReady, theme } from '$lib/stores';
  import { getMe } from '$lib/api';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import UserChip from '$lib/UserChip.svelte';

  let { children } = $props();

  onMount(async () => {
    const me = await getMe();
    if (me?.email) {
      user.set(me);
      hasData.set(me.has_data);
      const allowedForSE = ['/', '/me'];
      if (me.is_se && !allowedForSE.includes($page.url.pathname)) {
        goto('/me');
      }
    } else if ($page.url.pathname !== '/') {
      goto('/');
    }
    authReady.set(true);
  });

  $effect(() => {
    document.body.setAttribute('data-theme', $theme);
  });
</script>

<UserChip />
{@render children()}
