/** Links: tracked short links with UTM tags, and the link-in-bio page. */
import { useState, type FormEvent } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { BarChart3, Copy, ExternalLink, GripVertical, Link2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useBrand, usePerms } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useBio, useCreateLink, useDeleteLink, useLinks, useLists, useSaveBio, type BioOut, type LinkOut } from "@/features/api4";
import { LinkDetails } from "@/features/links/tracker";
import { BACK_HALF, withUtm } from "@/features/links/utm";
import { useCampaigns, useMedia } from "@/features/posts/api";
import { fmtDay, fromLocalInput, zonedDateKey } from "@/lib/time";
import { cn } from "@/lib/utils";

export function LinksPage() {
  const search = useSearch({ strict: false }) as { tab?: string };
  const navigate = useNavigate();
  const tab = search.tab === "bio" ? "bio" : "links";
  return (
    <>
      <PageHeader title="Links" description="Short links that show where each click came from, and the page behind the link in your bio." />
      <div role="tablist" className="mb-5 flex gap-1 border-b border-line">
        {[["links", "Short links"], ["bio", "Bio page"]].map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => void navigate({ to: ".", search: (p) => ({ ...p, tab: k }) })}
                  className={cn("-mb-px border-b-2 px-3 py-2 text-sm", tab === k ? "border-brand font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink")}>{label}</button>
        ))}
      </div>
      {tab === "links" ? <ShortLinks /> : <BioEditor />}
    </>
  );
}

const EMPTY = { destination: "", code: "", title: "", source: "", medium: "", campaign: "", content: "", term: "", expires: "", campaignId: "none" };

function ShortLinks() {
  const brand = useBrand();
  const { data, isPending } = useLinks(brand.id);
  const { data: campaigns = [] } = useCampaigns(brand.id);
  const create = useCreateLink(brand.id);
  const remove = useDeleteLink(brand.id);
  const { canEdit } = usePerms();
  const [f, setF] = useState(EMPTY);
  const [open, setOpen] = useState<LinkOut | null>(null);
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const camp = campaigns.find((c) => String(c.id) === f.campaignId);
  // The same order the server uses: what you type, then the campaign's name, then the brand's default
  const campaignTag = f.campaign.trim() || camp?.utm_campaign || brand.utm_campaign || "";
  const preview = withUtm(f.destination, { source: f.source, medium: f.medium, campaign: campaignTag, content: f.content, term: f.term });
  const badCode = f.code !== "" && !BACK_HALF.test(f.code);
  const base = `${location.origin.replace(/^https?:\/\//, "")}/l/`;
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (badCode) return;
    const t = (v: string) => v.trim() || null;
    create.mutate({
      destination: f.destination, title: t(f.title), code: t(f.code),
      utm_source: t(f.source), utm_medium: t(f.medium), utm_campaign: t(f.campaign), utm_content: t(f.content), utm_term: t(f.term),
      campaign_id: camp ? camp.id : null,
      expires_at: f.expires ? fromLocalInput(`${f.expires}T23:59`, brand.timezone) : null,
    }, { onSuccess: () => setF(EMPTY) });
  };
  // Links in sync with the dialog after an edit
  const current = open ? data?.items.find((l) => l.id === open.id) ?? open : null;
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <section className="min-w-0 lg:col-span-2">
        {isPending ? <Skeleton className="h-48" /> : !data?.items.length ? (
          <EmptyState icon={Link2} title="No short links yet" body="Short links count clicks per day, channel, post and referrer, and carry UTM tags so your web analytics sees each campaign." />
        ) : (
          <ul className="divide-y divide-line rounded-card border border-line bg-surface">
            {data.items.map((l) => (
              <li key={l.id} className="flex items-start gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><a href={l.short_url} target="_blank" rel="noopener" className="font-medium hover:underline">{l.short_url.replace(/^https?:\/\//, "")}</a>
                    <button type="button" className="text-ink-2 hover:text-ink" aria-label="Copy short link" onClick={() => { void navigator.clipboard.writeText(l.short_url); toast.success("Copied"); }}><Copy className="size-3.5" /></button>
                    {l.expired ? <Badge variant="outline" className="text-st-failed">Expired</Badge> : l.expires_at ? <Badge variant="outline">Until {fmtDay(zonedDateKey(l.expires_at, brand.timezone), { day: "numeric", month: "short" })}</Badge> : null}
                    {l.post_id && <Badge variant="outline">From a post</Badge>}
                    {l.campaign_id && campaigns.find((c) => c.id === l.campaign_id) && <Badge variant="outline">{campaigns.find((c) => c.id === l.campaign_id)?.name}</Badge>}
                  </div>
                  <div className="truncate text-xs text-ink-2" title={l.destination}>{l.title ? `${l.title} · ` : ""}{l.destination}</div>
                  {l.created_at && <div className="text-xs text-ink-2">{fmtDay(l.created_at.slice(0, 10), { day: "numeric", month: "short", year: "numeric" })}</div>}
                </div>
                <button type="button" onClick={() => setOpen(l)} className="rounded-control px-2 py-1 text-right hover:bg-hover" aria-label={`Clicks and QR code for ${l.short_url}`}>
                  <div className="font-semibold tnum">{l.clicks}</div><div className="flex items-center gap-1 text-xs text-ink-2"><BarChart3 className="size-3" />clicks</div>
                </button>
                {canEdit && <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Delete link" onClick={() => confirm("Delete this link? It stops redirecting.") && remove.mutate(l.id)}><Trash2 className="size-4" /></Button>}
              </li>
            ))}
          </ul>
        )}
      </section>
      {canEdit && (
        <form onSubmit={submit} className="min-w-0 space-y-3 self-start rounded-card border border-line bg-surface p-4">
          <h2 className="font-semibold">New short link</h2>
          <div className="space-y-1.5"><Label htmlFor="l-dest">Destination</Label><Input id="l-dest" value={f.destination} onChange={set("destination")} required placeholder="example.com/page" /></div>
          <div className="space-y-1.5"><Label htmlFor="l-code">Short link</Label>
            <div className="flex items-center rounded-control border border-line bg-surface focus-within:ring-2 focus-within:ring-brand/40">
              <span className="truncate pl-3 text-sm text-ink-2" title={base}>{base}</span>
              <input id="l-code" value={f.code} onChange={set("code")} placeholder="random" aria-invalid={badCode} aria-describedby="l-code-help" className="h-9 min-w-0 flex-1 bg-transparent pr-3 text-sm outline-none" />
            </div>
            <p id="l-code-help" className={cn("text-xs", badCode ? "text-st-failed" : "text-ink-2")}>{badCode ? "Use 2 to 64 letters, digits, - or _, starting with a letter or digit." : "Leave empty for a random code."}</p>
          </div>
          <div className="space-y-1.5"><Label htmlFor="l-title">Title</Label><Input id="l-title" value={f.title} onChange={set("title")} placeholder="Optional, for you" /></div>
          {campaigns.length > 0 && (
            <div className="space-y-1.5"><Label>Campaign</Label>
              <Select value={f.campaignId} onValueChange={(v) => setF((x) => ({ ...x, campaignId: v }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">None</SelectItem>{campaigns.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}</SelectContent></Select>
            </div>
          )}
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium">UTM tags</legend>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5"><Label htmlFor="l-src" className="text-xs">Source</Label><Input id="l-src" value={f.source} onChange={set("source")} placeholder="newsletter" /></div>
              <div className="space-y-1.5"><Label htmlFor="l-med" className="text-xs">Medium</Label><Input id="l-med" value={f.medium} onChange={set("medium")} placeholder="email" /></div>
              <div className="space-y-1.5"><Label htmlFor="l-camp" className="text-xs">Campaign</Label><Input id="l-camp" value={f.campaign} onChange={set("campaign")} placeholder={camp?.utm_campaign || brand.utm_campaign || "autumn-sale"} /></div>
              <div className="space-y-1.5"><Label htmlFor="l-content" className="text-xs">Content</Label><Input id="l-content" value={f.content} onChange={set("content")} placeholder="header-button" /></div>
              <div className="col-span-2 space-y-1.5"><Label htmlFor="l-term" className="text-xs">Term</Label><Input id="l-term" value={f.term} onChange={set("term")} placeholder="Paid search keyword, rarely needed" /></div>
            </div>
            {preview && <p className="break-all rounded-control bg-paper px-2 py-1.5 text-xs text-ink-2"><span className="font-medium text-ink">Sends people to </span>{preview}</p>}
            <p className="text-xs text-ink-2">Links in posts get the channel as source and the post as content automatically.</p>
          </fieldset>
          <div className="space-y-1.5"><Label htmlFor="l-exp">Stops working after</Label><Input id="l-exp" type="date" value={f.expires} onChange={set("expires")} /><p className="text-xs text-ink-2">Optional. After this day the link shows that it has expired.</p></div>
          <Button type="submit" className="w-full" disabled={create.isPending || badCode}><Plus className="size-4" />Create link</Button>
        </form>
      )}
      <LinkDetails link={current} onClose={() => setOpen(null)} />
    </div>
  );
}

type BioLinkRow = BioOut["links"][number];

function BioEditor() {
  const brand = useBrand();
  const { data, isPending } = useBio(brand.id);
  if (isPending || !data) return <Skeleton className="h-64" />;
  // keyed on the saved links so a fresh save re-seeds the form without an effect
  return <BioForm key={JSON.stringify(data.links)} data={data} />;
}

function BioForm({ data }: { data: BioOut }) {
  const brand = useBrand();
  const { data: lists = [] } = useLists(brand.id);
  const { data: media } = useMedia(brand.id);
  const save = useSaveBio(brand.id);
  const { canEdit } = usePerms();
  const [links, setLinks] = useState<BioLinkRow[]>(() => data.links);
  const images = media?.items.filter((m) => !m.is_video) ?? [];
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    save.mutate({
      title: String(fd.get("title")), bio: String(fd.get("bio")) || null, theme: String(fd.get("theme")),
      capture_email: fd.get("capture_email") === "on", is_published: fd.get("is_published") === "on",
      capture_list_id: fd.get("capture_list_id") && fd.get("capture_list_id") !== "none" ? Number(fd.get("capture_list_id")) : null,
      avatar_media_id: fd.get("avatar_media_id") && fd.get("avatar_media_id") !== "none" ? Number(fd.get("avatar_media_id")) : null,
      links,
    });
  };
  const move = (from: number, to: number) => setLinks((ls) => { if (to < 0 || to >= ls.length) return ls; const c = [...ls]; const [it] = c.splice(from, 1); c.splice(to, 0, it); return c; });
  return (
    <form onSubmit={submit} className="grid gap-6 lg:grid-cols-3">
      <fieldset disabled={!canEdit} className="space-y-5 lg:col-span-2">
        <section className="space-y-4 rounded-card border border-line bg-surface p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-semibold">Page</h2>
            <a href={data.public_url} target="_blank" rel="noopener" className="flex items-center gap-1 text-sm text-ink-2 hover:text-ink hover:underline">{data.public_url.replace(/^https?:\/\//, "")}<ExternalLink className="size-3.5" /></a>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5"><Label htmlFor="b-title">Title</Label><Input id="b-title" name="title" defaultValue={data.title} required /></div>
            <div className="space-y-1.5"><Label>Theme</Label><Select name="theme" defaultValue={data.theme}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="light">Light</SelectItem><SelectItem value="dark">Dark</SelectItem></SelectContent></Select></div>
          </div>
          <div className="space-y-1.5"><Label htmlFor="b-bio">Bio</Label><Textarea id="b-bio" name="bio" rows={3} defaultValue={data.bio ?? ""} /></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Avatar</Label>
              <Select name="avatar_media_id" defaultValue={data.avatar_media_id ? String(data.avatar_media_id) : "none"}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Brand initial</SelectItem>{images.map((m) => <SelectItem key={m.id} value={String(m.id)}>{m.name}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-1.5"><Label>Email sign-ups go to</Label>
              <Select name="capture_list_id" defaultValue={data.capture_list_id ? String(data.capture_list_id) : "none"}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">No list</SelectItem>{lists.map((l) => <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>)}</SelectContent></Select></div>
          </div>
          <div className="flex flex-wrap gap-6 text-sm">
            <label className="flex items-center gap-2"><Switch name="capture_email" defaultChecked={data.capture_email} />Show an email sign-up form</label>
            <label className="flex items-center gap-2"><Switch name="is_published" defaultChecked={data.is_published} />Page is public</label>
          </div>
        </section>
        <section className="space-y-3 rounded-card border border-line bg-surface p-5">
          <div className="flex items-center justify-between"><h2 className="font-semibold">Links</h2><span className="text-xs text-ink-2 tnum">{data.total_clicks} clicks total · {data.views} page views</span></div>
          <ul className="space-y-2">
            {links.map((l, i) => (
              <li key={l.code ?? `new-${i}`} className="flex items-center gap-2">
                <div className="flex flex-col text-ink-2"><button type="button" aria-label="Move up" onClick={() => move(i, i - 1)} className="hover:text-ink">▲</button><button type="button" aria-label="Move down" onClick={() => move(i, i + 1)} className="hover:text-ink">▼</button></div>
                <GripVertical className="size-4 text-ink-2/50" aria-hidden />
                <Input value={l.label} onChange={(e) => setLinks(links.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} placeholder="Label" className="w-40" />
                <Input value={l.url} onChange={(e) => setLinks(links.map((x, j) => j === i ? { ...x, url: e.target.value } : x))} placeholder="https://" type="url" className="flex-1" />
                <span className="w-14 text-right text-xs text-ink-2 tnum">{l.clicks ?? 0} clicks</span>
                <Button type="button" variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Remove link" onClick={() => setLinks(links.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
              </li>
            ))}
          </ul>
          <Button type="button" variant="outline" size="sm" onClick={() => setLinks([...links, { label: "", url: "", code: null, clicks: 0 }])}><Plus className="size-4" />Add link</Button>
        </section>
        {canEdit && <Button type="submit" disabled={save.isPending}>Save bio page</Button>}
      </fieldset>
      <aside className="text-sm text-ink-2 lg:col-span-1">
        <div className="rounded-card border border-line bg-surface p-4 space-y-2">
          <h3 className="font-semibold text-ink">How it works</h3>
          <p>Every link on the page is a tracked short link, so clicks count here and in Analytics. Changing a link's URL starts a fresh counter.</p>
          <p>Put the public address in your profiles' bio fields.</p>
        </div>
      </aside>
    </form>
  );
}
