import { writable } from 'svelte/store';

export interface User {
  email: string;
  sf_access:       'full' | 'se_restricted';
  sf_role_name:    string | null;
  sf_display_name: string | null;
  sf_title:        string | null;
  sf_is_se:        boolean;
  sf_se_name:      string | null;
  sf_team:         string | null;
}

export const user = writable<User | null>(null);
export const hasData = writable<boolean>(false);
export const authReady = writable<boolean>(false);

type Theme = 'p5' | 'twilio';

function createThemeStore() {
  const stored = typeof localStorage !== 'undefined' ? (localStorage.getItem('theme') as Theme) : null;
  const { subscribe, set } = writable<Theme>(stored ?? 'p5');
  return {
    subscribe,
    set(v: Theme) {
      if (typeof localStorage !== 'undefined') localStorage.setItem('theme', v);
      set(v);
    },
    toggle() {
      const current = typeof localStorage !== 'undefined' ? (localStorage.getItem('theme') as Theme) : 'p5';
      this.set(current === 'p5' ? 'twilio' : 'p5');
    }
  };
}

export const theme = createThemeStore();

// Persists the selected SE Scorecard V2 team across page navigations
function createSFTeamStore() {
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('sf_team') : null;
  const { subscribe, set } = writable<string>(stored ?? 'digital_sales');
  return {
    subscribe,
    set(v: string) {
      if (typeof localStorage !== 'undefined') localStorage.setItem('sf_team', v);
      set(v);
    }
  };
}

export const sfTeam = createSFTeamStore();

function createPersistedStore(key: string, fallback: string) {
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null;
  const { subscribe, set } = writable<string>(stored ?? fallback);
  return {
    subscribe,
    set(v: string) {
      if (typeof localStorage !== 'undefined') localStorage.setItem(key, v);
      set(v);
    }
  };
}

export const sfPeriod  = createPersistedStore('sf_period',  '2026_Q1');
export const sfSubteam = createPersistedStore('sf_subteam', 'none');
