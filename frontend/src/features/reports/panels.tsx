/** Reports on the Analytics page: the list and the "new report" dialog. */
import { useState, type FormEvent } from "react";
import { Download, FileText, Trash2 } from "lucide-react";
import { useBrand, usePerms } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { csvUrl, reportPath, useCreateReport, useDeleteReport, useReports } from "@/features/reports/api";
import { fmtDay } from "@/lib/time";

const iso = (d: Date) => d.toISOString().slice(0, 10);
const presets = () => {
  const today = new Date();
  const ago = (n: number) => { const d = new Date(today); d.setDate(d.getDate() - n); return d; };
  const first = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastFirst = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  const lastEnd = new Date(today.getFullYear(), today.getMonth(), 0);
  return [
    { label: "Last 7 days", start: iso(ago(6)), end: iso(today) },
    { label: "Last 30 days", start: iso(ago(29)), end: iso(today) },
    { label: "Last month", start: iso(lastFirst), end: iso(lastEnd) },
    { label: "This month", start: iso(first), end: iso(today) },
    { label: "Last 90 days", start: iso(ago(89)), end: iso(today) },
  ];
};

export function ReportsSection() {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data = [], isPending } = useReports(brand.id);
  const create = useCreateReport(brand.id);
  const remove = useDeleteReport(brand.id);
  const [open, setOpen] = useState(false);
  const [range, setRange] = useState(() => presets()[1]);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    create.mutate({ start: String(fd.get("start")), end: String(fd.get("end")), title: String(fd.get("title") || "").trim() || null }, {
      onSuccess: (r) => { setOpen(false); window.open(reportPath(brand.id, r.id), "_blank", "noopener"); },
    });
  };
  return (
    <section className="rounded-card border border-line bg-surface">
      <header className="flex items-center justify-between border-b border-line px-5 py-3">
        <div><h2 className="font-semibold">Reports</h2><p className="text-xs text-ink-2">A period's numbers frozen on a page you can print to PDF or export as CSV, with an AI summary of what worked.</p></div>
        {canEdit && <Button size="sm" onClick={() => setOpen(true)}><FileText className="size-4" />New report</Button>}
      </header>
      {isPending ? <Skeleton className="m-5 h-16" /> : data.length === 0 ? <p className="px-5 py-4 text-sm text-ink-2">No reports yet. The first one takes a few seconds.</p> : (
        <ul className="divide-y divide-line">
          {data.map((r) => {
            const t = (r.data as { totals?: { published?: number; impressions?: number; engagements?: number } }).totals ?? {};
            return (
              <li key={r.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <a href={reportPath(brand.id, r.id)} target="_blank" rel="noopener" className="font-medium hover:underline">{r.title}</a>
                  <div className="text-xs text-ink-2 tnum">{fmtDay(r.start, { day: "numeric", month: "short" })} – {fmtDay(r.end, { day: "numeric", month: "short", year: "numeric" })} · {t.published ?? 0} posts · {new Intl.NumberFormat().format(t.engagements ?? 0)} engagements{r.summary ? " · summary written" : ""}</div>
                </div>
                <Button asChild size="sm" variant="ghost"><a href={csvUrl(brand.id, r.id)} aria-label={`Download ${r.title} as CSV`}><Download className="size-4" />CSV</a></Button>
                {canEdit && <Button size="icon" variant="ghost" aria-label={`Delete ${r.title}`} onClick={() => confirm(`Delete the report “${r.title}”?`) && remove.mutate(r.id)}><Trash2 className="size-4" /></Button>}
              </li>
            );
          })}
        </ul>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New report</DialogTitle></DialogHeader>
          <form className="space-y-4" onSubmit={submit}>
            <div className="flex flex-wrap gap-1.5">{presets().map((p) => <button key={p.label} type="button" onClick={() => setRange(p)} className={`rounded-full border px-2.5 py-1 text-xs ${range.label === p.label ? "border-brand bg-brand-soft" : "border-line text-ink-2"}`}>{p.label}</button>)}</div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label htmlFor="rp-start">From</Label><Input id="rp-start" name="start" type="date" value={range.start} onChange={(e) => setRange({ ...range, label: "Custom", start: e.target.value })} required /></div>
              <div className="space-y-1.5"><Label htmlFor="rp-end">To</Label><Input id="rp-end" name="end" type="date" value={range.end} onChange={(e) => setRange({ ...range, label: "Custom", end: e.target.value })} required /></div>
            </div>
            <div className="space-y-1.5"><Label htmlFor="rp-title">Title (optional)</Label><Input id="rp-title" name="title" placeholder={`${brand.name} · October`} /></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" disabled={create.isPending}>{create.isPending ? "Counting…" : "Make the report"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
