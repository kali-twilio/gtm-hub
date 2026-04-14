export const prerender = false;
export const ssr = false;

export async function load({ fetch }) {
  const r = await fetch('/api/me');
  const me = r.ok ? await r.json() : null;
  return { me };
}
