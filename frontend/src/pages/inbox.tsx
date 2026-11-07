/**
 * Inbox: everything people say to the brand (comments, messages, reviews, mentions), kept in
 * Spark, labelled by AI, answered from one place. Three columns: filters, the list, the thread.
 */
import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { ArchiveRestore, Check, ExternalLink, Heart, Inbox, Loader2, MessageSquareText, RefreshCw, Send, Sparkles, Star } from "lucide-react";
import { useBrand, usePerms, useSession } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useMembers } from "@/features/collab/api";
import {
  INTENT_LABEL, KIND_LABEL, useAssignItem, useInboxItem, useInboxItems, useLikeItem, useReplyItem, useSavedReplies, useSetItemStatus, useSuggestReplies,
  useSyncInbox, type InboxFilters, type InboxItem,
} from "@/features/inbox/api";
import { PlatformMark } from "@/lib/platforms";
import { fmtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

const SENTIMENT: Record<string, string> = { positive: "bg-st-published", neutral: "bg-ink-2/50", negative: "bg-st-failed" };

export function InboxPage() {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data: session } = useSession();
  const [filters, setFilters] = useState<InboxFilters>({ status: "open" });
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const { data, isPending } = useInboxItems(brand.id, { ...filters, q: q.trim() || undefined });
  const sync = useSyncInbox(brand.id);
  const set = (patch: InboxFilters) => setFilters((f) => ({ ...f, ...patch }));
  const counts = data?.counts;
  const items = data?.items ?? [];
  const activeId = openId != null && items.some((i) => i.id === openId) ? openId : null;
  const isOwner = session?.user?.role === "owner";

  return (
    <>
      <PageHeader title={<>Inbox{counts?.open ? <span className="ml-2 align-middle text-base font-normal text-ink-2 tnum">{counts.open} open</span> : null}</>}
                  description="Comments, messages, reviews and mentions, answered from one place."
                  actions={<div className="flex items-center gap-2">
                    <div className="flex rounded-control border border-line p-0.5 text-sm">{(["open", "resolved", "all"] as const).map((s) => <button key={s} onClick={() => set({ status: s })} className={cn("rounded-[4px] px-2.5 py-1 capitalize", filters.status === s ? "bg-hover font-medium" : "text-ink-2")}>{s}</button>)}</div>
                    {canEdit && data?.ready && <Button size="sm" variant="outline" disabled={sync.isPending} onClick={() => sync.mutate(undefined)}><RefreshCw className={cn("size-4", sync.isPending && "animate-spin")} />Sync</Button>}
                  </div>} />
      {isPending && !data ? <Skeleton className="h-64" /> : !data?.ready ? (
        <EmptyState icon={Inbox} title="The inbox needs Zernio" body="Comments, messages and reviews arrive through Zernio-connected channels. Add the Zernio key and connect a channel; webhooks fill the inbox from then on."
                    action={isOwner ? <Button asChild size="sm"><Link to="/settings" search={(p) => ({ ...p, tab: "connectors", connector: "zernio" })}>Set up Zernio</Link></Button> : undefined} />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[13rem_minmax(0,1fr)_minmax(0,1.3fr)]">
          <aside className="space-y-4 text-sm">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" aria-label="Search the inbox" className="h-8" />
            <nav aria-label="Inbox filters" className="space-y-0.5">
              <FilterRow label="Everything" count={counts?.open} active={!filters.kind && !filters.has_draft && !filters.sentiment && filters.assignee !== "me"} onClick={() => set({ kind: undefined, has_draft: undefined, sentiment: undefined, assignee: undefined })} />
              {Object.entries(KIND_LABEL).map(([k, label]) => <FilterRow key={k} label={label} count={counts?.by_kind[k]} active={filters.kind === k} onClick={() => set({ kind: filters.kind === k ? undefined : k })} />)}
            </nav>
            <nav aria-label="Triage" className="space-y-0.5 border-t border-line pt-3">
              <FilterRow label="Assigned to me" active={filters.assignee === "me"} onClick={() => set({ assignee: filters.assignee === "me" ? undefined : "me" })} />
              <FilterRow label="Negative" count={counts?.negative} tone="text-st-failed" active={filters.sentiment === "negative"} onClick={() => set({ sentiment: filters.sentiment === "negative" ? undefined : "negative" })} />
              <FilterRow label="Replies to approve" count={counts?.drafts} tone="text-st-pending" active={Boolean(filters.has_draft)} onClick={() => set({ has_draft: filters.has_draft ? undefined : true })} />
            </nav>
            {data.accounts.length > 1 && (
              <nav aria-label="Channels" className="space-y-0.5 border-t border-line pt-3">
                {data.accounts.map((a) => <button key={a.id} type="button" onClick={() => set({ account: filters.account === a.id ? undefined : a.id })} className={cn("nav-item w-full", filters.account === a.id && "bg-brand-soft")}><PlatformMark platform={a.platform} size={14} /><span className="truncate">{a.handle}</span></button>)}
              </nav>
            )}
          </aside>

          <section aria-label="Conversations" className="min-w-0">
            {items.length === 0 ? (
              <div className="rounded-card border border-dashed border-line p-8 text-center text-sm text-ink-2">
                {filters.status === "open" && !filters.kind && !q ? <><Check className="mx-auto mb-2 size-5 text-st-published" />Nothing waits for an answer. New comments, messages and reviews land here as they arrive.</> : "Nothing matches these filters."}
              </div>
            ) : (
              <ul className="divide-y divide-line rounded-card border border-line bg-surface">
                {items.map((it) => <Row key={it.id} it={it} active={activeId === it.id} onOpen={() => setOpenId(it.id)} tz={brand.timezone} />)}
              </ul>
            )}
          </section>

          <section aria-label="Thread" className="min-w-0">
            {activeId ? <ThreadPane id={activeId} onClose={() => setOpenId(null)} /> : (
              <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-ink-2">Pick a conversation to read it and answer.</p>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function FilterRow({ label, count, active, onClick, tone }: { label: string; count?: number; active: boolean; onClick: () => void; tone?: string }) {
  return (
    <button type="button" onClick={onClick} className={cn("nav-item w-full", active && "bg-brand-soft font-medium")}>
      <span className="flex-1 truncate">{label}</span>
      {typeof count === "number" && count > 0 && <span className={cn("text-xs tnum", tone ?? "text-ink-2")}>{count}</span>}
    </button>
  );
}

function Avatar({ it, size = 9 }: { it: InboxItem; size?: number }) {
  const cls = `size-${size}`;
  return it.author.picture ? <img src={it.author.picture} alt="" className={cn(cls, "shrink-0 rounded-full object-cover")} />
    : <span className={cn(cls, "grid shrink-0 place-items-center rounded-full bg-brand-soft text-xs font-semibold")}>{(it.author.name || "?").slice(0, 1).toUpperCase()}</span>;
}

function Stars({ n }: { n: number }) {
  return <span className="inline-flex items-center gap-0.5" aria-label={`${n} stars`}>{Array.from({ length: 5 }).map((_, i) => <Star key={i} className={cn("size-3", i < n ? "fill-st-pending text-st-pending" : "text-line")} />)}</span>;
}

function Row({ it, active, onOpen, tz }: { it: InboxItem; active: boolean; onOpen: () => void; tz: string }) {
  return (
    <li>
      <button type="button" onClick={onOpen} className={cn("flex w-full items-start gap-3 px-3 py-2.5 text-left text-sm hover:bg-hover", active && "bg-brand-soft")}>
        <Avatar it={it} />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className={cn("size-1.5 shrink-0 rounded-full", SENTIMENT[it.sentiment ?? ""] ?? "bg-transparent")} aria-label={it.sentiment ?? undefined} />
            <span className="truncate font-medium">{it.author.name}</span>
            <PlatformMark platform={it.account.platform} size={11} />
            {it.rating ? <Stars n={it.rating} /> : null}
            {it.received_at && <span className="ml-auto shrink-0 text-xs text-ink-2 tnum">{fmtDateTime(it.received_at, tz)}</span>}
          </span>
          <span className="mt-0.5 line-clamp-2 text-ink-2">{it.text || "(no text)"}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1 text-[10px]">
            <span className="rounded-full border border-line px-1.5 text-ink-2">{KIND_LABEL[it.kind]?.replace(/s$/, "") ?? it.kind}</span>
            {it.intent && it.intent !== "other" && <span className={cn("rounded-full border px-1.5", it.intent === "complaint" ? "border-st-failed/40 text-st-failed" : it.intent === "lead" ? "border-st-published/40 text-st-published" : "border-line text-ink-2")}>{INTENT_LABEL[it.intent]}</span>}
            {it.draft_reply && <span className="rounded-full border border-st-pending/40 px-1.5 text-st-pending">reply ready</span>}
            {it.assignee && <span className="text-ink-2">→ {it.assignee.name}</span>}
          </span>
        </span>
      </button>
    </li>
  );
}

function ThreadPane({ id, onClose }: { id: number; onClose: () => void }) {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data: session } = useSession();
  const { data, isPending } = useInboxItem(brand.id, id);
  const { data: saved = [] } = useSavedReplies(brand.id);
  const { data: members = [] } = useMembers(brand.id);
  const reply = useReplyItem(brand.id);
  const status = useSetItemStatus(brand.id);
  const assign = useAssignItem(brand.id);
  const suggest = useSuggestReplies(brand.id);
  const like = useLikeItem(brand.id);
  const [text, setText] = useState("");
  const [seeded, setSeeded] = useState<number | null>(null);
  const it = data?.item;
  if (it && seeded !== it.id) { setSeeded(it.id); setText(it.draft_reply ?? ""); }
  if (isPending || !it) return <Skeleton className="h-64" />;
  const send = (e?: FormEvent) => {
    e?.preventDefault();
    const t = text.trim();
    if (!t) return;
    reply.mutate({ id: it.id, body: { text: t, from_draft: Boolean(it.draft_reply && t === it.draft_reply) } }, { onSuccess: () => setText("") });
  };
  const thread = data.thread.length ? data.thread : [it];
  const ai = session?.features.ai;
  return (
    <div className="flex max-h-[calc(100dvh-11rem)] flex-col rounded-card border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5 text-sm">
        <Avatar it={it} size={8} />
        <div className="min-w-0 flex-1"><div className="truncate font-medium">{it.author.name}{it.author.handle && <span className="ml-1 font-normal text-ink-2">@{it.author.handle}</span>}</div><div className="truncate text-xs text-ink-2">{KIND_LABEL[it.kind]?.replace(/s$/, "")} on {it.account.handle}{it.post?.location ? ` · ${it.post.location}` : ""}</div></div>
        {it.permalink && <a href={it.permalink} target="_blank" rel="noopener" className="text-ink-2 hover:text-ink" title="Open on the network"><ExternalLink className="size-4" /></a>}
        {canEdit && (
          <>
            <Select value={it.assignee ? String(it.assignee.id) : "none"} onValueChange={(v) => assign.mutate({ id: it.id, user_id: v === "none" ? null : Number(v) })}>
              <SelectTrigger className="h-7 w-32 text-xs" aria-label="Assign to"><SelectValue placeholder="Assign" /></SelectTrigger>
              <SelectContent><SelectItem value="none">Unassigned</SelectItem>{members.map((m) => <SelectItem key={m.user_id} value={String(m.user_id)}>{m.name}</SelectItem>)}</SelectContent>
            </Select>
            {it.status === "open" ? <Button size="sm" variant="outline" onClick={() => status.mutate({ id: it.id, status: "resolved" })}><Check className="size-4" />Resolve</Button>
              : <Button size="sm" variant="ghost" onClick={() => status.mutate({ id: it.id, status: "open" })}><ArchiveRestore className="size-4" />Reopen</Button>}
          </>
        )}
        <button type="button" onClick={onClose} className="text-xs text-ink-2 hover:text-ink lg:hidden">Close</button>
      </header>

      {it.kind === "comment" && Boolean(it.post?.content) && (
        <div className="flex items-center gap-3 border-b border-line bg-paper px-4 py-2 text-xs text-ink-2">
          {Boolean(it.post.image) && <img src={String(it.post.image)} alt="" className="size-8 rounded object-cover" />}
          <span className="line-clamp-2 flex-1">On your post: {String(it.post.content)}</span>
        </div>
      )}

      <ol className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm">
        {thread.map((m) => (
          <li key={m.id} className={cn("flex", m.direction === "outgoing" ? "justify-end" : "justify-start")}>
            <div className={cn("max-w-[85%] rounded-card px-3 py-2", m.direction === "outgoing" ? "bg-brand text-brand-fg" : "bg-hover", m.id === it.id && m.direction === "incoming" && "ring-1 ring-brand/40")}>
              <div className={cn("mb-0.5 flex items-center gap-2 text-[11px]", m.direction === "outgoing" ? "text-brand-fg/80" : "text-ink-2")}><span className="font-medium">{m.author.name}</span>{m.rating ? <Stars n={m.rating} /> : null}{m.received_at && <span className="tnum">{fmtDateTime(m.received_at, brand.timezone)}</span>}</div>
              <p className="whitespace-pre-wrap">{m.text || "(attachment)"}</p>
              {m.attachments.length > 0 && <p className={cn("mt-1 text-[11px]", m.direction === "outgoing" ? "text-brand-fg/80" : "text-ink-2")}>{m.attachments.length} attachment{m.attachments.length === 1 ? "" : "s"}</p>}
            </div>
          </li>
        ))}
      </ol>

      {canEdit && it.direction === "incoming" && it.kind !== "mention" && (
        <form onSubmit={send} className="space-y-2 border-t border-line p-3">
          {it.draft_reply && text === it.draft_reply && (
            <div className="flex items-center gap-2 rounded-control border border-st-pending/40 bg-st-pending/5 px-2.5 py-1.5 text-xs">
              <Sparkles className="size-3.5 text-st-pending" />{it.draft_rule ? `The rule “${it.draft_rule.name}” prepared this reply.` : "A rule prepared this reply."} Send it, edit it, or <button type="button" className="underline" onClick={() => status.mutate({ id: it.id, status: "open" })}>discard</button>.
            </div>
          )}
          {(it.suggestions.length > 0 || ai) && (
            <div className="flex flex-wrap items-center gap-1.5">
              {it.suggestions.map((s, i) => s && <button key={i} type="button" onClick={() => setText(s)} className="max-w-full truncate rounded-full border border-line px-2.5 py-1 text-left text-xs text-ink-2 hover:border-brand hover:text-ink" title={s}>{s}</button>)}
              {ai && <button type="button" disabled={suggest.isPending} onClick={() => suggest.mutate(it.id)} className="flex items-center gap-1 rounded-full border border-dashed border-line px-2.5 py-1 text-xs text-ink-2 hover:border-brand hover:text-ink">{suggest.isPending ? <Loader2 className="size-3 animate-spin" /> : <Sparkles className="size-3" />}{it.suggestions.length ? "Suggest again" : "Suggest replies"}</button>}
            </div>
          )}
          <div className="flex items-end gap-2">
            <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder={`Reply to ${it.author.name}…`} className="min-h-10 text-sm" aria-label="Reply" onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }} />
            <div className="flex shrink-0 flex-col gap-1">
              {saved.length > 0 && (
                <Select value="" onValueChange={(v) => { const s = saved.find((x) => String(x.id) === v); if (s) setText((t) => (t ? t + "\n" : "") + s.body); }}>
                  <SelectTrigger className="h-8 w-28 text-xs" aria-label="Insert a saved reply"><MessageSquareText className="size-3.5" /><span className="truncate">Saved</span></SelectTrigger>
                  <SelectContent>{saved.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.title}{s.shortcut ? ` · /${s.shortcut}` : ""}</SelectItem>)}</SelectContent>
                </Select>
              )}
              <Button type="submit" size="sm" disabled={reply.isPending || !text.trim()}>{reply.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}Send</Button>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs text-ink-2">
            {it.kind === "comment" && <button type="button" className="flex items-center gap-1 hover:text-ink" onClick={() => like.mutate({ id: it.id, liked: true })}><Heart className="size-3.5" />Like</button>}
            <span>⌘↵ sends · goes out as {it.account.handle}</span>
          </div>
        </form>
      )}
    </div>
  );
}
