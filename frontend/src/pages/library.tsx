/** Library: media, templates and hashtag groups the composer draws from. */
import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { Hash, Images, LayoutTemplate, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { useBrand, useSession } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { keys, uploadMedia, useHashtagGroups, useMedia, useTemplates, type HashtagGroupOut, type MediaOut, type TemplateOut } from "@/features/posts/api";
import { api, unwrap } from "@/lib/api";
import { cn } from "@/lib/utils";

const TABS = [["media", "Media", Images], ["templates", "Templates", LayoutTemplate], ["hashtags", "Hashtag groups", Hash]] as const;

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
      {tab === "media" ? <MediaTab /> : tab === "templates" ? <TemplatesTab /> : <HashtagsTab />}
    </>
  );
}

function MediaTab() {
  const brand = useBrand();
  const { data, isPending } = useMedia(brand.id);
  const qc = useQueryClient();
  const { data: session } = useSession();
  const canEdit = session?.user?.role !== "viewer";
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploads, setUploads] = useState<{ key: string; name: string; pct: number }[]>([]);
  const [dragging, setDragging] = useState(false);
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.media(brand.id) });

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

  return (
    <div onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
         onDrop={(e) => { e.preventDefault(); setDragging(false); if (canEdit) files(e.dataTransfer.files); }} onPaste={(e) => { if (canEdit && e.clipboardData.files.length) files(e.clipboardData.files); }}
         className={cn("rounded-card", dragging && "ring-2 ring-brand")}>
      {canEdit && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Button size="sm" onClick={() => fileRef.current?.click()}><Upload className="size-4" />Upload</Button>
          <input ref={fileRef} type="file" className="sr-only" multiple accept="image/*,video/mp4,video/quicktime" onChange={(e) => { files(e.target.files); e.target.value = ""; }} />
          <span className="text-sm text-ink-2">or drop files anywhere here, or paste an image.</span>
        </div>
      )}
      {isPending ? <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">{Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)}</div>
       : !data?.items.length && !uploads.length ? (
        <EmptyState icon={Images} title="No media yet" body="Images and videos you upload here are one click away in the composer." />
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {uploads.map((u) => <li key={u.key} className="relative grid aspect-square place-items-center rounded-card border border-line bg-hover text-xs text-ink-2 tnum">{u.pct}%<div className="absolute inset-x-0 bottom-0 h-1 bg-line"><div className="h-full bg-brand" style={{ width: `${u.pct}%` }} /></div></li>)}
          {data?.items.map((m) => <MediaTile key={m.id} m={m} canEdit={canEdit} onAlt={(t) => alt.mutate({ id: m.id, alt_text: t })} onDelete={() => confirm(`Delete ${m.name}?`) && remove.mutate(m.id)} />)}
        </ul>
      )}
    </div>
  );
}

function MediaTile({ m, canEdit, onAlt, onDelete }: { m: MediaOut; canEdit: boolean; onAlt: (t: string) => void; onDelete: () => void }) {
  const [editing, setEditing] = useState(false);
  return (
    <li className="group overflow-hidden rounded-card border border-line bg-surface">
      <div className="relative aspect-square bg-hover">
        {m.is_video ? <video src={m.url} className="h-full w-full object-cover" muted /> : <img src={m.url} alt={m.alt_text ?? ""} className="h-full w-full object-cover" loading="lazy" />}
        {canEdit && <button onClick={onDelete} aria-label={`Delete ${m.name}`} className="absolute right-1 top-1 grid size-7 place-items-center rounded-control bg-surface/90 text-ink-2 opacity-0 hover:text-st-failed group-hover:opacity-100 focus:opacity-100"><Trash2 className="size-4" /></button>}
      </div>
      <div className="p-2 text-xs">
        <div className="truncate font-medium" title={m.name}>{m.name}</div>
        {editing ? (
          <form onSubmit={(e) => { e.preventDefault(); onAlt(String(new FormData(e.currentTarget).get("alt"))); setEditing(false); }} className="mt-1 flex gap-1">
            <Input name="alt" defaultValue={m.alt_text ?? ""} placeholder="Describe the image" className="h-7 text-xs" autoFocus /><Button size="sm" className="h-7 px-2">Save</Button>
          </form>
        ) : (
          <button type="button" disabled={!canEdit} onClick={() => setEditing(true)} className={cn("mt-0.5 block w-full truncate text-left", m.alt_text ? "text-ink-2" : "text-st-pending")} title="Alt text">
            {m.alt_text || (canEdit ? "Add alt text" : "No alt text")}
          </button>
        )}
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
