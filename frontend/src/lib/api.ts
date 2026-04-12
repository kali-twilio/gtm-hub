export interface AppManifest {
  id: string;
  name: string;
  description: string;
  icon: string;
  path: string;
  status: 'live' | 'coming_soon';
}

export async function getApps(): Promise<AppManifest[]> {
  const r = await fetch('/api/apps');
  if (!r.ok) return [];
  return r.json();
}

export async function getMe() {
  const r = await fetch('/api/me');
  if (!r.ok) return null;
  return r.json();
}

export async function getSEs() {
  const r = await fetch('/api/data/ses');
  if (!r.ok) return null;
  return r.json();
}

export async function getReport() {
  const r = await fetch('/api/data/report');
  if (!r.ok) return null;
  return r.json();
}

export async function getRankings() {
  const r = await fetch('/api/data/rankings');
  if (!r.ok) return null;
  return r.json();
}

export function fmt(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${n}`;
}
