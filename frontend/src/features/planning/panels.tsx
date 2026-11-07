/** Planning pieces: content pillars, guardrails, CSV import. */
import { useState, type FormEvent } from "react";
import { Pencil, Trash2, Upload } from "lucide-react";
import { useBrand, usePerms } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateBrand } from "@/features/api4";
import { useCreatePillar, useDeletePillar, useImportPosts, usePillars, useUpdatePillar, type PillarOut, type PostImportOut } from "@/features/planning/api";
import { cn } from "@/lib/utils";

// ---- pillars ---------------------------------------------------------------------------------
export function PillarsSection() {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data = [], isPending } = usePillars(brand.id);
  const create = useCreatePillar(brand.id);
  const update = useUpdatePillar(brand.id);
  const remove = useDeletePillar(brand.id);
  const [editing, setEditing] = useState<PillarOut | "new" | null>(null);
  const total = data.reduce((n, p) => n + p.posts_30d, 0);
  const targetSum = data.reduce((n, p) => n + p.target_share, 0);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const body = { name: String(fd.get("name")).trim(), color: String(fd.get("color")), target_share: Number(fd.get("target_share") || 0), description: String(fd.get("description") || "").trim() || null };
    if (editing === "new") create.mutate(body, { onSuccess: () => setEditing(null) });
    else if (editing) update.mutate({ id: editing.id, body }, { onSuccess: () => setEditing(null) });
  };
  return (
    <section className="rounded-card border border-line bg-surface">
      <header className="flex items-center justify-between border-b border-line px-5 py-3">
        <div><h3 className="font-semibold">Content pillars</h3><p className="text-xs text-ink-2">The themes {brand.name} keeps coming back to, and how much of the feed each should get.</p></div>
        {canEdit && <Button size="sm" variant="outline" onClick={() => setEditing("new")}>Add a pillar</Button>}
      </header>
      {isPending ? <Skeleton className="m-5 h-16" /> : data.length === 0 ? (
        <p className="px-5 py-4 text-sm text-ink-2">No pillars yet. Three to five themes (say Education, Behind the scenes, Offers) keep a feed balanced and give the planner something to aim for.</p>
      ) : (
        <ul className="divide-y divide-line">
          {data.map((p) => {
            const actual = total ? Math.round((p.posts_30d / total) * 100) : 0;
            return (
              <li key={p.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <span className="size-3 shrink-0 rounded-full" style={{ background: p.color }} aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{p.name}{p.description && <span className="ml-2 font-normal text-ink-2">{p.description}</span>}</div>
                  <div className="mt-1 flex items-center gap-2 text-xs text-ink-2">
                    <span className="relative h-1.5 w-32 overflow-hidden rounded bg-hover" title={`Target ${p.target_share}%, last 30 days ${actual}%`}>
                      <span className="absolute inset-y-0 left-0 rounded" style={{ width: `${Math.min(100, actual)}%`, background: p.color }} />
                      {p.target_share > 0 && <span className="absolute inset-y-0 w-px bg-ink" style={{ left: `${Math.min(100, p.target_share)}%` }} />}
                    </span>
                    <span className="tnum">{actual}% of the last 30 days{p.target_share ? ` · target ${p.target_share}%` : ""} · {p.posts_30d} {p.posts_30d === 1 ? "post" : "posts"}</span>
                  </div>
                </div>
                {canEdit && (
                  <span className="flex gap-0.5">
                    <Button size="icon" variant="ghost" aria-label={`Edit ${p.name}`} onClick={() => setEditing(p)}><Pencil className="size-4" /></Button>
                    <Button size="icon" variant="ghost" aria-label={`Remove ${p.name}`} onClick={() => confirm(`Remove the pillar ${p.name}? Posts keep their text and lose the tag.`) && remove.mutate(p.id)}><Trash2 className="size-4" /></Button>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {data.length > 0 && targetSum > 0 && targetSum !== 100 && <p className="border-t border-line px-5 py-2 text-xs text-st-pending">Targets add up to {targetSum}%, not 100%.</p>}
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing === "new" ? "New pillar" : "Edit pillar"}</DialogTitle></DialogHeader>
          <form key={editing === "new" ? "new" : editing?.id} className="space-y-4" onSubmit={submit}>
            <div className="grid grid-cols-[1fr_auto] gap-3">
              <div className="space-y-1.5"><Label htmlFor="p-name">Name</Label><Input id="p-name" name="name" required maxLength={80} autoFocus defaultValue={editing !== "new" ? editing?.name : ""} /></div>
              <div className="space-y-1.5"><Label htmlFor="p-color">Colour</Label><Input id="p-color" name="color" type="color" className="h-9 w-14 p-1" defaultValue={editing !== "new" ? editing?.color : "#6D4AE0"} /></div>
            </div>
            <div className="space-y-1.5"><Label htmlFor="p-share">Target share of posts, %</Label><Input id="p-share" name="target_share" type="number" min={0} max={100} defaultValue={editing !== "new" ? editing?.target_share : 0} /><p className="text-xs text-ink-2">0 means no target. The planner and the pillar bar use it.</p></div>
            <div className="space-y-1.5"><Label htmlFor="p-desc">What belongs here</Label><Textarea id="p-desc" name="description" rows={2} defaultValue={editing !== "new" ? editing?.description ?? "" : ""} placeholder="Tips, how-tos, answers to common questions" /></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" disabled={create.isPending || update.isPending}>{editing === "new" ? "Add pillar" : "Save"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}

// ---- guardrails --------------------------------------------------------------------------------
const lines = (v: FormDataEntryValue | null) => String(v ?? "").split(/\r?\n|,/).map((s) => s.trim()).filter(Boolean).slice(0, 100);

export function GuardrailsSection() {
  const brand = useBrand();
  const { canManage } = usePerms();
  const update = useUpdateBrand(brand.id);
  const cfg = (brand.agent_config ?? {}) as { never_say?: string[]; avoid_topics?: string[]; keywords?: string[] };
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    update.mutate({ agent_config: { ...cfg, never_say: lines(fd.get("never_say")), avoid_topics: lines(fd.get("avoid_topics")), keywords: lines(fd.get("keywords")) } });
  };
  return (
    <form className="rounded-card border border-line bg-surface" onSubmit={submit}>
      <header className="border-b border-line px-5 py-3"><h3 className="font-semibold">Guardrails</h3><p className="text-xs text-ink-2">Checked on every post before it goes out, and handed to the AI in every request. One item per line.</p></header>
      <div className="grid gap-4 p-5 sm:grid-cols-3">
        <div className="space-y-1.5"><Label htmlFor="g-never">Never say</Label><Textarea id="g-never" name="never_say" rows={5} defaultValue={(cfg.never_say ?? []).join("\n")} placeholder={"cheap\nguaranteed results"} readOnly={!canManage} /><p className="text-xs text-ink-2">A post with one of these stays a draft.</p></div>
        <div className="space-y-1.5"><Label htmlFor="g-avoid">Topics to avoid</Label><Textarea id="g-avoid" name="avoid_topics" rows={5} defaultValue={(cfg.avoid_topics ?? []).join("\n")} placeholder={"politics\ncompetitor names"} readOnly={!canManage} /><p className="text-xs text-ink-2">Shown as a warning, not blocked.</p></div>
        <div className="space-y-1.5"><Label htmlFor="g-kw">Keywords people search for</Label><Textarea id="g-kw" name="keywords" rows={5} defaultValue={(cfg.keywords ?? []).join("\n")} placeholder={"design workshop\nbrand strategy"} readOnly={!canManage} /><p className="text-xs text-ink-2">A gentle nudge when a post uses none of them.</p></div>
      </div>
      {canManage && <div className="border-t border-line px-5 py-3"><Button type="submit" size="sm" disabled={update.isPending}>Save guardrails</Button></div>}
    </form>
  );
}

// ---- CSV import -----------------------------------------------------------------------------------
export function ImportCsvButton({ className }: { className?: string }) {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const run = useImportPosts(brand.id);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [result, setResult] = useState<PostImportOut | null>(null);
  if (!canEdit) return null;
  const close = () => { setOpen(false); setResult(null); setText(""); };
  const onFile = (f: File | undefined) => { if (f) void f.text().then(setText); };
  return (
    <>
      <Button size="sm" variant="outline" className={className} onClick={() => setOpen(true)}><Upload className="size-4" />Import CSV</Button>
      <Dialog open={open} onOpenChange={(o) => !o && close()}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader><DialogTitle>Import posts from a CSV</DialogTitle></DialogHeader>
          {result ? (
            <div className="space-y-3 text-sm">
              <p>{result.created} {result.created === 1 ? "post" : "posts"} imported into {brand.name}. Rows with a date are scheduled; the rest are drafts.</p>
              {result.errors.length > 0 && <ul className="max-h-48 space-y-1 overflow-y-auto rounded-control border border-line p-3 text-xs">{result.errors.map((e) => <li key={e.row}><span className="font-medium tnum">Row {e.row}:</span> {e.error}</li>)}</ul>}
              <DialogFooter><Button onClick={close}>Done</Button></DialogFooter>
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <p className="text-ink-2">Columns: <code className="rounded bg-hover px-1">content, link, when, channels, pillar</code>. <code className="rounded bg-hover px-1">when</code> is <code className="rounded bg-hover px-1">YYYY-MM-DD HH:MM</code> in {brand.timezone}; leave it empty for a draft. Channels are handles or platforms separated by <code className="rounded bg-hover px-1">;</code>, empty means every channel.</p>
              <Input type="file" accept=".csv,text/csv" onChange={(e) => onFile(e.target.files?.[0])} aria-label="CSV file" />
              <Textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={"content,link,when,channels\n\"Three tips for better briefs\",https://example.com/briefs,2026-11-12 09:00,linkedin\nA draft for later,,,"} className={cn("font-mono text-xs")} aria-label="CSV text" />
              <DialogFooter><Button variant="ghost" onClick={close}>Cancel</Button><Button disabled={!text.trim() || run.isPending} onClick={() => run.mutate(text, { onSuccess: setResult })}>{run.isPending ? "Importing…" : "Import"}</Button></DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
