import { writable } from 'svelte/store';

export interface User {
  email: string;
  is_se: boolean;
  se_name: string | null;
}

export const user = writable<User | null>(null);
export const hasData = writable<boolean>(false);
