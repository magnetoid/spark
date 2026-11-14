/**
 * "Resume unfinished post?" — decided once, when the composer opens. The autosaved post is read
 * a single time (`offer`); later autosaves of the post being typed never bring the question back.
 */
export type ResumeChoice = "pending" | "resumed" | "discarded";

export interface ResumeState<P extends { id: number; status: string }> {
  offer: P | null; // the unfinished post found when the composer opened
  choice: ResumeChoice;
  ownId: number | null; // the hidden draft this composer is autosaving
}

export function offerResume<P extends { id: number; status: string }>(s: ResumeState<P>, editingId: number | null): boolean {
  return !!s.offer && s.choice === "pending" && s.offer.status === "draft" && s.offer.id !== editingId && s.offer.id !== s.ownId;
}

export function startFrom<P extends { id: number; status: string }, D>(s: ResumeState<P>, initial: D, fromPost: (p: P) => D): D {
  return s.choice === "resumed" && s.offer ? fromPost(s.offer) : initial;
}

export function composerKey<P extends { id: number; status: string }>(s: ResumeState<P>, initialPostId: number | null | undefined): string {
  return s.choice === "resumed" && s.offer ? `resume-${s.offer.id}` : `fresh-${initialPostId ?? "new"}`;
}
