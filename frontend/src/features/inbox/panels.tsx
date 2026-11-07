/** Inbox settings: saved replies and rules that prepare replies for approval. */
import { useState, type FormEvent } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { useBrand, usePerms } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useMembers } from "@/features/collab/api";
import {
  INTENT_LABEL, KIND_LABEL, useCreateRule, useCreateSavedReply, useDeleteRule, useDeleteSavedReply, useInboxRules, useSavedReplies, useUpdateRule,
  useUpdateSavedReply, type InboxRule, type SavedReply,
} from "@/features/inbox/api";
import { cn } from "@/lib/utils";

const lines = (v: FormDataEntryValue | null) => String(v ?? "").split(/\r?\n|,/).map((s) => s.trim()).filter(Boolean);

export function SavedRepliesSection() {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data = [], isPending } = useSavedReplies(brand.id);
  const create = useCreateSavedReply(brand.id);
  const update = useUpdateSavedReply(brand.id);
  const remove = useDeleteSavedReply(brand.id);
  const [editing, setEditing] = useState<SavedReply | "new" | null>(null);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const body = { title: String(fd.get("title")).trim(), body: String(fd.get("body")).trim(), shortcut: String(fd.get("shortcut") || "").trim() || null };
    if (editing === "new") create.mutate(body, { onSuccess: () => setEditing(null) });
    else if (editing) update.mutate({ id: editing.id, body }, { onSuccess: () => setEditing(null) });
  };
  return (
    <section className="rounded-card border border-line bg-surface">
      <header className="flex items-center justify-between border-b border-line px-5 py-3">
        <div><h3 className="font-semibold">Saved replies</h3><p className="text-xs text-ink-2">Answers the team sends often. Insert them in the inbox, or let a rule use them.</p></div>
        {canEdit && <Button size="sm" variant="outline" onClick={() => setEditing("new")}>Add a reply</Button>}
      </header>
      {isPending ? <Skeleton className="m-5 h-16" /> : data.length === 0 ? <p className="px-5 py-4 text-sm text-ink-2">None yet. Prices, opening hours, shipping, “thanks for the kind words”: the usual suspects.</p> : (
        <ul className="divide-y divide-line">
          {data.map((s) => (
            <li key={s.id} className="flex items-start gap-3 px-5 py-3 text-sm">
              <div className="min-w-0 flex-1"><div className="font-medium">{s.title}{s.shortcut && <span className="ml-2 rounded bg-hover px-1 text-xs font-normal text-ink-2">/{s.shortcut}</span>}</div><p className="line-clamp-2 text-ink-2">{s.body}</p></div>
              <span className="text-xs text-ink-2 tnum">{s.uses} {s.uses === 1 ? "use" : "uses"}</span>
              {canEdit && <span className="flex gap-0.5"><Button size="icon" variant="ghost" aria-label={`Edit ${s.title}`} onClick={() => setEditing(s)}><Pencil className="size-4" /></Button><Button size="icon" variant="ghost" aria-label={`Remove ${s.title}`} onClick={() => confirm(`Remove “${s.title}”?`) && remove.mutate(s.id)}><Trash2 className="size-4" /></Button></span>}
            </li>
          ))}
        </ul>
      )}
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing === "new" ? "New saved reply" : "Edit saved reply"}</DialogTitle></DialogHeader>
          <form key={editing === "new" ? "new" : editing?.id} className="space-y-4" onSubmit={submit}>
            <div className="grid grid-cols-[1fr_8rem] gap-3">
              <div className="space-y-1.5"><Label htmlFor="sr-title">Title</Label><Input id="sr-title" name="title" required maxLength={120} autoFocus defaultValue={editing !== "new" ? editing?.title : ""} /></div>
              <div className="space-y-1.5"><Label htmlFor="sr-short">Shortcut</Label><Input id="sr-short" name="shortcut" maxLength={40} placeholder="price" defaultValue={editing !== "new" ? editing?.shortcut ?? "" : ""} /></div>
            </div>
            <div className="space-y-1.5"><Label htmlFor="sr-body">Reply</Label><Textarea id="sr-body" name="body" rows={4} required defaultValue={editing !== "new" ? editing?.body : ""} placeholder="Thanks for asking! The workshop is 120 EUR; early birds 99 until Friday." /><p className="text-xs text-ink-2">{"{name}"} becomes the person's first name when a rule sends it.</p></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" disabled={create.isPending || update.isPending}>{editing === "new" ? "Add" : "Save"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}

export function RulesSection() {
  const brand = useBrand();
  const { canManage } = usePerms();
  const { data = [], isPending } = useInboxRules(brand.id);
  const { data: saved = [] } = useSavedReplies(brand.id);
  const { data: members = [] } = useMembers(brand.id);
  const create = useCreateRule(brand.id);
  const update = useUpdateRule(brand.id);
  const remove = useDeleteRule(brand.id);
  const [editing, setEditing] = useState<InboxRule | "new" | null>(null);
  const [kinds, setKinds] = useState<string[]>([]);
  const [intents, setIntents] = useState<string[]>([]);
  const [sentiments, setSentiments] = useState<string[]>([]);
  const open = (r: InboxRule | "new") => { setEditing(r); setKinds(r === "new" ? [] : r.kinds); setIntents(r === "new" ? [] : r.intents); setSentiments(r === "new" ? [] : r.sentiments); };
  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const sr = String(fd.get("saved_reply_id") || "none");
    const assignee = String(fd.get("assign_to_id") || "none");
    const body = { name: String(fd.get("name")).trim(), enabled: fd.get("enabled") === "on", kinds, intents, sentiments, platforms: [], keywords: lines(fd.get("keywords")),
      saved_reply_id: sr === "none" ? null : Number(sr), reply_text: sr === "none" ? String(fd.get("reply_text") || "").trim() || null : null, assign_to_id: assignee === "none" ? null : Number(assignee) };
    if (editing === "new") create.mutate(body, { onSuccess: () => setEditing(null) });
    else if (editing) update.mutate({ id: editing.id, body }, { onSuccess: () => setEditing(null) });
  };
  return (
    <section className="rounded-card border border-line bg-surface">
      <header className="flex items-center justify-between border-b border-line px-5 py-3">
        <div><h3 className="font-semibold">Rules</h3><p className="text-xs text-ink-2">When a message matches, a rule prepares a reply or assigns it. Nothing is sent until a person approves it.</p></div>
        {canManage && <Button size="sm" variant="outline" onClick={() => open("new")}>Add a rule</Button>}
      </header>
      {isPending ? <Skeleton className="m-5 h-16" /> : data.length === 0 ? <p className="px-5 py-4 text-sm text-ink-2">No rules yet. A good first one: keywords “price, how much” → the saved reply with the price.</p> : (
        <ul className="divide-y divide-line">
          {data.map((r) => (
            <li key={r.id} className="flex items-center gap-3 px-5 py-3 text-sm">
              {canManage && <Switch checked={r.enabled} onCheckedChange={(v) => update.mutate({ id: r.id, body: { enabled: v } })} aria-label={`${r.name} enabled`} />}
              <div className="min-w-0 flex-1">
                <div className={cn("font-medium", !r.enabled && "text-ink-2")}>{r.name}</div>
                <p className="truncate text-xs text-ink-2">
                  {[r.kinds.length ? r.kinds.map((k) => KIND_LABEL[k]).join("/") : "any kind", r.keywords.length ? `says ${r.keywords.map((k) => `“${k}”`).join(" or ")}` : null, r.intents.length ? r.intents.map((i) => INTENT_LABEL[i]).join("/") : null, r.sentiments.length ? r.sentiments.join("/") : null].filter(Boolean).join(" · ")}
                  {" → "}{r.saved_reply_id ? `reply “${saved.find((s) => s.id === r.saved_reply_id)?.title ?? "saved reply"}”` : r.reply_text ? "reply" : ""}{r.assign_to_id ? `${r.saved_reply_id || r.reply_text ? ", " : ""}assign ${members.find((m) => m.user_id === r.assign_to_id)?.name ?? ""}` : ""}
                </p>
              </div>
              <span className="text-xs text-ink-2 tnum">{r.hits} {r.hits === 1 ? "hit" : "hits"}</span>
              {canManage && <span className="flex gap-0.5"><Button size="icon" variant="ghost" aria-label={`Edit ${r.name}`} onClick={() => open(r)}><Pencil className="size-4" /></Button><Button size="icon" variant="ghost" aria-label={`Remove ${r.name}`} onClick={() => confirm(`Remove the rule “${r.name}”?`) && remove.mutate(r.id)}><Trash2 className="size-4" /></Button></span>}
            </li>
          ))}
        </ul>
      )}
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{editing === "new" ? "New rule" : "Edit rule"}</DialogTitle></DialogHeader>
          <form key={editing === "new" ? "new" : editing?.id} className="space-y-4 text-sm" onSubmit={submit}>
            <div className="flex items-end gap-3">
              <div className="flex-1 space-y-1.5"><Label htmlFor="r-name">Name</Label><Input id="r-name" name="name" required autoFocus defaultValue={editing !== "new" ? editing?.name : ""} placeholder="Price questions" /></div>
              <label className="flex items-center gap-2 pb-2"><Switch name="enabled" defaultChecked={editing === "new" ? true : editing?.enabled} />On</label>
            </div>
            <fieldset className="space-y-1.5"><legend className="text-xs text-ink-2">When it is a…</legend><div className="flex flex-wrap gap-1.5">{Object.entries(KIND_LABEL).map(([k, l]) => <Chip key={k} on={kinds.includes(k)} onClick={() => toggle(kinds, setKinds, k)}>{l}</Chip>)}</div></fieldset>
            <div className="space-y-1.5"><Label htmlFor="r-kw">…that says any of (comma separated)</Label><Input id="r-kw" name="keywords" defaultValue={editing !== "new" ? editing?.keywords.join(", ") : ""} placeholder="price, how much, cost" /></div>
            <div className="grid gap-3 sm:grid-cols-2">
              <fieldset className="space-y-1.5"><legend className="text-xs text-ink-2">…read by AI as</legend><div className="flex flex-wrap gap-1.5">{Object.entries(INTENT_LABEL).map(([k, l]) => <Chip key={k} on={intents.includes(k)} onClick={() => toggle(intents, setIntents, k)}>{l}</Chip>)}</div></fieldset>
              <fieldset className="space-y-1.5"><legend className="text-xs text-ink-2">…with sentiment</legend><div className="flex flex-wrap gap-1.5">{["positive", "neutral", "negative"].map((k) => <Chip key={k} on={sentiments.includes(k)} onClick={() => toggle(sentiments, setSentiments, k)}>{k}</Chip>)}</div></fieldset>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5"><Label>Prepare this saved reply</Label><Select name="saved_reply_id" defaultValue={editing !== "new" && editing?.saved_reply_id ? String(editing.saved_reply_id) : "none"}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">None (write below)</SelectItem>{saved.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.title}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-1.5"><Label>Assign to</Label><Select name="assign_to_id" defaultValue={editing !== "new" && editing?.assign_to_id ? String(editing.assign_to_id) : "none"}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Nobody</SelectItem>{members.map((m) => <SelectItem key={m.user_id} value={String(m.user_id)}>{m.name}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <div className="space-y-1.5"><Label htmlFor="r-text">Or prepare this text</Label><Textarea id="r-text" name="reply_text" rows={3} defaultValue={editing !== "new" ? editing?.reply_text ?? "" : ""} placeholder="Thanks {name}! We will get back to you today." /></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" disabled={create.isPending || update.isPending}>{editing === "new" ? "Add rule" : "Save"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" onClick={onClick} className={cn("rounded-full border px-2 py-0.5 text-xs capitalize", on ? "border-brand bg-brand-soft text-ink" : "border-line text-ink-2 hover:text-ink")}>{children}</button>;
}
