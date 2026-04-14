<script lang="ts">
  import { user } from '$lib/stores';
  let open = $state(false);
</script>

{#if $user?.email}
<div class="chip-wrap"
  onmouseenter={() => open = true}
  onmouseleave={() => open = false}
  role="status"
>
  <div class="chip">
    <span class="avatar">{($user.sf_display_name ?? $user.email)[0].toUpperCase()}</span>
    <span class="name">{$user.sf_display_name ?? $user.email}</span>
    <span class="caret">▾</span>
  </div>

  {#if open}
  <div class="tooltip" role="tooltip">
    <!-- Header -->
    <div class="t-header">
      <div class="t-avatar">{($user.sf_display_name ?? $user.email)[0].toUpperCase()}</div>
      <div>
        {#if $user.sf_display_name}
        <div class="t-name">{$user.sf_display_name}</div>
        {/if}
        <div class="t-email">{$user.email}</div>
      </div>
    </div>

    <!-- SF Profile rows -->
    <div class="t-rows">
      {#if $user.sf_title}
      <div class="t-row">
        <span class="t-label">Title</span>
        <span class="t-val">{$user.sf_title}</span>
      </div>
      {/if}
      {#if $user.sf_role_name}
      <div class="t-row">
        <span class="t-label">Role</span>
        <span class="t-val">{$user.sf_role_name}</span>
      </div>
      {/if}
      {#if $user.sf_team}
      <div class="t-row">
        <span class="t-label">Team</span>
        <span class="t-val">{$user.sf_team}</span>
      </div>
      {/if}
      <div class="t-row">
        <span class="t-label">Access</span>
        <span class="t-val {$user.sf_access === 'se_restricted' ? 'restricted' : 'full'}">
          {$user.sf_access === 'se_restricted' ? 'SE (restricted)' : 'Full'}
        </span>
      </div>
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

/* Tooltip */
.tooltip {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 260px;
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
  padding: 8px 0;
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
.t-val.full  { color: #0aab6b; }
.t-val.restricted { color: #F22F46; }

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
