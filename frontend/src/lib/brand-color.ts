/**
 * Turn a brand's hex colour into the workspace accent.
 *
 * The brand colour is used as-is for identity (dots, rails), but as a *working* accent it
 * must stay legible on both themes: filled buttons need a readable label, and pale or
 * near-black brand colours would otherwise vanish. So the accent is the brand colour with
 * its lightness and chroma clamped in OKLCH, the label colour is whichever of black or
 * white contrasts more, and the soft tint is the same hue washed out for selections.
 */
import { formatHex, oklch, parse, wcagContrast } from "culori";

export interface BrandPalette {
  brand: string;
  fg: string;
  soft: string;
  ring: string;
}

const INK = "#171a21";
const WHITE = "#ffffff";

export function brandPalette(hex: string, theme: "light" | "dark"): BrandPalette {
  const parsed = parse(hex) ?? parse("#f2a516")!;
  const c = oklch(parsed);
  const l = c.l ?? 0.6;
  const chroma = c.c ?? 0;
  const h = c.h ?? 0;
  const light = theme === "light";
  // Filled buttons and selected states: mid lightness so a label can sit on it.
  const accentL = clamp(l, light ? 0.45 : 0.62, light ? 0.72 : 0.84);
  const accentC = clamp(chroma, 0, light ? 0.2 : 0.17);
  const brand = formatHex({ mode: "oklch", l: accentL, c: accentC, h });
  const fg = wcagContrast(brand, INK) >= wcagContrast(brand, WHITE) ? INK : WHITE;
  const soft = formatHex({ mode: "oklch", l: light ? 0.95 : 0.3, c: clamp(chroma * 0.35, 0, 0.06), h });
  const ring = formatHex({ mode: "oklch", l: light ? 0.6 : 0.72, c: clamp(chroma, 0.04, 0.2), h });
  return { brand, fg, soft, ring };
}

export function applyBrandColor(hex: string, root: HTMLElement = document.documentElement) {
  const theme = root.classList.contains("dark") ? "dark" : "light";
  const p = brandPalette(hex, theme);
  root.style.setProperty("--brand", p.brand);
  root.style.setProperty("--brand-fg", p.fg);
  root.style.setProperty("--brand-soft", p.soft);
  root.style.setProperty("--brand-ring", p.ring);
}

function clamp(v: number, min: number, max: number) {
  return Math.min(max, Math.max(min, v));
}
