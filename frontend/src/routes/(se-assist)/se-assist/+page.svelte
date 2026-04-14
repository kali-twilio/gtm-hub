<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  onMount(() => goto('/se-assist/emails', { replaceState: true }));
</script>
