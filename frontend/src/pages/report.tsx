/**
 * A report, as a page you read on screen and print to PDF. Lives outside the shell so the
 * print has no sidebar: the brand's colour, the period, the numbers, what worked, what next.
 */
import { useEffect } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowLeft, Download, Printer, Sparkles } from "lucide-react";
import { useSession } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { csvUrl, useReport, useSummarizeReport, type ReportData, type ReportSummary } from "@/features/reports/api";
import { applyBrandColor } from "@/lib/brand-color";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { fmtDay } from "@/lib/time";
import { cn } from "@/lib/utils";

const fmt = (n: number) => new Intl.NumberFormat().format(n);

export function ReportPage() {
  const { brandId, reportId } = useParams({ from: "/brands/$brandId/reports/$reportId" });
  const b = Number(brandId), id = Number(reportId);
  const { data: session } = useSession();
  const brand = session?.brands.find((x) => x.id === b);
  const { data, isPending, error } = useReport(b, id);
  const summarize = useSummarizeReport(b, id);
  useEffect(() => { if (brand?.color) applyBrandColor(brand.color); }, [brand?.color]);
  const canEdit = brand && brand.role !== "viewer" && brand.role !== "client";
  if (isPending) return <Frame><Skeleton className="h-10 w-80" /><Skeleton className="mt-6 h-64" /></Frame>;
  if (error || !data) return <Frame><p className="text-sm text-st-failed">{error?.message ?? "Could not load this report."}</p></Frame>;
  const d = data.data as ReportData;
  const s = data.summary as ReportSummary | null;
  const period = `${fmtDay(d.period.start, { day: "numeric", month: "short" })} – ${fmtDay(d.period.end, { day: "numeric", month: "short", year: "numeric" })}`;
  return (
    <Frame>
      <div className="mb-6 flex flex-wrap items-center gap-2 print:hidden">
        <Button asChild size="sm" variant="ghost"><Link to="/analytics" search={(p) => p}><ArrowLeft className="size-4" />Analytics</Link></Button>
        <span className="flex-1" />
        {canEdit && session?.features.ai && <Button size="sm" variant="outline" disabled={summarize.isPending} onClick={() => summarize.mutate(undefined)}><Sparkles className="size-4" />{s ? "Rewrite summary" : "Write summary with AI"}</Button>}
        <Button asChild size="sm" variant="outline"><a href={csvUrl(b, id)}><Download className="size-4" />CSV</a></Button>
        <Button size="sm" onClick={() => window.print()}><Printer className="size-4" />Print / save as PDF</Button>
      </div>

      <header className="mb-8 border-b border-line pb-6">
        <p className="flex items-center gap-2 text-sm text-ink-2"><span className="inline-block size-3 rounded-full bg-brand" aria-hidden />{brand?.name ?? "Report"}</p>
        <h1 className="display mt-1 text-3xl font-semibold leading-tight">{data.title}</h1>
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

      <section className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Kpi label="Posts published" value={d.totals.published} cmp={d.compare.published} />
        <Kpi label="Impressions" value={d.totals.impressions} cmp={d.compare.impressions} />
        <Kpi label="Engagements" value={d.totals.engagements} cmp={d.compare.engagements} />
        <Kpi label="Engagement rate" value={d.totals.engagement_rate_pct} suffix="%" />
        <Kpi label="Followers" value={d.followers.end} delta={d.followers.delta} />
      </section>

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
          <dl className="mt-4 grid grid-cols-3 gap-3 rounded-card border border-line bg-surface p-3 text-sm">
            <div><dt className="text-xs text-ink-2">Messages received</dt><dd className="font-medium tnum">{d.inbox.received}</dd></div>
            <div><dt className="text-xs text-ink-2">Answered</dt><dd className="font-medium tnum">{d.inbox.replied}</dd></div>
            <div><dt className="text-xs text-ink-2">Negative</dt><dd className={cn("font-medium tnum", d.inbox.negative && "text-st-failed")}>{d.inbox.negative}</dd></div>
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
                <div className="shrink-0 text-right text-xs text-ink-2"><div className="text-sm font-medium text-ink tnum">{fmt(p.engagements)}</div>engagements · {fmt(p.impressions)} impr.</div>
              </li>
            ))}
          </ol>
        )}
      </section>
      <footer className="text-xs text-ink-2">Made with Spark. Impressions and engagements come from the networks through Zernio; engagements count likes, comments, shares and clicks.</footer>
    </Frame>
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
