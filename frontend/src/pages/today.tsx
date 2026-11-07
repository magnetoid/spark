import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, CalendarPlus, CheckCircle2, FileText, Sunrise } from "lucide-react";
import { useBrand } from "@/app/session";
import { api, unwrap } from "@/lib/api";
import type { components } from "@/api/schema";
import { EmptyState, PageHeader, StatusBadge, statusColorVar } from "@/components/page";
import { PlatformMark } from "@/lib/platforms";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useComposer } from "@/features/composer/composer-host";

type Today = components["schemas"]["TodayOut"];

export function TodayPage() {
  const brand = useBrand();
  const { data, isPending, error } = useQuery({
    queryKey: ["today", brand.id],
    queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/today", { params: { path: { brand_id: brand.id } } })),
    refetchInterval: 60_000,
  });

  const title = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "short", timeZone: brand.timezone })
    .format(data ? new Date(data.now) : new Date());

  return (
    <>
      <PageHeader title={<>Today <span className="text-ink-2 font-normal">· {title}</span></>}
                  description={`${brand.name} · ${brand.timezone}`} />
      {error && <p role="alert" className="text-sm text-st-failed">Could not load today: {error.message}</p>}
      {isPending ? <TodaySkeleton /> : data ? <TodayBody data={data} tz={brand.timezone} /> : null}
    </>
  );
}

function TodayBody({ data, tz }: { data: Today; tz: string }) {
  const composer = useComposer();
  const n = data.needs_you;
  const needs = [
    { count: n.approvals, label: "to approve", icon: CheckCircle2, to: "/publishing", search: { view: "approvals" }, tone: "text-st-pending" },
    { count: n.failed, label: n.failed === 1 ? "failed post" : "failed posts", icon: AlertTriangle, to: "/publishing", search: { view: "sent" }, tone: "text-st-failed" },
    { count: n.drafts, label: n.drafts === 1 ? "draft waiting" : "drafts waiting", icon: FileText, to: "/publishing", search: { view: "drafts" }, tone: "text-ink-2" },
  ].filter((x) => x.count > 0);

  return (
    <div className="space-y-6">
      <section aria-labelledby="timeline-h" className="rounded-card border border-line bg-surface p-5">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 id="timeline-h" className="text-base font-semibold">Going out today</h2>
          <span className="text-sm text-ink-2 tnum">
            {data.timeline.length} {data.timeline.length === 1 ? "post" : "posts"}
            {data.free_slots_today > 0 && <> · {data.free_slots_today} free {data.free_slots_today === 1 ? "slot" : "slots"}</>}
          </span>
        </div>
        <Timeline items={data.timeline} now={data.now} tz={tz} />
        {data.timeline.length === 0 ? (
          <EmptyState icon={Sunrise} title="Nothing scheduled for today" className="mt-4"
                      body={data.free_slots_today > 0 ? `${data.free_slots_today} posting ${data.free_slots_today === 1 ? "slot is" : "slots are"} still free today.` : "Tomorrow's queue is where the next posts are."}
                      action={<Button size="sm" variant="outline" onClick={() => composer.open()}><CalendarPlus className="size-4" />Write a post</Button>} />
        ) : (
          <ul className="mt-4 divide-y divide-line">
            {data.timeline.map((it) => (
              <li key={it.post_id} className="flex items-start gap-3 py-2.5">
                <time dateTime={it.at} className="w-12 shrink-0 pt-0.5 text-sm text-ink-2 tnum">{fmtTime(it.at, tz)}</time>
                <div className="flex shrink-0 -space-x-1 pt-0.5">
                  {it.channels.map((c) => <span key={c.account_id} className="grid size-6 place-items-center rounded-full border border-line bg-surface" title={`${c.handle} · ${c.platform}`}><PlatformMark platform={c.platform} size={13} /></span>)}
                </div>
                <button type="button" onClick={() => composer.open({ postId: it.post_id })} className="min-w-0 flex-1 truncate text-left text-sm hover:underline">{it.content || <span className="text-ink-2">(media only)</span>}</button>
                <StatusBadge status={it.status} className="shrink-0" />
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="needs-h" className="rounded-card border border-line bg-surface p-5">
          <h2 id="needs-h" className="mb-3 text-base font-semibold">Needs you</h2>
          {needs.length === 0 ? (
            <p className="text-sm text-ink-2">Nothing waits on you. Approvals, failures and drafts show up here.</p>
          ) : (
            <ul className="space-y-1">
              {needs.map((x) => (
                <li key={x.label}>
                  <Link to={x.to} search={(p) => ({ ...p, ...x.search })} className="flex items-center gap-3 rounded-control px-2 py-2 hover:bg-hover">
                    <x.icon className={`size-4 ${x.tone}`} aria-hidden />
                    <span className="text-sm"><span className="font-semibold tnum">{x.count}</span> {x.label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="week-h" className="rounded-card border border-line bg-surface p-5">
          <h2 id="week-h" className="mb-1 text-base font-semibold">This week</h2>
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="display text-4xl font-semibold tnum leading-none">{fmtNum(data.week.engagements)}</div>
              <div className="mt-1 text-sm text-ink-2">engagements <Delta pct={data.week.change_pct.engagements} /></div>
            </div>
            <Sparkline values={data.week.series.map((p) => p.engagements)} />
          </div>
          <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-3 text-sm">
            <div><dt className="text-ink-2">Impressions</dt><dd className="font-medium tnum">{fmtNum(data.week.impressions)} <Delta pct={data.week.change_pct.impressions} /></dd></div>
            <div><dt className="text-ink-2">Published</dt><dd className="font-medium tnum">{data.week.published}</dd></div>
            <div><dt className="text-ink-2">Engagement rate</dt><dd className="font-medium tnum">{data.week.engagement_rate_pct}%</dd></div>
          </dl>
          <Link to="/analytics" search={(p) => p} className="mt-3 inline-block text-sm text-ink-2 hover:text-ink hover:underline">Open analytics</Link>
        </section>
      </div>
    </div>
  );
}

/** The day as a strip: midnight to midnight, a dot per post coloured by status, a marker for now. */
function Timeline({ items, now, tz }: { items: Today["timeline"]; now: string; tz: string }) {
  const pos = (iso: string) => (minutesOfDay(iso, tz) / 1440) * 100;
  return (
    <div className="relative h-10" role="img" aria-label={`${items.length} posts across today`}>
      <div className="absolute inset-x-0 top-1/2 h-px bg-line-strong" />
      {[0, 6, 12, 18, 24].map((h) => (
        <span key={h} className="absolute top-full -translate-x-1/2 text-[10px] text-ink-2 tnum" style={{ left: `${(h / 24) * 100}%` }}>{h === 24 ? "24" : String(h).padStart(2, "0")}</span>
      ))}
      <span className="absolute top-1 h-8 w-px bg-brand" style={{ left: `${pos(now)}%` }} aria-hidden />
      {items.map((it) => (
        <span key={it.post_id} className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface"
              style={{ left: `${pos(it.at)}%`, background: statusColorVar(it.status) }} title={`${fmtTime(it.at, tz)} · ${it.content.slice(0, 60)}`} />
      ))}
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const w = 120, h = 36;
  const max = Math.max(1, ...values);
  const pts = values.map((v, i) => `${(i / Math.max(1, values.length - 1)) * w},${h - (v / max) * (h - 4) - 2}`);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden className="shrink-0 text-brand">
      <polyline points={pts.join(" ")} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function Delta({ pct }: { pct: number | null | undefined }) {
  if (pct === null || pct === undefined) return null;
  const up = pct >= 0;
  return <span className={`tnum text-xs ${up ? "text-st-published" : "text-st-failed"}`}>{up ? "+" : ""}{Math.round(pct)}%</span>;
}

function TodaySkeleton() {
  return <div className="space-y-6"><Skeleton className="h-44 w-full" /><div className="grid gap-6 md:grid-cols-2"><Skeleton className="h-40" /><Skeleton className="h-40" /></div></div>;
}

function minutesOfDay(iso: string, tz: string) {
  const parts = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: tz }).formatToParts(new Date(iso));
  const h = Number(parts.find((p) => p.type === "hour")?.value ?? 0);
  const m = Number(parts.find((p) => p.type === "minute")?.value ?? 0);
  return h * 60 + m;
}

function fmtTime(iso: string, tz: string) {
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date(iso));
}

function fmtNum(n: number) {
  return new Intl.NumberFormat(undefined, { notation: n >= 10_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
}
