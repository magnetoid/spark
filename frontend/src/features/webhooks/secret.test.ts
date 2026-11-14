import { describe, expect, it } from "vitest";
import { secretAfterDelete } from "./secret";

const fresh = { id: 7, url: "https://example.com/hook", secret: "whsec_x" };

describe("the signing secret shown once after a webhook is added", () => {
  it("goes away when that webhook is deleted", () => {
    expect(secretAfterDelete(fresh, 7)).toBeNull();
  });
  it("stays when another webhook is deleted", () => {
    expect(secretAfterDelete(fresh, 8)).toBe(fresh);
  });
  it("stays empty when there was none", () => {
    expect(secretAfterDelete(null, 7)).toBeNull();
  });
});
