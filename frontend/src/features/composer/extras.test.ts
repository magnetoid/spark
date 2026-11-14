import { describe, expect, it } from "vitest";
import { aiLabel, cleanExtras, hasExtras, noExtras, parsePeople, pollRules } from "@/features/composer/extras";
import type { MediaOut } from "@/features/posts/api";

const media = (source: string) => ({ id: 1, source }) as MediaOut;

describe("parsePeople", () => {
  it("reads usernames separated by commas or spaces, without the @", () => {
    expect(parsePeople("@friend,  other\n@third")).toEqual(["friend", "other", "third"]);
  });
  it("drops blanks and repeats", () => {
    expect(parsePeople(" , @a, a ,, ")).toEqual(["a"]);
  });
});

describe("aiLabel", () => {
  it("follows the media when nobody chose", () => {
    expect(aiLabel(noExtras, [media("generated")])).toBe(true);
    expect(aiLabel(noExtras, [media("upload")])).toBe(false);
  });
  it("keeps an explicit choice over the media", () => {
    expect(aiLabel({ ...noExtras, ai_generated: false }, [media("generated")])).toBe(false);
    expect(aiLabel({ ...noExtras, ai_generated: true }, [])).toBe(true);
  });
});

describe("pollRules", () => {
  it("gives LinkedIn a question, longer options and two weeks", () => {
    expect(pollRules("linkedin")).toEqual({ days: [1, 3, 7, 14], optionChars: 30, questionChars: 140 });
  });
  it("gives every other network X's rules", () => {
    expect(pollRules("x")).toEqual({ days: [1, 3, 7], optionChars: 25, questionChars: 0 });
  });
});

describe("hasExtras and cleanExtras", () => {
  it("knows an untouched channel from one with something set", () => {
    expect(hasExtras(noExtras)).toBe(false);
    expect(hasExtras(undefined)).toBe(false);
    expect(hasExtras({ ...noExtras, ai_generated: false })).toBe(true);
    expect(hasExtras({ ...noExtras, poll: { question: "", options: ["", ""], days: 3 } })).toBe(true);
  });
  it("fills in what a saved post leaves out", () => {
    expect(cleanExtras({ paid_partnership: true })).toEqual({ ...noExtras, paid_partnership: true });
    expect(cleanExtras(undefined)).toEqual(noExtras);
  });
});
