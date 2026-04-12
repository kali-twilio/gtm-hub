import { writable } from 'svelte/store';

export interface User {
  email: string;
  is_se: boolean;
  se_name: string | null;
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
