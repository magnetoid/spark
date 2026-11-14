/**
 * Extras only some networks carry: the AI label, the paid partnership label, collaborators
 * and a poll. The channel says which ones it takes (`capabilities.options`); the server keeps
 * only those and checks them, so these helpers stay small.
 */
import type { components } from "@/api/schema";
import type { MediaOut } from "@/features/posts/api";

export type Extras = components["schemas"]["TargetOptions"];
export type Poll = components["schemas"]["PollIn"];

export const noExtras: Extras = { ai_generated: null, paid_partnership: false, collaborators: [], poll: null };

export const cleanExtras = (o: Partial<Extras> | undefined | null): Extras => ({
  ai_generated: o?.ai_generated ?? null, paid_partnership: Boolean(o?.paid_partnership),
  collaborators: o?.collaborators ?? [], poll: o?.poll ?? null,
});

export const hasExtras = (o: Partial<Extras> | undefined | null): boolean =>
  Boolean(o && (o.ai_generated != null || o.paid_partnership || o.collaborators?.length || o.poll));

/** "@friend, other" → ["friend", "other"] */
export function parsePeople(text: string): string[] {
  const names = text.split(/[\s,]+/).map((n) => n.replace(/^@+/, "").trim()).filter(Boolean);
  return [...new Set(names)];
}

/** Unset means: label the post when any of its media came from the image model. */
export const aiLabel = (o: Extras | undefined, media: MediaOut[]): boolean =>
  o?.ai_generated ?? media.some((m) => m.source === "generated");

export function pollRules(platform: string): { days: number[]; optionChars: number; questionChars: number } {
  return platform === "linkedin"
    ? { days: [1, 3, 7, 14], optionChars: 30, questionChars: 140 }
    : { days: [1, 3, 7], optionChars: 25, questionChars: 0 };
}
