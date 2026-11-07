/** Inbox: comments on your posts across channels, answered from one place (live from Zernio). */
import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { Heart, Inbox, Send } from "lucide-react";
import { useBrand, useSession } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useComments, useInbox, useLike, useReply, type InboxOut } from "@/features/api4";
import { PlatformMark } from "@/lib/platforms";
import { cn } from "@/lib/utils";

type Item = InboxOut["items"][number];

export function InboxPage() {
  const brand = useBrand();
  const [account, setAccount] = useState<string | undefined>();
  const [days, setDays] = useState(30);
  const { data, isPending } = useInbox(brand.id, account, days);
  const [open, setOpen] = useState<Item | null>(null);
  const { data: session } = useSession();
  const isOwner = session?.user?.role === "owner";

  return (
    <>
      <PageHeader title="Inbox" description="Comments on your posts, newest first."
                  actions={data?.ready && <div className="flex rounded-control border border-line p-0.5 text-sm">{[7, 30, 90].map((d) => <button key={d} onClick={() => setDays(d)} className={cn("rounded-[4px] px-2.5 py-1 tnum", days === d ? "bg-hover font-medium" : "text-ink-2")}>{d}d</button>)}</div>} />
      {isPending ? <Skeleton className="h-64" /> : !data?.ready ? (
        <EmptyState icon={Inbox} title="The inbox needs Zernio" body="Comments arrive through Zernio-connected channels. Add the Zernio key and connect a channel."
                    action={isOwner ? <Button asChild size="sm"><Link to="/settings" search={(p) => ({ ...p, tab: "connectors", connector: "zernio" })}>Set up Zernio</Link></Button> : undefined} />
      ) : data.accounts.length === 0 ? (
        <EmptyState icon={Inbox} title="No Zernio channels yet" body="Connect a channel through Zernio and its comments show up here." action={<Button asChild size="sm"><Link to="/channels" search={(p) => p}>Channels</Link></Button>} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="space-y-3 lg:col-span-2">
            <div className="flex flex-wrap gap-1">
              <button onClick={() => setAccount(undefined)} className={cn("rounded-full border px-2.5 py-0.5 text-xs", !account ? "border-ink bg-ink text-paper" : "border-line text-ink-2")}>All</button>
              {data.accounts.map((a) => <button key={a.id} onClick={() => setAccount(a.external_id)} className={cn("flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs", account === a.external_id ? "border-ink bg-ink text-paper" : "border-line text-ink-2")}><PlatformMark platform={a.platform} size={11} mono={account === a.external_id} />{a.handle}</button>)}
            </div>
            {data.error && <p className="text-sm text-st-failed">{data.error}</p>}
            {data.items.length === 0 ? <p className="rounded-card border border-dashed border-line-strong p-6 text-center text-sm text-ink-2">No comments in the last {days} days.</p> : (
              <ul className="divide-y divide-line rounded-card border border-line bg-surface">
                {data.items.map((it) => (
                  <li key={`${it.account.id}-${it.post_id}`}>
                    <button type="button" onClick={() => setOpen(it)} className={cn("flex w-full items-start gap-3 px-3 py-2.5 text-left text-sm hover:bg-hover", open?.post_id === it.post_id && "bg-brand-soft")}>
                      {it.picture ? <img src={it.picture} alt="" className="size-10 shrink-0 rounded object-cover" /> : <span className="grid size-10 shrink-0 place-items-center rounded border border-line"><PlatformMark platform={it.platform} size={16} /></span>}
                      <span className="min-w-0 flex-1"><span className="line-clamp-2">{it.content || "(media post)"}</span><span className="mt-0.5 block text-xs text-ink-2">{it.account.handle} · {it.comment_count} comments · {it.like_count} likes</span></span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="lg:col-span-3">
            {open ? <Thread item={open} /> : <p className="rounded-card border border-dashed border-line-strong p-10 text-center text-sm text-ink-2">Pick a post to read and answer its comments.</p>}
          </div>
        </div>
      )}
    </>
  );
}

function Thread({ item }: { item: Item }) {
  const brand = useBrand();
  const { data, isPending } = useComments(brand.id, item.post_id, item.account.external_id);
  const reply = useReply(brand.id);
  const like = useLike(brand.id);
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const { data: session } = useSession();
  const canEdit = session?.user?.role !== "viewer";
  const send = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const form = e.currentTarget;
    const target = data?.comments.find((c) => str(c.id) === replyTo) as Record<string, unknown> | undefined;
    reply.mutate({ postId: item.post_id, body: { account: item.account.external_id, message: String(fd.get("message")), comment_id: replyTo,
      root_uri: str(target?.rootUri) || null, root_cid: str(target?.rootCid) || null, parent_cid: str(target?.cid) || null } }, { onSuccess: () => { form.reset(); setReplyTo(null); } });
  };
  return (
    <section className="rounded-card border border-line bg-surface">
      <header className="flex items-start gap-3 border-b border-line px-4 py-3 text-sm">
        <PlatformMark platform={item.platform} size={16} />
        <div className="min-w-0 flex-1"><p className="line-clamp-3">{item.content || "(media post)"}</p><div className="text-xs text-ink-2">{item.account.handle}{item.permalink && <> · <a href={item.permalink} target="_blank" rel="noopener" className="underline">Open post</a></>}</div></div>
      </header>
      <div className="max-h-[50vh] overflow-y-auto">
        {isPending ? <Skeleton className="m-4 h-24" /> : data?.comments.length === 0 ? <p className="p-4 text-sm text-ink-2">No comments yet.</p> : (
          <ul className="divide-y divide-line">
            {data?.comments.map((c) => {
              const id = str(c.id);
              const author = (c.author as Record<string, unknown> | undefined) ?? {};
              return (
                <li key={id} className="px-4 py-3 text-sm">
                  <div className="flex items-center gap-2 text-xs text-ink-2"><span className="font-medium text-ink">{str(author.name) || str(author.username) || "Someone"}</span>{c.createdAt ? <span>{new Date(str(c.createdAt)).toLocaleString()}</span> : null}</div>
                  <p className="mt-0.5 whitespace-pre-wrap">{str(c.text) || str(c.message)}</p>
                  {canEdit && (
                    <div className="mt-1 flex gap-3 text-xs">
                      <button type="button" className="text-ink-2 hover:text-ink" onClick={() => setReplyTo(id)}>Reply</button>
                      <button type="button" className={cn("flex items-center gap-1 hover:text-ink", c.liked ? "text-st-failed" : "text-ink-2")} onClick={() => like.mutate({ postId: item.post_id, body: { account: item.account.external_id, comment_id: id, liked: !c.liked } })}><Heart className={cn("size-3", Boolean(c.liked) && "fill-current")} />{c.liked ? "Liked" : "Like"}</button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {canEdit && (
        <form onSubmit={send} className="space-y-2 border-t border-line p-3">
          {replyTo && <div className="flex items-center justify-between text-xs text-ink-2"><span>Replying to a comment</span><button type="button" className="underline" onClick={() => setReplyTo(null)}>Reply to the post instead</button></div>}
          <Textarea name="message" rows={2} required placeholder="Write a reply…" />
          <div className="flex justify-end"><Button type="submit" size="sm" disabled={reply.isPending}><Send className="size-4" />{reply.isPending ? "Sending…" : "Reply"}</Button></div>
        </form>
      )}
    </section>
  );
}

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}
