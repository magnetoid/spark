/** The agent in the UI: the Ask Spark panel, a run's live view and proposal, the plan tray, settings. */
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { CalendarCheck, Loader2, Pencil, RefreshCw, Sparkles, Square, Trash2 } from "lucide-react";
import { useBrand, usePerms, useWorkspace } from "@/app/session";
import { EmptyState, StatusBadge } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  proposalPosts, proposalVoice, useAgentRun, useAgentRuns, useAgentStatus, useApplyRun, useJanusUpdate, usePlan, useSchedulePlan, useStartRun,
  useStopRun, type AgentRunOut, type RunKind,
} from "@/features/agent/api";
import { useUpdateBrand } from "@/features/api4";
import { useComposer } from "@/features/composer/composer-host";
import { useAccounts, usePostActions } from "@/features/posts/api";
import { PlatformMark } from "@/lib/platforms";
import { fmtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

const OPEN_EVENT = "spark:ask";
const LIVE = ["queued", "running", "waiting_approval"];
const KIND_LABEL: Record<string, string> = { ask: "Ask Spark", weekly_plan: "Weekly plan", voice: "Voice learning", repurpose: "Repurpose", report: "Report" };
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** Open the Ask Spark panel from anywhere (the command palette, Today, Settings). */
export function openAskSpark(prompt = "", kind: RunKind = "ask", runId: number | null = null) {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: { prompt, kind, runId } }));
}

export function AskSparkHost() {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [kind, setKind] = useState<RunKind>("ask");
  const [runId, setRunId] = useState<number | null>(null);
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent<{ prompt?: string; kind?: RunKind; runId?: number | null }>).detail ?? {};
      setPrompt(d.prompt ?? ""); setKind(d.kind ?? "ask"); setRunId(d.runId ?? null); setOpen(true);
    };
    window.addEventListener(OPEN_EVENT, h);
    return () => window.removeEventListener(OPEN_EVENT, h);
  }, []);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-xl">
        <SheetHeader className="border-b border-line px-5 py-3"><SheetTitle className="flex items-center gap-2 text-base"><Sparkles className="size-4 text-brand" aria-hidden />Ask Spark</SheetTitle></SheetHeader>
        {open && <AskBody prompt={prompt} setPrompt={setPrompt} kind={kind} setKind={setKind} runId={runId} setRunId={setRunId} />}
      </SheetContent>
    </Sheet>
  );
}

function AskBody({ prompt, setPrompt, kind, setKind, runId, setRunId }: {
  prompt: string; setPrompt: (v: string) => void; kind: RunKind; setKind: (k: RunKind) => void; runId: number | null; setRunId: (id: number | null) => void;
}) {
  const { brand } = useWorkspace();
  const { canEdit } = usePerms();
  const { data: status, isPending } = useAgentStatus(brand?.id ?? 0, Boolean(brand));
  const start = useStartRun(brand?.id ?? 0);
  const { data: runs = [] } = useAgentRuns(brand?.id ?? 0);
  if (!brand) return <p className="p-5 text-sm text-ink-2">Pick a brand first.</p>;
  if (isPending) return <Skeleton className="m-5 h-24" />;
  if (!status?.configured) {
    return (
      <div className="p-5 text-sm">
        <p>Spark's agent is <b>Janus</b>, a separate service that reads this workspace and proposes posts, plans and a voice profile. It is not connected yet.</p>
        <p className="mt-2 text-ink-2">An owner adds its address and API key under Settings → Connectors → Janus agent. The setup notes live in <code className="rounded bg-hover px-1">deploy/janus/README.md</code>.</p>
        <Link to="/settings" search={(p) => ({ ...p, tab: "connectors", connector: "janus" })} className="mt-4 inline-block text-sm underline">Open the Janus connector</Link>
      </div>
    );
  }
  const send = (e?: FormEvent) => {
    e?.preventDefault();
    if (kind === "ask" && !prompt.trim()) return;
    start.mutate({ kind, prompt: prompt.trim() || null }, { onSuccess: (r) => setRunId(r.id) });
  };
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {runId ? (
        <div className="min-h-0 flex-1 overflow-y-auto p-5"><RunView id={runId} onBack={() => setRunId(null)} /></div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {!status.healthy && <p className="mb-3 rounded-control border border-st-failed/40 px-3 py-2 text-xs text-st-failed">Janus at {status.base_url} is not answering right now. Runs will fail until it is back.</p>}
          <form onSubmit={send} className="space-y-3">
            <Textarea autoFocus rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={kind === "weekly_plan" ? "Anything the plan should keep in mind (optional)" : kind === "voice" ? "Notes about the voice (optional)" : `What should ${brand.name} post? Ask for ideas, a week of posts, a rewrite plan…`}
                      onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }} disabled={!canEdit} />
            <div className="flex flex-wrap items-center gap-2">
              <Select value={kind} onValueChange={(v) => setKind(v as RunKind)}><SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="ask">Ask anything</SelectItem><SelectItem value="weekly_plan">Plan next week</SelectItem><SelectItem value="voice">Learn the voice</SelectItem></SelectContent></Select>
              <Button type="submit" size="sm" disabled={!canEdit || start.isPending || (kind === "ask" && !prompt.trim())}>{start.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}{kind === "weekly_plan" ? "Plan the week" : kind === "voice" ? "Learn the voice" : "Ask"}</Button>
              <span className="text-xs text-ink-2">Janus proposes; you approve. Nothing is scheduled by itself.</span>
            </div>
          </form>
          <div className="mt-5 flex flex-wrap gap-1.5">
            {["Three posts about what we learned this month", "A LinkedIn post from our latest blog entry", "What should we post tomorrow morning?"].map((q) => (
              <button key={q} type="button" className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-2 hover:border-brand hover:text-ink" onClick={() => { setKind("ask"); setPrompt(q); }}>{q}</button>
            ))}
          </div>
          {runs.length > 0 && (
            <section className="mt-6">
              <h3 className="mb-2 text-xs font-medium text-ink-2">Recent runs</h3>
              <ul className="divide-y divide-line rounded-card border border-line">
                {runs.slice(0, 8).map((r) => (
                  <li key={r.id}><button type="button" onClick={() => setRunId(r.id)} className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-hover">
                    <RunStatus status={r.status} />
                    <span className="min-w-0 flex-1 truncate">{r.prompt || r.summary || KIND_LABEL[r.kind]}</span>
                    <span className="shrink-0 text-xs text-ink-2">{KIND_LABEL[r.kind]}{r.posts ? ` · ${r.posts} posts` : ""}{r.created_at ? ` · ${fmtDateTime(r.created_at, brand.timezone)}` : ""}</span>
                  </button></li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function RunStatus({ status }: { status: string }) {
  const live = LIVE.includes(status);
  const color = status === "completed" ? "bg-st-published" : status === "failed" ? "bg-st-failed" : status === "cancelled" ? "bg-ink-2" : "bg-brand";
  return <span className={cn("size-2 shrink-0 rounded-full", color, live && "animate-pulse")} aria-label={status} />;
}

const toolLabel = (t: string) => t.replace(/^mcp_spark_/, "").replace(/_/g, " ");

export function RunView({ id, onBack }: { id: number; onBack?: () => void }) {
  const brand = useBrand();
  const { canEdit, canManage } = usePerms();
  const { data: run, isPending } = useAgentRun(brand.id, id);
  const apply = useApplyRun(brand.id);
  const stop = useStopRun(brand.id);
  const [picked, setPicked] = useState<number[] | null>(null);
  if (isPending || !run) return <Skeleton className="h-40" />;
  const live = LIVE.includes(run.status);
  const posts = proposalPosts(run);
  const voice = proposalVoice(run);
  const selected = picked ?? posts.map((_, i) => i);
  const text = (run.output ?? "").replace(/```\s*spark-proposal[\s\S]*?```/i, "").trim();
  const partial = run.events.filter((e) => e.event === "message.delta").map((e) => String(e.delta ?? "")).join("");
  const tools = run.events.filter((e) => e.event === "tool.completed" || e.event === "tool.started");
  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-start gap-3">
        {onBack && <button type="button" onClick={onBack} className="text-xs text-ink-2 hover:underline">← Back</button>}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2"><RunStatus status={run.status} /><span className="font-medium">{KIND_LABEL[run.kind]}</span><span className="text-xs text-ink-2">{run.status.replace("_", " ")}{run.user ? ` · ${run.user.name}` : ""}</span></div>
          {run.prompt && <p className="mt-1 text-ink-2">{run.prompt}</p>}
        </div>
        {live && canEdit && run.janus_run_id && <Button size="sm" variant="ghost" onClick={() => stop.mutate(run.id)}><Square className="size-3.5" />Stop</Button>}
      </div>
      {tools.length > 0 && <div className="flex flex-wrap gap-1">{tools.filter((e) => e.event === "tool.completed").map((e, i) => <span key={i} className="rounded-full border border-line px-2 py-0.5 text-[11px] text-ink-2">read {toolLabel(String(e.tool))}</span>)}{live && tools.at(-1)?.event === "tool.started" && <span className="flex items-center gap-1 text-[11px] text-ink-2"><Loader2 className="size-3 animate-spin" />reading {toolLabel(String(tools.at(-1)?.tool))}…</span>}</div>}
      {(text || partial) && <p className="whitespace-pre-wrap leading-relaxed">{text || partial}{live && !text && <span className="animate-pulse">▍</span>}</p>}
      {live && !text && !partial && <p className="flex items-center gap-2 text-ink-2"><Loader2 className="size-4 animate-spin" />Janus is thinking…</p>}
      {run.status === "failed" && <p className="rounded-control border border-st-failed/40 px-3 py-2 text-st-failed">{run.error || "The run failed."}</p>}

      {posts.length > 0 && (
        <section className="rounded-card border border-line">
          <header className="flex items-center justify-between border-b border-line px-4 py-2"><h3 className="font-semibold">{posts.length} proposed {posts.length === 1 ? "post" : "posts"}</h3>{!run.applied_at && posts.length > 1 && <button type="button" className="text-xs text-ink-2 hover:underline" onClick={() => setPicked(selected.length === posts.length ? [] : posts.map((_, i) => i))}>{selected.length === posts.length ? "Select none" : "Select all"}</button>}</header>
          <ul className="divide-y divide-line">
            {posts.map((p, i) => (
              <li key={i} className="flex gap-3 px-4 py-3">
                {!run.applied_at && <input type="checkbox" className="mt-1 accent-[var(--brand)]" checked={selected.includes(i)} onChange={() => setPicked(selected.includes(i) ? selected.filter((x) => x !== i) : [...selected, i])} aria-label={`Include post ${i + 1}`} />}
                <div className="min-w-0 flex-1">
                  <p className="whitespace-pre-wrap">{p.content}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-2">
                    <ChannelMarks ids={p.channel_ids} />
                    {p.when && <span className="tnum">{fmtDateTime(p.when, brand.timezone)}</span>}
                    {p.pillar && <span>{p.pillar}</span>}
                    {p.link && <a href={p.link} target="_blank" rel="noopener" className="truncate underline">{p.link}</a>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          <footer className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
            {run.applied_at ? (
              <span className="text-xs text-ink-2">Added to the plan {fmtDateTime(run.applied_at, brand.timezone)}. <Link to="/publishing" search={(s) => ({ ...s, view: "plan" })} className="underline">Open the plan</Link></span>
            ) : canEdit ? (
              <>
                <Button size="sm" disabled={apply.isPending || selected.length === 0} onClick={() => apply.mutate({ id: run.id, body: { post_indexes: selected, schedule: false } })}><CalendarCheck className="size-4" />Add {selected.length} to the plan as drafts</Button>
                <Button size="sm" variant="outline" disabled={apply.isPending || selected.length === 0} onClick={() => apply.mutate({ id: run.id, body: { post_indexes: selected, schedule: true } })}>Schedule {selected.length} now</Button>
                <span className="text-xs text-ink-2">Drafts land in Publishing › Plan for a last look.</span>
              </>
            ) : <span className="text-xs text-ink-2">An editor adds these to the plan.</span>}
          </footer>
        </section>
      )}

      {voice && (
        <section className="rounded-card border border-line">
          <header className="border-b border-line px-4 py-2"><h3 className="font-semibold">Proposed voice</h3><p className="text-xs text-ink-2">{voice.summary}</p></header>
          <dl className="grid gap-3 px-4 py-3 sm:grid-cols-2">
            {(["tone", "audience", "rules", "examples"] as const).map((k) => (
              <div key={k}><dt className="text-xs capitalize text-ink-2">{k}</dt><dd className="whitespace-pre-wrap">{voice[k] || "—"}</dd>
                {brand[`voice_${k}`] && brand[`voice_${k}`] !== voice[k] && <dd className="mt-1 text-xs text-ink-2 line-through">{brand[`voice_${k}`]}</dd>}</div>
            ))}
          </dl>
          <footer className="flex items-center gap-2 border-t border-line px-4 py-3">
            {run.applied_at ? <span className="text-xs text-ink-2">In use since {fmtDateTime(run.applied_at, brand.timezone)}.</span>
              : canManage ? <Button size="sm" disabled={apply.isPending} onClick={() => apply.mutate({ id: run.id, body: {} })}>Use this voice</Button>
              : <span className="text-xs text-ink-2">An owner decides whether to adopt it.</span>}
          </footer>
        </section>
      )}
    </div>
  );
}

function ChannelMarks({ ids }: { ids: number[] }) {
  const brand = useBrand();
  const { data: accounts = [] } = useAccounts(brand.id);
  const chosen = accounts.filter((a) => ids.includes(a.id));
  if (!chosen.length) return null;
  return <span className="flex items-center gap-1">{chosen.map((a) => <span key={a.id} title={a.handle} className="grid size-5 place-items-center rounded-full border border-line bg-surface"><PlatformMark platform={a.platform} size={11} /></span>)}<span>{chosen.map((a) => a.handle).join(", ")}</span></span>;
}

// ---- Publishing › Plan ------------------------------------------------------------------------
export function PlanView() {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data, isPending } = usePlan(brand.id);
  const schedule = useSchedulePlan(brand.id);
  const actions = usePostActions(brand.id);
  const composer = useComposer();
  if (isPending || !data) return <Skeleton className="h-48" />;
  const run = data.run;
  if (data.posts.length === 0) {
    return (
      <EmptyState icon={Sparkles} title="No plan waiting" body={run && LIVE.includes(run.status) ? "Janus is working on next week's plan. It shows up here when it is done." : "Ask Spark to plan next week: it reads your pillars, posting times and recent posts and proposes finished drafts you approve here."}
                  action={canEdit ? <Button size="sm" onClick={() => openAskSpark("", "weekly_plan", run && LIVE.includes(run.status) ? run.id : null)}><Sparkles className="size-4" />{run && LIVE.includes(run.status) ? "Watch the run" : "Plan next week"}</Button> : undefined} />
    );
  }
  const days = new Map<string, typeof data.posts>();
  for (const p of data.posts) {
    const key = p.proposed_for ? new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "short", timeZone: brand.timezone }).format(new Date(p.proposed_for)) : "No time yet";
    days.set(key, [...(days.get(key) ?? []), p]);
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 rounded-card border border-dashed border-line px-4 py-3 text-sm">
        <Sparkles className="size-4 shrink-0 text-brand" aria-hidden />
        <span className="min-w-0 flex-1 text-ink-2">{run?.summary || `${data.posts.length} drafts proposed by Janus wait for a last look.`}{run && <button type="button" className="ml-2 underline" onClick={() => openAskSpark("", "weekly_plan", run.id)}>See the run</button>}</span>
        {canEdit && <Button size="sm" disabled={schedule.isPending} onClick={() => schedule.mutate(null)}><CalendarCheck className="size-4" />Schedule all {data.posts.length}</Button>}
      </div>
      {[...days.entries()].map(([day, posts]) => (
        <section key={day}>
          <h3 className="mb-2 text-xs font-medium text-ink-2">{day}</h3>
          <ul className="divide-y divide-line rounded-card border border-line bg-surface">
            {posts.map((p) => (
              <li key={p.id} className="flex items-start gap-4 px-4 py-3">
                <div className="flex shrink-0 -space-x-1 pt-0.5">{p.targets.map((t) => <span key={t.id} className="grid size-6 place-items-center rounded-full border border-line bg-surface"><PlatformMark platform={t.platform} size={12} /></span>)}</div>
                <div className="min-w-0 flex-1">
                  <button type="button" onClick={() => composer.open({ postId: p.id })} className="line-clamp-3 text-left text-sm hover:underline">{p.content || "(no text)"}</button>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-2"><StatusBadge status={p.status} />{p.proposed_for && <span className="tnum">proposed for {fmtDateTime(p.proposed_for, brand.timezone)}</span>}</div>
                </div>
                {canEdit && (
                  <div className="flex shrink-0 items-center gap-0.5">
                    <Button size="sm" onClick={() => schedule.mutate([p.id])}>Schedule</Button>
                    <Button size="icon" variant="ghost" aria-label="Edit" onClick={() => composer.open({ postId: p.id })}><Pencil className="size-4" /></Button>
                    <Button size="icon" variant="ghost" aria-label="Discard" onClick={() => confirm("Discard this proposed post?") && actions.remove.mutate(p.id)}><Trash2 className="size-4" /></Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

// ---- Settings › Brand: the agent ----------------------------------------------------------------
export function AgentSection() {
  const brand = useBrand();
  const { canManage, canEdit } = usePerms();
  const update = useUpdateBrand(brand.id);
  const { data: status } = useAgentStatus(brand.id);
  const cfg = (brand.agent_config ?? {}) as { auto_schedule?: boolean; weekly_plan?: { enabled?: boolean; weekday?: number; posts?: number } };
  const wp = cfg.weekly_plan ?? {};
  const voice = (brand.voice_profile ?? {}) as { summary?: string; learned_at?: string };
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    update.mutate({ agent_config: { ...cfg, auto_schedule: fd.get("auto_schedule") === "on",
      weekly_plan: { enabled: fd.get("wp_enabled") === "on", weekday: Number(fd.get("wp_weekday") ?? 0), posts: Math.min(30, Math.max(1, Number(fd.get("wp_posts") || 5))) } } });
  };
  return (
    <form className="rounded-card border border-line bg-surface" onSubmit={submit}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3">
        <div><h3 className="font-semibold">Agent</h3><p className="text-xs text-ink-2">Janus plans, learns the voice and answers Ask Spark. It proposes; people approve.</p></div>
        <span className={cn("text-xs", status?.configured && status.healthy ? "text-st-published" : "text-ink-2")}>{!status ? "" : !status.configured ? "Not connected" : status.healthy ? `Connected${status.version ? ` · v${status.version}` : ""}` : "Connected, not answering"}</span>
      </header>
      <div className="space-y-5 p-5 text-sm">
        <div className="grid gap-4 sm:grid-cols-[auto_1fr]">
          <label className="flex items-start gap-3"><Switch name="wp_enabled" defaultChecked={Boolean(wp.enabled)} disabled={!canManage} /><span>Plan every week<span className="block text-xs text-ink-2">Janus proposes next week's posts as drafts in Publishing › Plan.</span></span></label>
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
            on <Select name="wp_weekday" defaultValue={String(wp.weekday ?? 4)} disabled={!canManage}><SelectTrigger className="h-8 w-32"><SelectValue /></SelectTrigger><SelectContent>{WEEKDAYS.map((d, i) => <SelectItem key={d} value={String(i)}>{d}</SelectItem>)}</SelectContent></Select>
            with <Input name="wp_posts" type="number" min={1} max={30} defaultValue={wp.posts ?? 5} className="h-8 w-16" disabled={!canManage} aria-label="Posts per week" /> posts
          </div>
        </div>
        <label className="flex items-start gap-3"><Switch name="auto_schedule" defaultChecked={Boolean(cfg.auto_schedule)} disabled={!canManage} /><span>Schedule what the agent proposes without a review<span className="block text-xs text-ink-2">Off by default. Turn it on once you trust the plans; approval rules still apply.</span></span></label>
        <div className="rounded-control border border-line p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div><div className="font-medium">Learned voice</div><p className="text-xs text-ink-2">{voice.summary ? `${voice.summary}${voice.learned_at ? ` · learned ${fmtDateTime(voice.learned_at, brand.timezone)}` : ""}` : "Not learned yet. Janus reads the best published posts and proposes tone, audience, rules and examples; you accept or not."}</p></div>
            {canEdit && <Button type="button" size="sm" variant="outline" onClick={() => openAskSpark("", "voice")}><Sparkles className="size-4" />{voice.summary ? "Learn again" : "Learn the voice"}</Button>}
          </div>
        </div>
      </div>
      {canManage && <div className="border-t border-line px-5 py-3"><Button type="submit" size="sm" disabled={update.isPending}>Save agent settings</Button></div>}
    </form>
  );
}

// ---- Settings › Connectors › Janus --------------------------------------------------------------
export function JanusSection({ info }: { info?: Record<string, unknown> | null }) {
  const { user } = useWorkspace();
  const update = useJanusUpdate();
  const s = (info ?? {}) as { configured?: boolean; healthy?: boolean; version?: string | null; base_url?: string | null; checked_at?: string; can_update?: boolean };
  return (
    <section className="mt-6 space-y-3 rounded-card border border-line bg-surface p-5 text-sm">
      <h3 className="font-semibold">Service</h3>
      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-[auto_1fr]">
        <dt className="text-ink-2">Status</dt><dd className={cn(s.configured && s.healthy ? "text-st-published" : s.configured ? "text-st-failed" : "text-ink-2")}>{!s.configured ? "Not set up" : s.healthy ? "Healthy" : "Not answering"}</dd>
        <dt className="text-ink-2">Version</dt><dd className="tnum">{s.version ?? (s.healthy ? "hidden by this install" : "—")}</dd>
        <dt className="text-ink-2">Address</dt><dd className="truncate">{s.base_url ?? "—"}</dd>
      </dl>
      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
        {user.role === "owner" && <Button size="sm" variant="outline" disabled={!s.can_update || update.isPending} onClick={() => update.mutate(undefined)}><RefreshCw className={cn("size-4", update.isPending && "animate-spin")} />Update now</Button>}
        <span className="text-xs text-ink-2">{s.can_update ? "Rebuilds Janus from the latest main branch through Coolify. A GitHub Action does the same every Monday." : "Add the update webhook above to rebuild Janus from here."}</span>
      </div>
      <p className="text-xs text-ink-2">Setup notes: <a className="underline" href="https://github.com/magnetoid/spark/tree/main/deploy/janus" target="_blank" rel="noopener">deploy/janus/README.md</a>.</p>
      <div className="flex items-center gap-2 text-xs text-ink-2"><Label className="text-xs">Mounted config</Label><code className="rounded bg-hover px-1">/opt/data/config.yaml</code> read-only Spark tools, no shell</div>
    </section>
  );
}

export function kindLabel(run: AgentRunOut) {
  return KIND_LABEL[run.kind] ?? run.kind;
}
