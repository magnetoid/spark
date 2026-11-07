/** The Ideas board: four columns, drag between them, turn an idea into a post. */
import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { GripVertical, Lightbulb, MoreHorizontal, Plus, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useBrand, usePerms, useSession } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useComposer } from "@/features/composer/composer-host";
import { keys, useIdeas, type IdeaOut } from "@/features/posts/api";
import { api, unwrap } from "@/lib/api";
import { cn } from "@/lib/utils";

const COLUMNS = [["idea", "Ideas"], ["drafting", "Drafting"], ["ready", "Ready"], ["done", "Done"]] as const;
const TAG_COLORS = ["#2F6FED", "#1F8F5F", "#D13B3B", "#F2A516", "#6D4AE0", "#0E9AA7", "#DB2777", "#65A30D"];
const tagColor = (t: string) => TAG_COLORS[[...t].reduce((a, c) => a + c.charCodeAt(0), 0) % TAG_COLORS.length];

export function IdeasPage() {
  const brand = useBrand();
  const [tag, setTag] = useState<string | undefined>();
  const { data, isPending } = useIdeas(brand.id, tag);
  const [editing, setEditing] = useState<IdeaOut | "new" | null>(null);
  const qc = useQueryClient();
  const composer = useComposer();
  const { data: session } = useSession();
  const { canEdit } = usePerms();
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.ideas(brand.id) });
  const bp = (idea_id: number) => ({ params: { path: { brand_id: brand.id, idea_id } } });

  const move = useMutation({
    mutationFn: async ({ id, status, position }: { id: number; status: string; position: number }) => unwrap(await api.POST("/brands/{brand_id}/ideas/{idea_id}/move", { ...bp(id), body: { status, position } })),
    onSuccess: () => void invalidate(), onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/ideas/{idea_id}", bp(id))),
    onSuccess: () => { void invalidate(); toast.success("Idea deleted"); }, onError: (e) => toast.error(e.message),
  });
  const expand = useMutation({
    mutationFn: async (id: number) => unwrap(await api.POST("/brands/{brand_id}/ideas/{idea_id}/ai", bp(id))),
    onSuccess: () => { void invalidate(); toast.success("Draft written. Review it on the card."); }, onError: (e) => toast.error(e.message),
  });
  const toPost = useMutation({
    mutationFn: async (idea: IdeaOut) => idea.post_id ? { post: { id: idea.post_id } } : unwrap(await api.POST("/brands/{brand_id}/ideas/{idea_id}/to-post", bp(idea.id))),
    onSuccess: (r) => { void invalidate(); composer.open({ postId: r.post.id }); }, onError: (e) => toast.error(e.message),
  });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const byStatus = useMemo(() => {
    const m: Record<string, IdeaOut[]> = { idea: [], drafting: [], ready: [], done: [] };
    for (const i of data?.items ?? []) (m[i.status] ??= []).push(i);
    return m;
  }, [data]);

  const onDragEnd = (e: DragEndEvent) => {
    const id = Number(e.active.id);
    const status = e.over?.id ? String(e.over.id).replace(/^col:/, "") : null;
    const idea = data?.items.find((i) => i.id === id);
    if (!idea || !status || idea.status === status) return;
    const top = Math.min(0, ...byStatus[status].map((i) => i.position)) - 1;
    move.mutate({ id, status, position: top });
  };

  return (
    <>
      <PageHeader title="Ideas" description="A scratchpad for what you might post. Drag cards as they ripen."
                  actions={canEdit && <Button size="sm" onClick={() => setEditing("new")}><Plus className="size-4" />New idea</Button>} />
      {data && data.tags.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          <TagChip label="All" active={!tag} onClick={() => setTag(undefined)} />
          {data.tags.map((t) => <TagChip key={t} label={`#${t}`} color={tagColor(t)} active={tag === t} onClick={() => setTag(tag === t ? undefined : t)} />)}
        </div>
      )}
      {isPending ? <div className="grid gap-4 md:grid-cols-4">{COLUMNS.map(([k]) => <Skeleton key={k} className="h-64" />)}</div>
       : data?.items.length === 0 && !tag ? (
        <EmptyState icon={Lightbulb} title="No ideas yet" body="Capture half-thoughts here. Expand them with AI, then turn the good ones into posts."
                    action={canEdit && <Button size="sm" onClick={() => setEditing("new")}>Add the first idea</Button>} />
      ) : (
        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <div className="grid gap-4 md:grid-cols-4">
            {COLUMNS.map(([key, label]) => (
              <Column key={key} id={key} label={label} count={byStatus[key].length}>
                {byStatus[key].map((i) => (
                  <Card key={i.id} idea={i} canEdit={canEdit} ai={session?.features.ai ?? false} busy={expand.isPending && expand.variables === i.id}
                        onEdit={() => setEditing(i)} onDelete={() => confirm("Delete this idea?") && remove.mutate(i.id)}
                        onExpand={() => expand.mutate(i.id)} onToPost={() => toPost.mutate(i)}
                        onMove={(status) => move.mutate({ id: i.id, status, position: Math.min(0, ...byStatus[status].map((x) => x.position)) - 1 })} />
                ))}
              </Column>
            ))}
          </div>
        </DndContext>
      )}
      <IdeaDialog brandId={brand.id} idea={editing} onClose={() => setEditing(null)} onSaved={() => { void invalidate(); setEditing(null); }} />
    </>
  );
}

function TagChip({ label, color, active, onClick }: { label: string; color?: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={cn("rounded-full border px-2.5 py-0.5 text-xs", active ? "border-ink bg-ink text-paper" : "border-line text-ink-2 hover:text-ink")}
            style={!active && color ? { color } : undefined}>{label}</button>
  );
}

function Column({ id, label, count, children }: { id: string; label: string; count: number; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: `col:${id}` });
  return (
    <section ref={setNodeRef} className={cn("flex min-h-64 flex-col rounded-card border border-line bg-paper/60 p-2", isOver && "border-brand bg-brand-soft/50")}>
      <h2 className="flex items-center justify-between px-1.5 pb-2 text-sm font-semibold">{label}<span className="text-xs font-normal text-ink-2 tnum">{count}</span></h2>
      <div className="flex-1 space-y-2">{children}</div>
    </section>
  );
}

function Card({ idea, canEdit, ai, busy, onEdit, onDelete, onExpand, onToPost, onMove }: {
  idea: IdeaOut; canEdit: boolean; ai: boolean; busy: boolean; onEdit: () => void; onDelete: () => void; onExpand: () => void; onToPost: () => void; onMove: (s: string) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: idea.id, disabled: !canEdit });
  return (
    <article ref={setNodeRef} className={cn("group rounded-card border border-line bg-surface p-3 text-sm shadow-xs", isDragging && "opacity-50")}>
      <div className="flex items-start gap-1.5">
        {canEdit && (
          <button type="button" {...attributes} {...listeners} aria-label={`Drag ${idea.title}`} title="Drag to another column"
                  className="-ml-1.5 -mt-0.5 cursor-grab touch-none rounded p-1 text-ink-2/60 hover:bg-hover hover:text-ink focus-visible:text-ink">
            <GripVertical className="size-4" />
          </button>
        )}
        <h3 className="min-w-0 flex-1 font-medium">{idea.title}</h3>
        {canEdit && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild><button type="button" className="-mr-1 -mt-1 rounded p-1 text-ink-2 hover:bg-hover hover:text-ink" aria-label="Idea actions"><MoreHorizontal className="size-4" /></button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={onEdit}>Edit</DropdownMenuItem>
              {ai && <DropdownMenuItem onSelect={onExpand}><Sparkles className="size-4" />Expand with AI</DropdownMenuItem>}
              <DropdownMenuItem onSelect={onToPost}>{idea.post_id ? "Open the post" : "Turn into a post"}</DropdownMenuItem>
              {COLUMNS.filter(([k]) => k !== idea.status).map(([k, l]) => <DropdownMenuItem key={k} onSelect={() => onMove(k)}>Move to {l}</DropdownMenuItem>)}
              <DropdownMenuItem variant="destructive" onSelect={onDelete}>Delete</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      {idea.body && <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-ink-2">{busy ? "Writing…" : idea.body}</p>}
      {(idea.tags.length > 0 || idea.source_url || idea.post_id) && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          {idea.tags.map((t) => <span key={t} className="rounded-full px-1.5 py-0.5" style={{ color: tagColor(t), background: `${tagColor(t)}1a` }}>#{t}</span>)}
          {idea.source_url && <a href={idea.source_url} target="_blank" rel="noopener" className="truncate text-ink-2 underline">source</a>}
          {idea.post_id && <span className="ml-auto text-ink-2">post #{idea.post_id}</span>}
        </div>
      )}
    </article>
  );
}

function IdeaDialog({ brandId, idea, onClose, onSaved }: { brandId: number; idea: IdeaOut | "new" | null; onClose: () => void; onSaved: () => void }) {
  const open = idea !== null;
  const existing = idea && idea !== "new" ? idea : null;
  const save = useMutation({
    mutationFn: async (form: { title: string; body: string; tags: string; source_url: string }) => {
      const body = { title: form.title, body: form.body || null, tags: form.tags.split(/[,\s]+/).filter(Boolean), source_url: form.source_url || null };
      return existing
        ? unwrap(await api.PATCH("/brands/{brand_id}/ideas/{idea_id}", { params: { path: { brand_id: brandId, idea_id: existing.id } }, body }))
        : unwrap(await api.POST("/brands/{brand_id}/ideas", { params: { path: { brand_id: brandId } }, body: { ...body, status: "idea" } }));
    },
    onSuccess: () => { toast.success(existing ? "Idea updated" : "Idea added"); onSaved(); },
    onError: (e) => toast.error(e.message),
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    save.mutate({ title: String(fd.get("title")), body: String(fd.get("body")), tags: String(fd.get("tags")), source_url: String(fd.get("source_url")) });
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{existing ? "Edit idea" : "New idea"}</DialogTitle></DialogHeader>
        <form key={existing?.id ?? "new"} onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5"><Label htmlFor="i-title">Title</Label><Input id="i-title" name="title" required maxLength={200} defaultValue={existing?.title ?? ""} autoFocus /></div>
          <div className="space-y-1.5"><Label htmlFor="i-body">Notes</Label><Textarea id="i-body" name="body" rows={4} defaultValue={existing?.body ?? ""} placeholder="Angle, facts, a rough draft…" /></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5"><Label htmlFor="i-tags">Tags</Label><Input id="i-tags" name="tags" defaultValue={existing?.tags.join(" ") ?? ""} placeholder="launch, tips" /></div>
            <div className="space-y-1.5"><Label htmlFor="i-url">Source link</Label><Input id="i-url" name="source_url" type="url" defaultValue={existing?.source_url ?? ""} placeholder="https://" /></div>
          </div>
          <DialogFooter><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={save.isPending}>{existing ? "Save" : "Add idea"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
