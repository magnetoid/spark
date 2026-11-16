/**
 * Follower goals on Analytics: per channel the followers now, the goal and a forecast drawn from
 * the channel's own daily counts, and how its posting rate went with growth in recent weeks.
 */
import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Target } from "lucide-react";
import type { components } from "@/api/schema";
import { useBrand, usePerms } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";
import { PlatformMark } from "@/lib/platforms";
import { fmtDay } from "@/lib/time";
import { cn } from "@/lib/utils";

type S = components["schemas"];
export type FollowerGoal = S["FollowerGoalChannel"];
const bp = (brand_id: number) => ({ params: { path: { brand_id } } });

export const useFollowerGoals = (b: number) => useQuery({ queryKey: ["follower-goals", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/follower-goals", bp(b))) });
export const useSetFollowerGoals = (b: number) => useAction(async (body: S["FollowerGoalsIn"]) => unwrap(await api.PUT("/brands/{brand_id}/follower-goals", { ...bp(b), body })),
  [["follower-goals", b], ["activity", b]], "Follower goals saved");

const n = (v: number) => v.toLocaleString();
const signed = (v: number) => `${v > 0 ? "+" : ""}${n(v)}`;
const day = (d: string) => fmtDay(d, { day: "numeric", month: "short", year: "numeric" });

export function FollowerGoals() {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data, isPending } = useFollowerGoals(brand.id);
  const [editing, setEditing] = useState(false);
  if (isPending) return <Skeleton className="h-28" />;
  const channels = data?.channels ?? [];
  if (!channels.length) return null;
  const withGoal = channels.filter((c) => c.goal);
  if (!withGoal.length && !canEdit) return null;
  return (
    <section aria-labelledby="fg-h" className="rounded-card border border-line bg-surface p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="fg-h" className="text-base font-semibold">Follower goals</h2>
        {canEdit && <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Target className="size-4" />{withGoal.length ? "Change goals" : "Set a goal"}</Button>}
      </div>
      {withGoal.length === 0 ? (
        <p className="text-sm text-ink-2">Set a follower target, with a date if there is one. Spark forecasts it from each channel's own daily follower counts.</p>
      ) : (
        <ul className="divide-y divide-line">{withGoal.map((c) => <GoalRow key={c.account_id} c={c} />)}</ul>
      )}
      {canEdit && <GoalsDialog open={editing} onClose={() => setEditing(false)} channels={channels} />}
    </section>
  );
}

function status(c: FollowerGoal): { text: string; tone: string } {
  switch (c.status) {
    case "reached": return { text: "Goal reached", tone: "text-st-published" };
    case "on_track": return { text: `On track: ${signed(c.per_week ?? 0)} a week, there around ${day(c.eta!)}`, tone: "text-st-published" };
    case "behind": return { text: `Behind: ${signed(c.per_week ?? 0)} a week now, ${n(c.needed_per_week ?? 0)} a week needed`, tone: "text-st-failed" };
    case "stalled": return { text: "Not growing over the last 60 days", tone: "text-st-failed" };
    case "learning": return { text: `Forecast after two weeks of daily counts (${c.history_days} so far)`, tone: "text-ink-2" };
    default: return { text: "", tone: "text-ink-2" };
  }
}

function GoalRow({ c }: { c: FollowerGoal }) {
  const goal = c.goal ?? 0;
  const now = c.followers ?? 0;
  const pct = goal > 0 ? Math.min(100, (now / goal) * 100) : 0;
  const gained = c.start != null && c.followers != null ? c.followers - c.start : null;
  const s = status(c);
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <PlatformMark platform={c.platform} size={14} />
        <span className="font-medium">@{c.handle}</span>
        <span className="text-ink-2 tnum">{c.followers != null ? n(c.followers) : "No count yet"} of {n(goal)}{c.by && ` by ${day(c.by)}`}</span>
        {gained != null && gained !== 0 && c.since && <span className="text-ink-2 tnum">· {signed(gained)} since {day(c.since)}</span>}
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-hover" role="progressbar" aria-valuemin={0} aria-valuemax={goal} aria-valuenow={now} aria-label={`@${c.handle} followers toward the goal`}>
        <span className="block h-full rounded-full bg-[var(--st-published)]" style={{ width: `${pct}%` }} />
      </div>
      <p className={cn("mt-1.5 text-sm", s.tone)}>{s.text}{c.status === "on_track" && c.by && c.expected_by_date != null && <span className="text-ink-2"> · about {n(c.expected_by_date)} by {day(c.by)}</span>}</p>
      {c.driver && (
        <p className="mt-1 text-xs text-ink-2">
          Weeks with {c.driver.threshold}+ posts: {signed(c.driver.gain_more)} followers on average ({c.driver.weeks_more} weeks). Other weeks: {signed(c.driver.gain_less)} ({c.driver.weeks_less} weeks). This shows what went together, not the cause.
        </p>
      )}
    </li>
  );
}

function GoalsDialog({ open, onClose, channels }: { open: boolean; onClose: () => void; channels: FollowerGoal[] }) {
  const brand = useBrand();
  const save = useSetFollowerGoals(brand.id);
  const [tomorrow] = useState(() => new Date(Date.now() + 86_400_000).toISOString().slice(0, 10));
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const goals = channels.map((c) => {
      const target = String(fd.get(`t-${c.account_id}`) ?? "").trim();
      const by = String(fd.get(`b-${c.account_id}`) ?? "").trim();
      return { account_id: c.account_id, target: target ? Number(target) : null, by: target && by ? by : null };
    });
    save.mutate({ goals }, { onSuccess: onClose });
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader><DialogTitle>Follower goals</DialogTitle></DialogHeader>
        <form className="space-y-4 text-sm" onSubmit={submit}>
          <p className="text-ink-2">A target per channel and, if there is one, a date. Leave the target empty for no goal.</p>
          <ul className="space-y-3">
            {channels.map((c) => (
              <li key={c.account_id} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_10rem] sm:items-center">
                <span className="flex min-w-0 items-center gap-2"><PlatformMark platform={c.platform} size={14} /><span className="truncate">@{c.handle}</span><span className="text-xs text-ink-2 tnum">{c.followers != null ? `${n(c.followers)} now` : ""}</span></span>
                <Input name={`t-${c.account_id}`} aria-label={`Follower target for @${c.handle}`} type="number" inputMode="numeric" min={1} defaultValue={c.goal ?? ""} placeholder="Target" />
                <Input name={`b-${c.account_id}`} aria-label={`Date for @${c.handle}`} type="date" min={tomorrow} defaultValue={c.by ?? ""} />
              </li>
            ))}
          </ul>
          <DialogFooter><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save goals"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
