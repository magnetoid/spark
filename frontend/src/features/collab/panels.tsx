/** Collaboration pieces used across pages: comments on a post, review links, recent activity, members. */
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Check, Copy, Link2, MessageSquareText, Trash2, X } from "lucide-react";
import { useBrand, usePerms, useWorkspace } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useActivity, useAddBrandMember, useAddComment, useComments, useCreateShareLink, useMembers, useRemoveBrandMember, useRevokeShareLink,
  useShareLinks, useUpdateBrandMember, type MemberRole, type ShareLinkCreated,
} from "@/features/collab/api";
import { ApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

const ROLES: { value: MemberRole; label: string; hint: string }[] = [
  { value: "owner", label: "Owner", hint: "Approves, manages members and settings" },
  { value: "editor", label: "Editor", hint: "Writes and schedules" },
  { value: "viewer", label: "Viewer", hint: "Reads" },
  { value: "client", label: "Client", hint: "Sees this brand only, approves posts" },
];

// ---- comments on a post --------------------------------------------------------------------
export function CommentsPanel({ postId }: { postId: number }) {
  const brand = useBrand();
  const { data = [], isPending } = useComments(brand.id, postId);
  const add = useAddComment(brand.id, postId);
  const [text, setText] = useState("");
  const send = () => { const t = text.trim(); if (t) add.mutate(t, { onSuccess: () => setText("") }); };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); } };
  return (
    <section className="rounded-card border border-line bg-surface" aria-labelledby="comments-h">
      <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <h3 id="comments-h" className="flex items-center gap-1.5 text-sm font-semibold"><MessageSquareText className="size-4" />Comments</h3>
        <span className="text-xs text-ink-2 tnum">{data.length}</span>
      </header>
      {isPending ? <Skeleton className="m-4 h-12" /> : data.length === 0 ? (
        <p className="px-4 pt-3 text-sm text-ink-2">Notes for the team and from clients who review this post show up here.</p>
      ) : (
        <ul className="max-h-72 space-y-3 overflow-y-auto px-4 pt-3 text-sm">
          {data.map((c) => (
            <li key={c.id}>
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">{c.author.name}</span>
                {c.kind === "change_request" && <span className="text-xs text-st-pending">requested changes</span>}
                {c.kind === "approval" && <span className="text-xs text-st-published">approved</span>}
                {c.created_at && <span className="text-xs text-ink-2 tnum">{fmtDateTime(c.created_at, brand.timezone)}</span>}
              </div>
              <p className="whitespace-pre-wrap text-ink-2">{c.body}</p>
            </li>
          ))}
        </ul>
      )}
      <form className="flex items-end gap-2 p-3" onSubmit={(e: FormEvent) => { e.preventDefault(); send(); }}>
        <Textarea rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} placeholder="Add a note…" className="min-h-9 text-sm" aria-label="New comment" />
        <Button type="submit" size="sm" variant="outline" disabled={add.isPending || !text.trim()}>Comment</Button>
      </form>
    </section>
  );
}

// ---- review links (Publishing › Approvals) ----------------------------------------------------
export function ReviewLinksBar() {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const { data = [] } = useShareLinks(brand.id);
  const create = useCreateShareLink(brand.id);
  const revoke = useRevokeShareLink(brand.id);
  const [created, setCreated] = useState<ShareLinkCreated | null>(null);
  const [copied, setCopied] = useState(false);
  if (!canEdit) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-card border border-dashed border-line px-4 py-3 text-sm">
      <Link2 className="size-4 shrink-0 text-ink-2" aria-hidden />
      <span className="text-ink-2">Clients approve without an account through a review link.</span>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {data.map((l) => (
          <span key={l.id} className="flex items-center gap-1.5 rounded-control border border-line px-2 py-1 text-xs">
            <span className="tnum">{l.prefix}…</span>
            {l.expires_at && <span className="text-ink-2">until {fmtDateTime(l.expires_at, brand.timezone)}</span>}
            <button type="button" aria-label={`Revoke link ${l.prefix}`} className="text-ink-2 hover:text-st-failed" onClick={() => revoke.mutate(l.id)}><X className="size-3" /></button>
          </span>
        ))}
        <Button size="sm" variant="outline" disabled={create.isPending} onClick={() => create.mutate({ days: 14 }, { onSuccess: (r) => { setCreated(r); setCopied(false); } })}>New review link</Button>
      </div>
      <Dialog open={!!created} onOpenChange={(o) => !o && setCreated(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Review link ready</DialogTitle></DialogHeader>
          <p className="text-sm text-ink-2">Anyone with this link sees {brand.name}'s posts that wait for approval and can approve them or ask for changes. It works for 14 days and is shown only now.</p>
          <div className="flex items-center gap-2">
            <Input readOnly value={created?.url ?? ""} onFocus={(e) => e.currentTarget.select()} aria-label="Review link" />
            <Button size="sm" onClick={() => { void navigator.clipboard.writeText(created?.url ?? ""); setCopied(true); }}>{copied ? <Check className="size-4" /> : <Copy className="size-4" />}{copied ? "Copied" : "Copy"}</Button>
          </div>
          <DialogFooter><Button onClick={() => setCreated(null)}>Done</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---- recent activity (Today) ---------------------------------------------------------------------
export function ActivitySection({ limit = 12 }: { limit?: number }) {
  const brand = useBrand();
  const { data, isPending } = useActivity(brand.id, limit);
  const items = data?.items ?? [];
  return (
    <section aria-labelledby="activity-h" className="rounded-card border border-line bg-surface p-5">
      <h2 id="activity-h" className="mb-3 text-base font-semibold">Recent activity</h2>
      {isPending ? <Skeleton className="h-24" /> : items.length === 0 ? (
        <p className="text-sm text-ink-2">Nothing yet. What the team and clients do with {brand.name}'s posts shows up here.</p>
      ) : (
        <ul className="divide-y divide-line text-sm">
          {items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-baseline gap-x-2 py-2">
              <span><span className="font-medium">{a.actor.name}</span> {a.verb} {a.object_type === "post" ? "a post" : a.object_type === "member" ? "a member" : a.object_type === "share_link" ? "a review link" : a.object_type === "brand" ? "the brand" : a.object_type}</span>
              {a.summary && <span className="min-w-0 flex-1 truncate text-ink-2">{a.summary}</span>}
              <span className="ml-auto shrink-0 text-xs text-ink-2 tnum">{fmtDateTime(a.created_at, brand.timezone)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---- members of this brand (Settings) ---------------------------------------------------------------
export function MembersSection() {
  const brand = useBrand();
  const { user } = useWorkspace();
  const { data = [], isPending } = useMembers(brand.id);
  const add = useAddBrandMember(brand.id);
  const update = useUpdateBrandMember(brand.id);
  const remove = useRemoveBrandMember(brand.id);
  const [adding, setAdding] = useState(false);
  const [newAccount, setNewAccount] = useState(false);
  const close = () => { setAdding(false); setNewAccount(false); };
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const s = (k: string) => String(fd.get(k) ?? "").trim();
    add.mutate({ email: s("email"), role: s("role") as MemberRole, name: newAccount ? s("name") : null, password: newAccount ? s("password") : null },
      { onSuccess: close, onError: (err) => { if (err instanceof ApiError && err.status === 404) setNewAccount(true); } });
  };
  return (
    <section className="rounded-card border border-line bg-surface">
      <header className="flex items-center justify-between border-b border-line px-5 py-3">
        <div><h3 className="font-semibold">Members of {brand.name}</h3><p className="text-xs text-ink-2">Who sees this brand and what they can do.</p></div>
        <Button size="sm" variant="outline" onClick={() => setAdding(true)}>Add a member</Button>
      </header>
      {isPending ? <Skeleton className="m-5 h-20" /> : (
        <ul className="divide-y divide-line">
          {data.map((m) => {
            const self = m.user_id === user.id;
            const fixed = self || m.workspace_owner;
            return (
              <li key={m.user_id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{m.name}{self && <span className="ml-1 text-xs text-ink-2">(you)</span>}</div>
                  <div className="text-xs text-ink-2">{m.email}{m.workspace_owner && " · workspace owner, sees every brand"}{!m.is_active && " · deactivated"}</div>
                </div>
                {fixed ? <span className={cn("text-xs capitalize text-ink-2")}>{m.role}</span> : (
                  <>
                    <Select value={m.role} onValueChange={(role) => update.mutate({ user_id: m.user_id, role: role as MemberRole })}>
                      <SelectTrigger className="w-28" aria-label={`Role of ${m.name}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{ROLES.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
                    </Select>
                    <Button size="icon" variant="ghost" aria-label={`Remove ${m.name} from ${brand.name}`} onClick={() => confirm(`Remove ${m.name} from ${brand.name}?`) && remove.mutate(m.user_id)}><Trash2 className="size-4" /></Button>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <Dialog open={adding} onOpenChange={(o) => !o && close()}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add a member to {brand.name}</DialogTitle></DialogHeader>
          <form className="space-y-4" onSubmit={submit}>
            <div className="space-y-1.5"><Label htmlFor="m-email">Email</Label><Input id="m-email" name="email" type="email" required autoFocus /><p className="text-xs text-ink-2">Someone with a Spark account, or a new person: then you set a name and a first password.</p></div>
            {newAccount && (
              <>
                <div className="space-y-1.5"><Label htmlFor="m-name">Name</Label><Input id="m-name" name="name" required /></div>
                <div className="space-y-1.5"><Label htmlFor="m-pass">Temporary password</Label><Input id="m-pass" name="password" type="text" required minLength={8} autoComplete="off" /><p className="text-xs text-ink-2">Share it privately; they can change it under Preferences.</p></div>
              </>
            )}
            <div className="space-y-1.5">
              <Label>Role</Label>
              <Select name="role" defaultValue="editor"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{ROLES.map((r) => <SelectItem key={r.value} value={r.value}>{r.label} <span className="text-ink-2">· {r.hint}</span></SelectItem>)}</SelectContent></Select>
            </div>
            <DialogFooter><Button type="button" variant="ghost" onClick={close}>Cancel</Button><Button type="submit" disabled={add.isPending}>{newAccount ? "Create and add" : "Add member"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
