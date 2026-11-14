/**
 * A report, as a page you read on screen and print to PDF. Lives outside the shell so the
 * print has no sidebar: the brand's colour, the period, the numbers, what worked, what next.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowLeft, Check, Copy, Download, Printer, Share2, Sparkles, X } from "lucide-react";
import { useSession } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useRevokeShareLink, useShareLinks } from "@/features/collab/api";
import { csvUrl, usePublicReport, useReport, useShareReport, useSummarizeReport, type ReportData, type ReportSummary } from "@/features/reports/api";
import { ApiError } from "@/lib/api";
import { applyBrandColor } from "@/lib/brand-color";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { fmtDateTime, fmtDay } from "@/lib/time";
import { cn } from "@/lib/utils";

const fmt = (n: number) => new Intl.NumberFormat().format(n);
const minutes = (m: number) => m < 60 ? `${m} min` : m < 48 * 60 ? `${Math.round(m / 6) / 10} h` : `${Math.round(m / 144) / 10} days`;

export function ReportPage() {
  const { brandId, reportId } = useParams({ from: "/brands/$brandId/reports/$reportId" });
  const b = Number(brandId), id = Number(reportId);
  const { data: session } = useSession();
  const brand = session?.brands.find((x) => x.id === b);
  const { data, isPending, error } = useReport(b, id);
  const summarize = useSummarizeReport(b, id);
  const [sharing, setSharing] = useState(false);
  useEffect(() => { if (brand?.color) applyBrandColor(brand.color); }, [brand?.color]);
  const canEdit = brand && brand.role !== "viewer" && brand.role !== "client";
  if (isPending) return <Frame><Skeleton className="h-10 w-80" /><Skeleton className="mt-6 h-64" /></Frame>;
  if (error || !data) return <Frame><p className="text-sm text-st-failed">{error?.message ?? "Could not load this report."}</p></Frame>;
  const s = data.summary as ReportSummary | null;
  return (
    <Frame>
      <div className="mb-6 flex flex-wrap items-center gap-2 print:hidden">
        <Button asChild size="sm" variant="ghost"><Link to="/analytics" search={(p) => p}><ArrowLeft className="size-4" />Analytics</Link></Button>
        <span className="flex-1" />
        {canEdit && session?.features.ai && <Button size="sm" variant="outline" disabled={summarize.isPending} onClick={() => summarize.mutate(undefined)}><Sparkles className="size-4" />{s ? "Rewrite summary" : "Write summary with AI"}</Button>}
        {canEdit && <Button size="sm" variant="outline" onClick={() => setSharing(true)}><Share2 className="size-4" />Share</Button>}
        <Button asChild size="sm" variant="outline"><a href={csvUrl(b, id)}><Download className="size-4" />CSV</a></Button>
        <Button size="sm" onClick={() => window.print()}><Printer className="size-4" />Print / save as PDF</Button>
      </div>
      <ReportView title={data.title} brandName={brand?.name ?? "Report"} d={data.data as ReportData} s={s} />
      {canEdit && <ShareDialog open={sharing} onClose={() => setSharing(false)} brandId={b} reportId={id} timezone={brand?.timezone ?? "UTC"} />}
    </Frame>
  );
}

/** The same report for a client, from a link that needs no account. */
export function PublicReportPage() {
  const { token } = useParams({ from: "/r/$token" });
  const { data, isPending, error } = usePublicReport(token);
  useEffect(() => { if (data?.brand.color) applyBrandColor(data.brand.color); }, [data?.brand.color]);
  if (isPending) return <Frame><Skeleton className="h-10 w-80" /><Skeleton className="mt-6 h-64" /></Frame>;
  if (error || !data) {
    const gone = error instanceof ApiError && error.status === 404;
    return (
      <Frame>
        <div className="rounded-card border border-line bg-surface p-6 text-center">
          <h1 className="display text-2xl font-semibold">{gone ? "This report link no longer works" : "Could not load the report"}</h1>
          <p className="mt-2 text-sm text-ink-2">{gone ? "It may have expired or been revoked. Ask the team for a new one." : error?.message}</p>
        </div>
      </Frame>
    );
  }
  return (
    <Frame>
      <div className="mb-6 flex justify-end print:hidden"><Button size="sm" variant="outline" onClick={() => window.print()}><Printer className="size-4" />Print / save as PDF</Button></div>
      <ReportView title={data.title} brandName={data.brand.name} d={data.data as ReportData} s={data.summary as ReportSummary | null} />
    </Frame>
  );
}

function ShareDialog({ open, onClose, brandId, reportId, timezone }: { open: boolean; onClose: () => void; brandId: number; reportId: number; timezone: string }) {
  const share = useShareReport(brandId, reportId);
  const { data: links = [] } = useShareLinks(brandId);
  const revoke = useRevokeShareLink(brandId);
  const [days, setDays] = useState("30");
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const mine = links.filter((l) => l.kind === "report" && l.report_id === reportId);
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { onClose(); setUrl(null); } }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Share this report</DialogTitle></DialogHeader>
        <p className="text-sm text-ink-2">Anyone with the link sees this report, without an account and without the rest of Spark. The link is shown only once.</p>
        {url ? (
          <div className="flex items-center gap-2">
            <Input readOnly value={url} onFocus={(e) => e.currentTarget.select()} aria-label="Report link" />
            <Button size="sm" onClick={() => { void navigator.clipboard.writeText(url); setCopied(true); }}>{copied ? <Check className="size-4" /> : <Copy className="size-4" />}{copied ? "Copied" : "Copy"}</Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1.5"><Label>Works for</Label>
              <Select value={days} onValueChange={setDays}><SelectTrigger className="w-36"><SelectValue /></SelectTrigger><SelectContent>{["7", "30", "90", "365"].map((d) => <SelectItem key={d} value={d}>{d} days</SelectItem>)}</SelectContent></Select>
            </div>
            <Button disabled={share.isPending} onClick={() => share.mutate(Number(days), { onSuccess: (r) => { setUrl(r.url); setCopied(false); } })}>Create link</Button>
          </div>
        )}
        {mine.length > 0 && (
          <div>
            <h3 className="mb-1.5 text-sm font-semibold">Links that work now</h3>
            <ul className="space-y-1.5 text-sm">
              {mine.map((l) => (
                <li key={l.id} className="flex items-center gap-2">
                  <span className="tnum">{l.prefix}…</span>
                  <span className="flex-1 text-xs text-ink-2">{l.expires_at ? `until ${fmtDateTime(l.expires_at, timezone)}` : ""}{l.last_used_at ? ` · opened ${fmtDateTime(l.last_used_at, timezone)}` : " · not opened yet"}</span>
                  <Button size="sm" variant="ghost" onClick={() => revoke.mutate(l.id)}><X className="size-3.5" />Revoke</Button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <DialogFooter><Button variant="ghost" onClick={() => { onClose(); setUrl(null); }}>Done</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReportView({ title, brandName, d, s }: { title: string; brandName: string; d: ReportData; s: ReportSummary | null }) {
  const period = `${fmtDay(d.period.start, { day: "numeric", month: "short" })} – ${fmtDay(d.period.end, { day: "numeric", month: "short", year: "numeric" })}`;
  const seen = d.totals.seen ?? d.totals.impressions;
  const wide = [d.totals.reach != null && `${fmt(d.totals.reach)} reach`, d.totals.views != null && `${fmt(d.totals.views)} views`, d.totals.saves != null && `${fmt(d.totals.saves)} saves`].filter(Boolean);
  const byChannel = d.followers.by_channel ?? [];
  const reply = d.inbox.median_reply_minutes;
  return (
    <>
      <header className="mb-8 border-b border-line pb-6">
        <p className="flex items-center gap-2 text-sm text-ink-2"><span className="inline-block size-3 rounded-full bg-brand" aria-hidden />{brandName}</p>
        <h1 className="display mt-1 text-3xl font-semibold leading-tight">{title}</h1>
        <p className="mt-1 text-sm text-ink-2">{period} · {d.period.days} days · made {fmtDay(d.generated_at.slice(0, 10), { day: "numeric", month: "short", year: "numeric" })}</p>
      </header>

      {s && (
        <section className="mb-8 rounded-card border border-line bg-surface p-5 print:border-0 print:p-0">
          <h2 className="display text-xl font-semibold leading-snug">{s.headline}</h2>
          <div className="mt-4 grid gap-6 sm:grid-cols-2">
            <div><h3 className="mb-2 text-sm font-semibold">What worked</h3><ul className="list-disc space-y-1 pl-5 text-sm">{s.worked.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            <div><h3 className="mb-2 text-sm font-semibold">What next</h3><ul className="list-disc space-y-1 pl-5 text-sm">{s.next.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          </div>
        </section>
      )}

      <section className="mb-2 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Posts published" value={d.totals.published} cmp={d.compare.published} />
        <Kpi label="Seen" value={seen} cmp={d.compare.seen ?? d.compare.impressions} />
        <Kpi label="Engagements" value={d.totals.engagements} cmp={d.compare.engagements} />
        <Kpi label="Engagement rate" value={d.totals.engagement_rate_pct} suffix="%" />
        {d.totals.link_clicks !== undefined && <Kpi label="Link clicks" value={d.totals.link_clicks} cmp={d.compare.link_clicks} />}
        <Kpi label="Followers" value={d.followers.end} delta={d.followers.delta} />
      </section>
      <p className="mb-8 text-xs text-ink-2">{wide.length > 0 && <>{wide.join(" · ")}, where the networks report them. </>}Seen counts impressions, or views, or reach, whichever the network reports.</p>

      <section className="mb-8 grid gap-6 lg:grid-cols-5">
        <div className="rounded-card border border-line bg-surface p-4 lg:col-span-3">
          <h3 className="mb-2 text-sm font-semibold">Engagements and impressions by day</h3>
          <div className="h-52">
            <ResponsiveContainer>
              <AreaChart data={d.series} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="day" tickFormatter={(v: string) => fmtDay(v, { day: "numeric", month: "short" })} tick={{ fontSize: 11, fill: "var(--ink-2)" }} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tick={{ fontSize: 11, fill: "var(--ink-2)" }} tickLine={false} axisLine={false} width={36} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }} />
                <Area type="monotone" dataKey="impressions" stroke="var(--ink-2)" fill="var(--hover)" strokeWidth={1.5} name="Impressions" />
                <Area type="monotone" dataKey="engagements" stroke="var(--brand)" fill="var(--brand-soft)" strokeWidth={2} name="Engagements" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-card border border-line bg-surface p-4 lg:col-span-2">
          <h3 className="mb-2 text-sm font-semibold">Followers</h3>
          {d.followers.series.length > 1 ? (
            <div className="h-52"><ResponsiveContainer><LineChart data={d.followers.series} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="day" tickFormatter={(v: string) => fmtDay(v, { day: "numeric", month: "short" })} tick={{ fontSize: 11, fill: "var(--ink-2)" }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "var(--ink-2)" }} tickLine={false} axisLine={false} width={44} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }} />
              <Line type="monotone" dataKey="followers" stroke="var(--brand)" strokeWidth={2} dot={false} name="Followers" />
            </LineChart></ResponsiveContainer></div>
          ) : <p className="text-sm text-ink-2">Follower counts are recorded once a day from now on; the growth line fills in over the coming weeks.</p>}
          {byChannel.length > 0 && (
            <ul className="mt-3 space-y-1 border-t border-line pt-3 text-sm">
              {byChannel.map((c) => <li key={c.account_id} className="flex items-center gap-2"><PlatformMark platform={c.platform} size={13} /><span className="min-w-0 flex-1 truncate">{c.handle}</span><span className="tnum">{fmt(c.end)}</span><span className={cn("w-16 text-right text-xs tnum", c.delta >= 0 ? "text-st-published" : "text-st-failed")}>{c.delta >= 0 ? "+" : ""}{fmt(c.delta)}</span></li>)}
            </ul>
          )}
        </div>
      </section>

      <section className="mb-8 grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold">By channel</h3>
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-left text-xs text-ink-2"><th className="py-1.5 font-medium">Channel</th><th className="py-1.5 text-right font-medium">Posts</th><th className="py-1.5 text-right font-medium">Impr.</th><th className="py-1.5 text-right font-medium">Eng.</th><th className="py-1.5 text-right font-medium">Rate</th></tr></thead>
            <tbody>{d.channels.map((c) => <tr key={c.account_id} className="border-b border-line/60"><td className="flex items-center gap-2 py-1.5"><PlatformMark platform={c.platform} size={13} />{c.handle}<span className="text-xs text-ink-2">{platformLabel(c.platform)}</span></td><td className="py-1.5 text-right tnum">{c.posts}</td><td className="py-1.5 text-right tnum">{fmt(c.impressions)}</td><td className="py-1.5 text-right tnum">{fmt(c.engagements)}</td><td className="py-1.5 text-right tnum">{c.engagement_rate_pct}%</td></tr>)}</tbody>
          </table>
          {d.channels.length === 0 && <p className="text-sm text-ink-2">No published posts with metrics in this period.</p>}
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold">Pillars and the inbox</h3>
          {d.pillars.length > 0 ? (
            <ul className="space-y-1.5 text-sm">{d.pillars.map((p) => <li key={p.name} className="flex items-center gap-2"><span className="size-2.5 rounded-full" style={{ background: p.color }} /><span className="flex-1">{p.name}</span><span className="relative h-1.5 w-28 overflow-hidden rounded bg-hover"><span className="absolute inset-y-0 left-0" style={{ width: `${p.share_pct}%`, background: p.color }} /></span><span className="w-20 text-right text-xs text-ink-2 tnum">{p.share_pct}%{p.target_share ? ` / ${p.target_share}%` : ""}</span></li>)}</ul>
          ) : <p className="text-sm text-ink-2">No pillars tagged in this period.</p>}
          <dl className="mt-4 grid grid-cols-2 gap-3 rounded-card border border-line bg-surface p-3 text-sm sm:grid-cols-4">
            <div><dt className="text-xs text-ink-2">Messages received</dt><dd className="font-medium tnum">{d.inbox.received}</dd></div>
            <div><dt className="text-xs text-ink-2">Answered</dt><dd className="font-medium tnum">{d.inbox.replied}</dd></div>
            <div><dt className="text-xs text-ink-2">Negative</dt><dd className={cn("font-medium tnum", d.inbox.negative && "text-st-failed")}>{d.inbox.negative}</dd></div>
            <div><dt className="text-xs text-ink-2">Typical reply</dt><dd className="font-medium tnum">{reply == null ? "–" : minutes(reply)}</dd></div>
          </dl>
        </div>
      </section>

      <section className="mb-8">
        <h3 className="mb-2 text-sm font-semibold">Top posts</h3>
        {d.top_posts.length === 0 ? <p className="text-sm text-ink-2">Nothing to rank yet.</p> : (
          <ol className="divide-y divide-line rounded-card border border-line bg-surface">
            {d.top_posts.slice(0, 5).map((p, i) => (
              <li key={p.post_id} className="flex items-start gap-3 px-4 py-2.5 text-sm">
                <span className="w-5 pt-0.5 text-ink-2 tnum">{i + 1}.</span>
                <div className="min-w-0 flex-1"><p className="line-clamp-2">{p.content}</p><p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-2"><PlatformMark platform={p.platform} size={11} />{p.handle} · {fmtDay(p.published_at.slice(0, 10), { day: "numeric", month: "short" })}{p.url && <a href={p.url} target="_blank" rel="noopener" className="underline print:hidden">open</a>}</p></div>
                <div className="shrink-0 text-right text-xs text-ink-2"><div className="text-sm font-medium text-ink tnum">{fmt(p.engagements)}</div>engagements · {fmt(p.seen ?? p.impressions)} seen{p.link_clicks ? ` · ${fmt(p.link_clicks)} clicks` : ""}</div>
              </li>
            ))}
          </ol>
        )}
      </section>
      <footer className="text-xs text-ink-2">Made with Spark. Numbers come from the networks through Zernio. Engagements count likes, comments, shares, saves and clicks; link clicks come from Spark's short links.</footer>
    </>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return <main className="min-h-dvh bg-paper px-4 py-8 text-ink print:bg-white print:px-0 print:py-0"><div className="mx-auto w-full max-w-4xl">{children}</div></main>;
}

function Kpi({ label, value, suffix = "", cmp, delta }: { label: string; value: number; suffix?: string; cmp?: { pct: number | null; previous: number }; delta?: number }) {
  const pct = cmp?.pct ?? null;
  return (
    <div className="rounded-card border border-line bg-surface p-3 print:border-line">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="display mt-0.5 text-2xl font-semibold leading-none tnum">{fmt(value)}{suffix}</div>
      {cmp && <div className={cn("mt-1 text-xs tnum", pct == null ? "text-ink-2" : pct >= 0 ? "text-st-published" : "text-st-failed")}>{pct == null ? `vs ${fmt(cmp.previous)} before` : `${pct >= 0 ? "+" : ""}${pct}% vs previous`}</div>}
      {typeof delta === "number" && <div className={cn("mt-1 text-xs tnum", delta >= 0 ? "text-st-published" : "text-st-failed")}>{delta >= 0 ? "+" : ""}{fmt(delta)} in the period</div>}
    </div>
  );
}
