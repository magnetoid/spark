/** Links: tracked short links with UTM tags, and the link-in-bio page. */
import { useState, type FormEvent } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { Copy, ExternalLink, GripVertical, Link2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useBrand, usePerms } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useBio, useCreateLink, useDeleteLink, useLinks, useLists, useSaveBio, type BioOut } from "@/features/api4";
import { useCampaigns, useMedia } from "@/features/posts/api";
import { fmtDay } from "@/lib/time";
import { cn } from "@/lib/utils";

export function LinksPage() {
  const search = useSearch({ strict: false }) as { tab?: string };
  const navigate = useNavigate();
  const tab = search.tab === "bio" ? "bio" : "links";
  return (
    <>
      <PageHeader title="Links" description="Short links that count clicks, and the page behind the link in your bio." />
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

function ShortLinks() {
  const brand = useBrand();
  const { data, isPending } = useLinks(brand.id);
  const { data: campaigns = [] } = useCampaigns(brand.id);
  const create = useCreateLink(brand.id);
  const remove = useDeleteLink(brand.id);
  const { canEdit } = usePerms();
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const form = e.currentTarget;
    create.mutate({
      destination: String(fd.get("destination")), title: String(fd.get("title")) || null, utm_source: String(fd.get("utm_source")) || null,
      utm_medium: String(fd.get("utm_medium")) || null, utm_campaign: String(fd.get("utm_campaign")) || null, utm_content: String(fd.get("utm_content")) || null,
      campaign_id: fd.get("campaign_id") && fd.get("campaign_id") !== "none" ? Number(fd.get("campaign_id")) : null,
    }, { onSuccess: () => form.reset() });
  };
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <section className="lg:col-span-2">
        {isPending ? <Skeleton className="h-48" /> : !data?.items.length ? (
          <EmptyState icon={Link2} title="No short links yet" body="Short links track clicks and carry UTM tags, so Analytics shows what each post drove." />
        ) : (
          <ul className="divide-y divide-line rounded-card border border-line bg-surface">
            {data.items.map((l) => (
              <li key={l.id} className="flex items-start gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2"><a href={l.short_url} target="_blank" rel="noopener" className="font-medium hover:underline">{l.short_url.replace(/^https?:\/\//, "")}</a>
                    <button type="button" className="text-ink-2 hover:text-ink" aria-label="Copy short link" onClick={() => { void navigator.clipboard.writeText(l.short_url); toast.success("Copied"); }}><Copy className="size-3.5" /></button></div>
                  <div className="truncate text-xs text-ink-2" title={l.destination}>{l.title ? `${l.title} · ` : ""}{l.destination}</div>
                  {l.created_at && <div className="text-xs text-ink-2">{fmtDay(l.created_at.slice(0, 10), { day: "numeric", month: "short", year: "numeric" })}</div>}
                </div>
                <div className="text-right"><div className="font-semibold tnum">{l.clicks}</div><div className="text-xs text-ink-2">clicks</div></div>
                {canEdit && <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Delete link" onClick={() => confirm("Delete this link? It stops redirecting.") && remove.mutate(l.id)}><Trash2 className="size-4" /></Button>}
              </li>
            ))}
          </ul>
        )}
      </section>
      {canEdit && (
        <form onSubmit={submit} className="space-y-3 self-start rounded-card border border-line bg-surface p-4">
          <h2 className="font-semibold">New short link</h2>
          <div className="space-y-1.5"><Label htmlFor="l-dest">Destination</Label><Input id="l-dest" name="destination" required placeholder="example.com/page" /></div>
          <div className="space-y-1.5"><Label htmlFor="l-title">Title</Label><Input id="l-title" name="title" placeholder="Optional, for you" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5"><Label htmlFor="l-src">utm_source</Label><Input id="l-src" name="utm_source" placeholder="newsletter" /></div>
            <div className="space-y-1.5"><Label htmlFor="l-med">utm_medium</Label><Input id="l-med" name="utm_medium" placeholder="email" /></div>
            <div className="space-y-1.5"><Label htmlFor="l-camp">utm_campaign</Label><Input id="l-camp" name="utm_campaign" placeholder={brand.name.toLowerCase()} /></div>
            <div className="space-y-1.5"><Label htmlFor="l-content">utm_content</Label><Input id="l-content" name="utm_content" /></div>
          </div>
          {campaigns.length > 0 && (
            <div className="space-y-1.5"><Label>Campaign</Label>
              <Select name="campaign_id" defaultValue="none"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">None</SelectItem>{campaigns.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}</SelectContent></Select>
            </div>
          )}
          <Button type="submit" className="w-full" disabled={create.isPending}><Plus className="size-4" />Create link</Button>
        </form>
      )}
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
