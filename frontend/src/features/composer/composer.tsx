/**
 * The composer: one text, many channels. Left: what you write and when it goes out.
 * Right: each channel's version, limits and problems, previews, and AI help.
 */
import { useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import { toast } from "sonner";
import { Link } from "@tanstack/react-router";
import { ImagePlus, Library, Sparkles, X } from "lucide-react";
import { useBrand, usePerms, useSession } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/page";
import { PlatformMark } from "@/lib/platforms";
import { fromLocalInput } from "@/lib/time";
import { cn } from "@/lib/utils";
import {
  aiGenerate, aiHashtags, aiRewrite, CannotPlace, uploadMedia, useAccounts, useCampaigns, useHashtagGroups,
  usePostActions, useTemplates, type MediaOut, type PostOut,
} from "@/features/posts/api";
import { MediaPicker } from "@/features/composer/media-picker";
import { PostPreview } from "@/features/composer/previews";
import { CommentsPanel } from "@/features/collab/panels";
import { useComposerState, type Action, type ComposerDraft } from "@/features/composer/use-composer-state";

const ACTIONS: { key: Action; label: string; button: string }[] = [
  { key: "queue", label: "Next free slot", button: "Add to queue" },
  { key: "next", label: "Share next", button: "Share next" },
  { key: "schedule", label: "Pick a time", button: "Schedule" },
  { key: "now", label: "Publish now", button: "Publish now" },
  { key: "draft", label: "Save draft", button: "Save draft" },
];

export function Composer({ initial, existing, onSaved, onCancel, compact }: {
  initial: ComposerDraft; existing?: PostOut | null; onSaved: (post: PostOut, action: Action) => void; onCancel?: () => void; compact?: boolean;
}) {
  const brand = useBrand();
  const { data: session } = useSession();
  const { data: accounts = [] } = useAccounts(brand.id);
  const { data: campaigns = [] } = useCampaigns(brand.id);
  const { data: templates = [] } = useTemplates(brand.id);
  const { data: hashtagGroups = [] } = useHashtagGroups(brand.id);
  const active = accounts.filter((a) => a.is_active);
  const s = useComposerState(initial, brand.id, accounts, true);
  const { draft, set } = s;
  const actions = usePostActions(brand.id);
  const [picker, setPicker] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [uploads, setUploads] = useState<{ key: string; pct: number }[]>([]);
  const [dragging, setDragging] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [brief, setBrief] = useState("");
  const [briefUrl, setBriefUrl] = useState("");
  const dragFrom = useRef<number | null>(null);
  const ai = session?.features.ai ?? false;
  const { canApprove } = usePerms();

  async function submit() {
    try {
      const res = await actions.save.mutateAsync({ id: draft.postId ?? undefined, body: s.toWrite((v) => fromLocalInput(v, brand.timezone)) });
      toast.success(res.message);
      onSaved(res.post, draft.action);
    } catch (e) {
      if (e instanceof CannotPlace) {
        set({ postId: e.post.id });
        toast.error(e.problems.join(" · "));
      } else toast.error(e instanceof Error ? e.message : "Could not save");
    }
  }

  function files(list: FileList | File[] | null) {
    if (!list) return;
    for (const file of Array.from(list)) {
      if (!/^(image|video)\//.test(file.type)) continue;
      const key = Math.random().toString(36).slice(2);
      setUploads((u) => [...u, { key, pct: 0 }]);
      uploadMedia(brand.id, file, (pct) => setUploads((u) => u.map((x) => x.key === key ? { ...x, pct } : x)))
        .then((items) => s.addMedia(items))
        .catch((e: Error) => toast.error(e.message))
        .finally(() => setUploads((u) => u.filter((x) => x.key !== key)));
    }
  }
  const onPaste = (e: ClipboardEvent) => { const fs = Array.from(e.clipboardData?.files ?? []); if (fs.length) { e.preventDefault(); files(fs); } };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDragging(false); files(e.dataTransfer.files); };

  async function runAi<T>(fn: () => Promise<T>, apply: (r: T) => void) {
    setAiBusy(true);
    try { apply(await fn()); } catch (e) { toast.error(e instanceof Error ? e.message : "AI request failed"); } finally { setAiBusy(false); }
  }
  const rewrite = (instruction: string) => runAi(() => aiRewrite(brand.id, { text: draft.content, instruction }), (r) => set({ content: r.text }));
  const adapt = (id: number) => {
    const a = s.byId.get(id)!;
    return runAi(() => aiRewrite(brand.id, { text: draft.content, platform: a.platform, instruction: `Adapt this for ${a.capabilities.label}, keeping the message. Fit within ${a.capabilities.max} characters.` }),
                 (r) => { s.setOverride(id, r.text); setEditing(id); });
  };
  const generate = () => {
    const platforms = [...new Set(draft.selected.map((id) => s.byId.get(id)?.platform).filter(Boolean))] as string[];
    return runAi(() => aiGenerate(brand.id, { brief, url: briefUrl || null, platforms: platforms.length ? platforms : ["x", "linkedin"], link: draft.link || null, variants: 1 }), (r) => {
      const byPlatform = new Map<string, string>();
      for (const d of r.drafts) if (!byPlatform.has(d.platform)) byPlatform.set(d.platform, d.text);
      const first = r.drafts[0]?.text ?? "";
      set((d) => ({
        content: first,
        overrides: Object.fromEntries(d.selected.map((id) => [id, byPlatform.get(s.byId.get(id)?.platform ?? "") ?? ""]).filter(([, t]) => t && t !== first)),
      }));
    });
  };

  const current = ACTIONS.find((a) => a.key === draft.action)!;
  const needsApproval = brand.require_approval && !canApprove;

  return (
    <div className={cn("grid gap-6 lg:grid-cols-5", compact && "lg:grid-cols-5")} onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
         onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }} onDrop={onDrop} onPaste={onPaste}>
      <form className="space-y-5 lg:col-span-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">{existing ? "Edit post" : "New post"}</h2>
          <div className="flex items-center gap-3 text-xs text-ink-2">
            {s.savedAt && <span>Draft saved {s.savedAt}</span>}
            {existing && <StatusBadge status={existing.status} />}
          </div>
        </div>

        {(templates.length > 0 || hashtagGroups.length > 0) && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {templates.length > 0 && (
              <Select onValueChange={(v) => { const t = templates.find((x) => String(x.id) === v); if (t && (!draft.content.trim() || confirm("Replace the current text with this template?"))) s.useTemplate(t.body); }}>
                <SelectTrigger className="w-52"><SelectValue placeholder="Use a template…" /></SelectTrigger>
                <SelectContent>{templates.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.name}{t.category ? ` · ${t.category}` : ""}</SelectItem>)}</SelectContent>
              </Select>
            )}
            {hashtagGroups.length > 0 && (
              <Select onValueChange={(v) => { const g = hashtagGroups.find((x) => String(x.id) === v); if (g) s.addHashtags(g.tags); }}>
                <SelectTrigger className="w-52"><SelectValue placeholder="Insert hashtags…" /></SelectTrigger>
                <SelectContent>{hashtagGroups.map((g) => <SelectItem key={g.id} value={String(g.id)}>{g.name} ({g.tags.length})</SelectItem>)}</SelectContent>
              </Select>
            )}
          </div>
        )}

        <div className="relative">
          <Textarea value={draft.content} onChange={(e) => set({ content: e.target.value })} rows={7} autoFocus
                    className="min-h-40 text-[15px]" placeholder="What do you want to say? Each channel can get its own version on the right. Drop or paste images here." />
          {dragging && <div className="pointer-events-none absolute inset-0 grid place-items-center rounded-control border-2 border-dashed border-brand bg-surface/80 text-sm font-medium">Drop to attach</div>}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
            <span className="tnum">{draft.content.length} characters</span>
            {ai && (
              <span className="flex flex-wrap gap-3">
                {[["Tighten", "Make it tighter and more concrete"], ["Conversational", "Make it more conversational"], ["Add a call to action", "Add a clear call to action at the end"]].map(([l, ins]) => (
                  <button key={l} type="button" className="underline-offset-2 hover:text-ink hover:underline disabled:opacity-50" disabled={aiBusy || !draft.content.trim()} onClick={() => void rewrite(ins)}>{l}</button>
                ))}
                <button type="button" className="underline-offset-2 hover:text-ink hover:underline disabled:opacity-50" disabled={aiBusy || !draft.content.trim()}
                        onClick={() => void runAi(() => aiHashtags(brand.id, draft.content), (r) => s.addHashtags(r.hashtags))}>Suggest hashtags</button>
              </span>
            )}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="c-link">Link</Label>
            <Input id="c-link" type="url" value={draft.link} onChange={(e) => set({ link: e.target.value })} placeholder="https://" />
            <p className="text-xs text-ink-2">{brand.auto_shorten_links ? "Shortened and UTM-tagged when the post is saved." : "Added to the text where the network has no link field."}</p>
          </div>
          <div className="space-y-1.5">
            <Label>Campaign</Label>
            <Select value={draft.campaignId ? String(draft.campaignId) : "none"} onValueChange={(v) => set({ campaignId: v === "none" ? null : Number(v) })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="none">None</SelectItem>{campaigns.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>

        <div>
          <Label>Media</Label>
          <div className="mt-1.5 flex flex-wrap gap-2">
            {draft.media.map((m, i) => (
              <div key={m.id} draggable onDragStart={(e) => { e.stopPropagation(); dragFrom.current = i; }} onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                   onDrop={(e) => { e.preventDefault(); e.stopPropagation(); if (dragFrom.current !== null) s.moveMedia(dragFrom.current, i); dragFrom.current = null; }}
                   className="relative size-20 cursor-grab overflow-hidden rounded-control border border-line bg-hover" title={m.name}>
                {m.is_video ? <div className="grid h-full place-items-center text-xs text-ink-2">video</div> : <img src={m.url} alt={m.alt_text ?? ""} className="pointer-events-none h-full w-full object-cover" />}
                <button type="button" onClick={() => s.removeMedia(m.id)} aria-label={`Remove ${m.name}`} className="absolute right-0.5 top-0.5 grid size-5 place-items-center rounded bg-surface/90 text-ink-2 hover:text-ink"><X className="size-3" /></button>
              </div>
            ))}
            {uploads.map((u) => (
              <div key={u.key} className="relative grid size-20 place-items-center rounded-control border border-line bg-hover text-xs text-ink-2 tnum">
                {u.pct}%<div className="absolute inset-x-0 bottom-0 h-1 bg-line"><div className="h-full bg-brand" style={{ width: `${u.pct}%` }} /></div>
              </div>
            ))}
            <label className="grid size-20 cursor-pointer place-items-center rounded-control border border-dashed border-line-strong text-ink-2 hover:border-brand hover:text-ink" title="Upload">
              <input type="file" className="sr-only" multiple accept="image/*,video/mp4,video/quicktime" onChange={(e) => { files(e.target.files); e.target.value = ""; }} />
              <ImagePlus className="size-5" aria-hidden /><span className="sr-only">Upload media</span>
            </label>
            <Button type="button" variant="ghost" size="sm" className="self-end text-ink-2" onClick={() => setPicker(true)}><Library className="size-4" />Library</Button>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="c-notes">Internal notes</Label>
          <Input id="c-notes" value={draft.notes} onChange={(e) => set({ notes: e.target.value })} placeholder="Only your team sees this" />
        </div>

        <div className="space-y-3 rounded-card border border-line bg-surface p-4">
          <div role="radiogroup" aria-label="When to publish" className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
            {ACTIONS.map((a) => (
              <label key={a.key} className="flex cursor-pointer items-center gap-1.5">
                <input type="radio" name="action" value={a.key} checked={draft.action === a.key} onChange={() => set({ action: a.key })} className="accent-[var(--brand)]" />{a.label}
              </label>
            ))}
          </div>
          {draft.action === "schedule" && (
            <div className="max-w-xs space-y-1.5">
              <Label htmlFor="c-when">When ({brand.timezone})</Label>
              <Input id="c-when" type="datetime-local" value={draft.scheduledAt} onChange={(e) => set({ scheduledAt: e.target.value })} required />
            </div>
          )}
          {needsApproval && draft.action !== "draft" && <p className="text-xs text-ink-2">This brand requires approval: an owner reviews it before it goes out.</p>}
          <div className="flex items-center gap-3 pt-1">
            <Button type="submit" disabled={actions.save.isPending || (s.hasProblems && draft.action !== "draft") || (draft.action !== "draft" && !draft.selected.length)}>
              {actions.save.isPending ? "Saving…" : current.button}
            </Button>
            {s.hasProblems && draft.action !== "draft" && <span className="text-xs text-st-failed">Fix the issues on the right first.</span>}
            {!draft.selected.length && draft.action !== "draft" && !s.hasProblems && <span className="text-xs text-ink-2">Pick at least one channel.</span>}
            {onCancel && <Button type="button" variant="ghost" size="sm" className="ml-auto" onClick={onCancel}>Cancel</Button>}
          </div>
        </div>
      </form>

      <aside className="space-y-4 lg:col-span-2">
        <section className="rounded-card border border-line bg-surface">
          <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <h3 className="text-sm font-semibold">Post to</h3>
            <span className="text-xs text-ink-2 tnum">{draft.selected.length} selected</span>
          </header>
          {active.length === 0 ? (
            <p className="p-4 text-sm text-ink-2">No active channels. <Link className="underline" to="/channels" search={(p) => p}>Connect one</Link>.</p>
          ) : (
            <ul className="divide-y divide-line">
              {active.map((a) => {
                const sel = draft.selected.includes(a.id);
                const len = s.textFor(a.id).length;
                const max = a.capabilities.max;
                const isOver = s.over(a.id);
                const thread = draft.threads[a.id] ?? [];
                const probs = s.problems[String(a.id)] ?? [];
                return (
                  <li key={a.id} className="px-4 py-3">
                    <label className="flex cursor-pointer items-center gap-3">
                      <input type="checkbox" checked={sel} onChange={() => s.toggle(a.id)} className="accent-[var(--brand)]" />
                      <PlatformMark platform={a.platform} size={16} />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{a.handle}</span>
                      <span className={cn("text-xs tnum", isOver ? "text-st-failed" : "text-ink-2")}>{len}/{max}</span>
                    </label>
                    <div className="mt-2 h-1 overflow-hidden rounded bg-hover"><div className={cn("h-full", isOver ? "bg-st-failed" : len > max * 0.9 ? "bg-st-pending" : "bg-brand")} style={{ width: `${Math.min(100, (len / max) * 100)}%` }} /></div>
                    {sel && (
                      <div className="mt-2 space-y-2 text-xs">
                        <div className="flex flex-wrap gap-3">
                          <button type="button" className="text-ink-2 underline-offset-2 hover:text-ink hover:underline" onClick={() => setEditing(editing === a.id ? null : a.id)}>
                            {draft.overrides[a.id] ? "Custom text" : "Same as main text"}{editing === a.id ? " · close" : " · edit"}
                          </button>
                          {ai && <button type="button" className="text-ink-2 underline-offset-2 hover:text-ink hover:underline disabled:opacity-50" disabled={aiBusy} onClick={() => void adapt(a.id)}>Adapt with AI</button>}
                          {a.capabilities.threadable && isOver && !thread.length && <button type="button" className="font-medium text-brand underline-offset-2 hover:underline" onClick={() => s.split(a.id)}>Split into thread</button>}
                          {a.capabilities.first_comment && <button type="button" className="text-ink-2 underline-offset-2 hover:text-ink hover:underline" onClick={() => s.setFirstComment(a.id, draft.firstComments[a.id] ?? "")}>{draft.firstComments[a.id] !== undefined ? "First comment" : "+ First comment"}</button>}
                        </div>
                        {editing === a.id && (
                          <div className="space-y-1">
                            <Textarea rows={4} value={draft.overrides[a.id] ?? ""} onChange={(e) => s.setOverride(a.id, e.target.value)} placeholder="Leave empty to use the main text" className="text-sm" />
                            <button type="button" className="text-ink-2 underline" onClick={() => s.setOverride(a.id, "")}>Reset to main text</button>
                          </div>
                        )}
                        {thread.length > 0 && (
                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between"><span className="font-medium">Thread · {thread.length + 1} items</span><button type="button" className="text-ink-2 underline" onClick={() => s.setThread(a.id, [])}>Remove thread</button></div>
                            {thread.map((item, i) => (
                              <div key={i} className="flex items-start gap-2">
                                <span className="w-5 pt-2 text-ink-2 tnum">{i + 2}.</span>
                                <div className="flex-1">
                                  <Textarea rows={2} value={item} onChange={(e) => s.setThread(a.id, thread.map((t, j) => j === i ? e.target.value : t))} className="text-sm" />
                                  <div className="mt-0.5 flex justify-between"><span className={cn("tnum", item.length > max ? "text-st-failed" : "text-ink-2")}>{item.length}/{max}</span><button type="button" className="text-ink-2 hover:text-st-failed" onClick={() => s.setThread(a.id, thread.filter((_, j) => j !== i))}>remove</button></div>
                                </div>
                              </div>
                            ))}
                            <button type="button" className="text-brand" onClick={() => s.setThread(a.id, [...thread, ""])}>+ Add item</button>
                          </div>
                        )}
                        {draft.firstComments[a.id] !== undefined && (
                          <Textarea rows={2} value={draft.firstComments[a.id]} onChange={(e) => s.setFirstComment(a.id, e.target.value)} className="text-sm" placeholder="Posted as the first reply right after publishing: links, hashtags, context" />
                        )}
                        {probs.length > 0 && <ul className="space-y-0.5 text-st-failed">{probs.map((p) => <li key={p}>{p}</li>)}</ul>}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {draft.selected.length > 0 && (
          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Preview</h3>
            {draft.selected.map((id) => { const a = s.byId.get(id); return a ? (
              <PostPreview key={id} account={a} text={s.textFor(id)} thread={draft.threads[id] ?? []} firstComment={draft.firstComments[id] ?? ""} media={draft.media} link={draft.link} brandColor={brand.color} />
            ) : null; })}
          </section>
        )}

        {existing && <CommentsPanel postId={existing.id} />}

        {ai && (
          <section className="space-y-2 rounded-card border border-line bg-surface p-4">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold"><Sparkles className="size-4" />Write with AI</h3>
            <Textarea rows={3} value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="Brief: what's the post about, what should people do?" className="text-sm" />
            <Input type="url" value={briefUrl} onChange={(e) => setBriefUrl(e.target.value)} placeholder="Optional: a URL to write about" className="text-sm" />
            <div className="flex items-center gap-2">
              <Button type="button" size="sm" disabled={aiBusy || (!brief.trim() && !briefUrl.trim())} onClick={() => void generate()}>{aiBusy ? "Thinking…" : "Generate for selected channels"}</Button>
            </div>
            <p className="text-xs text-ink-2">Uses {brand.name}'s voice. Fills the main text and a version per channel.</p>
          </section>
        )}
      </aside>
      <MediaPicker brandId={brand.id} open={picker} onOpenChange={setPicker} selectedIds={draft.media.map((m) => m.id)} onPick={(items: MediaOut[]) => s.addMedia(items)} />
    </div>
  );
}
