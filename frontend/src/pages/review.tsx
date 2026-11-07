/**
 * The public review page. A client opens a link the team shared, reads the posts that wait for
 * approval and approves or asks for changes. No account, no sidebar: the brand's colour and a list.
 */
import { useEffect, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { CheckCircle2, MessageSquareText } from "lucide-react";
import type { ReactNode } from "react";
import { StatusBadge } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useReview, useReviewAction, type ReviewPost } from "@/features/collab/api";
import { ApiError } from "@/lib/api";
import { applyBrandColor } from "@/lib/brand-color";
import { PlatformMark } from "@/lib/platforms";
import { fmtDateTime } from "@/lib/time";

const NAME_KEY = "spark.reviewer";

export function ReviewPage() {
  const { token } = useParams({ from: "/review/$token" });
  const { data, isPending, error } = useReview(token);
  const [name, setName] = useState(() => { try { return localStorage.getItem(NAME_KEY) ?? ""; } catch { return ""; } });
  useEffect(() => { if (data?.brand.color) applyBrandColor(data.brand.color); }, [data?.brand.color]);
  useEffect(() => { try { localStorage.setItem(NAME_KEY, name); } catch { /* private mode: the name just isn't remembered */ } }, [name]);

  if (isPending) return <Frame><Skeleton className="h-10 w-64" /><Skeleton className="mt-6 h-40" /></Frame>;
  if (error || !data) {
    const gone = error instanceof ApiError && error.status === 404;
    return (
      <Frame>
        <div className="rounded-card border border-line bg-surface p-6 text-center">
          <h1 className="display text-2xl font-semibold">{gone ? "This review link no longer works" : "Could not load the review"}</h1>
          <p className="mt-2 text-sm text-ink-2">{gone ? "It may have expired or been revoked. Ask the team for a new one." : error?.message}</p>
        </div>
      </Frame>
    );
  }
  const pending = data.posts.filter((p) => p.status === "pending_approval").length;
  return (
    <Frame>
      <header className="mb-6">
        <p className="text-sm text-ink-2">Posts to review for</p>
        <h1 className="display text-3xl font-semibold leading-tight"><span className="mr-2 inline-block size-3 rounded-full bg-brand align-middle" aria-hidden />{data.brand.name}</h1>
        <p className="mt-2 text-sm text-ink-2">
          {pending ? `${pending} ${pending === 1 ? "post waits" : "posts wait"} for your approval.` : "Nothing waits for approval right now."}
          {data.expires_at && ` This link works until ${fmtDateTime(data.expires_at, data.timezone)}.`}
        </p>
        <div className="mt-4 max-w-xs space-y-1.5">
          <Label htmlFor="reviewer">Your name</Label>
          <Input id="reviewer" value={name} onChange={(e) => setName(e.target.value)} placeholder="So the team knows who answered" autoComplete="name" />
        </div>
      </header>
      {data.posts.length === 0 ? (
        <p className="rounded-card border border-line bg-surface p-6 text-center text-sm text-ink-2">No posts to review yet. Check back later.</p>
      ) : (
        <ul className="space-y-4">{data.posts.map((p) => <ReviewCard key={p.id} post={p} token={token} tz={data.timezone} name={name.trim()} />)}</ul>
      )}
      <footer className="mt-10 text-center text-xs text-ink-2">Shared from Spark. Your name and notes reach the {data.brand.name} team only.</footer>
    </Frame>
  );
}

function Frame({ children }: { children: ReactNode }) {
  return <main className="min-h-dvh bg-paper px-4 py-10 text-ink"><div className="mx-auto w-full max-w-2xl">{children}</div></main>;
}

function ReviewCard({ post, token, tz, name }: { post: ReviewPost; token: string; tz: string; name: string }) {
  const approve = useReviewAction(token, "approve");
  const request = useReviewAction(token, "request-changes");
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState("");
  const pending = post.status === "pending_approval";
  const busy = approve.isPending || request.isPending;
  const needName = !name;
  return (
    <li className="rounded-card border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
        <div className="flex -space-x-1">{post.channels.map((c, i) => <span key={i} title={c.handle} className="grid size-6 place-items-center rounded-full border border-line bg-surface"><PlatformMark platform={c.platform} size={12} /></span>)}</div>
        <span className="truncate">{post.channels.map((c) => c.handle).join(", ")}</span>
        <span className="ml-auto flex items-center gap-2">{post.scheduled_at && <span className="tnum">{fmtDateTime(post.scheduled_at, tz)}</span>}<StatusBadge status={post.status} /></span>
      </div>
      <p className="mt-3 whitespace-pre-wrap text-[15px] leading-relaxed">{post.content}</p>
      {post.link && <a href={post.link} target="_blank" rel="noopener" className="mt-2 block truncate text-sm text-brand underline">{post.link}</a>}
      {post.media.length > 0 && <div className="mt-3 grid grid-cols-3 gap-2">{post.media.map((m) => <img key={m} src={m} alt="" className="aspect-square w-full rounded-control object-cover" />)}</div>}
      {post.comments.length > 0 && (
        <ul className="mt-4 space-y-2 border-t border-line pt-3 text-sm">
          {post.comments.map((c) => (
            <li key={c.id}>
              <span className="font-medium">{c.author.name}</span>
              {c.kind === "change_request" && <span className="ml-1 text-st-pending">asked for changes</span>}
              {c.kind === "approval" && <span className="ml-1 text-st-published">approved</span>}
              {c.created_at && <span className="text-ink-2"> · {fmtDateTime(c.created_at, tz)}</span>}
              <p className="text-ink-2">{c.body}</p>
            </li>
          ))}
        </ul>
      )}
      {pending && (
        <div className="mt-4 space-y-3 border-t border-line pt-4">
          {asking ? (
            <>
              <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What should change?" autoFocus />
              <div className="flex gap-2">
                <Button size="sm" disabled={busy || needName || !note.trim()} onClick={() => request.mutate({ post_id: post.id, name, body: note }, { onSuccess: () => { setAsking(false); setNote(""); } })}>Send</Button>
                <Button size="sm" variant="ghost" onClick={() => setAsking(false)}>Cancel</Button>
              </div>
            </>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" disabled={busy || needName} onClick={() => approve.mutate({ post_id: post.id, name })}><CheckCircle2 className="size-4" />Approve</Button>
              <Button size="sm" variant="outline" disabled={busy || needName} onClick={() => setAsking(true)}><MessageSquareText className="size-4" />Request changes</Button>
              {needName && <span className="text-xs text-ink-2">Add your name above first.</span>}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
