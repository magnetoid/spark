import { describe, expect, it } from "vitest";
import { BACK_HALF, withUtm } from "./utm";

describe("withUtm", () => {
  it("adds https and the filled tags", () => {
    expect(withUtm("shop.example.com/a", { source: "newsletter", medium: "", campaign: "autumn" }))
      .toBe("https://shop.example.com/a?utm_source=newsletter&utm_campaign=autumn");
  });
  it("keeps tags the address already has", () => {
    expect(withUtm("https://x.example/?utm_source=bio", { source: "email" })).toBe("https://x.example/?utm_source=bio");
  });
  it("answers null for an empty or broken address", () => {
    expect(withUtm("  ", {})).toBeNull();
    expect(withUtm("http://", {})).toBeNull();
  });
});

describe("BACK_HALF", () => {
  it("accepts letters, digits, dashes and underscores", () => {
    expect(BACK_HALF.test("autumn-sale")).toBe(true);
    expect(BACK_HALF.test("bad code")).toBe(false);
    expect(BACK_HALF.test("-x")).toBe(false);
  });
});
