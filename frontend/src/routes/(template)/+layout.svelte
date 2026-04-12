<!--
  Template layout for a new app.
  Each app gets its own layout — put your chrome, nav, theme here.
  Delete this file entirely if you don't need a custom layout.
  The root layout already handles auth; users here are guaranteed logged in.
-->
<script lang="ts">
  let { children } = $props();
</script>

{@render children()}
