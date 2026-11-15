/** All clients: every brand you work on and what needs you there, the most urgent first. */
import { Link } from "@tanstack/react-router";
import { AlertTriangle, CalendarX2, CheckCircle2, MessageSquareText, Plug, Building2 } from "lucide-react";
import type { ReactNode } from "react";
import { EmptyState, PageHeader } from "@/components/page";
import { Skeleton } from "@/components/ui/skeleton";
import { useOverview, type OverviewBrand, type OverviewOut } from "@/features/agency/api";
import { fmtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

export function OverviewPage() {
  const { data, isPending, error } = useOverview();
  return (
    <>
      <PageHeader title="All clients" description={data ? summary(data) : "What needs you in each brand."} />
      {error && <p role="alert" className="text-sm text-st-failed">Could not load the overview: {error.message}</p>}
      {isPending ? <Skeleton className="h-64" /> : data && data.brands.length === 0
        ? <EmptyState icon={Building2} title="No brands yet" body="Brands you work on appear here with what needs attention in each." />
        : data && <BrandList rows={data.brands} />}
    </>
  );
}

function summary(d: OverviewOut): string {
  const t = d.totals;
  const parts = [
    t.failed && `${t.failed} failed ${t.failed === 1 ? "post" : "posts"}`,
    t.channels && `${t.channels} ${t.channels === 1 ? "channel" : "channels"} to reconnect`,
    t.approvals && `${t.approvals} waiting for approval${t.approvals_overdue ? ` (${t.approvals_overdue} past due)` : ""}`,
    t.replies && `${t.replies} ${t.replies === 1 ? "reply" : "replies"} waiting`,
  ].filter(Boolean);
  const n = d.brands.length;
  return parts.length ? `${parts.join(", ")} across ${n} ${n === 1 ? "brand" : "brands"}.` : `Nothing needs you in ${n === 1 ? "your brand" : `any of ${n} brands`}.`;
}

function BrandList({ rows }: { rows: OverviewBrand[] }) {
  return (
    <ul aria-label="Brands" className="divide-y divide-line rounded-card border border-line bg-surface">
      {rows.map((b) => <BrandRow key={b.brand_id} b={b} />)}
    </ul>
  );
}

function BrandRow({ b }: { b: OverviewBrand }) {
  const s = (extra: Record<string, string> = {}) => ({ brand: b.slug, ...extra });
  const client = b.role === "client";
  const chips: ReactNode[] = [];
  if (b.failed) chips.push(<Chip key="f" to="/publishing" search={s({ view: "failed" })} tone="failed" icon={AlertTriangle}>{b.failed} failed</Chip>);
  if (b.channels) chips.push(<Chip key="c" to="/channels" search={s()} tone="failed" icon={Plug}>{b.channels} to reconnect</Chip>);
  if (b.approvals) chips.push(<Chip key="a" to="/publishing" search={s({ view: "approvals" })} tone={b.approvals_overdue ? "failed" : "pending"} icon={CheckCircle2}>
    {b.approvals} to approve{b.approvals_overdue ? `, ${b.approvals_overdue} past due` : ""}</Chip>);
  if (b.replies && !client) chips.push(<Chip key="r" to="/inbox" search={s()} tone="scheduled" icon={MessageSquareText}>{b.replies} {b.replies === 1 ? "reply" : "replies"}</Chip>);
  if (b.empty_days && b.channels_total && !client) chips.push(<Chip key="e" to="/publishing" search={s({ view: "calendar", cal: "week" })} tone="muted" icon={CalendarX2}>
    {b.empty_days === 7 ? "Nothing planned this week" : `${b.empty_days} empty ${b.empty_days === 1 ? "day" : "days"}`}</Chip>);

  return (
    <li className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:gap-5">
      <Link to="/" search={s()} className="flex min-w-0 items-center gap-3 sm:w-56 sm:shrink-0">
        <span className="size-8 shrink-0 rounded-control" style={{ background: b.color }} aria-hidden />
        <span className="min-w-0">
          <span className="block truncate font-medium hover:underline">{b.name}</span>
          <span className="block text-xs text-ink-2">{b.channels_total} {b.channels_total === 1 ? "channel" : "channels"} · {b.role}</span>
        </span>
      </Link>
      <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">
        {chips.length ? chips : !b.channels_total && !client
          ? <Link to="/channels" search={s()} className="text-sm text-ink-2 hover:underline">No channels yet: connect one</Link>
          : <span className="inline-flex items-center gap-1.5 text-sm text-ink-2"><CheckCircle2 className="size-4 text-st-published" aria-hidden />All clear</span>}
      </div>
      <div className="text-sm sm:w-48 sm:shrink-0 sm:text-right">
        <span className="tnum">{b.scheduled_week} {b.scheduled_week === 1 ? "post" : "posts"}</span> <span className="text-ink-2">in 7 days</span>
        <span className="block text-xs text-ink-2 tnum">{b.next_post_at ? `next ${fmtDateTime(b.next_post_at, b.timezone)}` : "nothing scheduled"}</span>
      </div>
    </li>
  );
}

const TONES = {
  failed: "border-st-failed/30 bg-st-failed/10 text-st-failed",
  pending: "border-st-pending/30 bg-st-pending/10 text-st-pending",
  scheduled: "border-st-scheduled/30 bg-st-scheduled/10 text-st-scheduled",
  muted: "border-line bg-hover text-ink-2",
} as const;

function Chip({ to, search, tone, icon: Icon, children }: {
  to: string; search: Record<string, string>; tone: keyof typeof TONES; icon: typeof Plug; children: ReactNode;
}) {
  return (
    <Link to={to} search={search} className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium hover:underline", TONES[tone])}>
      <Icon className="size-3.5" aria-hidden />{children}
    </Link>
  );
}
