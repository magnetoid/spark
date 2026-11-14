/**
 * Open the composer from anywhere: `useComposer().open({...})`. The host renders the dialog
 * (full-screen sheet on phones), loads an existing post or a copy of one, and offers to
 * resume an unfinished draft when opened empty.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useBrand } from "@/app/session";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, unwrap } from "@/lib/api";
import { toLocalInput } from "@/lib/time";
import { fetchAutosave, keys, usePostActions, type IdeaOut, type MediaOut, type PostOut } from "@/features/posts/api";
import { Composer } from "@/features/composer/composer";
import { draftFromPost, emptyDraft, type Action, type ComposerDraft } from "@/features/composer/use-composer-state";
import { composerKey, offerResume, startFrom, type ResumeChoice } from "@/features/composer/resume";

export interface OpenOptions {
  postId?: number;
  fromPostId?: number;
  idea?: IdeaOut;
  account?: number;
  at?: string; // datetime-local in the brand's zone
  onSaved?: (post: PostOut, action: Action) => void;
}

interface ComposerApi { open: (o?: OpenOptions) => void; close: () => void }
const Ctx = createContext<ComposerApi | null>(null);

export function useComposer(): ComposerApi {
  const v = useContext(Ctx);
  if (!v) throw new Error("useComposer outside ComposerHost");
  return v;
}

export function ComposerHost({ children }: { children: ReactNode }) {
  const [opts, setOpts] = useState<OpenOptions | null>(null);
  const open = useCallback((o: OpenOptions = {}) => setOpts(o), []);
  const close = useCallback(() => setOpts(null), []);
  const value = useMemo(() => ({ open, close }), [open, close]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.key === "c" && !e.metaKey && !e.ctrlKey && !e.altKey && !opts && !(t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) && !t?.isContentEditable) {
        e.preventDefault(); open();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, opts]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <Dialog open={opts !== null} onOpenChange={(o) => { if (!o) close(); }}>
        <DialogContent className="max-h-dvh overflow-y-auto p-0 sm:max-h-[92vh] sm:max-w-5xl sm:rounded-overlay" showCloseButton>
          <DialogTitle className="sr-only">Compose a post</DialogTitle>
          {opts && <ComposerLoader opts={opts} onDone={close} />}
        </DialogContent>
      </Dialog>
    </Ctx.Provider>
  );
}

/** Loads whatever the composer starts from, then renders it. */
export function ComposerLoader({ opts, onDone, compact = true }: { opts: OpenOptions; onDone: () => void; compact?: boolean }) {
  const brand = useBrand();
  const actions = usePostActions(brand.id);
  const sourceId = opts.postId ?? opts.fromPostId ?? null;
  const { data: post, isPending: loadingPost } = useQuery({
    queryKey: keys.post(brand.id, sourceId ?? 0),
    queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/posts/{post_id}", { params: { path: { brand_id: brand.id, post_id: sourceId! } } })),
    enabled: sourceId !== null,
  });
  const mediaIds = post?.media_ids ?? opts.idea?.media_ids ?? [];
  const { data: library, isPending: loadingMedia } = useQuery({
    queryKey: keys.media(brand.id),
    queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/media", { params: { path: { brand_id: brand.id } } })),
    enabled: mediaIds.length > 0,
  });
  const wantsResume = !sourceId && !opts.idea && !opts.at && !opts.account;
  // Read once, when the composer opens: the post typed here is autosaved too, and must never
  // come back as "unfinished" while it is being written.
  const [offer, setOffer] = useState<PostOut | null>(null);
  const [choice, setChoice] = useState<ResumeChoice>("pending");
  const [ownId, setOwnId] = useState<number | null>(null);
  useEffect(() => {
    if (!wantsResume) return;
    let live = true;
    fetchAutosave(brand.id).then((p) => { if (live) setOffer(p ?? null); }).catch(() => { /* no offer */ });
    return () => { live = false; };
  }, [wantsResume, brand.id]);

  if ((sourceId !== null && loadingPost) || (mediaIds.length > 0 && loadingMedia)) {
    return <div className="space-y-4 p-6"><Skeleton className="h-8 w-40" /><Skeleton className="h-40" /><Skeleton className="h-24" /></div>;
  }
  const media: MediaOut[] = mediaIds.map((id) => library?.items.find((m) => m.id === id)).filter(Boolean) as MediaOut[];
  const toLocal = (iso: string | null) => toLocalInput(iso, brand.timezone);
  let initial: ComposerDraft;
  if (post && opts.postId) initial = draftFromPost(post, media, toLocal);
  else if (post && opts.fromPostId) initial = draftFromPost(post, media, toLocal, true);
  else if (opts.idea) initial = emptyDraft({ content: opts.idea.body || opts.idea.title, link: opts.idea.source_url ?? "", media, source: "idea", ideaId: opts.idea.id });
  else initial = emptyDraft({ selected: opts.account ? [opts.account] : [], action: opts.at ? "schedule" : "queue", scheduledAt: opts.at ?? "" });

  const onSaved = (saved: PostOut, action: Action) => { opts.onSaved?.(saved, action); onDone(); };
  const resume = { offer, choice, ownId };

  return (
    <div className={compact ? "p-4 sm:p-6" : ""}>
      {offer && offerResume(resume, initial.postId ?? null) && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-card border border-line bg-brand-soft/60 px-4 py-3 text-sm">
          <div className="min-w-0 flex-1">
            <div className="font-medium">Resume unfinished post?</div>
            <div className="truncate text-ink-2">“{offer.content || "(no text)"}”</div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => setChoice("resumed")}>Resume</Button>
            <Button size="sm" variant="outline" onClick={() => { actions.remove.mutate(offer.id); setChoice("discarded"); }}>Discard</Button>
          </div>
        </div>
      )}
      <Composer key={composerKey(resume, initial.postId)} initial={startFrom(resume, initial, (p) => draftFromPost(p, media, toLocal))}
                existing={opts.postId ? post : null} onSaved={onSaved} onCancel={onDone} compact={compact} onAutosaved={setOwnId} />
    </div>
  );
}
