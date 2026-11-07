/** Settings: brand & team, posting times, connectors (Zernio first), your preferences. */
import { useState, type FormEvent } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { Check, Copy, KeyRound, Plug, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { readTheme, setTheme, useBrand, usePerms, useWorkspace, type ThemeMode } from "@/app/session";
import { MembersSection } from "@/features/collab/panels";
import { AgentSection, JanusSection } from "@/features/agent/panels";
import { GuardrailsSection, PillarsSection } from "@/features/planning/panels";
import { useAccounts } from "@/features/posts/api";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  useAddMember, useAddSlots, useChangePassword, useConnector, useConnectors, useCreateToken, useDeleteBrand, useDeleteSlot, useDeleteToken,
  useSaveConnector, useSlots, useTeam, useTestConnector, useTokens, useUpdateBrand, useUpdateMe, useUpdateMember, useZernioWebhook,
} from "@/features/api4";
import { fmtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

const TABS = [["brand", "Brand & team"], ["times", "Posting times"], ["connectors", "Connectors"], ["me", "Preferences"]] as const;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const TIMEZONES: string[] = (() => { try { return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf("timeZone"); } catch { return ["UTC"]; } })();

export function SettingsPage() {
  const search = useSearch({ strict: false }) as { tab?: string; connector?: string };
  const navigate = useNavigate();
  const tab = TABS.find(([k]) => k === search.tab)?.[0] ?? "brand";
  const go = (patch: Record<string, string | undefined>) => void navigate({ to: ".", search: (p) => ({ ...p, ...patch }) });
  return (
    <>
      <PageHeader title="Settings" description="Brand, team, the services Spark connects to, and your own preferences." />
      <div role="tablist" className="mb-5 flex gap-1 overflow-x-auto border-b border-line">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => go({ tab: k, connector: undefined })}
                  className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm", tab === k ? "border-brand font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink")}>{label}</button>
        ))}
      </div>
      {tab === "brand" ? <BrandTab /> : tab === "times" ? <TimesTab /> : tab === "connectors" ? (search.connector ? <ConnectorDetail connectorKey={search.connector} onBack={() => go({ connector: undefined })} /> : <ConnectorsTab onOpen={(k) => go({ connector: k })} />) : <MeTab />}
    </>
  );
}

// ---- brand & team ---------------------------------------------------------------------------
function BrandTab() {
  const brand = useBrand();
  const { user, brands } = useWorkspace();
  const update = useUpdateBrand(brand.id);
  const remove = useDeleteBrand();
  const { canManage: isOwner, canEdit } = usePerms();
  const isWorkspaceOwner = user.role === "owner";
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const s = (k: string) => String(fd.get(k) ?? "");
    update.mutate({ name: s("name"), website: s("website") || null, timezone: s("timezone"), color: s("color"), voice_tone: s("voice_tone") || null,
      voice_audience: s("voice_audience") || null, voice_rules: s("voice_rules") || null, voice_examples: s("voice_examples") || null,
      default_hashtags: s("default_hashtags") || null, utm_campaign: s("utm_campaign") || null, require_approval: fd.get("require_approval") === "on", auto_shorten_links: fd.get("auto_shorten_links") === "on" });
  };
  return (
    <div className="grid gap-8 lg:grid-cols-3">
      <div className="space-y-8 lg:col-span-2">
        <form onSubmit={submit} className="space-y-5 rounded-card border border-line bg-surface p-5">
          <fieldset disabled={!isOwner} className="space-y-5">
            <h2 className="font-semibold">{brand.name}</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5"><Label htmlFor="b-name">Name</Label><Input id="b-name" name="name" defaultValue={brand.name} required /></div>
              <div className="space-y-1.5"><Label htmlFor="b-web">Website</Label><Input id="b-web" name="website" type="url" defaultValue={brand.website ?? ""} /></div>
              <div className="space-y-1.5"><Label>Timezone</Label><Select name="timezone" defaultValue={brand.timezone}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent className="max-h-72">{TIMEZONES.map((tz) => <SelectItem key={tz} value={tz}>{tz}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-1.5"><Label htmlFor="b-color">Brand colour</Label><div className="flex items-center gap-2"><input id="b-color" name="color" type="color" defaultValue={brand.color} className="h-9 w-14 rounded-control border border-line bg-surface p-1" /><span className="text-xs text-ink-2">The whole app takes this colour as its accent.</span></div></div>
            </div>
            <div className="space-y-3 border-t border-line pt-4">
              <h3 className="font-semibold">Brand voice</h3>
              <p className="-mt-1 text-sm text-ink-2">Every AI draft reads this. Be concrete: it's the difference between generic copy and yours.</p>
              <VoiceField name="voice_tone" label="Tone" rows={2} placeholder="e.g. Direct, warm, a little dry. Short sentences. We explain, we don't hype." />
              <VoiceField name="voice_audience" label="Audience" rows={2} placeholder="Who reads this and what they care about" />
              <VoiceField name="voice_rules" label="Rules: do and don't" rows={3} placeholder="Never use emoji. Don't mention competitors by name. Always link to the docs, not the homepage." />
              <VoiceField name="voice_examples" label="Example posts in your voice" rows={4} placeholder="Paste 2–3 posts you were happy with" />
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5"><Label htmlFor="b-tags">Preferred hashtags</Label><Input id="b-tags" name="default_hashtags" defaultValue={brand.default_hashtags ?? ""} placeholder="#spark #marketing" /></div>
                <div className="space-y-1.5"><Label htmlFor="b-utm">Default utm_campaign</Label><Input id="b-utm" name="utm_campaign" defaultValue={brand.utm_campaign ?? ""} /></div>
              </div>
            </div>
            <div className="space-y-3 border-t border-line pt-4">
              <h3 className="font-semibold">Workflow</h3>
              <label className="flex items-start gap-3 text-sm"><Switch name="require_approval" defaultChecked={brand.require_approval} /><span>Owners approve posts before they go out<span className="block text-xs text-ink-2">Editors' posts wait in “awaiting approval”.</span></span></label>
              <label className="flex items-start gap-3 text-sm"><Switch name="auto_shorten_links" defaultChecked={brand.auto_shorten_links} /><span>Track links automatically<span className="block text-xs text-ink-2">URLs in posts become short links with UTM tags.</span></span></label>
            </div>
          </fieldset>
          {isOwner && <Button type="submit" disabled={update.isPending}>Save brand settings</Button>}
          {!isOwner && <p className="text-xs text-ink-2">Only owners change brand settings.</p>}
        </form>
        <AgentSection />
        <PillarsSection />
        <GuardrailsSection />
        {isOwner && <MembersSection />}
        {isWorkspaceOwner && <TeamSection />}
        {isOwner && brands.length > 1 && (
          <section className="rounded-card border border-st-failed/40 bg-surface p-5">
            <h3 className="font-semibold">Delete this brand</h3>
            <p className="mt-1 text-sm text-ink-2">Removes {brand.name} with its posts, channels, contacts and links. This cannot be undone.</p>
            <Button variant="destructive" size="sm" className="mt-3" onClick={() => { if (prompt(`Type ${brand.name} to delete it`) === brand.name) remove.mutate(brand.id, { onSuccess: () => window.location.assign(import.meta.env.BASE_URL) }); }}>Delete brand</Button>
          </section>
        )}
      </div>
      <aside className="space-y-4 text-sm">
        <div className="space-y-2 rounded-card border border-line bg-surface p-4"><h3 className="font-semibold">Roles</h3><p className="text-ink-2">Roles are per brand. <b>Owners</b> approve posts, manage members and connectors. <b>Editors</b> write and schedule. <b>Viewers</b> read. <b>Clients</b> see only their brand and approve posts.</p>{canEdit && <p className="text-ink-2">Workspace owners see every brand without being added.</p>}</div>
      </aside>
    </div>
  );
}

function VoiceField({ name, label, rows, placeholder }: { name: "voice_tone" | "voice_audience" | "voice_rules" | "voice_examples"; label: string; rows: number; placeholder: string }) {
  const brand = useBrand();
  return <div className="space-y-1.5"><Label htmlFor={`b-${name}`}>{label}</Label><Textarea id={`b-${name}`} name={name} rows={rows} defaultValue={brand[name] ?? ""} placeholder={placeholder} /></div>;
}

function TeamSection() {
  const { data = [], isPending } = useTeam();
  const add = useAddMember();
  const update = useUpdateMember();
  const { user } = useWorkspace();
  const [adding, setAdding] = useState(false);
  return (
    <section className="rounded-card border border-line bg-surface">
      <header className="flex items-center justify-between border-b border-line px-5 py-3"><h3 className="font-semibold">Team</h3><Button size="sm" variant="outline" onClick={() => setAdding(true)}>Add a member</Button></header>
      {isPending ? <Skeleton className="m-5 h-20" /> : (
        <ul className="divide-y divide-line">
          {data.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
              <div className="min-w-0 flex-1"><div className="font-medium">{m.name}{m.id === user.id && <span className="ml-1 text-xs text-ink-2">(you)</span>}</div><div className="text-xs text-ink-2">{m.email}</div></div>
              {m.id === user.id ? <span className="text-xs text-ink-2 capitalize">{m.role}</span> : (
                <>
                  <Select value={m.role} onValueChange={(role) => update.mutate({ id: m.id, body: { role: role as "owner" | "editor" | "viewer" } })}><SelectTrigger className="w-28"><SelectValue /></SelectTrigger><SelectContent>{["owner", "editor", "viewer"].map((r) => <SelectItem key={r} value={r} className="capitalize">{r}</SelectItem>)}</SelectContent></Select>
                  <label className="flex items-center gap-2 text-xs"><Switch checked={m.is_active} onCheckedChange={(v) => update.mutate({ id: m.id, body: { is_active: v } })} />Active</label>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add a team member</DialogTitle></DialogHeader>
          <form className="space-y-4" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget);
            add.mutate({ name: String(fd.get("name")), email: String(fd.get("email")), password: String(fd.get("password")), role: String(fd.get("role")) as "owner" | "editor" | "viewer" }, { onSuccess: () => setAdding(false) }); }}>
            <div className="space-y-1.5"><Label htmlFor="t-name">Name</Label><Input id="t-name" name="name" required autoFocus /></div>
            <div className="space-y-1.5"><Label htmlFor="t-email">Email</Label><Input id="t-email" name="email" type="email" required /></div>
            <div className="space-y-1.5"><Label htmlFor="t-pass">Temporary password</Label><Input id="t-pass" name="password" type="text" required minLength={8} autoComplete="off" /><p className="text-xs text-ink-2">Share it privately; they can change it under Preferences.</p></div>
            <div className="space-y-1.5"><Label>Role</Label><Select name="role" defaultValue="editor"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="owner">Owner</SelectItem><SelectItem value="editor">Editor</SelectItem><SelectItem value="viewer">Viewer</SelectItem></SelectContent></Select></div>
            <DialogFooter><Button type="button" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button><Button type="submit" disabled={add.isPending}>Add member</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}

// ---- posting times ----------------------------------------------------------------------------
function TimesTab() {
  const brand = useBrand();
  const { data = [], isPending } = useSlots(brand.id);
  const add = useAddSlots(brand.id);
  const remove = useDeleteSlot(brand.id);
  const { canEdit } = usePerms();
  const { data: accounts = [] } = useAccounts(brand.id);
  const accountOf = (id: number | null | undefined) => accounts.find((a) => a.id === id);
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <section className="rounded-card border border-line bg-surface p-5 lg:col-span-2">
        <h2 className="font-semibold">Weekly posting times</h2>
        <p className="mt-1 text-sm text-ink-2">The queue fills these slots in {brand.timezone}. “Next free slot” means the first one that has no post.</p>
        {isPending ? <Skeleton className="mt-4 h-40" /> : (
          <div className="mt-4 grid grid-cols-7 gap-2 text-sm">
            {WEEKDAYS.map((d, i) => (
              <div key={d}><div className="mb-1 text-xs text-ink-2">{d}</div>
                <ul className="space-y-1">{data.filter((s) => s.weekday === i).map((s) => <li key={s.id} className="group flex items-center justify-between rounded-control border border-line px-1.5 py-1 tnum" title={s.account_id ? `${accountOf(s.account_id)?.handle ?? "channel"} only` : "All channels"}><span className="flex items-center gap-1">{s.account_id && accountOf(s.account_id) && <PlatformMark platform={accountOf(s.account_id)!.platform} size={10} />}{s.time}</span>{canEdit && <button type="button" aria-label={`Remove ${d} ${s.time}`} className="text-ink-2 opacity-0 hover:text-st-failed group-hover:opacity-100 focus:opacity-100" onClick={() => remove.mutate(s.id)}>×</button>}</li>)}</ul>
              </div>
            ))}
          </div>
        )}
        {data.length === 0 && !isPending && <p className="mt-4 text-sm text-st-pending">No slots: the queue falls back to 09:00, 12:30 and 17:00 every day until you add some.</p>}
      </section>
      {canEdit && (
        <form className="space-y-3 self-start rounded-card border border-line bg-surface p-4" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); const acc = String(fd.get("account_id") ?? "all"); add.mutate({ weekdays: fd.getAll("weekdays").map(Number), time: String(fd.get("time")), account_id: acc === "all" ? null : Number(acc) }); }}>
          <h2 className="font-semibold">Add a time</h2>
          <div className="flex flex-wrap gap-1.5">{WEEKDAYS.map((d, i) => <label key={d} className="flex items-center gap-1 rounded-control border border-line px-2 py-1 text-sm"><input type="checkbox" name="weekdays" value={i} defaultChecked={i < 5} className="accent-[var(--brand)]" />{d}</label>)}</div>
          <div className="space-y-1.5"><Label htmlFor="s-time">Time</Label><Input id="s-time" name="time" type="time" required defaultValue="09:00" /></div>
          {accounts.length > 1 && (
            <div className="space-y-1.5"><Label htmlFor="slot-channel">Channel</Label>
              <Select name="account_id" defaultValue="all"><SelectTrigger id="slot-channel"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="all">All channels</SelectItem>{accounts.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.handle} · {platformLabel(a.platform)}</SelectItem>)}</SelectContent></Select>
              <p className="text-xs text-ink-2">A channel with its own times ignores the shared ones.</p></div>
          )}
          <Button type="submit" className="w-full" disabled={add.isPending}>Add slot</Button>
        </form>
      )}
    </div>
  );
}

// ---- connectors --------------------------------------------------------------------------------
function ConnectorsTab({ onOpen }: { onOpen: (key: string) => void }) {
  const { data = [], isPending } = useConnectors();
  const { user } = useWorkspace();
  if (isPending) return <Skeleton className="h-48" />;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {data.map((c, i) => (
          <button key={c.key} type="button" onClick={() => onOpen(c.key)} className={cn("flex flex-col gap-3 rounded-card border border-line bg-surface p-5 text-left hover:border-brand", i === 0 && "ring-1 ring-brand/40")}>
            <div className="flex items-start gap-3">
              <span className={cn("grid size-9 shrink-0 place-items-center rounded-control border border-line bg-hover font-bold", c.key === "zernio" && "border-transparent bg-brand text-brand-fg")}>{c.name[0]}</span>
              <div className="min-w-0 flex-1"><div className="flex items-center gap-2"><h2 className="font-semibold">{c.name}</h2>{i === 0 && <span className="rounded-full border border-line px-1.5 text-[10px]">Primary</span>}</div><p className="text-sm text-ink-2">{c.tagline}</p></div>
            </div>
            <div className="mt-auto flex items-center justify-between pt-1 text-xs"><span className={cn("flex items-center gap-1.5 font-medium", c.configured ? "text-st-published" : c.kind === "service" ? "text-st-failed" : "text-ink-2")}><span className="status-dot" />{c.status}</span><span className="text-ink-2">{c.tags.join(" · ")}</span></div>
          </button>
        ))}
      </div>
      {user.role !== "owner" && <p className="mt-6 text-sm text-ink-2">Only owners change connectors. You can create your own MCP tokens.</p>}
    </>
  );
}

function ConnectorDetail({ connectorKey, onBack }: { connectorKey: string; onBack: () => void }) {
  const { data, isPending } = useConnector(connectorKey);
  const save = useSaveConnector();
  const test = useTestConnector();
  const webhook = useZernioWebhook();
  const { user } = useWorkspace();
  const isOwner = user.role === "owner";
  const [clear, setClear] = useState<string[]>([]);
  if (isPending || !data) return <Skeleton className="h-64" />;
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const values: Record<string, unknown> = {};
    for (const f of data.fields) {
      if (f.kind === "bool") values[f.name] = fd.get(f.name) === "on";
      else { const v = String(fd.get(f.name) ?? ""); if (f.kind === "secret" && !v) continue; values[f.name] = v; }
    }
    save.mutate({ key: data.key, body: { values, clear } }, { onSuccess: () => setClear([]) });
  };
  const extra = data.extra as { mcp_url?: string; tools?: { name: string; summary: string }[]; apps?: { label: string; configured: boolean; env: string }[]; redirect_base?: string; accounts?: number; webhook?: Record<string, unknown> | null; janus?: Record<string, unknown> | null };
  return (
    <div>
      <button type="button" onClick={onBack} className="text-sm text-ink-2 hover:underline">← All connectors</button>
      <div className="mb-6 mt-3 flex flex-wrap items-start gap-4">
        <span className={cn("grid size-12 place-items-center rounded-control border border-line bg-hover text-xl font-bold", data.key === "zernio" && "border-transparent bg-brand text-brand-fg")}>{data.name[0]}</span>
        <div className="min-w-0 flex-1"><div className="flex items-center gap-2"><h2 className="text-xl font-semibold">{data.name}</h2>{data.kind === "service" && <span className={cn("flex items-center gap-1.5 text-xs font-medium", data.configured ? "text-st-published" : "text-st-failed")}><span className="status-dot" />{data.configured ? "Connected" : "Not connected"}</span>}</div>
          <p className="max-w-2xl text-sm text-ink-2">{data.description}{data.docs && <> <a className="underline" href={data.docs} target="_blank" rel="noopener">Docs</a></>}</p></div>
      </div>
      <div className="grid gap-8 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {data.fields.length > 0 && (
            <form onSubmit={submit} className="space-y-4 rounded-card border border-line bg-surface p-5" autoComplete="off">
              <h3 className="font-semibold">Configuration</h3>
              <fieldset disabled={!isOwner} className="grid gap-4 sm:grid-cols-2">
                {data.fields.map((f) => (
                  <div key={f.name} className={cn("space-y-1.5", (f.kind === "secret" || ["zernio_base_url", "email_from"].includes(f.name)) && "sm:col-span-2")}>
                    {f.kind === "bool" ? <label className="flex items-center gap-2 text-sm"><Switch name={f.name} defaultChecked={Boolean(f.value)} />{f.label}</label> : (
                      <>
                        <Label htmlFor={`cf-${f.name}`} className="flex items-center gap-2">{f.label}<span className="text-xs font-normal text-ink-2">{f.source === "saved" ? "saved in Spark" : f.source === "env" ? "from server environment" : f.kind === "secret" ? (f.has_value ? "" : "not set") : "default"}</span></Label>
                        {f.kind === "select" ? <Select name={f.name} defaultValue={String(f.value ?? "")}><SelectTrigger id={`cf-${f.name}`}><SelectValue /></SelectTrigger><SelectContent>{f.options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent></Select>
                         : f.kind === "secret" ? <Input id={`cf-${f.name}`} name={f.name} type="password" autoComplete="new-password" className="font-mono" placeholder={f.has_value ? `Current: ${f.masked} · type to replace` : f.placeholder} />
                         : <Input id={`cf-${f.name}`} name={f.name} type={f.kind === "number" ? "number" : "text"} defaultValue={String(f.value ?? "")} placeholder={f.placeholder} />}
                      </>
                    )}
                    {f.help && <p className="text-xs text-ink-2">{f.help}</p>}
                    {f.source === "saved" && isOwner && <label className="flex items-center gap-2 text-xs text-ink-2"><input type="checkbox" checked={clear.includes(f.name)} onChange={(e) => setClear(e.target.checked ? [...clear, f.name] : clear.filter((x) => x !== f.name))} className="accent-[var(--brand)]" />Remove the saved value{f.kind === "secret" && " (falls back to the server environment)"}</label>}
                  </div>
                ))}
              </fieldset>
              {isOwner && <div className="flex flex-wrap items-center gap-2"><Button type="submit" disabled={save.isPending}>Save</Button><Button type="button" variant="outline" onClick={() => test.mutate(data.key)} disabled={test.isPending}>{data.key === "email" ? "Send test email" : "Test connection"}</Button><span className="text-xs text-ink-2">Save first, then test.</span></div>}
            </form>
          )}
          {data.key === "zernio" && data.configured && (
            <section className="space-y-4 rounded-card border border-line bg-surface p-5">
              <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">Accounts</h3><p className="text-sm text-ink-2">{extra.accounts ?? 0} account(s) come through Zernio. Connect more on Channels.</p></div></div>
              {extra.webhook !== undefined && (
                <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4 text-sm">
                  <div className="min-w-64 flex-1"><div className="font-medium">Instant updates (webhooks)</div>
                    {extra.webhook === null ? <p className="text-ink-2">Could not reach Zernio to check. Try Test connection.</p>
                     : extra.webhook.missing ? <p className="text-ink-2">Zernio does not notify this Spark yet. Publish results arrive on the next poll.</p>
                     : <p className="text-ink-2"><span className={extra.webhook.isActive ? "text-st-published" : "text-st-failed"}>{extra.webhook.isActive ? "active" : "disabled by Zernio"}</span> · {((extra.webhook.events as unknown[]) ?? []).length} events{extra.webhook.lastFiredAt ? ` · last delivery ${String(extra.webhook.lastFiredAt).slice(0, 16).replace("T", " ")}` : " · no deliveries yet"}{extra.webhook.failureCount ? ` · ${String(extra.webhook.failureCount)} recent failure(s)` : ""}</p>}
                    {extra.webhook && <p className="mt-1 text-xs text-ink-2"><code>{String(extra.webhook.url ?? "")}</code></p>}</div>
                  {isOwner && extra.webhook && <><Button size="sm" variant={extra.webhook.missing ? "default" : "outline"} onClick={() => webhook.mutate("register")} disabled={webhook.isPending}>{extra.webhook.missing ? "Enable webhooks" : "Refresh registration"}</Button>{!extra.webhook.missing && <Button size="sm" variant="ghost" onClick={() => webhook.mutate("test")}>Send test</Button>}</>}
                </div>
              )}
            </section>
          )}
          {data.key === "janus" && <JanusSection info={extra.janus} />}
          {data.key === "mcp" && <McpSection mcpUrl={extra.mcp_url ?? ""} tools={extra.tools ?? []} />}
          {data.key === "direct" && (
            <section className="rounded-card border border-line bg-surface">
              <table className="w-full text-sm"><thead className="text-left text-xs text-ink-2"><tr><th className="px-4 py-2 font-medium">Platform</th><th className="px-4 py-2 font-medium">Status</th><th className="hidden px-4 py-2 font-medium sm:table-cell">Environment variables</th></tr></thead>
                <tbody className="divide-y divide-line">{extra.apps?.map((a) => <tr key={a.label}><td className="px-4 py-2">{a.label}</td><td className="px-4 py-2">{a.configured ? <span className="text-st-published">configured</span> : <span className="text-ink-2">not set</span>}</td><td className="hidden px-4 py-2 font-mono text-xs text-ink-2 sm:table-cell">{a.env}</td></tr>)}</tbody></table>
              <p className="border-t border-line p-4 text-sm text-ink-2">Register each app's OAuth redirect URL as <code>{extra.redirect_base}&lt;platform&gt;</code>, set the variables on the server, then redeploy.</p>
            </section>
          )}
        </div>
        <aside className="space-y-2 rounded-card border border-line bg-surface p-4 text-sm text-ink-2 lg:col-span-1 self-start">
          <h3 className="font-semibold text-ink">Where values come from</h3><p>A value saved here is encrypted and wins over the <code>SPARK_*</code> environment variable. Remove it to fall back.</p><p>The worker picks up changes within 30 seconds.</p>
        </aside>
      </div>
    </div>
  );
}

function McpSection({ mcpUrl, tools }: { mcpUrl: string; tools: { name: string; summary: string }[] }) {
  const { data = [], isPending } = useTokens();
  const create = useCreateToken();
  const remove = useDeleteToken();
  const { brand } = useWorkspace();
  const [fresh, setFresh] = useState<{ name: string; token: string } | null>(null);
  const copy = (t: string) => { void navigator.clipboard.writeText(t); toast.success("Copied"); };
  return (
    <>
      <section className="space-y-2 rounded-card border border-line bg-surface p-5">
        <h3 className="font-semibold">Server address</h3>
        <div className="flex gap-2"><Input readOnly value={mcpUrl} className="font-mono" onClick={(e) => e.currentTarget.select()} /><Button type="button" variant="outline" onClick={() => copy(mcpUrl)}><Copy className="size-4" />Copy</Button></div>
        <p className="text-sm text-ink-2">Streamable HTTP. Authenticate with <code>Authorization: Bearer &lt;token&gt;</code>. Tools act as you, with your role.</p>
      </section>
      <section className="space-y-4 rounded-card border border-line bg-surface p-5">
        <h3 className="font-semibold">Your tokens</h3>
        {fresh && (
          <div className="space-y-2 rounded-card border border-st-published/40 bg-brand-soft/50 p-3 text-sm">
            <p className="font-medium">Copy “{fresh.name}” now. Spark stores only a hash, so it won't be shown again.</p>
            <div className="flex gap-2"><Input readOnly value={fresh.token} className="font-mono text-xs" onClick={(e) => e.currentTarget.select()} /><Button size="sm" onClick={() => copy(fresh.token)}>Copy</Button></div>
            <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-control bg-paper p-2 text-xs">claude mcp add --transport http spark {mcpUrl} --header "Authorization: Bearer {fresh.token}"</pre>
          </div>
        )}
        {isPending ? <Skeleton className="h-16" /> : data.length === 0 ? <p className="text-sm text-ink-2">No tokens yet. Create one per client so you can revoke them separately.</p> : (
          <ul className="divide-y divide-line text-sm">
            {data.map((t) => <li key={t.id} className="flex items-center gap-3 py-2"><KeyRound className="size-4 text-ink-2" /><div className="min-w-0 flex-1"><div className="font-medium">{t.name}</div><div className="text-xs text-ink-2"><code>{t.prefix}…</code>{t.created_at && ` · created ${fmtDateTime(t.created_at, brand?.timezone ?? "UTC")}`} · {t.last_used_at ? `last used ${fmtDateTime(t.last_used_at, brand?.timezone ?? "UTC")}` : "never used"}</div></div><Button variant="ghost" size="sm" onClick={() => confirm("Revoke this token? Clients using it stop working.") && remove.mutate(t.id)}><Trash2 className="size-4" />Revoke</Button></li>)}
          </ul>
        )}
        <form className="flex flex-wrap gap-2" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); const f = e.currentTarget; create.mutate(String(fd.get("name") || "MCP client"), { onSuccess: (r) => { setFresh({ name: r.name, token: r.token }); f.reset(); } }); }}>
          <Input name="name" placeholder="Name, e.g. Claude Code on my laptop" className="min-w-48 flex-1" maxLength={120} /><Button type="submit" disabled={create.isPending}>Create token</Button>
        </form>
      </section>
      <section className="space-y-2 rounded-card border border-line bg-surface p-5 text-sm">
        <h3 className="font-semibold">What an assistant can do</h3>
        <ul className="grid gap-1 text-ink-2 sm:grid-cols-2">{tools.map((t) => <li key={t.name}><code className="text-xs text-ink">{t.name}</code> · {t.summary}</li>)}</ul>
      </section>
    </>
  );
}

// ---- preferences -----------------------------------------------------------------------------------
function MeTab() {
  const { user, session } = useWorkspace();
  const update = useUpdateMe();
  const password = useChangePassword();
  const [theme, setThemeState] = useState<ThemeMode>(readTheme);
  const prefs = { notify_failed: true, notify_approvals: true, digest_weekly: true, default_action: "queue", shortcuts: true, ...(user.prefs as Record<string, unknown>) };
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    update.mutate({ name: String(fd.get("name")), email: String(fd.get("email")), prefs: { notify_failed: fd.get("notify_failed") === "on", notify_approvals: fd.get("notify_approvals") === "on", digest_weekly: fd.get("digest_weekly") === "on", default_action: String(fd.get("default_action")), shortcuts: fd.get("shortcuts") === "on" } });
  };
  return (
    <div className="grid gap-8 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <form onSubmit={submit} className="space-y-6 rounded-card border border-line bg-surface p-5">
          <section className="space-y-4"><h2 className="font-semibold">Profile</h2>
            <div className="grid gap-4 sm:grid-cols-2"><div className="space-y-1.5"><Label htmlFor="m-name">Name</Label><Input id="m-name" name="name" defaultValue={user.name} required /></div><div className="space-y-1.5"><Label htmlFor="m-email">Email</Label><Input id="m-email" name="email" type="email" defaultValue={user.email} required /></div></div>
            <p className="text-xs text-ink-2">Role: <span className="capitalize">{user.role}</span>{user.role !== "owner" && " · an owner changes roles"}</p></section>
          <section className="space-y-3"><h2 className="font-semibold">Email notifications</h2>
            {!session.features.email && <p className="rounded-control border border-line bg-paper px-3 py-2 text-xs text-ink-2">Email is in console mode on this server: notifications are logged, not delivered. An owner sets up delivery under Connectors.</p>}
            {user.role !== "viewer" && <label className="flex items-start gap-3 text-sm"><Switch name="notify_failed" defaultChecked={Boolean(prefs.notify_failed)} /><span>A post failed to publish<span className="block text-xs text-ink-2">After the last retry, with the platform's error.</span></span></label>}
            {user.role === "owner" && <label className="flex items-start gap-3 text-sm"><Switch name="notify_approvals" defaultChecked={Boolean(prefs.notify_approvals)} /><span>A post waits for my approval<span className="block text-xs text-ink-2">Once per post, when editors schedule something.</span></span></label>}
            <label className="flex items-start gap-3 text-sm"><Switch name="digest_weekly" defaultChecked={Boolean(prefs.digest_weekly)} /><span>Weekly digest<span className="block text-xs text-ink-2">Monday morning: last week's numbers per brand, top posts, what's coming up.</span></span></label></section>
          <section className="space-y-3"><h2 className="font-semibold">Composer</h2>
            <div className="space-y-1.5"><Label>Default action when I open a new post</Label><Select name="default_action" defaultValue={String(prefs.default_action)}><SelectTrigger className="max-w-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="queue">Add to queue (next free slot)</SelectItem><SelectItem value="next">Share next</SelectItem><SelectItem value="schedule">Pick a time</SelectItem><SelectItem value="draft">Save as draft</SelectItem></SelectContent></Select></div>
            <label className="flex items-start gap-3 text-sm"><Switch name="shortcuts" defaultChecked={Boolean(prefs.shortcuts)} /><span>Keyboard shortcuts<span className="block text-xs text-ink-2"><kbd>c</kbd> new post, <kbd>⌘K</kbd> jump anywhere.</span></span></label></section>
          <section className="space-y-2"><h2 className="font-semibold">Theme</h2><div className="flex gap-1 rounded-control border border-line p-0.5 text-sm w-fit">{(["light", "dark", "system"] as const).map((m) => <button key={m} type="button" onClick={() => { setTheme(m); setThemeState(m); }} className={cn("flex items-center gap-1 rounded-[4px] px-2.5 py-1 capitalize", theme === m ? "bg-hover font-medium" : "text-ink-2")}>{theme === m && <Check className="size-3" />}{m}</button>)}</div></section>
          <Button type="submit" disabled={update.isPending}>Save preferences</Button>
        </form>
        <form className="space-y-4 rounded-card border border-line bg-surface p-5" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); const f = e.currentTarget; password.mutate({ current: String(fd.get("current")), new: String(fd.get("new")) }, { onSuccess: () => f.reset() }); }}>
          <h2 className="font-semibold">Password</h2>
          <div className="grid gap-4 sm:grid-cols-2"><div className="space-y-1.5"><Label htmlFor="p-cur">Current password</Label><Input id="p-cur" name="current" type="password" required autoComplete="current-password" /></div><div className="space-y-1.5"><Label htmlFor="p-new">New password</Label><Input id="p-new" name="new" type="password" required minLength={10} autoComplete="new-password" /><p className="text-xs text-ink-2">At least 10 characters.</p></div></div>
          <Button type="submit" variant="outline" disabled={password.isPending}>Change password</Button>
        </form>
      </div>
      <aside className="space-y-2 self-start rounded-card border border-line bg-surface p-4 text-sm text-ink-2"><h3 className="font-semibold text-ink">About notifications</h3><p>Failure and approval emails go out within a minute from the worker. The digest covers every brand you can see and skips brands without channels.</p><p>MCP tokens live under Connectors → <Plug className="inline size-3" /> MCP access.</p></aside>
    </div>
  );
}

