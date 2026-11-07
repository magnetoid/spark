/**
 * Everything the composer edits, in one place: text, per-channel versions, threads, first
 * comments, media, link, campaign, notes, and the action. Derived helpers answer "does this
 * channel's text fit" and the autosave/validate timers live here too.
 */
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { AccountOut, MediaOut, PostOut, PostWrite } from "@/features/posts/api";
import { autosavePost, validateTargets } from "@/features/posts/api";
import { insertHashtags, splitThread } from "@/features/composer/thread";

export type Action = PostWrite["action"];

export interface ComposerDraft {
  postId: number | null;
  content: string;
  link: string;
  media: MediaOut[];
  selected: number[];
  overrides: Record<number, string>;
  firstComments: Record<number, string>;
  threads: Record<number, string[]>;
  campaignId: number | null;
  notes: string;
  action: Action;
  scheduledAt: string; // datetime-local value in the brand's zone
  source: string;
  ideaId: number | null;
}

type Patch = Partial<ComposerDraft> | ((d: ComposerDraft) => Partial<ComposerDraft>);

export const emptyDraft = (over: Partial<ComposerDraft> = {}): ComposerDraft => ({
  postId: null, content: "", link: "", media: [], selected: [], overrides: {}, firstComments: {}, threads: {},
  campaignId: null, notes: "", action: "queue", scheduledAt: "", source: "manual", ideaId: null, ...over,
});

export function draftFromPost(post: PostOut, media: MediaOut[], toLocal: (iso: string | null) => string, asCopy = false): ComposerDraft {
  const overrides: Record<number, string> = {}, firstComments: Record<number, string> = {}, threads: Record<number, string[]> = {};
  for (const t of post.targets) {
    if (t.content_override) overrides[t.account_id] = t.content_override;
    if (t.first_comment) firstComments[t.account_id] = t.first_comment;
    if (t.thread?.length) threads[t.account_id] = t.thread;
  }
  const scheduled = !asCopy && ["scheduled", "pending_approval"].includes(post.status);
  return emptyDraft({
    postId: asCopy ? null : post.id, content: post.content, link: post.link ?? "", media,
    selected: post.targets.map((t) => t.account_id), overrides, firstComments, threads,
    campaignId: post.campaign_id, notes: asCopy ? "" : post.notes ?? "", source: asCopy ? "manual" : post.source,
    action: scheduled ? "schedule" : "queue", scheduledAt: scheduled ? toLocal(post.scheduled_at) : "",
  });
}

export function useComposerState(initial: ComposerDraft, brandId: number, accounts: AccountOut[], autosave: boolean) {
  const [draft, dispatch] = useReducer((d: ComposerDraft, patch: Patch) => ({ ...d, ...(typeof patch === "function" ? patch(d) : patch) }), initial);
  const [serverProblems, setProblems] = useState<Record<string, string[]>>({});
  const problems = draft.selected.length ? serverProblems : {};
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const byId = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);
  const set = useCallback((patch: Patch) => dispatch(patch), []);

  const textFor = useCallback((id: number) => draft.overrides[id] || draft.content, [draft]);
  const limit = useCallback((id: number) => byId.get(id)?.capabilities.max ?? Infinity, [byId]);
  const over = useCallback((id: number) => textFor(id).length > limit(id), [textFor, limit]);
  const threadOver = useCallback((id: number) => (draft.threads[id] ?? []).some((t) => t.length > limit(id)), [draft.threads, limit]);
  const hasProblems = draft.selected.some((id) => over(id) || threadOver(id) || (problems[String(id)] ?? []).length > 0);

  // live validation on the server (media rules, required media, video limits…), debounced
  const validateTimer = useRef<number | null>(null);
  useEffect(() => {
    if (validateTimer.current) window.clearTimeout(validateTimer.current);
    if (!draft.selected.length) return;
    validateTimer.current = window.setTimeout(() => {
      const targets = Object.fromEntries(draft.selected.map((id) => [String(id), textFor(id)]));
      validateTargets(brandId, targets, draft.media.map((m) => m.id), draft.link || null).then(setProblems).catch(() => { /* offline: keep client checks */ });
    }, 300);
    return () => { if (validateTimer.current) window.clearTimeout(validateTimer.current); };
  }, [brandId, draft.selected, draft.content, draft.overrides, draft.media, draft.link, textFor]);

  // autosave: keep an unfinished post as a hidden draft, two seconds after the last change
  const autosaveTimer = useRef<number | null>(null);
  const skipFirst = useRef(true);
  useEffect(() => {
    if (!autosave) return;
    if (skipFirst.current) { skipFirst.current = false; return; }
    if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current);
    autosaveTimer.current = window.setTimeout(async () => {
      if (!draft.content.trim() && !draft.media.length) return;
      try {
        const r = await autosavePost(brandId, {
          post_id: draft.postId, content: draft.content, link: draft.link || null, media_ids: draft.media.map((m) => m.id),
          source: draft.source, targets: draft.selected.map((id) => ({
            account_id: id, override: draft.overrides[id] || null, first_comment: draft.firstComments[id] || null, thread: draft.threads[id] ?? [],
          })),
        });
        if (r.post_id && r.post_id !== draft.postId) dispatch({ postId: r.post_id });
        setSavedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      } catch { /* offline: try again on the next change */ }
    }, 2000);
    return () => { if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autosave, brandId, draft.content, draft.link, draft.media, draft.selected, draft.overrides, draft.firstComments, draft.threads]);

  const toggle = (id: number) => set((d) => ({ selected: d.selected.includes(id) ? d.selected.filter((x) => x !== id) : [...d.selected, id] }));
  const setOverride = (id: number, text: string) => set((d) => ({ overrides: { ...d.overrides, [id]: text } }));
  const setFirstComment = (id: number, text: string) => set((d) => ({ firstComments: { ...d.firstComments, [id]: text } }));
  const setThread = (id: number, items: string[]) => set((d) => ({ threads: { ...d.threads, [id]: items } }));
  const split = (id: number) => {
    const parts = splitThread(draft.overrides[id] || draft.content, limit(id));
    if (!parts.length) return;
    set((d) => ({ overrides: { ...d.overrides, [id]: parts[0] }, threads: { ...d.threads, [id]: parts.slice(1) } }));
  };
  const addMedia = (items: MediaOut[]) => set((d) => ({ media: [...d.media, ...items.filter((m) => !d.media.some((x) => x.id === m.id))] }));
  const removeMedia = (id: number) => set((d) => ({ media: d.media.filter((m) => m.id !== id) }));
  const moveMedia = (from: number, to: number) => set((d) => { const m = [...d.media]; const [it] = m.splice(from, 1); m.splice(to, 0, it); return { media: m }; });
  const useTemplate = (body: string) => set({ content: body });
  const addHashtags = (tags: string[]) => set((d) => ({ content: insertHashtags(d.content, tags) }));

  const toWrite = (localToIso: (v: string) => string | null): PostWrite => ({
    content: draft.content, link: draft.link || null, media_ids: draft.media.map((m) => m.id), campaign_id: draft.campaignId,
    notes: draft.notes || null, source: draft.source, action: draft.action, idea_id: draft.ideaId,
    scheduled_at: draft.action === "schedule" && draft.scheduledAt ? localToIso(draft.scheduledAt) : null,
    targets: draft.selected.map((id) => ({
      account_id: id, override: draft.overrides[id] || null, first_comment: draft.firstComments[id] || null, thread: draft.threads[id] ?? [],
    })),
  });

  return { draft, set, problems, savedAt, byId, textFor, limit, over, threadOver, hasProblems, toggle, setOverride,
           setFirstComment, setThread, split, addMedia, removeMedia, moveMedia, useTemplate, addHashtags, toWrite };
}

export type ComposerState = ReturnType<typeof useComposerState>;
