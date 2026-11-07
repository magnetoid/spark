/** Audience: contacts, lists and email campaigns. */
import { useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { Download, Mail, Plus, Sparkles, Trash2, Upload, Users } from "lucide-react";
import { toast } from "sonner";
import { useBrand, usePerms, useSession } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  emailAi, importContacts, useAddContact, useContacts, useCreateEmail, useCreateList, useDeleteContact, useDeleteEmail, useDeleteList,
  useEmail, useEmails, useLists, useTestEmail, useUpdateEmail,
} from "@/features/api4";
import { fmtDateTime, fromLocalInput, toLocalInput } from "@/lib/time";
import { cn } from "@/lib/utils";

const TABS = [["contacts", "Contacts"], ["lists", "Lists"], ["email", "Email campaigns"]] as const;

export function AudiencePage() {
  const search = useSearch({ strict: false }) as { tab?: string };
  const navigate = useNavigate();
  const tab = TABS.find(([k]) => k === search.tab)?.[0] ?? "contacts";
  return (
    <>
      <PageHeader title="Audience" description="The people who gave you their email, and what you send them." />
      <div role="tablist" className="mb-5 flex gap-1 border-b border-line">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => void navigate({ to: ".", search: (p) => ({ ...p, tab: k }) })}
                  className={cn("-mb-px border-b-2 px-3 py-2 text-sm", tab === k ? "border-brand font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink")}>{label}</button>
        ))}
      </div>
      {tab === "contacts" ? <ContactsTab /> : tab === "lists" ? <ListsTab /> : <EmailTab />}
    </>
  );
}

function ContactsTab() {
  const brand = useBrand();
  const [q, setQ] = useState("");
  const [listId, setListId] = useState<string>("all");
  const { data, isPending } = useContacts(brand.id, q, listId === "all" ? undefined : Number(listId));
  const { data: lists = [] } = useLists(brand.id);
  const add = useAddContact(brand.id);
  const remove = useDeleteContact(brand.id);
  const [adding, setAdding] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { canEdit } = usePerms();

  const onImport = async (file: File | undefined) => {
    if (!file) return;
    try {
      const r = await importContacts(brand.id, file, listId === "all" ? [] : [Number(listId)]);
      toast.success(r.message);
      add.reset();
      window.dispatchEvent(new Event("spark:contacts"));
    } catch (e) { toast.error(e instanceof Error ? e.message : "Import failed"); }
  };

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search email or name" className="w-56" />
        <Select value={listId} onValueChange={setListId}><SelectTrigger className="w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All lists</SelectItem>{lists.map((l) => <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>)}</SelectContent></Select>
        {data && <span className="text-sm text-ink-2 tnum">{data.total} contacts · {data.subscribed} subscribed</span>}
        <div className="ml-auto flex gap-2">
          <Button asChild variant="outline" size="sm"><a href={`/api/v1/brands/${brand.id}/contacts/export`}><Download className="size-4" />Export CSV</a></Button>
          {canEdit && <><Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}><Upload className="size-4" />Import CSV</Button>
            <input ref={fileRef} type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => { void onImport(e.target.files?.[0]); e.target.value = ""; }} />
            <Button size="sm" onClick={() => setAdding(true)}><Plus className="size-4" />Add contact</Button></>}
        </div>
      </div>
      {isPending ? <Skeleton className="h-48" /> : !data?.items.length ? (
        <EmptyState icon={Users} title={q ? "No contacts match" : "No contacts yet"} body="Add people by hand, import a CSV with an email column, or collect sign-ups on your bio page." />
      ) : (
        <div className="overflow-x-auto rounded-card border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-ink-2"><tr><th className="px-4 py-2 font-medium">Email</th><th className="px-4 py-2 font-medium">Name</th><th className="px-4 py-2 font-medium">Lists</th><th className="px-4 py-2 font-medium">Status</th><th className="px-4 py-2 font-medium">Source</th><th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.items.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-2">{c.email}</td>
                  <td className="px-4 py-2">{[c.first_name, c.last_name].filter(Boolean).join(" ")}</td>
                  <td className="px-4 py-2 text-ink-2">{c.lists.map((id) => lists.find((l) => l.id === id)?.name).filter(Boolean).join(", ")}</td>
                  <td className="px-4 py-2">{c.subscribed ? <span className="text-st-published">subscribed</span> : <span className="text-ink-2">unsubscribed</span>}</td>
                  <td className="px-4 py-2 text-ink-2">{c.source}</td>
                  <td className="px-2 py-1 text-right">{canEdit && <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Delete contact" onClick={() => confirm(`Delete ${c.email}?`) && remove.mutate(c.id)}><Trash2 className="size-4" /></Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add a contact</DialogTitle></DialogHeader>
          <form className="space-y-4" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget);
            add.mutate({ email: String(fd.get("email")), first_name: String(fd.get("first_name")) || null, last_name: String(fd.get("last_name")) || null, list_ids: fd.getAll("list_ids").map(Number) }, { onSuccess: () => setAdding(false) }); }}>
            <div className="space-y-1.5"><Label htmlFor="ct-email">Email</Label><Input id="ct-email" name="email" type="email" required autoFocus /></div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5"><Label htmlFor="ct-first">First name</Label><Input id="ct-first" name="first_name" /></div>
              <div className="space-y-1.5"><Label htmlFor="ct-last">Last name</Label><Input id="ct-last" name="last_name" /></div>
            </div>
            {lists.length > 0 && <div className="space-y-1.5"><Label>Lists</Label><div className="flex flex-wrap gap-2">{lists.map((l) => <label key={l.id} className="flex items-center gap-1.5 rounded-control border border-line px-2 py-1 text-sm"><input type="checkbox" name="list_ids" value={l.id} className="accent-[var(--brand)]" />{l.name}</label>)}</div></div>}
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button><Button type="submit" disabled={add.isPending}>Save contact</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ListsTab() {
  const brand = useBrand();
  const { data = [], isPending } = useLists(brand.id);
  const create = useCreateList(brand.id);
  const remove = useDeleteList(brand.id);
  const { canEdit } = usePerms();
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">
        {isPending ? <Skeleton className="h-40" /> : data.length === 0 ? <EmptyState icon={Users} title="No lists yet" body="Lists group contacts for a campaign or a sign-up form." /> : (
          <ul className="divide-y divide-line rounded-card border border-line bg-surface">
            {data.map((l) => <li key={l.id} className="flex items-center gap-3 px-4 py-3 text-sm"><div className="min-w-0 flex-1"><div className="font-medium">{l.name}</div>{l.description && <div className="text-xs text-ink-2">{l.description}</div>}</div><span className="text-ink-2 tnum">{l.contacts} contacts</span>{canEdit && <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Delete list" onClick={() => confirm(`Delete “${l.name}”? Contacts stay.`) && remove.mutate(l.id)}><Trash2 className="size-4" /></Button>}</li>)}
          </ul>
        )}
      </div>
      {canEdit && (
        <form className="space-y-3 self-start rounded-card border border-line bg-surface p-4" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); const f = e.currentTarget; create.mutate({ name: String(fd.get("name")), description: String(fd.get("description")) || null }, { onSuccess: () => f.reset() }); }}>
          <h2 className="font-semibold">New list</h2>
          <div className="space-y-1.5"><Label htmlFor="ls-name">Name</Label><Input id="ls-name" name="name" required /></div>
          <div className="space-y-1.5"><Label htmlFor="ls-desc">Description</Label><Input id="ls-desc" name="description" /></div>
          <Button type="submit" className="w-full" disabled={create.isPending}>Create list</Button>
        </form>
      )}
    </div>
  );
}

function EmailTab() {
  const brand = useBrand();
  const { data = [], isPending } = useEmails(brand.id);
  const { data: lists = [] } = useLists(brand.id);
  const create = useCreateEmail(brand.id);
  const remove = useDeleteEmail(brand.id);
  const [open, setOpen] = useState<number | null>(null);
  const { data: session } = useSession();
  const { canEdit } = usePerms();
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {!session?.features.email && <span className="rounded-control border border-st-pending/40 bg-brand-soft px-2.5 py-1 text-xs">Email is in console mode on this server: campaigns are logged, not delivered. Set up delivery under Settings → Connectors.</span>}
        {canEdit && <form className="ml-auto flex gap-2" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); create.mutate({ name: String(fd.get("name")), list_id: fd.get("list_id") && fd.get("list_id") !== "none" ? Number(fd.get("list_id")) : null }, { onSuccess: (r) => setOpen(r.id) }); }}>
          <Input name="name" required placeholder="Campaign name" className="w-48" />
          <Select name="list_id" defaultValue="none"><SelectTrigger className="w-40"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Pick a list later</SelectItem>{lists.map((l) => <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>)}</SelectContent></Select>
          <Button type="submit" size="sm" disabled={create.isPending}><Plus className="size-4" />New email</Button>
        </form>}
      </div>
      {isPending ? <Skeleton className="h-40" /> : data.length === 0 ? <EmptyState icon={Mail} title="No email campaigns yet" body="Write an email to a list, send a test to yourself, then send or schedule it." /> : (
        <ul className="divide-y divide-line rounded-card border border-line bg-surface">
          {data.map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <button type="button" className="font-medium hover:underline" onClick={() => setOpen(c.id)}>{c.name}</button>
                <div className="text-xs text-ink-2">{c.subject || "No subject yet"} · <span className="capitalize">{c.status}</span>{c.scheduled_at && c.status === "scheduled" && ` for ${fmtDateTime(c.scheduled_at, brand.timezone)}`} · {c.recipients} recipients</div>
              </div>
              {c.status === "sent" && <span className="text-xs text-ink-2 tnum">{c.stats.sent} sent · {c.stats.opened} opened · {c.stats.clicked} clicked{c.stats.failed ? ` · ${c.stats.failed} failed` : ""}</span>}
              {canEdit && <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Delete campaign" onClick={() => confirm(`Delete “${c.name}”?`) && remove.mutate(c.id)}><Trash2 className="size-4" /></Button>}
            </li>
          ))}
        </ul>
      )}
      <EmailEditor id={open} onClose={() => setOpen(null)} />
    </>
  );
}

function EmailEditor({ id, onClose }: { id: number | null; onClose: () => void }) {
  const brand = useBrand();
  const { data } = useEmail(brand.id, id);
  const { data: lists = [] } = useLists(brand.id);
  const update = useUpdateEmail(brand.id);
  const test = useTestEmail(brand.id);
  const { data: session } = useSession();
  const [aiBusy, setAiBusy] = useState(false);
  const [draft, setDraft] = useState<{ subject: string; preheader: string; body_html: string } | null>(null);
  const locked = data ? ["sending", "sent"].includes(data.status) : false;
  const formRef = useRef<HTMLFormElement>(null);

  const collect = (action: "save" | "send" | "schedule" | "unschedule") => {
    const fd = new FormData(formRef.current!);
    const when = String(fd.get("scheduled_at") || "");
    return { name: String(fd.get("name")), subject: String(fd.get("subject")), preheader: String(fd.get("preheader")) || null, body_html: String(fd.get("body_html")),
             list_id: fd.get("list_id") && fd.get("list_id") !== "none" ? Number(fd.get("list_id")) : null, action,
             scheduled_at: action === "schedule" && when ? fromLocalInput(when, brand.timezone) : null };
  };
  const run = (action: "save" | "send" | "schedule" | "unschedule") => {
    if (!id) return;
    if (action === "send" && !confirm(`Send this email to ${data?.recipients ?? 0} recipients now?`)) return;
    update.mutate({ id, body: collect(action) }, { onSuccess: () => { if (action !== "save") onClose(); } });
  };
  const writeWithAi = async () => {
    const brief = prompt("What should this email say? One or two sentences.");
    if (!brief || !id) return;
    setAiBusy(true);
    try { const r = await emailAi(brand.id, id, brief); setDraft({ subject: r.subject, preheader: r.preheader ?? "", body_html: r.body_html }); }
    catch (e) { toast.error(e instanceof Error ? e.message : "AI failed"); } finally { setAiBusy(false); }
  };

  return (
    <Dialog open={id !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader><DialogTitle>{data?.name ?? "Email"}</DialogTitle></DialogHeader>
        {!data ? <Skeleton className="h-64" /> : (
          <form ref={formRef} key={`${data.id}-${draft ? "ai" : "db"}`} className="space-y-4" onSubmit={(e) => { e.preventDefault(); run("save"); }}>
            <fieldset disabled={locked} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5"><Label htmlFor="e-name">Name</Label><Input id="e-name" name="name" defaultValue={data.name} required /></div>
                <div className="space-y-1.5"><Label>List</Label><Select name="list_id" defaultValue={data.list_id ? String(data.list_id) : "none"}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Pick a list</SelectItem>{lists.map((l) => <SelectItem key={l.id} value={String(l.id)}>{l.name} ({l.contacts})</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-1.5"><Label htmlFor="e-subject">Subject</Label><Input id="e-subject" name="subject" defaultValue={draft?.subject ?? data.subject} /></div>
                <div className="space-y-1.5"><Label htmlFor="e-pre">Preheader</Label><Input id="e-pre" name="preheader" defaultValue={draft?.preheader ?? data.preheader ?? ""} /></div>
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between"><Label htmlFor="e-body">Body (HTML)</Label>{session?.features.ai && <Button type="button" variant="ghost" size="sm" onClick={() => void writeWithAi()} disabled={aiBusy}><Sparkles className="size-4" />{aiBusy ? "Writing…" : "Write with AI"}</Button>}</div>
                <Textarea id="e-body" name="body_html" rows={12} defaultValue={draft?.body_html ?? data.body_html} className="font-mono text-xs" />
                <p className="text-xs text-ink-2">Merge tags: {"{{first_name}}"}, {"{{last_name}}"}, {"{{email}}"}. An unsubscribe link is added automatically.</p>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1.5"><Label htmlFor="e-when">Schedule for ({brand.timezone})</Label><Input id="e-when" name="scheduled_at" type="datetime-local" defaultValue={toLocalInput(data.scheduled_at, brand.timezone)} /></div>
                <span className="text-sm text-ink-2 tnum">{data.recipients} recipients</span>
              </div>
            </fieldset>
            <DialogFooter className="flex-wrap gap-2 sm:justify-between">
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => id && test.mutate(id)} disabled={test.isPending}>Send me a test</Button>
                {data.status === "scheduled" && <Button type="button" variant="ghost" size="sm" onClick={() => run("unschedule")}>Unschedule</Button>}
              </div>
              {!locked && <div className="flex gap-2">
                <Button type="submit" variant="outline" disabled={update.isPending}>Save</Button>
                <Button type="button" variant="outline" onClick={() => run("schedule")} disabled={update.isPending}>Schedule</Button>
                <Button type="button" onClick={() => run("send")} disabled={update.isPending}>Send now</Button>
              </div>}
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
