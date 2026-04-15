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

export async function getSFPeriods(): Promise<{key: string; label: string}[]> {
  const r = await fetch('/api/se-scorecard-v2/periods');
  if (!r.ok) return [];
  return r.json();
}

function subteamParam(subteam: string) {
  return subteam && subteam !== 'none' ? `&subteam=${subteam}` : '';
}

export async function getSFSEs(team: string, period: string, icavMin = 0, subteam = '') {
  const r = await fetch(`/api/se-scorecard-v2/data/ses?team=${team}&period=${period}&icav_min=${icavMin}${subteamParam(subteam)}`);
  if (!r.ok) return null;
  return r.json();
}

export async function getSFReport(team: string, period: string, icavMin = 0, subteam = '') {
  const r = await fetch(`/api/se-scorecard-v2/data/report?team=${team}&period=${period}&icav_min=${icavMin}${subteamParam(subteam)}`);
  if (!r.ok) return null;
  return r.json();
}

export async function getSFRankings(team: string, period: string, icavMin = 0, subteam = '') {
  const r = await fetch(`/api/se-scorecard-v2/data/rankings?team=${team}&period=${period}&icav_min=${icavMin}${subteamParam(subteam)}`);
  if (!r.ok) return null;
  return r.json();
}

export function fmt(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${n}`;
}

/** MRR delta formatter — ceiling on absolute value so partial thousands round up.
 *  e.g. -16428 → -$17K/mo, not -$16K/mo. Handles negative numbers correctly. */
export function fmtMrr(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${Math.ceil(abs / 1_000)}K`;
  return `${sign}$${abs}`;
}
