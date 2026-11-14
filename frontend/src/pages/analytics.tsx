/** Analytics: one trend chart, the numbers behind it, top posts, best times. Colour means status only. */
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BarChart3, RefreshCw } from "lucide-react";
import { useBrand, usePerms } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalytics, useRefreshAnalytics } from "@/features/api4";
import { ReportsSection } from "@/features/reports/panels";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { fmtDay } from "@/lib/time";
import { cn } from "@/lib/utils";

const RANGES = [7, 30, 90];
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const TYPE_LABELS: Record<string, string> = { post: "Posts", carousel: "Carousels", reel: "Reels", story: "Stories", document: "Documents" };
const SMALL_SAMPLE = 3; // below this a rate says little; shown, but marked
type Analytics = NonNullable<ReturnType<typeof useAnalytics>["data"]>;
type Breakdown = Analytics["by_type"][number];

export function AnalyticsPage() {
  const brand = useBrand();
  const [days, setDays] = useState(30);
  const [chart, setChart] = useState<"published" | "daily">("published");
  const { data, isPending } = useAnalytics(brand.id, days);
  const refresh = useRefreshAnalytics(brand.id);
  const { canEdit } = usePerms();

  return (
    <>
      <PageHeader title="Analytics" description={`${brand.name} · last ${days} days`}
                  actions={<>
                    <div className="flex rounded-control border border-line p-0.5 text-sm">
                      {RANGES.map((r) => <button key={r} onClick={() => setDays(r)} className={cn("rounded-[4px] px-2.5 py-1 tnum", days === r ? "bg-hover font-medium" : "text-ink-2")}>{r}d</button>)}
                    </div>
                    {canEdit && <Button size="sm" variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending}><RefreshCw className={cn("size-4", refresh.isPending && "animate-spin")} />Pull latest</Button>}
                  </>} />
      {data && <MetricsNotice status={data.metrics_status} />}
      {isPending || !data ? <Skeleton className="h-80" /> : data.impressions === 0 && data.published === 0 ? (
        <EmptyState icon={BarChart3} title="No numbers yet" body="Metrics arrive a few hours after posts go out. Publish something and come back." />
      ) : (
        <div className="space-y-6">
          <section className="rounded-card border border-line bg-surface p-5">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="text-sm text-ink-2">Engagements</div>
                <div className="display text-4xl font-semibold tnum leading-none">{fmt(data.engagements)} <Delta pct={data.change_pct.engagements} /></div>
                <div className="mt-1 text-sm text-ink-2">{fmt(data.impressions)} impressions <Delta pct={data.change_pct.impressions} />{data.views !== null && data.views !== undefined && <> · {fmt(data.views)} views</>}{data.reach !== null && data.reach !== undefined && <> · {fmt(data.reach)} reach</>}{data.saves !== null && data.saves !== undefined && <> · {fmt(data.saves)} saves</>} · {data.engagement_rate_pct}% rate</div>
              </div>
              <dl className="grid grid-cols-3 gap-6 text-sm">
                <Stat label="Published" value={data.published} />
                <Stat label="Link clicks" value={data.link_clicks} />
                <Stat label="Followers" value={data.followers} />
              </dl>
            </div>
            <div className="mt-4 flex items-center justify-between gap-3">
              <p className="text-xs text-ink-2">{chart === "published" ? "Each post's numbers on the day it went out." : "What every day added, across all posts."}</p>
              <div role="tablist" aria-label="Chart" className="flex rounded-control border border-line p-0.5 text-xs">
                {([["published", "By publish day"], ["daily", "Each day"]] as const).map(([k, label]) => <button key={k} role="tab" aria-selected={chart === k} onClick={() => setChart(k)} className={cn("rounded-[4px] px-2 py-0.5", chart === k ? "bg-hover font-medium" : "text-ink-2")}>{label}</button>)}
              </div>
            </div>
            <div className="mt-2 h-56">
              <ResponsiveContainer>
                <AreaChart data={chart === "published" ? data.series : data.history} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                  <defs><linearGradient id="imp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--brand)" stopOpacity={0.35} /><stop offset="100%" stopColor="var(--brand)" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid vertical={false} stroke="var(--line)" />
                  <XAxis dataKey="day" tickFormatter={(d: string) => fmtDay(d, { day: "numeric", month: "short" })} tick={{ fill: "var(--ink-2)", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={24} />
                  <YAxis tick={{ fill: "var(--ink-2)", fontSize: 11 }} axisLine={false} tickLine={false} width={40} tickFormatter={fmt} />
                  <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }} labelFormatter={(d) => fmtDay(String(d))} />
                  <Area type="monotone" dataKey="impressions" name="Impressions" stroke="var(--brand)" fill="url(#imp)" strokeWidth={2} />
                  <Area type="monotone" dataKey="engagements" name="Engagements" stroke="var(--ink)" fill="transparent" strokeWidth={1.5} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-card border border-line bg-surface p-5">
              <h2 className="mb-3 text-base font-semibold">By network</h2>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-ink-2"><tr><th className="pb-2 font-medium">Network</th><th className="pb-2 text-right font-medium">Posts</th><th className="pb-2 text-right font-medium">Impressions</th><th className="pb-2 text-right font-medium">Views</th><th className="pb-2 text-right font-medium">Engagements</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {Object.entries(data.by_platform).sort((a, b) => b[1].impressions - a[1].impressions).map(([k, v]) => (
                    <tr key={k}><td className="flex items-center gap-2 py-2"><PlatformMark platform={k} size={14} />{platformLabel(k)}</td><td className="py-2 text-right tnum">{v.posts}</td><td className="py-2 text-right tnum">{fmt(v.impressions)}</td><td className="py-2 text-right tnum">{fmt(v.views ?? 0)}</td><td className="py-2 text-right tnum">{fmt(v.engagements)}</td></tr>
                  ))}
                  {Object.keys(data.by_platform).length === 0 && <tr><td colSpan={5} className="py-6 text-center text-ink-2">No metrics in this range.</td></tr>}
                </tbody>
              </table>
            </section>
            <section className="rounded-card border border-line bg-surface p-5">
              <h2 className="mb-3 text-base font-semibold">Link clicks</h2>
              <div className="h-40">
                <ResponsiveContainer>
                  <BarChart data={data.link_clicks_series} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--line)" />
                    <XAxis dataKey="day" tickFormatter={(d: string) => fmtDay(d, { day: "numeric", month: "short" })} tick={{ fill: "var(--ink-2)", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={24} />
                    <YAxis tick={{ fill: "var(--ink-2)", fontSize: 11 }} axisLine={false} tickLine={false} width={30} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }} labelFormatter={(d) => fmtDay(String(d))} cursor={{ fill: "var(--hover)" }} />
                    <Bar dataKey="clicks" name="Clicks" fill="var(--brand)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <h2 className="mb-2 mt-5 text-base font-semibold">Best times to post</h2>
              {data.best_times.length === 0 ? <p className="text-sm text-ink-2">Not enough published posts with metrics yet.</p> : (
                <ol className="space-y-1 text-sm">
                  {data.best_times.map((b, i) => <li key={`${b.day}-${b.hour}`} className="flex items-center gap-3"><span className="w-4 text-ink-2 tnum">{i + 1}</span><span className="flex-1">{String(b.day)} at {String(b.hour).padStart(2, "0")}:00</span><span className="text-xs text-ink-2 tnum">{String(b.posts)} posts</span></li>)}
                </ol>
              )}
            </section>
          </div>

          <WhatWorks data={data} />

          <section className="rounded-card border border-line bg-surface">
            <h2 className="border-b border-line px-5 py-3 text-base font-semibold">Top posts</h2>
            {data.top.length === 0 ? <p className="p-5 text-sm text-ink-2">No post has metrics in this range yet.</p> : (
              <ol className="divide-y divide-line">
                {data.top.map((t, i) => (
                  <li key={`${t.post_id}-${t.account_id}`} className="flex items-start gap-3 px-5 py-3 text-sm">
                    <span className="w-5 pt-0.5 text-ink-2 tnum">{i + 1}</span>
                    <span className="grid size-6 shrink-0 place-items-center rounded-full border border-line"><PlatformMark platform={t.platform} size={12} /></span>
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2">{t.text || "(media only)"}</p>
                      <div className="mt-0.5 text-xs text-ink-2">{t.handle}{t.published_at && ` · ${fmtDay(t.published_at.slice(0, 10), { day: "numeric", month: "short" })}`}{t.url && <> · <a href={t.url} target="_blank" rel="noopener" className="underline">View</a></>}</div>
                    </div>
                    <div className="text-right tnum"><div className="font-medium">{fmt(t.engagements)}</div><div className="text-xs text-ink-2">{fmt(t.impressions)} impr.</div></div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      )}
      {data?.saves_in_shares && <p className="mt-4 text-xs text-ink-2">Some numbers were read before Spark kept saves apart: on those posts, saves are counted inside shares.</p>}
      <div className="mt-6"><ReportsSection /></div>
    </>
  );
}

function MetricsNotice({ status }: { status: Analytics["metrics_status"] }) {
  if (status.state === "ok") return null;
  const text = status.state === "paused"
    ? `Spark is waiting${status.until ? ` until ${new Date(status.until).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""} before it reads numbers again, because Zernio asked it to slow down. Nothing is lost; the next run catches up.`
    : status.message ?? "Post numbers cannot be read right now.";
  return (
    <div role="status" className="mb-4 flex flex-wrap items-center gap-3 rounded-card border border-line bg-surface px-4 py-3 text-sm">
      <span className="flex-1">{text}</span>
      {status.state === "unavailable" && <a href="/settings?tab=connectors&connector=zernio" className="font-medium underline">Open Zernio settings</a>}
    </div>
  );
}

/** Which formats, pillars and times did best, each with how many posts it rests on. */
function WhatWorks({ data }: { data: Analytics }) {
  const slots = data.by_slot.filter((s) => s.posts >= 2).sort((a, b) => b.engagement_rate_pct - a.engagement_rate_pct).slice(0, 5);
  if (data.by_type.length === 0 && data.by_pillar.length === 0) return null;
  return (
    <section className="rounded-card border border-line bg-surface p-5">
      <h2 className="text-base font-semibold">What works</h2>
      <p className="mb-4 text-sm text-ink-2">Engagement rate by format, pillar and posting time. A rate from one or two posts is a hint, not a rule.</p>
      <div className="grid gap-6 lg:grid-cols-3">
        <BreakdownTable title="Format" rows={data.by_type} label={(k) => TYPE_LABELS[k] ?? k} />
        <BreakdownTable title="Pillar" rows={data.by_pillar} label={(k) => k} />
        <div>
          <h3 className="mb-2 text-sm font-medium">Best times</h3>
          {slots.length === 0 ? <p className="text-sm text-ink-2">Needs at least two posts in the same hour on one channel.</p> : (
            <ol className="space-y-1.5 text-sm">
              {slots.map((s) => (
                <li key={`${s.account_id}-${s.weekday}-${s.hour}`} className="flex items-center gap-2">
                  <PlatformMark platform={s.platform} size={12} />
                  <span className="flex-1">{WEEKDAYS[s.weekday]} {String(s.hour).padStart(2, "0")}:00</span>
                  <span className="tnum">{s.engagement_rate_pct}%</span>
                  <span className="w-14 text-right text-xs text-ink-2 tnum">{s.posts} posts</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </section>
  );
}

function BreakdownTable({ title, rows, label }: { title: string; rows: Breakdown[]; label: (key: string) => string }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      {rows.length === 0 ? <p className="text-sm text-ink-2">No posts with numbers yet.</p> : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-2"><tr><th className="pb-1.5 font-medium">{title}</th><th className="pb-1.5 text-right font-medium">Rate</th><th className="pb-1.5 text-right font-medium">Posts</th></tr></thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.key} className={cn(r.posts < SMALL_SAMPLE && "text-ink-2")}>
                <td className="py-1.5">{label(r.key)}</td>
                <td className="py-1.5 text-right tnum">{r.engagement_rate_pct}%</td>
                <td className="py-1.5 text-right tnum" title={r.posts < SMALL_SAMPLE ? "Small sample" : undefined}>{r.posts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div><dt className="text-ink-2">{label}</dt><dd className="text-lg font-semibold tnum">{fmt(value)}</dd></div>;
}

function Delta({ pct }: { pct: number | null | undefined }) {
  if (pct === null || pct === undefined) return null;
  return <span className={cn("ml-1 text-sm font-normal tnum", pct >= 0 ? "text-st-published" : "text-st-failed")}>{pct >= 0 ? "+" : ""}{Math.round(pct)}%</span>;
}

function fmt(n: number) {
  return new Intl.NumberFormat(undefined, { notation: n >= 10_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
}
