<script lang="ts">
  import { user } from '$lib/stores';
  import { page } from '$app/stores';

  let open = $state(false);

  // Hide on the launcher (app selector) page
  const visible = $derived($user?.email && $page.url.pathname !== '/');
</script>

{#if visible}
<div class="chip-wrap"
  onmouseenter={() => open = true}
  onmouseleave={() => open = false}
  role="status"
>
  <div class="chip">
    <span class="avatar">{($user!.sf_display_name ?? $user!.email)[0].toUpperCase()}</span>
    <span class="name">{$user!.sf_display_name ?? $user!.email}</span>
    <span class="caret">▾</span>
  </div>

  {#if open}
  <div class="tooltip" role="tooltip">
    <div class="t-header">
      <div class="t-avatar">{($user!.sf_display_name ?? $user!.email)[0].toUpperCase()}</div>
      <div>
        {#if $user!.sf_display_name}
        <div class="t-name">{$user!.sf_display_name}</div>
        {/if}
        <div class="t-email">{$user!.email}</div>
      </div>
    </div>

    <div class="t-rows">
      {#if $user!.sf_title}
      <div class="t-row">
        <span class="t-label">Title</span>
        <span class="t-val">{$user!.sf_title}</span>
      </div>
      {/if}
      {#if $user!.sf_department}
      <div class="t-row">
        <span class="t-label">Department</span>
        <span class="t-val">{$user!.sf_department}</span>
      </div>
      {/if}
      {#if $user!.sf_division}
      <div class="t-row">
        <span class="t-label">Division</span>
        <span class="t-val">{$user!.sf_division}</span>
      </div>
      {/if}
      {#if $user!.sf_role_name}
      <div class="t-row">
        <span class="t-label">Role</span>
        <span class="t-val">{$user!.sf_role_name}</span>
      </div>
      {/if}
      {#if $user!.sf_manager}
      <div class="t-row">
        <span class="t-label">Manager</span>
        <span class="t-val">{$user!.sf_manager}</span>
      </div>
      {/if}
      {#if $user!.sf_phone}
      <div class="t-row">
        <span class="t-label">Phone</span>
        <span class="t-val">{$user!.sf_phone}</span>
      </div>
      {/if}
    </div>

    <a href="/logout" class="t-signout">Sign out</a>
  </div>
  {/if}
</div>
{/if}

<style>
.chip-wrap {
  position: fixed;
  top: 12px;
  right: 16px;
  z-index: 500;
  user-select: none;
}

.chip {
  display: flex;
  align-items: center;
  gap: 7px;
  background: white;
  border: 1px solid rgba(13,18,43,0.12);
  border-radius: 999px;
  padding: 5px 10px 5px 6px;
  cursor: default;
  box-shadow: 0 1px 4px rgba(13,18,43,0.08);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.chip-wrap:hover .chip {
  border-color: rgba(242,47,70,0.4);
  box-shadow: 0 2px 8px rgba(13,18,43,0.12);
}

.avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #F22F46;
  color: white;
  font-size: 11px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.name {
  font-size: 12px;
  font-weight: 600;
  color: rgba(13,18,43,0.75);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.caret {
  font-size: 10px;
  color: rgba(13,18,43,0.35);
  transition: transform 0.15s;
}
.chip-wrap:hover .caret {
  transform: rotate(180deg);
  color: #F22F46;
}

.tooltip {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 268px;
  background: white;
  border: 1px solid rgba(13,18,43,0.1);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(13,18,43,0.12);
  overflow: hidden;
}

.t-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 14px 12px;
  background: rgba(242,47,70,0.04);
  border-bottom: 1px solid rgba(13,18,43,0.07);
}

.t-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #F22F46;
  color: white;
  font-size: 15px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.t-name {
  font-size: 13px;
  font-weight: 700;
  color: rgba(13,18,43,0.85);
  line-height: 1.3;
}

.t-email {
  font-size: 11px;
  color: rgba(13,18,43,0.45);
  font-weight: 500;
  margin-top: 1px;
}

.t-rows {
  padding: 6px 0;
}

.t-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  padding: 5px 14px;
}

.t-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: rgba(13,18,43,0.35);
  flex-shrink: 0;
}

.t-val {
  font-size: 12px;
  font-weight: 600;
  color: rgba(13,18,43,0.7);
  text-align: right;
}

.t-signout {
  display: block;
  text-align: center;
  padding: 9px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #F22F46;
  text-decoration: none;
  border-top: 1px solid rgba(13,18,43,0.07);
  transition: background 0.15s;
}
.t-signout:hover {
  background: rgba(242,47,70,0.06);
}
</style>
