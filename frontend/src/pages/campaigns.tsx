/** Campaigns: a goal and a window for a set of posts, optionally planned by AI. */
import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { BarChart3, Megaphone, Plus, Sparkles, Trash2 } from "lucide-react";
import { useBrand, usePerms, useSession } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCampaignsFull, useCreateCampaign, useDeleteCampaign, useUpdateCampaign, type CampaignFull } from "@/features/api4";
import { CampaignResults } from "@/features/links/tracker";
import { useAccounts } from "@/features/posts/api";
import { PlatformMark } from "@/lib/platforms";
import { fmtDay } from "@/lib/time";

export function CampaignsPage() {
  const brand = useBrand();
  const { data = [], isPending } = useCampaignsFull(brand.id);
  const [editing, setEditing] = useState<CampaignFull | "new" | null>(null);
  const [results, setResults] = useState<CampaignFull | null>(null);
  const remove = useDeleteCampaign(brand.id);
  const { canEdit } = usePerms();
  return (
    <>
      <PageHeader title="Campaigns" description="Group posts under a goal and a window; the calendar can filter by campaign."
                  actions={canEdit && <Button size="sm" onClick={() => setEditing("new")}><Plus className="size-4" />New campaign</Button>} />
      {isPending ? <Skeleton className="h-48" /> : data.length === 0 ? (
        <EmptyState icon={Megaphone} title="No campaigns yet" body="A campaign ties posts to a goal. With AI on, it can draft the whole series for you."
                    action={canEdit && <Button size="sm" onClick={() => setEditing("new")}>Create the first campaign</Button>} />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {data.map((c) => {
            const done = c.counts.published, total = c.counts.total;
            return (
              <li key={c.id} className="rounded-card border border-line bg-surface p-5">
                <div className="flex items-start gap-3">
                  <span className="mt-1 size-3 shrink-0 rounded-full" style={{ background: c.color }} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <h2 className="font-semibold">{c.name}</h2>
                    {c.goal && <p className="mt-0.5 text-sm text-ink-2">{c.goal}</p>}
                    <p className="mt-1 text-xs text-ink-2">
                      {c.starts_on ? fmtDay(c.starts_on.slice(0, 10), { day: "numeric", month: "short" }) : "No start"} – {c.ends_on ? fmtDay(c.ends_on.slice(0, 10), { day: "numeric", month: "short", year: "numeric" }) : "no end"}
                      {c.utm_campaign && <> · utm_campaign={c.utm_campaign}</>}
                    </p>
                  </div>
                  {canEdit && <><Button variant="ghost" size="sm" onClick={() => setEditing(c)}>Edit</Button><Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Delete campaign" onClick={() => confirm(`Delete “${c.name}”? Its posts stay, without a campaign.`) && remove.mutate(c.id)}><Trash2 className="size-4" /></Button></>}
                </div>
                <div className="mt-4">
                  <div className="flex justify-between text-xs text-ink-2 tnum"><span>{done} of {total} published</span><span>{c.counts.scheduled} scheduled · {c.counts.draft} drafts{c.counts.failed ? ` · ${c.counts.failed} failed` : ""}</span></div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded bg-hover"><div className="h-full" style={{ width: total ? `${(done / total) * 100}%` : 0, background: c.color }} /></div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <Button variant="outline" size="sm" onClick={() => setResults(c)}><BarChart3 className="size-4" />Results</Button>
                  <Link to="/publishing" search={(p) => ({ ...p, view: "calendar", campaign: String(c.id) })} className="text-sm text-ink-2 hover:text-ink hover:underline">Open in the calendar</Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <CampaignDialog editing={editing} onClose={() => setEditing(null)} />
      <CampaignResults campaign={results} onClose={() => setResults(null)} />
    </>
  );
}

function CampaignDialog({ editing, onClose }: { editing: CampaignFull | "new" | null; onClose: () => void }) {
  const brand = useBrand();
  const { data: session } = useSession();
  const { data: accounts = [] } = useAccounts(brand.id);
  const create = useCreateCampaign(brand.id);
  const update = useUpdateCampaign(brand.id);
  const existing = editing && editing !== "new" ? editing : null;
  const [aiPlan, setAiPlan] = useState(false);
  const ai = session?.features.ai ?? false;

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const base = {
      name: String(fd.get("name")), goal: String(fd.get("goal")) || null, starts_on: String(fd.get("starts_on")) || null,
      ends_on: String(fd.get("ends_on")) || null, utm_campaign: String(fd.get("utm_campaign")) || null, color: String(fd.get("color")),
    };
    if (existing) update.mutate({ id: existing.id, body: base }, { onSuccess: onClose });
    else create.mutate({ ...base, ai_plan: aiPlan ? { account_ids: fd.getAll("account_ids").map(Number), per_week: Number(fd.get("per_week") || 3) } : null }, { onSuccess: onClose });
  };

  return (
    <Dialog open={editing !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>{existing ? "Edit campaign" : "New campaign"}</DialogTitle></DialogHeader>
        <form key={existing?.id ?? "new"} onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
            <div className="space-y-1.5"><Label htmlFor="c-name">Name</Label><Input id="c-name" name="name" required defaultValue={existing?.name ?? ""} autoFocus /></div>
            <div className="space-y-1.5"><Label htmlFor="c-color">Colour</Label><input id="c-color" name="color" type="color" defaultValue={existing?.color ?? "#6366f1"} className="h-9 w-14 rounded-control border border-line bg-surface p-1" /></div>
          </div>
          <div className="space-y-1.5"><Label htmlFor="c-goal">Goal</Label><Textarea id="c-goal" name="goal" rows={2} defaultValue={existing?.goal ?? ""} placeholder="What should this campaign achieve, and for whom?" /></div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5"><Label htmlFor="c-start">Starts</Label><Input id="c-start" name="starts_on" type="date" defaultValue={existing?.starts_on?.slice(0, 10) ?? ""} /></div>
            <div className="space-y-1.5"><Label htmlFor="c-end">Ends</Label><Input id="c-end" name="ends_on" type="date" defaultValue={existing?.ends_on?.slice(0, 10) ?? ""} /></div>
            <div className="space-y-1.5"><Label htmlFor="c-utm">utm_campaign</Label><Input id="c-utm" name="utm_campaign" defaultValue={existing?.utm_campaign ?? ""} placeholder="spring-sale" /></div>
          </div>
          {!existing && ai && (
            <div className="space-y-3 rounded-card border border-line bg-paper p-3">
              <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={aiPlan} onChange={(e) => setAiPlan(e.target.checked)} className="accent-[var(--brand)]" /><Sparkles className="size-4" />Plan the posts with AI</label>
              {aiPlan && (
                <>
                  <p className="text-xs text-ink-2">Needs the goal and both dates. Creates draft posts at 10:00 on the planned days; nothing is scheduled until you review them.</p>
                  <div className="flex flex-wrap gap-2">
                    {accounts.filter((a) => a.is_active).map((a) => (
                      <label key={a.id} className="flex items-center gap-1.5 rounded-control border border-line px-2 py-1 text-sm"><input type="checkbox" name="account_ids" value={a.id} defaultChecked className="accent-[var(--brand)]" /><PlatformMark platform={a.platform} size={14} />{a.handle}</label>
                    ))}
                  </div>
                  <div className="flex items-center gap-2 text-sm"><Label htmlFor="c-pw">Posts per week</Label><Input id="c-pw" name="per_week" type="number" min={1} max={14} defaultValue={3} className="w-20" /></div>
                </>
              )}
            </div>
          )}
          <DialogFooter><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={create.isPending || update.isPending}>{create.isPending ? "Planning…" : existing ? "Save" : "Create"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
