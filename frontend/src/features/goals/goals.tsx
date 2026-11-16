/**
 * Posting goals on Today: a weekly target per channel, this week's progress, the streak of weeks
 * met, and a way to plan the posts still missing. Weeks run Monday to Sunday in the brand's zone.
 */
import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, Target } from "lucide-react";
import type { components } from "@/api/schema";
import { useBrand, usePerms } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAction } from "@/features/api4";
import { useComposer } from "@/features/composer/composer-host";
import { api, unwrap } from "@/lib/api";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { cn } from "@/lib/utils";

type S = components["schemas"];
export type GoalChannel = S["GoalChannel"];
const bp = (brand_id: number) => ({ params: { path: { brand_id } } });

export const useGoals = (b: number) => useQuery({ queryKey: ["goals", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/goals", bp(b))) });
export const useSetGoals = (b: number) => useAction(async (body: S["GoalsIn"]) => unwrap(await api.PUT("/brands/{brand_id}/goals", { ...bp(b), body })),
  [["goals", b], ["today", b], ["activity", b]], "Goals saved");

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export function GoalsCard() {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data, isPending } = useGoals(brand.id);
  const [editing, setEditing] = useState(false);
  if (isPending) return <Skeleton className="h-32" />;
  if (!data || data.channels.length === 0) return null;
  const withGoal = data.channels.filter((c) => c.goal);
  if (!withGoal.length && !canEdit) return null;
  return (
    <section aria-labelledby="goals-h" className="rounded-card border border-line bg-surface p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="goals-h" className="text-base font-semibold">Posting goals</h2>
        <span className="flex items-center gap-3 text-sm text-ink-2">
          {withGoal.length > 0 && <span className="tnum">{plural(data.days_left, "day", "days")} left this week</span>}
          {canEdit && <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Target className="size-4" />{withGoal.length ? "Change goals" : "Set goals"}</Button>}
        </span>
      </div>
      {withGoal.length === 0 ? (
        <p className="text-sm text-ink-2">Set how many posts each channel should get a week. Posting in more weeks, and more often each week, is what grows accounts most.</p>
      ) : (
        <ul className="divide-y divide-line">{withGoal.map((c) => <GoalRow key={c.account_id} c={c} />)}</ul>
      )}
      {canEdit && <GoalsDialog open={editing} onClose={() => setEditing(false)} channels={data.channels} />}
    </section>
  );
}

function GoalRow({ c }: { c: GoalChannel }) {
  const composer = useComposer();
  const { canEdit } = usePerms();
  const goal = c.goal ?? 1;
  const pct = (n: number) => `${Math.min(100, (n / goal) * 100)}%`;
  const done = c.published >= goal;
  return (
    <li className="grid gap-x-4 gap-y-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <PlatformMark platform={c.platform} size={14} />
          <span className="font-medium">@{c.handle}</span>
          <span className="text-ink-2 tnum">{c.published} of {c.goal} published{c.planned > 0 && `, ${c.planned} planned`}</span>
          {c.streak > 0 && <span className="text-ink-2 tnum">· {plural(c.streak, "week", "weeks")} in a row</span>}
        </div>
        <div className="mt-2 flex items-center gap-3">
          <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-hover" role="progressbar" aria-valuemin={0} aria-valuemax={goal} aria-valuenow={c.published} aria-label={`@${c.handle} this week`}>
            <span className="absolute inset-y-0 left-0 rounded-full bg-[var(--st-scheduled)] opacity-35" style={{ width: pct(c.published + c.planned) }} />
            <span className="absolute inset-y-0 left-0 rounded-full bg-[var(--st-published)]" style={{ width: pct(c.published) }} />
          </div>
          <Weeks weeks={c.weeks} handle={c.handle} />
        </div>
      </div>
      <div className="flex items-center gap-2 text-sm sm:justify-end">
        {done ? <span className="text-st-published">Goal met</span>
          : c.needed === 0 ? <span className="text-ink-2">On track</span>
          : <>
              <span className={cn("tnum", c.at_risk ? "text-st-failed" : "text-ink-2")}>{plural(c.needed, "more post", "more posts")} needed</span>
              {canEdit && <Button size="sm" variant="outline" onClick={() => composer.open({ account: c.account_id })}><CalendarPlus className="size-4" />Plan</Button>}
            </>}
      </div>
    </li>
  );
}

/** The last eight weeks as small squares: met, missed, or no goal yet (and this week, until met). */
function Weeks({ weeks, handle }: { weeks: GoalChannel["weeks"]; handle: string }) {
  const met = weeks.filter((w) => w.met).length;
  const counted = weeks.filter((w) => w.met !== null).length;
  return (
    <span className="flex shrink-0 gap-1" role="img" aria-label={`@${handle}: goal met in ${met} of the last ${counted} weeks with a goal`}>
      {weeks.map((w) => (
        <span key={w.start} title={`Week of ${w.start}: ${plural(w.published, "post", "posts")}`}
              className={cn("size-2.5 rounded-[3px]", w.met === true ? "bg-[var(--st-published)]" : w.met === false ? "bg-[var(--st-failed)] opacity-60" : "border border-line")} />
      ))}
    </span>
  );
}

function GoalsDialog({ open, onClose, channels }: { open: boolean; onClose: () => void; channels: GoalChannel[] }) {
  const brand = useBrand();
  const save = useSetGoals(brand.id);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const goals = channels.map((c) => {
      const raw = String(fd.get(`g-${c.account_id}`) ?? "").trim();
      return { account_id: c.account_id, posts_per_week: raw ? Number(raw) : null };
    });
    save.mutate({ goals }, { onSuccess: onClose });
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>Weekly posting goals</DialogTitle></DialogHeader>
        <form className="space-y-4 text-sm" onSubmit={submit}>
          <p className="text-ink-2">Posts a week per channel, Monday to Sunday in {brand.timezone}. Leave a channel empty for no goal. Changing a goal starts its streak again.</p>
          <ul className="space-y-2">
            {channels.map((c) => (
              <li key={c.account_id} className="flex items-center gap-3">
                <label htmlFor={`g-${c.account_id}`} className="flex min-w-0 flex-1 items-center gap-2">
                  <PlatformMark platform={c.platform} size={14} /><span className="truncate">@{c.handle}</span><span className="text-xs text-ink-2">{platformLabel(c.platform)}</span>
                </label>
                <Input id={`g-${c.account_id}`} name={`g-${c.account_id}`} type="number" inputMode="numeric" min={1} max={50} defaultValue={c.goal ?? ""} placeholder="No goal" className="w-28" />
              </li>
            ))}
          </ul>
          <DialogFooter><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save goals"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
