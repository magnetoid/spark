import { describe, expect, it } from "vitest";
import { afterSignInError } from "./sign-in";

describe("afterSignInError", () => {
  it("moves on to the code step without an error when the account has two-factor", () => {
    expect(afterSignInError(401, "two_factor_required", "")).toEqual({ step: "code", error: null });
  });
  it("stays on the code step when the code is wrong", () => {
    const r = afterSignInError(401, "invalid_code", "");
    expect(r.step).toBe("code");
    expect(r.error).toMatch(/code didn't work/);
  });
  it("shows the server's wait time after too many wrong codes", () => {
    expect(afterSignInError(429, "too_many_attempts", "Too many wrong codes. Wait 15 minutes and try again."))
      .toEqual({ step: "code", error: "Too many wrong codes. Wait 15 minutes and try again." });
  });
  it("goes back to the password step when the password is wrong", () => {
    expect(afterSignInError(401, "invalid_credentials", "")).toEqual({ step: "password", error: "That email and password don't match." });
  });
  it("says to wait when sign-in is rate limited, keeping the step", () => {
    const r = afterSignInError(429, "rate_limited", "");
    expect(r.step).toBeUndefined();
    expect(r.error).toMatch(/Wait a minute/);
  });
  it("falls back to a plain message for anything else", () => {
    expect(afterSignInError(500, "error", "")).toEqual({ error: "Could not sign in. Try again." });
  });
});
