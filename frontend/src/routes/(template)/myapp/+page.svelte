<!--
  Template page — rename (template) to (myapp) and myapp/ to your app name.
  Auth is guaranteed by the root layout. Use /api/myapp/* for your backend calls.
-->
<script lang="ts">
  import { user } from '$lib/stores';
</script>

<div style="padding: 40px; font-family: sans-serif;">
  <h1>My App</h1>
  <p>Logged in as {$user?.email}</p>
</div>
