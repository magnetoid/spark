import { wcagContrast } from "culori";
import { describe, expect, it } from "vitest";
import { brandPalette } from "./brand-color";

const extremes = ["#ffffff", "#000000", "#ffff00", "#0b0b3b", "#f2a516", "#2f6fed", "#d13b3b", "#e5e7eb", "#1f8f5f"];

describe("brandPalette", () => {
  it("keeps the label readable on the accent for any brand colour, both themes", () => {
    for (const hex of extremes) {
      for (const theme of ["light", "dark"] as const) {
        const p = brandPalette(hex, theme);
        expect(wcagContrast(p.brand, p.fg), `${hex} ${theme}`).toBeGreaterThanOrEqual(3.5);
      }
    }
  });

  it("keeps the soft tint distinguishable from the surface", () => {
    expect(wcagContrast(brandPalette("#f2a516", "light").soft, "#ffffff")).toBeGreaterThan(1.02);
    expect(wcagContrast(brandPalette("#f2a516", "dark").soft, "#1e2128")).toBeGreaterThan(1.1);
  });

  it("falls back to Spark amber for garbage input", () => {
    expect(brandPalette("nope", "light").brand).toBe(brandPalette("#f2a516", "light").brand);
  });
});
