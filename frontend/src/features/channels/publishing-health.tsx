/** How publishing is going: success over 7 and 30 days, why posts failed, what is next per channel. */
import { Link } from "@tanstack/react-router";
import { usePublishingHealth } from "@/features/api4";
import { HealthBadge } from "@/features/channels/health";
import { Skeleton } from "@/components/ui/skeleton";
import { PlatformMark } from "@/lib/platforms";
import { fmtDateTime } from "@/lib/time";

function Rate({ label, r }: { label: string; r: { published: number; failed: number; success_rate_pct: number | null } }) {
  return (
    <div>
      <div className="text-xs text-ink-2">{label}</div>
      <div className="font-display text-2xl tnum">{r.success_rate_pct === null ? "–" : `${r.success_rate_pct}%`}</div>
      <div className="text-xs text-ink-2 tnum">{r.published} published · {r.failed} failed</div>
    </div>
  );
}

export function PublishingHealthCard({ brandId, timezone }: { brandId: number; timezone: string }) {
  const { data, isPending } = usePublishingHealth(brandId);
  if (isPending) return <Skeleton className="mb-5 h-36" />;
  if (!data) return null;
  const attention = data.channels.filter((c) => c.account.health === "reconnect" || c.account.health === "expiring");
  return (
    <section aria-labelledby="ph-h" className="mb-5 rounded-card border border-line bg-surface p-5">
      <h2 id="ph-h" className="mb-3 text-base font-semibold">Publishing health</h2>
      <div className="grid gap-5 sm:grid-cols-[auto_auto_1fr]">
        <Rate label="Last 7 days" r={data.week} />
        <Rate label="Last 30 days" r={data.month} />
        <div className="min-w-0 text-sm">
          <div className="mb-1 text-xs text-ink-2">Why posts failed (30 days)</div>
          {data.failures_by_reason.length === 0 ? <p className="text-ink-2">No failures.</p> : (
            <ul className="space-y-0.5">
              {data.failures_by_reason.slice(0, 3).map((f) => <li key={f.reason} className="flex gap-2"><span className="tnum text-st-failed">{f.count}×</span><span className="truncate" title={f.reason}>{f.reason}</span></li>)}
            </ul>
          )}
        </div>
      </div>
      {(attention.length > 0 || data.stuck > 0) && (
        <div className="mt-4 space-y-1.5 border-t border-line pt-3 text-sm">
          {attention.map((c) => (
            <div key={c.account.id} className="flex flex-wrap items-center gap-2"><PlatformMark platform={c.account.platform} size={14} />@{c.account.handle.replace(/^@/, "")}<HealthBadge account={c.account} timezone={timezone} />
              <Link to="/channels" search={(p) => p} className="text-xs underline">Open channels</Link></div>
          ))}
          {data.stuck > 0 && <p className="text-ink-2">{data.stuck} {data.stuck === 1 ? "post has" : "posts have"} been publishing for over 30 minutes. Spark puts them back in the queue on its own.</p>}
        </div>
      )}
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-ink-2 hover:text-ink">Next post per channel</summary>
        <ul className="mt-2 grid gap-1 sm:grid-cols-2">
          {data.channels.map((c) => (
            <li key={c.account.id} className="flex items-center gap-2"><PlatformMark platform={c.account.platform} size={13} /><span className="truncate">@{c.account.handle.replace(/^@/, "")}</span>
              <span className="ml-auto text-xs text-ink-2 tnum">{c.next_scheduled_at ? fmtDateTime(c.next_scheduled_at, timezone) : "Nothing scheduled"}</span></li>
          ))}
        </ul>
      </details>
    </section>
  );
}
