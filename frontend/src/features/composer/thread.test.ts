import { describe, expect, it } from "vitest";
import { insertHashtags, splitThread } from "./thread";

describe("splitThread", () => {
  it("returns nothing when the text fits", () => {
    expect(splitThread("short", 280)).toEqual([]);
  });
  it("splits long text into numbered parts within the limit", () => {
    const text = Array.from({ length: 12 }, (_, i) => `Sentence number ${i + 1} is here and it is reasonably long.`).join(" ");
    const parts = splitThread(text, 140);
    expect(parts.length).toBeGreaterThan(2);
    for (const p of parts) expect(p.length).toBeLessThanOrEqual(140);
    expect(parts[0]).toMatch(/\(1\/\d+\)$/);
    expect(parts.at(-1)).toMatch(new RegExp(`\\(${parts.length}/${parts.length}\\)$`));
  });
});

describe("insertHashtags", () => {
  it("adds only the tags that are missing", () => {
    expect(insertHashtags("Hello #spark", ["spark", "launch"])).toBe("Hello #spark\n\n#launch");
    expect(insertHashtags("Hello #spark #launch", ["spark", "launch"])).toBe("Hello #spark #launch");
  });
});
