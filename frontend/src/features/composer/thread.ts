/**
 * "Split into thread": paragraphs first, then sentences, then hard wraps, each part within
 * the limit minus room for a " (n/m)" counter; short neighbours are merged so items are
 * not tiny. Returns [] when the text already fits.
 */
export function splitThread(source: string, maxChars: number): string[] {
  const max = Math.max(40, maxChars - 8);
  const text = source.trim();
  if (text.length <= maxChars) return [];
  const parts: string[] = [];
  const push = (s: string) => { s = s.trim(); if (s) parts.push(s); };
  for (const para of text.split(/\n{2,}/)) {
    if (para.length <= max) { push(para); continue; }
    let buf = "";
    for (const sent of para.split(/(?<=[.!?])\s+/)) {
      if ((buf + " " + sent).trim().length <= max) { buf = (buf + " " + sent).trim(); continue; }
      push(buf); buf = "";
      if (sent.length <= max) { buf = sent; continue; }
      for (let i = 0; i < sent.length; i += max) push(sent.slice(i, i + max));
    }
    push(buf);
  }
  const merged: string[] = [];
  for (const p of parts) {
    const last = merged[merged.length - 1];
    if (last !== undefined && (last + "\n\n" + p).length <= max) merged[merged.length - 1] = last + "\n\n" + p;
    else merged.push(p);
  }
  if (merged.length < 2) return [];
  const n = merged.length;
  return merged.map((p, i) => `${p} (${i + 1}/${n})`);
}

export function insertHashtags(content: string, tags: string[]): string {
  const missing = tags.filter((tag) => !new RegExp(`(^|\\s)#${escapeRe(tag)}(\\s|$)`, "i").test(content));
  if (!missing.length) return content;
  return (content.trimEnd() + "\n\n" + missing.map((t) => `#${t}`).join(" ")).trim();
}

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
