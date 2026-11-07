/** Library: media, templates and hashtag groups the composer draws from. */
import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { Crop, Hash, Images, LayoutTemplate, Rss, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { useBrand, usePerms, useSession } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { keys, uploadMedia, useAccounts, useHashtagGroups, useMedia, useTemplates, type HashtagGroupOut, type MediaOut, type TemplateOut } from "@/features/posts/api";
import { useCreateFeed, useDeleteFeed, useFeeds, useUpdateFeed } from "@/features/api4";
import { PlatformMark } from "@/lib/platforms";
import { Switch } from "@/components/ui/switch";
import { api, unwrap } from "@/lib/api";
import { AltTextButton, CropDialog, GenerateImageButton, RepurposeButton, TagEditor } from "@/features/media/panels";
import { useMediaTags } from "@/features/media/api";
import { cn } from "@/lib/utils";

const TABS = [["media", "Media", Images], ["templates", "Templates", LayoutTemplate], ["hashtags", "Hashtag groups", Hash], ["sources", "RSS sources", Rss]] as const;

export function LibraryPage() {
  const search = useSearch({ strict: false }) as { tab?: string };
  const navigate = useNavigate();
  const tab = TABS.find(([k]) => k === search.tab)?.[0] ?? "media";
  return (
    <>
      <PageHeader title="Library" description="Reusable pieces: images and video, post templates, hashtag groups." />
      <div role="tablist" className="mb-5 flex gap-1 border-b border-line">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => void navigate({ to: ".", search: (p: Record<string, unknown>) => ({ ...p, tab: k }) })}
                  className={cn("-mb-px border-b-2 px-3 py-2 text-sm", tab === k ? "border-brand font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink")}>{label}</button>
        ))}
      </div>
      {tab === "media" ? <MediaTab /> : tab === "templates" ? <TemplatesTab /> : tab === "hashtags" ? <HashtagsTab /> : <SourcesTab />}
    </>
  );
}

function MediaTab() {
  const brand = useBrand();
  const { data, isPending } = useMedia(brand.id);
  const { data: tags = [] } = useMediaTags(brand.id);
  const qc = useQueryClient();
  const { canEdit } = usePerms();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploads, setUploads] = useState<{ key: string; name: string; pct: number }[]>([]);
  const [dragging, setDragging] = useState(false);
  const [tag, setTag] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [cropping, setCropping] = useState<MediaOut | null>(null);
  const invalidate = () => { void qc.invalidateQueries({ queryKey: keys.media(brand.id) }); void qc.invalidateQueries({ queryKey: ["media-tags", brand.id] }); };

  const files = (list: FileList | null) => {
    for (const f of Array.from(list ?? [])) {
      const key = Math.random().toString(36).slice(2);
      setUploads((u) => [...u, { key, name: f.name, pct: 0 }]);
      uploadMedia(brand.id, f, (pct) => setUploads((u) => u.map((x) => x.key === key ? { ...x, pct } : x)))
        .then(() => invalidate()).catch((e: Error) => toast.error(e.message))
        .finally(() => setUploads((u) => u.filter((x) => x.key !== key)));
    }
  };
  const alt = useMutation({
    mutationFn: async ({ id, alt_text }: { id: number; alt_text: string }) => unwrap(await api.PATCH("/brands/{brand_id}/media/{media_id}", { params: { path: { brand_id: brand.id, media_id: id } }, body: { alt_text } })),
    onSuccess: () => { void invalidate(); toast.success("Alt text saved"); }, onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/media/{media_id}", { params: { path: { brand_id: brand.id, media_id: id } } })),
    onSuccess: () => { void invalidate(); toast.success("File deleted"); }, onError: (e) => toast.error(e.message),
  });
  const needle = q.trim().toLowerCase();
  const items = (data?.items ?? []).filter((m) => (!tag || m.tags.includes(tag)) && (!needle || m.name.toLowerCase().includes(needle) || (m.alt_text ?? "").toLowerCase().includes(needle)));

  return (
    <div onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
         onDrop={(e) => { e.preventDefault(); setDragging(false); if (canEdit) files(e.dataTransfer.files); }} onPaste={(e) => { if (canEdit && e.clipboardData.files.length) files(e.clipboardData.files); }}
         className={cn("rounded-card", dragging && "ring-2 ring-brand")}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {canEdit && (
          <>
            <Button size="sm" onClick={() => fileRef.current?.click()}><Upload className="size-4" />Upload</Button>
            <input ref={fileRef} type="file" className="sr-only" multiple accept="image/*,video/mp4,video/quicktime,application/pdf" onChange={(e) => { files(e.target.files); e.target.value = ""; }} />
            <GenerateImageButton />
            <span className="hidden text-sm text-ink-2 md:inline">or drop files anywhere here, or paste an image. PDFs become LinkedIn documents.</span>
          </>
        )}
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or alt text" className="ml-auto h-8 w-56" aria-label="Search media" />
      </div>
      {tags.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5 text-xs">
          <button type="button" onClick={() => setTag(null)} className={cn("rounded-full border px-2 py-0.5", tag === null ? "border-brand bg-brand-soft" : "border-line text-ink-2")}>All</button>
          {tags.map((t) => <button key={t.tag} type="button" onClick={() => setTag(tag === t.tag ? null : t.tag)} className={cn("rounded-full border px-2 py-0.5", tag === t.tag ? "border-brand bg-brand-soft" : "border-line text-ink-2")}>{t.tag} <span className="tnum">{t.count}</span></button>)}
        </div>
      )}
      {isPending ? <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">{Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)}</div>
       : !data?.items.length && !uploads.length ? (
        <EmptyState icon={Images} title="No media yet" body="Images, videos and PDFs you upload here are one click away in the composer. With an image connector you can also generate pictures." />
      ) : items.length === 0 && !uploads.length ? (
        <p className="rounded-card border border-dashed border-line p-6 text-center text-sm text-ink-2">Nothing matches{tag ? ` the tag “${tag}”` : ""}{needle ? ` “${q}”` : ""}.</p>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {uploads.map((u) => <li key={u.key} className="relative grid aspect-square place-items-center rounded-card border border-line bg-hover text-xs text-ink-2 tnum">{u.pct}%<div className="absolute inset-x-0 bottom-0 h-1 bg-line"><div className="h-full bg-brand" style={{ width: `${u.pct}%` }} /></div></li>)}
          {items.map((m) => <MediaTile key={m.id} m={m} canEdit={canEdit} onAlt={(t) => alt.mutate({ id: m.id, alt_text: t })} onCrop={() => setCropping(m)} onDelete={() => confirm(`Delete ${m.name}?`) && remove.mutate(m.id)} />)}
        </ul>
      )}
      {cropping && <CropDialog media={cropping} open onOpenChange={(o) => !o && setCropping(null)} />}
    </div>
  );
}

function MediaTile({ m, canEdit, onAlt, onCrop, onDelete }: { m: MediaOut; canEdit: boolean; onAlt: (t: string) => void; onCrop: () => void; onDelete: () => void }) {
  const [editing, setEditing] = useState(false);
  const isPdf = m.content_type === "application/pdf";
  return (
    <li className="group overflow-hidden rounded-card border border-line bg-surface">
      <div className="relative aspect-square bg-hover">
        {m.is_video ? <video src={m.url} className="h-full w-full object-cover" muted /> : isPdf ? <div className="grid h-full place-items-center text-xs text-ink-2">PDF</div> : <img src={m.url} alt={m.alt_text ?? ""} className="h-full w-full object-cover" loading="lazy" />}
        {canEdit && (
          <div className="absolute right-1 top-1 flex gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
            {!m.is_video && !isPdf && <button type="button" onClick={onCrop} aria-label={`Crop ${m.name}`} className="grid size-7 place-items-center rounded-control bg-surface/90 text-ink-2 hover:text-ink"><Crop className="size-4" /></button>}
            <button onClick={onDelete} aria-label={`Delete ${m.name}`} className="grid size-7 place-items-center rounded-control bg-surface/90 text-ink-2 hover:text-st-failed"><Trash2 className="size-4" /></button>
          </div>
        )}
        {m.width && m.height && <span className="absolute bottom-1 left-1 rounded bg-surface/90 px-1 text-[10px] tnum text-ink-2">{m.width}×{m.height}{m.source !== "upload" ? ` · ${m.source}` : ""}</span>}
      </div>
      <div className="p-2 text-xs">
        <div className="truncate font-medium" title={m.name}>{m.name}</div>
        {editing ? (
          <form onSubmit={(e) => { e.preventDefault(); onAlt(String(new FormData(e.currentTarget).get("alt"))); setEditing(false); }} className="mt-1 flex gap-1">
            <Input name="alt" defaultValue={m.alt_text ?? ""} placeholder="Describe the image" className="h-7 text-xs" autoFocus /><Button size="sm" className="h-7 px-2">Save</Button>
          </form>
        ) : (
          <div className="mt-0.5 flex items-center gap-1">
            <button type="button" disabled={!canEdit} onClick={() => setEditing(true)} className={cn("block min-w-0 flex-1 truncate text-left", m.alt_text ? "text-ink-2" : isPdf || m.is_video ? "text-ink-2" : "text-st-pending")} title="Alt text">
              {m.alt_text || (isPdf || m.is_video ? "—" : canEdit ? "Add alt text" : "No alt text")}
            </button>
            {canEdit && <AltTextButton media={m} />}
          </div>
        )}
        <TagEditor media={m} canEdit={canEdit} />
      </div>
    </li>
  );
}

function TemplatesTab() {
  const brand = useBrand();
  const { data = [], isPending } = useTemplates(brand.id);
  const qc = useQueryClient();
  const [editing, setEditing] = useState<TemplateOut | "new" | null>(null);
  const { data: session } = useSession();
  const canEdit = session?.user?.role !== "viewer";
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.templates(brand.id) });
  const save = useMutation({
    mutationFn: async ({ id, body }: { id?: number; body: { name: string; body: string; category: string | null } }) =>
      id ? unwrap(await api.PATCH("/brands/{brand_id}/templates/{template_id}", { params: { path: { brand_id: brand.id, template_id: id } }, body }))
         : unwrap(await api.POST("/brands/{brand_id}/templates", { params: { path: { brand_id: brand.id } }, body })),
    onSuccess: () => { void invalidate(); setEditing(null); toast.success("Template saved"); }, onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/templates/{template_id}", { params: { path: { brand_id: brand.id, template_id: id } } })),
    onSuccess: () => { void invalidate(); toast.success("Template deleted"); }, onError: (e) => toast.error(e.message),
  });
  const existing = editing && editing !== "new" ? editing : null;
  return (
    <>
      {canEdit && <div className="mb-4"><Button size="sm" onClick={() => setEditing("new")}>New template</Button></div>}
      {isPending ? <Skeleton className="h-40" /> : data.length === 0 ? (
        <EmptyState icon={LayoutTemplate} title="No templates yet" body="A template is a post skeleton with {{placeholders}} you fill in from the composer." />
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.map((t) => (
            <li key={t.id} className="rounded-card border border-line bg-surface p-4 text-sm">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1"><div className="font-medium">{t.name}</div>{t.category && <div className="text-xs text-ink-2">{t.category}</div>}</div>
                {canEdit && <><Button variant="ghost" size="sm" onClick={() => setEditing(t)}>Edit</Button><Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Delete" onClick={() => confirm("Delete this template?") && remove.mutate(t.id)}><Trash2 className="size-4" /></Button></>}
              </div>
              <p className="mt-2 line-clamp-4 whitespace-pre-wrap text-ink-2">{t.body}</p>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{existing ? "Edit template" : "New template"}</DialogTitle></DialogHeader>
          <form key={existing?.id ?? "new"} className="space-y-4" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); save.mutate({ id: existing?.id, body: { name: String(fd.get("name")), body: String(fd.get("body")), category: String(fd.get("category")) || null } }); }}>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5"><Label htmlFor="t-name">Name</Label><Input id="t-name" name="name" required defaultValue={existing?.name ?? ""} autoFocus /></div>
              <div className="space-y-1.5"><Label htmlFor="t-cat">Category</Label><Input id="t-cat" name="category" defaultValue={existing?.category ?? ""} placeholder="tip, story, question…" /></div>
            </div>
            <div className="space-y-1.5"><Label htmlFor="t-body">Body</Label><Textarea id="t-body" name="body" rows={6} required defaultValue={existing?.body ?? ""} placeholder="Monday tip: {{tip}}&#10;&#10;Read more: {{link}}" /></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" disabled={save.isPending}>Save</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function HashtagsTab() {
  const brand = useBrand();
  const { data = [], isPending } = useHashtagGroups(brand.id);
  const qc = useQueryClient();
  const [editing, setEditing] = useState<HashtagGroupOut | "new" | null>(null);
  const { data: session } = useSession();
  const canEdit = session?.user?.role !== "viewer";
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.hashtags(brand.id) });
  const save = useMutation({
    mutationFn: async ({ id, body }: { id?: number; body: { name: string; tags: string[] } }) =>
      id ? unwrap(await api.PATCH("/brands/{brand_id}/hashtag-groups/{group_id}", { params: { path: { brand_id: brand.id, group_id: id } }, body }))
         : unwrap(await api.POST("/brands/{brand_id}/hashtag-groups", { params: { path: { brand_id: brand.id } }, body })),
    onSuccess: () => { void invalidate(); setEditing(null); toast.success("Hashtag group saved"); }, onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/hashtag-groups/{group_id}", { params: { path: { brand_id: brand.id, group_id: id } } })),
    onSuccess: () => { void invalidate(); toast.success("Group deleted"); }, onError: (e) => toast.error(e.message),
  });
  const existing = editing && editing !== "new" ? editing : null;
  return (
    <>
      {canEdit && <div className="mb-4"><Button size="sm" onClick={() => setEditing("new")}>New group</Button></div>}
      {isPending ? <Skeleton className="h-40" /> : data.length === 0 ? (
        <EmptyState icon={Hash} title="No hashtag groups yet" body="Save the sets you reuse and insert them from the composer in one click." />
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.map((g) => (
            <li key={g.id} className="rounded-card border border-line bg-surface p-4 text-sm">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1 font-medium">{g.name} <span className="font-normal text-ink-2 tnum">· {g.tags.length}</span></div>
                {canEdit && <><Button variant="ghost" size="sm" onClick={() => setEditing(g)}>Edit</Button><Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Delete" onClick={() => confirm("Delete this group?") && remove.mutate(g.id)}><Trash2 className="size-4" /></Button></>}
              </div>
              <p className="mt-2 break-words text-ink-2">{g.tags.map((t) => `#${t}`).join(" ")}</p>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{existing ? "Edit hashtag group" : "New hashtag group"}</DialogTitle></DialogHeader>
          <form key={existing?.id ?? "new"} className="space-y-4" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); save.mutate({ id: existing?.id, body: { name: String(fd.get("name")), tags: String(fd.get("tags")).split(/[\s,]+/).filter(Boolean) } }); }}>
            <div className="space-y-1.5"><Label htmlFor="h-name">Name</Label><Input id="h-name" name="name" required defaultValue={existing?.name ?? ""} autoFocus /></div>
            <div className="space-y-1.5"><Label htmlFor="h-tags">Hashtags</Label><Textarea id="h-tags" name="tags" rows={3} required defaultValue={existing?.tags.map((t) => `#${t}`).join(" ") ?? ""} placeholder="#spark #marketing #launch" /></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" disabled={save.isPending}>Save</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}


function SourcesTab() {
  const brand = useBrand();
  const { data = [], isPending } = useFeeds(brand.id);
  const { data: accounts = [] } = useAccounts(brand.id);
  const create = useCreateFeed(brand.id);
  const update = useUpdateFeed(brand.id);
  const remove = useDeleteFeed(brand.id);
  const { data: session } = useSession();
  const canEdit = session?.user?.role !== "viewer";
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-ink-2"><RepurposeButton /><span>Turn a page, pasted text or a transcript into drafts for every channel.</span></div>
        {isPending ? <Skeleton className="h-40" /> : data.length === 0 ? (
          <EmptyState icon={Rss} title="No RSS sources yet" body="Every new item in a feed becomes a draft (optionally written by AI for each channel), or goes straight into the queue." />
        ) : (
          <ul className="divide-y divide-line rounded-card border border-line bg-surface">
            {data.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 flex-1"><div className="font-medium">{f.name || f.url}</div><div className="truncate text-xs text-ink-2">{f.url}{f.last_checked_at && ` · checked ${new Date(f.last_checked_at).toLocaleString()}`}</div>
                  <div className="mt-1 flex gap-1">{f.account_ids.map((id) => { const a = accounts.find((x) => x.id === id); return a ? <PlatformMark key={id} platform={a.platform} size={12} /> : null; })}</div></div>
                {canEdit && <><label className="flex items-center gap-1.5 text-xs"><Switch checked={f.use_ai} onCheckedChange={(v) => update.mutate({ id: f.id, body: { use_ai: v } })} />AI text</label>
                  <label className="flex items-center gap-1.5 text-xs"><Switch checked={f.auto_queue} onCheckedChange={(v) => update.mutate({ id: f.id, body: { auto_queue: v } })} />Auto-queue</label>
                  <label className="flex items-center gap-1.5 text-xs"><Switch checked={f.is_active} onCheckedChange={(v) => update.mutate({ id: f.id, body: { is_active: v } })} />Active</label>
                  <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Remove feed" onClick={() => confirm("Remove this feed?") && remove.mutate(f.id)}><Trash2 className="size-4" /></Button></>}
              </li>
            ))}
          </ul>
        )}
      </div>
      {canEdit && (
        <form className="space-y-3 self-start rounded-card border border-line bg-surface p-4" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); const form = e.currentTarget;
          create.mutate({ url: String(fd.get("url")), name: String(fd.get("name")) || null, use_ai: fd.get("use_ai") === "on", auto_queue: fd.get("auto_queue") === "on", account_ids: fd.getAll("account_ids").map(Number) }, { onSuccess: () => form.reset() }); }}>
          <h2 className="font-semibold">Add a feed</h2>
          <div className="space-y-1.5"><Label htmlFor="f-url">Feed URL</Label><Input id="f-url" name="url" type="url" required placeholder="https://blog.example.com/rss.xml" /></div>
          <div className="space-y-1.5"><Label htmlFor="f-name">Name</Label><Input id="f-name" name="name" placeholder="Company blog" /></div>
          <div className="space-y-1.5"><Label>Post to</Label><div className="flex flex-wrap gap-1.5">{accounts.filter((a) => a.is_active).map((a) => <label key={a.id} className="flex items-center gap-1 rounded-control border border-line px-2 py-1 text-xs"><input type="checkbox" name="account_ids" value={a.id} defaultChecked className="accent-[var(--brand)]" /><PlatformMark platform={a.platform} size={12} />{a.handle}</label>)}</div></div>
          <label className="flex items-center gap-2 text-sm"><Switch name="use_ai" defaultChecked />Write the post with AI per channel</label>
          <label className="flex items-center gap-2 text-sm"><Switch name="auto_queue" />Queue automatically (otherwise drafts)</label>
          <Button type="submit" className="w-full" disabled={create.isPending}>Add feed</Button>
        </form>
      )}
    </div>
  );
}
