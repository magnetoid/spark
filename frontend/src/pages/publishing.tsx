/**
 * Publishing: the queue per channel, the calendar, and the drafts / approvals / sent lists.
 * One page, one URL per view (?view=queue|calendar|drafts|approvals|sent).
 */
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { ArrowUpToLine, CalendarDays, ChevronLeft, ChevronRight, Copy, GripVertical, Pencil, Plus, Send, Trash2, X } from "lucide-react";
import { useBrand, usePerms } from "@/app/session";
import { EmptyState, PageHeader, StatusBadge, statusColorVar } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ReviewLinksBar } from "@/features/collab/panels";
import { useComposer } from "@/features/composer/composer-host";
import { useAccounts, useCampaigns, usePostActions, usePosts, useQueue, type AccountOut, type PostOut, type QueueOut } from "@/features/posts/api";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { addDays, fmtDateTime, fmtDay, fmtTime, fromLocalInput, startOfWeek, toLocalInput, todayKey, zonedDateKey } from "@/lib/time";
import { cn } from "@/lib/utils";

const VIEWS = [["queue", "Queue"], ["calendar", "Calendar"], ["drafts", "Drafts"], ["approvals", "Approvals"], ["sent", "Sent"], ["failed", "Failed"]] as const;
type View = (typeof VIEWS)[number][0];

export function PublishingPage() {
  const brand = useBrand();
  const search = useSearch({ strict: false }) as { view?: string; account?: string; cal?: string; month?: string; campaign?: string };
  const navigate = useNavigate();
  const view: View = (VIEWS.find(([k]) => k === search.view)?.[0] ?? "queue");
  const setSearch = (patch: Record<string, string | undefined>) => void navigate({ to: ".", search: (p: Record<string, unknown>) => ({ ...p, ...patch }) });
  const { data: accounts = [], isPending } = useAccounts(brand.id);
  const composer = useComposer();

  return (
    <>
      <PageHeader title="Publishing" description="What goes out, where and when."
                  actions={<Button size="sm" onClick={() => composer.open()}><Plus className="size-4" />New post</Button>} />
      <div role="tablist" aria-label="Publishing views" className="mb-5 flex gap-1 border-b border-line">
        {VIEWS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={view === k} onClick={() => setSearch({ view: k })}
                  className={cn("-mb-px border-b-2 px-3 py-2 text-sm", view === k ? "border-brand font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink")}>{label}</button>
        ))}
      </div>
      {isPending ? <Skeleton className="h-64" /> : accounts.length === 0 ? (
        <EmptyState icon={CalendarDays} title="No channels connected yet" body="Connect a social account and the queue fills with your posting slots."
                    action={<Button asChild size="sm"><Link to="/channels" search={(p) => p}>Connect a channel</Link></Button>} />
      ) : view === "queue" ? <QueueView accounts={accounts} accountParam={search.account} onAccount={(id) => setSearch({ account: String(id) })} />
        : view === "calendar" ? <CalendarView accounts={accounts} mode={search.cal === "week" ? "week" : "month"} monthKey={search.month} campaign={search.campaign} onChange={setSearch} />
        : <ListView status={view === "drafts" ? "draft" : view === "approvals" ? "pending_approval" : view === "failed" ? "failed" : "published"} />}
    </>
  );
}

// ---- queue ---------------------------------------------------------------------------------
function QueueView({ accounts, accountParam, onAccount }: { accounts: AccountOut[]; accountParam?: string; onAccount: (id: number) => void }) {
  const brand = useBrand();
  const current = accounts.find((a) => String(a.id) === accountParam) ?? accounts[0];
  const { data, isPending, error } = useQueue(brand.id, current.id);
  const actions = usePostActions(brand.id);
  const composer = useComposer();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const tz = brand.timezone;

  const days = useMemo(() => {
    const groups = new Map<string, QueueOut["items"]>();
    for (const it of data?.items ?? []) {
      const k = zonedDateKey(it.when, tz);
      groups.set(k, [...(groups.get(k) ?? []), it]);
    }
    return [...groups.entries()];
  }, [data, tz]);

  const onDragEnd = (e: DragEndEvent) => {
    const postId = Number(e.active.id);
    const when = e.over?.id ? String(e.over.id).replace(/^slot:/, "") : null;
    if (when && postId) actions.move.mutate({ id: postId, when });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-4">
      <aside className="lg:col-span-1">
        <ul className="flex gap-1 overflow-x-auto lg:flex-col">
          {accounts.map((a) => (
            <li key={a.id}>
              <button onClick={() => onAccount(a.id)} aria-current={a.id === current.id ? "page" : undefined}
                      className={cn("nav-item w-full whitespace-nowrap", !a.is_active && "opacity-60")}>
                <PlatformMark platform={a.platform} size={16} />
                <span className="truncate">{a.handle}</span>
                {!a.is_active && <span className="ml-auto text-[10px]">paused</span>}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <div className="space-y-4 lg:col-span-3">
        <div className="flex items-center gap-3 text-sm text-ink-2">
          <PlatformMark platform={current.platform} size={18} />
          <span className="font-medium text-ink">{current.handle}</span><span>{platformLabel(current.platform)}</span>
          {data && <span className="ml-auto tnum">{data.counts.queue} queued · {data.counts.drafts} drafts{data.counts.approvals ? ` · ${data.counts.approvals} awaiting approval` : ""}</span>}
        </div>
        {error && <p className="text-sm text-st-failed">{error.message}</p>}
        {isPending ? <Skeleton className="h-64" /> : days.length === 0 ? (
          <EmptyState icon={CalendarDays} title="No posting times set" body="The queue fills your weekly slots. Add some under Settings → Brand & team."
                      action={<Button asChild size="sm" variant="outline"><Link to="/settings" search={(p) => ({ ...p, tab: "times" })}>Add slots</Link></Button>} />
        ) : (
          <DndContext sensors={sensors} onDragEnd={onDragEnd}>
            {days.map(([day, items]) => (
              <section key={day} className="rounded-card border border-line bg-surface">
                <h2 className="border-b border-line px-4 py-2 text-sm font-semibold">{day === todayKey(tz) ? "Today" : fmtDay(day)}</h2>
                <ul className="divide-y divide-line">
                  {items.map((it) => <Slot key={it.when} item={it} tz={tz} account={current} actions={actions} onCompose={() => composer.open({ account: current.id, at: toLocalInput(it.when, tz) })} onEdit={(id) => composer.open({ postId: id })} />)}
                </ul>
              </section>
            ))}
          </DndContext>
        )}
      </div>
    </div>
  );
}

function Slot({ item, tz, account, actions, onCompose, onEdit }: {
  item: QueueOut["items"][number]; tz: string; account: AccountOut; actions: ReturnType<typeof usePostActions>; onCompose: () => void; onEdit: (id: number) => void;
}) {
  const { canEdit } = usePerms();
  const { canApprove } = usePerms();
  const { setNodeRef, isOver } = useDroppable({ id: `slot:${item.when}`, disabled: !!item.post });
  const post = item.post;
  const target = post?.targets.find((t) => t.account_id === account.id);
  return (
    <li ref={setNodeRef} className={cn("flex items-start gap-4 px-4 py-3", isOver && "bg-brand-soft")}>
      <time className={cn("w-14 shrink-0 pt-0.5 text-sm tnum", !post && "text-ink-2")}>{fmtTime(item.when, tz)}</time>
      {post && target ? (
        <>
          <Draggable id={post.id} disabled={!canEdit || target.status === "publishing"}>
            <button type="button" onClick={() => onEdit(post.id)} className="line-clamp-2 text-left text-sm hover:underline">{target.content_override || post.content || "(no text)"}</button>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-2">
              <StatusBadge status={target.status} />
              {post.media_ids.length > 0 && <span>{post.media_ids.length} media</span>}
              {post.targets.length > 1 && <span>+{post.targets.length - 1} other {post.targets.length > 2 ? "channels" : "channel"}</span>}
            </div>
          </Draggable>
          {canEdit && (
            <div className="flex shrink-0 items-center gap-0.5">
              <IconBtn label="Move to top" onClick={() => actions.place.mutate({ id: post.id, action: "next" })}><ArrowUpToLine className="size-4" /></IconBtn>
              <IconBtn label="Share now" onClick={() => confirm("Publish this post now?") && actions.place.mutate({ id: post.id, action: "now" })}><Send className="size-4" /></IconBtn>
              {target.status === "pending_approval" && canApprove && <Button size="sm" onClick={() => actions.approve.mutate(post.id)}>Approve</Button>}
              <IconBtn label="Remove from queue" onClick={() => actions.unschedule.mutate(post.id)}><X className="size-4" /></IconBtn>
            </div>
          )}
        </>
      ) : (
        <button type="button" onClick={onCompose} className="flex-1 rounded-control border border-dashed border-line-strong px-3 py-1.5 text-left text-sm text-ink-2 hover:border-brand hover:text-ink">
          Empty slot · add a post <span className="hidden text-xs sm:inline">or drop one here</span>
        </button>
      )}
    </li>
  );
}

/** The post row with a grip handle: the handle drags, everything else stays clickable. */
function Draggable({ id, disabled, children }: { id: number; disabled?: boolean; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id, disabled });
  return (
    <div ref={setNodeRef} className={cn("flex min-w-0 flex-1 items-start gap-1", isDragging && "opacity-50")}>
      {!disabled && (
        <button type="button" {...attributes} {...listeners} aria-label="Drag to another slot" title="Drag to another slot"
                className="-ml-2 mt-0.5 cursor-grab touch-none rounded p-0.5 text-ink-2/60 hover:bg-hover hover:text-ink focus-visible:text-ink"><GripVertical className="size-4" /></button>
      )}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

function IconBtn({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label={label} title={label} onClick={onClick}>{children}</Button>;
}

// ---- calendar -----------------------------------------------------------------------------
function CalendarView({ accounts, mode, monthKey, campaign, onChange }: {
  accounts: AccountOut[]; mode: "week" | "month"; monthKey?: string; campaign?: string; onChange: (p: Record<string, string | undefined>) => void;
}) {
  const brand = useBrand();
  const tz = brand.timezone;
  const today = todayKey(tz);
  const anchor = monthKey && /^\d{4}-\d{2}-\d{2}$/.test(monthKey) ? monthKey : today;
  const { data: campaigns = [] } = useCampaigns(brand.id);
  const [account, setAccount] = useState<string>("all");
  const composer = useComposer();
  const actions = usePostActions(brand.id);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const { first, days, title } = useMemo(() => {
    if (mode === "week") {
      const start = startOfWeek(anchor);
      return { first: start, days: Array.from({ length: 7 }, (_, i) => addDays(start, i)), title: `${fmtDay(start, { day: "numeric", month: "short" })} – ${fmtDay(addDays(start, 6), { day: "numeric", month: "short", year: "numeric" })}` };
    }
    const firstOfMonth = anchor.slice(0, 8) + "01";
    const start = startOfWeek(firstOfMonth);
    return { first: firstOfMonth, days: Array.from({ length: 42 }, (_, i) => addDays(start, i)), title: fmtDay(firstOfMonth, { month: "long", year: "numeric" }) };
  }, [anchor, mode]);

  const since = fromLocalInput(`${days[0]}T00:00`, tz)!;
  const until = fromLocalInput(`${addDays(days[days.length - 1], 1)}T00:00`, tz)!;
  const { data, isPending } = usePosts(brand.id, { since, until, limit: 200, account: account === "all" ? undefined : Number(account), campaign: campaign ? Number(campaign) : undefined });
  const byDay = useMemo(() => {
    const m = new Map<string, PostOut[]>();
    for (const p of data?.items ?? []) if (p.scheduled_at) m.set(zonedDateKey(p.scheduled_at, tz), [...(m.get(zonedDateKey(p.scheduled_at, tz)) ?? []), p]);
    return m;
  }, [data, tz]);

  const step = (n: number) => onChange({ month: mode === "week" ? addDays(startOfWeek(anchor), 7 * n) : addDays(first, n > 0 ? 32 : -1).slice(0, 8) + "01" });
  const onDragEnd = (e: DragEndEvent) => {
    const id = Number(e.active.id);
    const day = e.over?.id ? String(e.over.id).replace(/^day:/, "") : null;
    if (id && day) actions.move.mutate({ id, day });
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="icon" aria-label="Previous" onClick={() => step(-1)}><ChevronLeft className="size-4" /></Button>
        <h2 className="min-w-44 text-center text-base font-semibold">{title}</h2>
        <Button variant="ghost" size="icon" aria-label="Next" onClick={() => step(1)}><ChevronRight className="size-4" /></Button>
        <Button variant="ghost" size="sm" onClick={() => onChange({ month: undefined })}>Today</Button>
        <div className="ml-auto flex items-center gap-2">
          <div className="flex rounded-control border border-line p-0.5 text-sm">
            {(["week", "month"] as const).map((m) => <button key={m} onClick={() => onChange({ cal: m })} className={cn("rounded-[4px] px-2.5 py-1 capitalize", mode === m ? "bg-hover font-medium" : "text-ink-2")}>{m}</button>)}
          </div>
          <Select value={account} onValueChange={setAccount}>
            <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">All channels</SelectItem>{accounts.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.handle}</SelectItem>)}</SelectContent>
          </Select>
          {campaigns.length > 0 && (
            <Select value={campaign ?? "all"} onValueChange={(v) => onChange({ campaign: v === "all" ? undefined : v })}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All campaigns</SelectItem>{campaigns.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          )}
        </div>
      </div>
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="overflow-x-auto rounded-card border border-line bg-surface">
          <div className="grid min-w-[700px] grid-cols-7 border-b border-line text-xs text-ink-2">
            {days.slice(0, 7).map((d) => <div key={d} className="px-2 py-1.5">{fmtDay(d, { weekday: "short" })}{mode === "week" && <span className={cn("ml-1 tnum", d === today && "rounded bg-brand-soft px-1 font-medium text-ink")}>{Number(d.slice(8))}</span>}</div>)}
          </div>
          <div className="grid min-w-[700px] grid-cols-7">
            {days.map((d) => (
              <Day key={d} day={d} today={today} other={mode === "month" && d.slice(0, 7) !== first.slice(0, 7)} week={mode === "week"} posts={byDay.get(d) ?? []} tz={tz} loading={isPending}
                   onAdd={() => composer.open({ at: `${d}T10:00`, account: account === "all" ? undefined : Number(account) })} onOpen={(id) => composer.open({ postId: id })} />
            ))}
          </div>
        </div>
      </DndContext>
    </div>
  );
}

function Day({ day, today, other, week, posts, tz, loading, onAdd, onOpen }: {
  day: string; today: string; other: boolean; week: boolean; posts: PostOut[]; tz: string; loading: boolean; onAdd: () => void; onOpen: (id: number) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `day:${day}` });
  const past = day < today;
  return (
    <div ref={setNodeRef} className={cn("border-b border-r border-line p-1.5 align-top", week ? "min-h-56" : "min-h-24", other && "bg-paper/60 text-ink-2", isOver && "bg-brand-soft")}>
      <div className="flex items-center justify-between">
        {!week && <span className={cn("grid size-5 place-items-center rounded-full text-xs tnum", day === today && "bg-brand text-brand-fg font-semibold")}>{Number(day.slice(8))}</span>}
        {!past && <button onClick={onAdd} className="ml-auto text-xs text-ink-2 hover:text-ink" aria-label={`New post on ${day}`}>+</button>}
      </div>
      {loading && <Skeleton className="mt-1 h-4" />}
      {posts.map((p) => <Chip key={p.id} post={p} tz={tz} week={week} onOpen={() => onOpen(p.id)} />)}
    </div>
  );
}

function Chip({ post, tz, week, onOpen }: { post: PostOut; tz: string; week: boolean; onOpen: () => void }) {
  const movable = ["scheduled", "pending_approval", "draft"].includes(post.status);
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: post.id, disabled: !movable });
  return (
    <button ref={setNodeRef} {...attributes} {...listeners} onClick={onOpen} title={post.content}
            className={cn("mt-1 block w-full rounded-control border-l-2 bg-paper px-1.5 py-1 text-left text-xs hover:bg-hover", isDragging && "opacity-50", movable && "cursor-grab")}
            style={{ borderLeftColor: statusColorVar(post.status) }}>
      <span className="text-ink-2 tnum">{post.scheduled_at ? fmtTime(post.scheduled_at, tz) : ""}</span>{" "}
      <span className={week ? "line-clamp-3 whitespace-normal" : "truncate"}>{post.content || "(no text)"}</span>
      {week && <span className="mt-0.5 flex gap-1">{post.targets.map((t) => <PlatformMark key={t.id} platform={t.platform} size={12} />)}</span>}
    </button>
  );
}

// ---- lists --------------------------------------------------------------------------------
function ListView({ status }: { status: "draft" | "pending_approval" | "published" | "failed" }) {
  const brand = useBrand();
  const { data, isPending } = usePosts(brand.id, { status, limit: 100 });
  const actions = usePostActions(brand.id);
  const composer = useComposer();
  const { canApprove } = usePerms();
  if (isPending) return <Skeleton className="h-48" />;
  const items = data?.items ?? [];
  const bar = status === "pending_approval" ? <ReviewLinksBar /> : null;
  if (!items.length) {
    const copy = { draft: ["No drafts", "Start a post and save it as a draft; it waits here."], pending_approval: ["Nothing waits for approval", "Posts from editors show up here when the brand requires approval."], published: ["Nothing sent yet", "Published posts appear here with their links."], failed: ["Nothing failed", "Posts that could not be published after retrying show up here with the platform's error."] }[status];
    return <>{bar}<EmptyState icon={CalendarDays} title={copy[0]} body={copy[1]} action={status !== "published" ? <Button size="sm" onClick={() => composer.open()}>Write a post</Button> : undefined} /></>;
  }
  return (
    <>{bar}
    <ul className="divide-y divide-line rounded-card border border-line bg-surface">
      {items.map((p) => (
        <li key={p.id} className="flex items-start gap-4 px-4 py-3">
          <div className="flex shrink-0 -space-x-1 pt-0.5">{p.targets.map((t) => <span key={t.id} className="grid size-6 place-items-center rounded-full border border-line bg-surface"><PlatformMark platform={t.platform} size={12} /></span>)}</div>
          <div className="min-w-0 flex-1">
            <button type="button" onClick={() => composer.open({ postId: p.id })} className="line-clamp-2 text-left text-sm hover:underline">{p.content || "(no text)"}</button>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-2">
              <StatusBadge status={p.status} />
              {status === "published" && p.scheduled_at && <span className="tnum">{fmtDateTime(p.scheduled_at, brand.timezone)}</span>}
              {status === "failed" && p.targets.filter((t) => t.error).map((t) => <span key={t.id} className="text-st-failed">{t.handle}: {t.error}</span>)}
              {status === "published" && p.targets.filter((t) => t.remote_url).map((t) => <a key={t.id} href={t.remote_url!} target="_blank" rel="noopener" className="underline">View on {platformLabel(t.platform)}</a>)}
              {status !== "published" && p.updated_at && <span className="tnum">updated {fmtDateTime(p.updated_at, brand.timezone)}</span>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-0.5">
            {status === "draft" && <Button size="sm" variant="outline" onClick={() => actions.place.mutate({ id: p.id, action: "next" })}>Share next</Button>}
            {status === "failed" && <Button size="sm" onClick={() => actions.retry.mutate(p.id)}>Retry</Button>}
            {status === "pending_approval" && canApprove && <Button size="sm" onClick={() => actions.approve.mutate(p.id)}>Approve</Button>}
            {status === "published" && <IconBtn label="Reuse" onClick={() => composer.open({ fromPostId: p.id })}><Copy className="size-4" /></IconBtn>}
            {status !== "published" && <IconBtn label="Edit" onClick={() => composer.open({ postId: p.id })}><Pencil className="size-4" /></IconBtn>}
            {status === "draft" && <IconBtn label="Delete" onClick={() => confirm("Delete this draft?") && actions.remove.mutate(p.id)}><Trash2 className="size-4" /></IconBtn>}
          </div>
        </li>
      ))}
    </ul>
    </>
  );
}
