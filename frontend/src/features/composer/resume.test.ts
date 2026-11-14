import { describe, expect, it } from "vitest";
import { composerKey, offerResume, startFrom, type ResumeState } from "./resume";

const post = (id: number, status = "draft") => ({ id, status }) as { id: number; status: string };
const state = (over: Partial<ResumeState<{ id: number; status: string }>> = {}): ResumeState<{ id: number; status: string }> => ({
  offer: post(7), choice: "pending", ownId: null, ...over,
});

describe("offerResume", () => {
  it("offers the unfinished post found when the composer opened", () => {
    expect(offerResume(state(), null)).toBe(true);
  });
  it("never offers the post this composer is autosaving itself", () => {
    expect(offerResume(state({ ownId: 7 }), null)).toBe(false);
  });
  it("never offers the post being edited", () => {
    expect(offerResume(state(), 7)).toBe(false);
  });
  it("stops offering once resumed or discarded", () => {
    expect(offerResume(state({ choice: "resumed" }), null)).toBe(false);
    expect(offerResume(state({ choice: "discarded" }), null)).toBe(false);
  });
  it("offers nothing when there was nothing, or it is no longer a draft", () => {
    expect(offerResume(state({ offer: null }), null)).toBe(false);
    expect(offerResume(state({ offer: post(7, "scheduled") }), null)).toBe(false);
  });
});

describe("startFrom", () => {
  const fresh = { name: "fresh" };
  const from = (p: { id: number }) => ({ name: `resumed-${p.id}` });
  it("keeps the fresh draft unless the person pressed Resume", () => {
    expect(startFrom(state(), fresh, from)).toBe(fresh);
    expect(startFrom(state({ choice: "discarded" }), fresh, from)).toBe(fresh);
    expect(startFrom(state({ choice: "resumed" }), fresh, from)).toEqual({ name: "resumed-7" });
  });
  it("changes the composer key only when resuming, so typing is never thrown away", () => {
    expect(composerKey(state(), null)).toBe("fresh-new");
    expect(composerKey(state({ choice: "discarded" }), null)).toBe("fresh-new");
    expect(composerKey(state({ choice: "resumed" }), null)).toBe("resume-7");
  });
});
