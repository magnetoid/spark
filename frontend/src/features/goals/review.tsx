/**
 * The weekly review on Analytics: a week's posts against each channel's own usual (the median of
 * its posts in the 90 days before), with the plain findings the next weekly plan also reads.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { components } from "@/api/schema";
import { useBrand } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useComposer } from "@/features/composer/composer-host";
import { api, unwrap } from "@/lib/api";
import { PlatformMark } from "@/lib/platforms";
import { addDays, fmtDay, startOfWeek, todayKey } from "@/lib/time";
import { cn } from "@/lib/utils";

type S = components["schemas"];
type ReviewPost = S["ReviewPostOut"];

export const useWeeklyReview = (b: number, week: string | null) => useQuery({
  queryKey: ["weekly-review", b, week],
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/weekly-review", { params: { path: { brand_id: b }, query: week ? { week } : {} } })),
});

const VERDICT: Record<ReviewPost["verdict"], string> = {
  above: "text-st-published",
  usual: "text-ink-2",
  below: "text-st-failed",
  unrated: "text-ink-2",
};

export function WeeklyReview() {
  const brand = useBrand();
  const [week, setWeek] = useState<string | null>(null);
  const { data, isPending } = useWeeklyReview(brand.id, week);
  const composer = useComposer();
  if (isPending || !data) return <Skeleton className="h-40" />;
  const range = `${fmtDay(data.week_start, { day: "numeric", month: "short" })} to ${fmtDay(data.week_end, { day: "numeric", month: "short" })}`;
  const c = data.counts;
  const rated = c.above + c.usual + c.below;
  return (
    <section aria-labelledby="wr-h" className="rounded-card border border-line bg-surface p-5">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h2 id="wr-h" className="text-base font-semibold">Week in review <span className="font-normal text-ink-2">· {range}</span></h2>
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" aria-label="Week before" onClick={() => setWeek(addDays(data.week_start, -7))}><ChevronLeft className="size-4" /></Button>
          <Button size="sm" variant="ghost" aria-label="Week after" disabled={week === null} onClick={() => { const next = addDays(data.week_start, 7); setWeek(next >= addDays(startOfWeek(todayKey(brand.timezone)), -7) ? null : next); }}><ChevronRight className="size-4" /></Button>
        </div>
      </div>
      <p className="text-sm text-ink-2">
        {c.posts === 0 ? "Nothing was published that week." : <>
          {c.posts} {c.posts === 1 ? "post" : "posts"}{rated > 0 && <>: {c.above} above their channel's usual, {c.usual} usual, {c.below} below</>}{c.unrated > 0 && <>{rated > 0 ? "; " : ": "}{c.unrated} not rated yet</>}.
        </>}
        {" "}Usual is the middle result of the channel's posts in the 90 days before, once it has five.
      </p>
      {data.findings.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {data.findings.map((f) => <li key={f} className="flex gap-2"><span aria-hidden className="text-ink-2">•</span><span>{f}</span></li>)}
        </ul>
      )}
      {data.posts.length > 0 && (
        <ul className="mt-4 divide-y divide-line border-t border-line">
          {data.posts.map((p) => (
            <li key={p.target_id} className="flex items-center gap-3 py-2 text-sm">
              <PlatformMark platform={p.platform} size={14} />
              <button type="button" onClick={() => composer.open({ postId: p.post_id })} className="min-w-0 flex-1 truncate text-left hover:underline">{p.text || <span className="text-ink-2">(media only)</span>}</button>
              <span className="hidden shrink-0 text-xs text-ink-2 tnum sm:inline">{p.engagements != null ? `${p.engagements.toLocaleString()} engagements` : "no numbers yet"}</span>
              <span className={cn("w-24 shrink-0 text-right text-xs font-medium tnum", VERDICT[p.verdict])}>
                {p.vs_usual != null ? `${p.vs_usual.toFixed(1)}× usual` : p.verdict === "unrated" ? "not rated" : p.verdict}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
