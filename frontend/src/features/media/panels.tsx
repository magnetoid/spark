/** Media pieces: generate an image, crop to a network's ratio, tag, write alt text, the channel grid, repurpose a source. */
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Crop, Grid3x3, Loader2, Recycle, Sparkles, Wand2, X } from "lucide-react";
import { useBrand, usePerms, useSession } from "@/app/session";
import { StatusBadge } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { openAskSpark } from "@/features/agent/panels";
import {
  RATIOS, useChannelGrid, useCropMedia, useGenerateImage, useRepurpose, useUpdateMedia, useWriteAltText, type CropRatio, type ImageSize, type MediaOut,
} from "@/features/media/api";
import { useAccounts } from "@/features/posts/api";
import { PlatformMark } from "@/lib/platforms";
import { fmtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

// ---- generate --------------------------------------------------------------------------------
export function GenerateImageButton({ onDone, compact, className }: { onDone?: (m: MediaOut) => void; compact?: boolean; className?: string }) {
  const brand = useBrand();
  const { data: session } = useSession();
  const gen = useGenerateImage(brand.id);
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [size, setSize] = useState<ImageSize>("square");
  if (!session?.features.images) return null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    gen.mutate({ prompt: prompt.trim(), size }, { onSuccess: (m) => { onDone?.(m); setOpen(false); setPrompt(""); } });
  };
  return (
    <>
      {compact ? (
        <button type="button" onClick={() => setOpen(true)} title="Generate an image" className={cn("grid size-20 place-items-center rounded-control border border-dashed border-line-strong text-ink-2 hover:border-brand hover:text-ink", className)}>
          <Wand2 className="size-5" aria-hidden /><span className="sr-only">Generate an image</span>
        </button>
      ) : (
        <Button size="sm" variant="outline" className={className} onClick={() => setOpen(true)}><Wand2 className="size-4" />Generate image</Button>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Generate an image</DialogTitle></DialogHeader>
          <form className="space-y-4" onSubmit={submit}>
            <div className="space-y-1.5"><Label htmlFor="gi-prompt">What should it show?</Label><Textarea id="gi-prompt" rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} autoFocus placeholder="A warm, uncluttered studio desk with a sketchbook and a mug, morning light, no text" /><p className="text-xs text-ink-2">Describe the scene, the mood and the light. Say "no text" unless you want letters in it; the brand's tone of voice is added as the mood.</p></div>
            <div className="space-y-1.5"><Label>Shape</Label>
              <Select value={size} onValueChange={(v) => setSize(v as ImageSize)}><SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="square">Square · feed</SelectItem><SelectItem value="portrait">Portrait · stories, reels</SelectItem><SelectItem value="landscape">Landscape · link cards, X</SelectItem></SelectContent></Select></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" disabled={gen.isPending || prompt.trim().length < 3}>{gen.isPending ? <><Loader2 className="size-4 animate-spin" />Drawing…</> : "Generate"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ---- crop ----------------------------------------------------------------------------------------
export function CropDialog({ media, open, onOpenChange, onDone }: { media: MediaOut; open: boolean; onOpenChange: (o: boolean) => void; onDone?: (m: MediaOut) => void }) {
  const brand = useBrand();
  const crop = useCropMedia(brand.id);
  const [ratio, setRatio] = useState<CropRatio>("1:1");
  const [x, setX] = useState(0.5);
  const [y, setY] = useState(0.5);
  const [rw, rh] = ratio.split(":").map(Number);
  const W = media.width ?? 1, H = media.height ?? 1;
  const wide = W / H > rw / rh;
  const cw = wide ? (H * rw / rh) / W : 1, ch = wide ? 1 : (W * rh / rw) / H;  // crop box as a fraction of the image
  const left = Math.min(Math.max(x - cw / 2, 0), 1 - cw), top = Math.min(Math.max(y - ch / 2, 0), 1 - ch);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>Crop {media.name}</DialogTitle></DialogHeader>
        <div className="flex flex-wrap gap-1.5">{RATIOS.map((r) => <button key={r.value} type="button" onClick={() => setRatio(r.value)} className={cn("rounded-control border px-2 py-1 text-xs", ratio === r.value ? "border-brand bg-brand-soft text-ink" : "border-line text-ink-2 hover:text-ink")} title={r.hint}>{r.label}<span className="ml-1 text-ink-2">{r.hint}</span></button>)}</div>
        <div className="relative mx-auto max-h-80 overflow-hidden rounded-control bg-hover" style={{ aspectRatio: `${W} / ${H}` }}>
          <img src={media.url} alt={media.alt_text ?? ""} className="h-full w-full object-contain" />
          <div className="pointer-events-none absolute inset-0 bg-ink/40" />
          <div className="pointer-events-none absolute border-2 border-brand" style={{ left: `${left * 100}%`, top: `${top * 100}%`, width: `${cw * 100}%`, height: `${ch * 100}%`, boxShadow: "0 0 0 9999px rgba(0,0,0,.35)" }} />
        </div>
        <div className="grid gap-2 text-xs text-ink-2">
          {wide && <label className="flex items-center gap-2">Left – right <input type="range" min={0} max={100} value={Math.round(x * 100)} onChange={(e) => setX(Number(e.target.value) / 100)} className="flex-1 accent-[var(--brand)]" /></label>}
          {!wide && <label className="flex items-center gap-2">Top – bottom <input type="range" min={0} max={100} value={Math.round(y * 100)} onChange={(e) => setY(Number(e.target.value) / 100)} className="flex-1 accent-[var(--brand)]" /></label>}
          <span>{W}×{H} → about {Math.round(W * cw)}×{Math.round(H * ch)}. The original stays in the library.</span>
        </div>
        <DialogFooter><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={crop.isPending} onClick={() => crop.mutate({ id: media.id, body: { ratio, x, y } }, { onSuccess: (m) => { onDone?.(m); onOpenChange(false); } })}><Crop className="size-4" />Save crop</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---- tags + alt text ---------------------------------------------------------------------------------
export function TagEditor({ media, canEdit }: { media: MediaOut; canEdit: boolean }) {
  const brand = useBrand();
  const update = useUpdateMedia(brand.id);
  const [draft, setDraft] = useState("");
  const add = () => { const t = draft.trim().toLowerCase(); if (t && !media.tags.includes(t)) update.mutate({ id: media.id, body: { tags: [...media.tags, t] } }); setDraft(""); };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } };
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      {media.tags.map((t) => <span key={t} className="flex items-center gap-0.5 rounded-full border border-line px-1.5 text-[10px] text-ink-2">{t}{canEdit && <button type="button" aria-label={`Remove tag ${t}`} onClick={() => update.mutate({ id: media.id, body: { tags: media.tags.filter((x) => x !== t) } })}><X className="size-2.5" /></button>}</span>)}
      {canEdit && <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={add} placeholder={media.tags.length ? "+" : "+ tag"} className="h-4 w-12 bg-transparent text-[10px] outline-none placeholder:text-ink-2" aria-label="Add a tag" />}
    </div>
  );
}

export function AltTextButton({ media, className }: { media: MediaOut; className?: string }) {
  const brand = useBrand();
  const { data: session } = useSession();
  const write = useWriteAltText(brand.id);
  if (!session?.features.ai || media.is_video) return null;
  return <button type="button" onClick={() => write.mutate(media.id)} disabled={write.isPending} title="Write alt text with AI" className={cn("text-ink-2 hover:text-ink", className)}>{write.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}<span className="sr-only">Write alt text with AI</span></button>;
}

// ---- the channel grid ------------------------------------------------------------------------------------
export function ChannelGrid({ accountId }: { accountId: number }) {
  const brand = useBrand();
  const { data, isPending } = useChannelGrid(brand.id, accountId);
  if (isPending || !data) return <Skeleton className="h-64" />;
  if (!data.items.length) return <p className="rounded-card border border-dashed border-line p-6 text-center text-sm text-ink-2">Nothing scheduled or published on this channel yet. The grid shows how the profile will look.</p>;
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs text-ink-2"><Grid3x3 className="size-3.5" />How {data.account.handle} will look: newest first, scheduled posts first.</div>
      <ul className="grid max-w-md grid-cols-3 gap-0.5 overflow-hidden rounded-card border border-line">
        {data.items.map((it) => (
          <li key={it.post_id} className="relative aspect-square bg-hover" title={it.content}>
            {it.image ? (it.is_video ? <video src={it.image} className="h-full w-full object-cover" muted /> : <img src={it.image} alt="" className="h-full w-full object-cover" loading="lazy" />)
              : <p className="line-clamp-5 p-2 text-[11px] leading-tight text-ink-2">{it.content}</p>}
            <span className="absolute bottom-1 left-1"><StatusBadge status={it.status} className="scale-90" /></span>
            {it.when && <span className="absolute right-1 top-1 rounded bg-surface/90 px-1 text-[10px] tnum">{fmtDateTime(it.when, brand.timezone)}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---- repurpose ---------------------------------------------------------------------------------------------
export function RepurposeButton({ className }: { className?: string }) {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data: session } = useSession();
  const { data: accounts = [] } = useAccounts(brand.id);
  const run = useRepurpose(brand.id);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"url" | "text">("url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [picked, setPicked] = useState<number[] | null>(null);
  if (!canEdit || !(session?.features.ai || session?.features.janus)) return null;
  const active = accounts.filter((a) => a.is_active);
  const selected = picked ?? active.map((a) => a.id);
  const onFile = (f: File | undefined) => { if (!f) return; void f.text().then((t) => { setText(t); setFileName(f.name); setMode("text"); }); };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate({ source_url: mode === "url" ? url.trim() : null, source_text: mode === "text" ? text : null, source_name: fileName, account_ids: selected, notes: notes.trim() || null }, {
      onSuccess: (r) => {
        setOpen(false);
        if (r.mode === "janus" && r.run_id) openAskSpark("", "repurpose", r.run_id);
        else void navigate({ to: "/publishing", search: (p) => ({ ...p, view: "drafts" }) });
      },
    });
  };
  return (
    <>
      <Button size="sm" variant="outline" className={className} onClick={() => setOpen(true)}><Recycle className="size-4" />Repurpose</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader><DialogTitle>Repurpose a source into posts</DialogTitle></DialogHeader>
          <form className="space-y-4 text-sm" onSubmit={submit}>
            <p className="text-ink-2">A blog post, a page, pasted notes or a talk's transcript (.txt, .srt, .vtt) becomes a series of drafts, one per channel at least. {session?.features.janus ? "Janus reads it and proposes; you approve." : "Claude writes them straight into Drafts."}</p>
            <div role="tablist" className="flex gap-1 border-b border-line">
              {(["url", "text"] as const).map((m) => <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)} className={cn("-mb-px border-b-2 px-3 py-1.5", mode === m ? "border-brand font-medium" : "border-transparent text-ink-2")}>{m === "url" ? "A link" : "Text or transcript"}</button>)}
            </div>
            {mode === "url" ? (
              <div className="space-y-1.5"><Label htmlFor="rp-url">Page URL</Label><Input id="rp-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourblog.com/post" required autoFocus /></div>
            ) : (
              <div className="space-y-2">
                <Input type="file" accept=".txt,.srt,.vtt,text/plain" onChange={(e) => onFile(e.target.files?.[0])} aria-label="Transcript file" />
                <Textarea rows={6} value={text} onChange={(e) => { setText(e.target.value); setFileName(null); }} placeholder="Paste the text or a transcript…" aria-label="Source text" />
                {fileName && <p className="text-xs text-ink-2">From {fileName}; timing lines are dropped.</p>}
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Channels</Label>
              <div className="flex flex-wrap gap-1.5">{active.map((a) => { const on = selected.includes(a.id); return <button key={a.id} type="button" onClick={() => setPicked(on ? selected.filter((x) => x !== a.id) : [...selected, a.id])} className={cn("flex items-center gap-1.5 rounded-control border px-2 py-1 text-xs", on ? "border-brand bg-brand-soft" : "border-line text-ink-2")}><PlatformMark platform={a.platform} size={12} />{a.handle}</button>; })}</div>
            </div>
            <div className="space-y-1.5"><Label htmlFor="rp-notes">Notes (optional)</Label><Input id="rp-notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Lead with the pricing change; keep it under 3 posts" /></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" disabled={run.isPending || selected.length === 0 || (mode === "url" ? !url.trim() : text.trim().length < 80)}>{run.isPending ? <><Loader2 className="size-4 animate-spin" />Reading…</> : "Make drafts"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
