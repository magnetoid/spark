/** Reports on the Analytics page: the list and the "new report" dialog. */
import { useState, type FormEvent } from "react";
import { CalendarClock, Download, FileText, Trash2 } from "lucide-react";
import { useBrand, usePerms, useSession } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { csvUrl, reportPath, useCreateReport, useCreateReportSchedule, useDeleteReport, useDeleteReportSchedule, useReports, useReportSchedules, useUpdateReportSchedule, type ReportScheduleOut } from "@/features/reports/api";
import { fmtDateTime, fmtDay } from "@/lib/time";

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
      {canEdit && <ScheduledReports />}
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

// ---- scheduled reports --------------------------------------------------------------------------
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;

function ScheduledReports() {
  const brand = useBrand();
  const { data = [], isPending } = useReportSchedules(brand.id);
  const update = useUpdateReportSchedule(brand.id);
  const remove = useDeleteReportSchedule(brand.id);
  const [editing, setEditing] = useState<ReportScheduleOut | "new" | null>(null);
  return (
    <div className="border-t border-line px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h3 className="text-sm font-semibold">Sent on a schedule</h3><p className="text-xs text-ink-2">Spark makes the report after each week or month and emails a link that opens without an account.</p></div>
        <Button size="sm" variant="outline" onClick={() => setEditing("new")}><CalendarClock className="size-4" />Schedule a report</Button>
      </div>
      {isPending ? <Skeleton className="mt-3 h-10" /> : data.length > 0 && (
        <ul className="mt-3 divide-y divide-line rounded-control border border-line">
          {data.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
              <div className="min-w-0 flex-1">
                <div className="font-medium">{s.cadence === "weekly" ? "Weekly, Mondays" : "Monthly, on the 1st"} at {hh(s.hour)} <span className="font-normal text-ink-2">to {s.recipients.join(", ")}</span></div>
                <div className="text-xs text-ink-2 tnum">
                  {s.is_active ? <>Next: {fmtDay(s.next_period.start, { day: "numeric", month: "short" })} – {fmtDay(s.next_period.end, { day: "numeric", month: "short" })}, sent {fmtDateTime(s.next_period.send_at, brand.timezone)}</> : "Paused"}
                  {s.last_sent_at && <> · last sent {fmtDateTime(s.last_sent_at, brand.timezone)}</>}
                </div>
                {s.last_error && <div className="text-xs text-st-failed">{s.last_error}</div>}
              </div>
              <label className="flex items-center gap-2 text-xs text-ink-2"><Switch checked={s.is_active} onCheckedChange={(v) => update.mutate({ id: s.id, body: { is_active: v } })} aria-label={s.is_active ? "Pause this schedule" : "Resume this schedule"} />{s.is_active ? "On" : "Paused"}</label>
              <Button size="sm" variant="ghost" onClick={() => setEditing(s)}>Edit</Button>
              <Button size="icon" variant="ghost" className="size-8 text-ink-2" aria-label="Remove this schedule" onClick={() => confirm("Stop sending this report? Reports already sent stay.") && remove.mutate(s.id)}><Trash2 className="size-4" /></Button>
            </li>
          ))}
        </ul>
      )}
      <ScheduleDialog editing={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

function ScheduleDialog({ editing, onClose }: { editing: ReportScheduleOut | "new" | null; onClose: () => void }) {
  const existing = editing && editing !== "new" ? editing : null;
  return (
    <Dialog open={editing !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{existing ? "Edit scheduled report" : "Schedule a report"}</DialogTitle></DialogHeader>
        {/* mounted per opening, so its fields start from the schedule being edited */}
        {editing !== null && <ScheduleForm key={existing?.id ?? "new"} existing={existing} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function ScheduleForm({ existing, onClose }: { existing: ReportScheduleOut | null; onClose: () => void }) {
  const brand = useBrand();
  const { data: session } = useSession();
  const create = useCreateReportSchedule(brand.id);
  const update = useUpdateReportSchedule(brand.id);
  const [cadence, setCadence] = useState(existing?.cadence ?? "weekly");
  const [hour, setHour] = useState(String(existing?.hour ?? 8));
  const [days, setDays] = useState(String(existing?.share_days ?? 30));
  const [error, setError] = useState<string | null>(null);
  const submit = (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    const fd = new FormData(ev.currentTarget);
    const recipients = String(fd.get("recipients")).split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
    if (!recipients.length) { setError("Add at least one email address."); return; }
    const body = { cadence: cadence as "weekly" | "monthly", hour: Number(hour), recipients, share_days: Number(days), with_summary: session?.features.ai ? fd.get("with_summary") === "on" : existing?.with_summary ?? true };
    if (existing) update.mutate({ id: existing.id, body }, { onSuccess: onClose });
    else create.mutate(body, { onSuccess: onClose });
  };
  return (
    <form className="space-y-4" onSubmit={submit}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5"><Label>How often</Label>
          <Select value={cadence} onValueChange={setCadence}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="weekly">Weekly, the last Monday to Sunday</SelectItem><SelectItem value="monthly">Monthly, the last month</SelectItem></SelectContent></Select>
        </div>
        <div className="space-y-1.5"><Label>Sent at</Label>
          <Select value={hour} onValueChange={setHour}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{HOURS.map((h) => <SelectItem key={h} value={String(h)}>{hh(h)}</SelectItem>)}</SelectContent></Select>
          <p className="text-xs text-ink-2">{brand.timezone}</p>
        </div>
      </div>
      <div className="space-y-1.5"><Label htmlFor="rs-to">Send to</Label>
        <Textarea id="rs-to" name="recipients" rows={2} defaultValue={existing ? existing.recipients.join(", ") : session?.user?.email ?? ""} placeholder="client@example.com, you@agency.com" aria-invalid={!!error} aria-describedby="rs-to-help" onChange={() => error && setError(null)} />
        <p id="rs-to-help" className={error ? "text-xs text-st-failed" : "text-xs text-ink-2"}>{error ?? "Up to 20 addresses, separated by commas. They don't need a Spark account."}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5"><Label>The link works for</Label>
          <Select value={days} onValueChange={setDays}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["7", "30", "90", "365"].map((d) => <SelectItem key={d} value={d}>{d} days</SelectItem>)}</SelectContent></Select>
        </div>
        {session?.features.ai && <label className="flex items-center gap-2 self-end pb-2 text-sm"><Switch name="with_summary" defaultChecked={existing?.with_summary ?? true} />Add an AI summary</label>}
      </div>
      <DialogFooter><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={create.isPending || update.isPending}>{existing ? "Save" : "Schedule"}</Button></DialogFooter>
    </form>
  );
}
