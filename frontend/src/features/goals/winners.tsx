/**
 * Winners on Analytics: recent posts in the top tenth of their own channel's engagement rate, with
 * two offers each. "New angle" has the AI write the idea again; "Post to other channels" copies it
 * to the channels it missed. Both make drafts and open them; nothing goes out until scheduled.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Share2, Sparkles } from "lucide-react";
import type { components } from "@/api/schema";
import { useBrand, usePerms } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useComposer } from "@/features/composer/composer-host";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";
import { PlatformMark } from "@/lib/platforms";

type S = components["schemas"];
type Winner = S["WinnerOut"];
const tp = (brand_id: number, target_id: number) => ({ params: { path: { brand_id, target_id } } });

export const useWinners = (b: number) => useQuery({
  queryKey: ["winners", b],
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/winners", { params: { path: { brand_id: b } } })),
});
const keys = (b: number) => [["winners", b], ["posts", b], ["activity", b], ["today", b]];
export const useNewAngle = (b: number) => useAction(async (target_id: number) =>
  unwrap(await api.POST("/brands/{brand_id}/winners/{target_id}/new-angle", { ...tp(b, target_id), body: {} })), keys(b));
export const useShareWinner = (b: number) => useAction(async ({ target_id, account_ids }: { target_id: number; account_ids: number[] }) =>
  unwrap(await api.POST("/brands/{brand_id}/winners/{target_id}/share", { ...tp(b, target_id), body: { account_ids } })), keys(b));

export function Winners() {
  const brand = useBrand();
  const { data, isPending } = useWinners(brand.id);
  const [sharing, setSharing] = useState<Winner | null>(null);
  if (isPending || !data) return <Skeleton className="h-32" />;
  const rated = data.channels.filter((c) => c.rated);
  return (
    <section aria-labelledby="win-h" className="rounded-card border border-line bg-surface p-5">
      <h2 id="win-h" className="mb-1 text-base font-semibold">Winners</h2>
      <p className="text-sm text-ink-2">
        Posts from the last {data.window_days} days in the top {data.top_share_pct}% of their own channel's engagement rate. Each offer makes a draft; nothing goes out until you schedule it.
      </p>
      {rated.length === 0 ? (
        <p className="mt-3 text-sm">
          A channel needs {data.min_posts} posts with numbers in the last 90 days before Spark can pick its winners
          {data.channels.length > 0 && <>: {data.channels.map((c) => `@${c.handle} has ${c.posts}`).join(", ")}</>}.
        </p>
      ) : data.winners.length === 0 ? (
        <p className="mt-3 text-sm">No standouts in the last {data.window_days} days. A winner needs at least 1.5 times its channel's usual rate.</p>
      ) : (
        <ul className="mt-4 divide-y divide-line border-t border-line">
          {data.winners.map((w) => <WinnerRow key={w.target_id} w={w} onShare={() => setSharing(w)} />)}
        </ul>
      )}
      <ShareDialog winner={sharing} onClose={() => setSharing(null)} />
    </section>
  );
}

function WinnerRow({ w, onShare }: { w: Winner; onShare: () => void }) {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const composer = useComposer();
  const angle = useNewAngle(brand.id);
  return (
    <li className="py-3 text-sm">
      <div className="flex items-start gap-3">
        <PlatformMark platform={w.platform} size={14} className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <button type="button" onClick={() => composer.open({ postId: w.post_id })} className="block w-full truncate text-left font-medium hover:underline">{w.text || <span className="text-ink-2">(media only)</span>}</button>
          <p className="text-xs text-ink-2 tnum">
            @{w.handle}: {w.engagement_rate_pct.toFixed(1)}% engagement rate{w.vs_usual != null && <>, {w.vs_usual.toFixed(1)}× the channel's usual {w.median_rate_pct.toFixed(1)}%</>}, out of {w.channel_posts} posts
          </p>
          {w.follow_ups.length > 0 && (
            <p className="mt-1 flex flex-wrap gap-x-3 text-xs">
              {w.follow_ups.map((f) => (
                <button key={f.post_id} type="button" className="text-brand hover:underline" onClick={() => composer.open({ postId: f.post_id })}>
                  {f.kind === "angle" ? "New angle" : "Copy"} ({f.status})
                </button>
              ))}
            </p>
          )}
        </div>
      </div>
      {canEdit && (
        <div className="mt-2 flex flex-wrap gap-2 pl-[26px]">
          <Button size="sm" variant="outline" disabled={angle.isPending} onClick={() => angle.mutate(w.target_id, { onSuccess: (r) => composer.open({ postId: r.post_id }) })}>
            <Sparkles className="size-4" />{angle.isPending ? "Writing…" : "New angle"}
          </Button>
          {w.missed.length > 0 && (
            <Button size="sm" variant="outline" onClick={onShare}>
              <Share2 className="size-4" />Post to {w.missed.length === 1 ? `@${w.missed[0].handle}` : `${w.missed.length} more channels`}
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

function ShareDialog({ winner, onClose }: { winner: Winner | null; onClose: () => void }) {
  const brand = useBrand();
  const composer = useComposer();
  const share = useShareWinner(brand.id);
  const [picked, setPicked] = useState<number[] | null>(null);
  const chosen = picked ?? winner?.missed.map((m) => m.account_id) ?? [];
  const close = () => { setPicked(null); onClose(); };
  const toggle = (id: number) => setPicked(chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id]);
  return (
    <Dialog open={winner !== null} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Post to other channels</DialogTitle></DialogHeader>
        {winner && (
          <form className="space-y-4 text-sm" onSubmit={(e) => {
            e.preventDefault();
            share.mutate({ target_id: winner.target_id, account_ids: chosen }, { onSuccess: (r) => { close(); composer.open({ postId: r.post_id }); } });
          }}>
            <p className="text-ink-2">A draft with the same text and media opens next, so you can fit it to each channel before scheduling.</p>
            <fieldset className="space-y-2">
              <legend className="sr-only">Channels</legend>
              {winner.missed.map((m) => (
                <label key={m.account_id} htmlFor={`win-${winner.target_id}-${m.account_id}`} className="flex items-center gap-2 rounded-control border border-line px-3 py-2 has-[:checked]:border-brand">
                  <input id={`win-${winner.target_id}-${m.account_id}`} type="checkbox" className="accent-[var(--brand)]" checked={chosen.includes(m.account_id)} onChange={() => toggle(m.account_id)} />
                  <PlatformMark platform={m.platform} size={14} />@{m.handle}
                </label>
              ))}
            </fieldset>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={close}>Cancel</Button>
              <Button type="submit" disabled={share.isPending || chosen.length === 0}>{share.isPending ? "Making…" : "Make draft"}</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
