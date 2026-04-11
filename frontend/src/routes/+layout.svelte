<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { user, hasData } from '$lib/stores';
  import { getMe } from '$lib/api';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';

  let { children } = $props();

  onMount(async () => {
    const me = await getMe();
    if (me?.email) {
      user.set(me);
      hasData.set(me.has_data);
      if (me.is_se && $page.url.pathname !== '/me') {
        goto('/me');
      }
    } else if ($page.url.pathname !== '/') {
      goto('/');
    }
  });
</script>

<!-- Fixed P5 chrome -->
<div style="position:fixed;top:0;left:0;right:0;height:4px;background:var(--red);z-index:100;box-shadow:0 0 12px var(--red)"></div>
<div style="position:fixed;bottom:0;left:0;right:0;height:4px;background:var(--red);z-index:100;box-shadow:0 0 12px var(--red)"></div>
<div style="position:fixed;top:16px;left:16px;width:22px;height:22px;border-top:3px solid var(--red);border-left:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;top:16px;right:16px;width:22px;height:22px;border-top:3px solid var(--red);border-right:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:16px;left:16px;width:22px;height:22px;border-bottom:3px solid var(--red);border-left:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:16px;right:16px;width:22px;height:22px;border-bottom:3px solid var(--red);border-right:3px solid var(--red);z-index:99;pointer-events:none"></div>
<div style="position:fixed;bottom:-30px;right:-10px;font-size:280px;font-weight:900;font-style:italic;color:rgba(232,0,61,0.04);line-height:1;pointer-events:none;user-select:none;transform:skewX(-5deg);z-index:0">5</div>

{@render children()}
