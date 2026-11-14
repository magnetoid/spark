/** The address a new short link will send people to, as the server builds it: tags already in
 * the address stay, empty fields add nothing. */
export type UtmFields = { source?: string; medium?: string; campaign?: string; content?: string; term?: string };

export function withUtm(destination: string, utm: UtmFields): string | null {
  const raw = destination.trim();
  if (!raw) return null;
  let url: URL;
  try {
    url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
  } catch {
    return null;
  }
  for (const [k, v] of Object.entries(utm)) {
    const value = (v ?? "").trim();
    if (value && !url.searchParams.has(`utm_${k}`)) url.searchParams.set(`utm_${k}`, value);
  }
  return url.toString();
}

export const BACK_HALF = /^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$/;
