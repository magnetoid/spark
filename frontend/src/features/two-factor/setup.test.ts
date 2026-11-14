import { describe, expect, it } from "vitest";
import { groupSecret } from "./setup";

describe("groupSecret", () => {
  it("splits the key into groups of four for typing by hand", () => {
    expect(groupSecret("GEZDGNBVGY3TQOJQ")).toBe("GEZD GNBV GY3T QOJQ");
  });
  it("leaves no trailing space", () => {
    expect(groupSecret("ABCDEFGH")).toBe("ABCD EFGH");
    expect(groupSecret("ABCDEF")).toBe("ABCD EF");
  });
});
