/** Where a link's clicks came from (day, channel, post, referrer), its QR code, and a
 * campaign's results. Shared by the Links and Campaigns pages. */
import { useRef, useState } from "react";
import { QRCodeCanvas, QRCodeSVG } from "qrcode.react";
import { Download } from "lucide-react";
import { useBrand, usePerms } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { campaignCsvUrl, useCampaignSummary, useLinkStats, useUpdateLink, type CampaignFull, type LinkOut } from "@/features/api4";
import { PLATFORMS, PlatformMark, platformLabel } from "@/lib/platforms";
import { fmtDay, fromLocalInput, zonedDateKey } from "@/lib/time";
import { cn } from "@/lib/utils";

type Day = { day: string; clicks: number };
type Count = { key: string; clicks: number };

function ClickBars({ days }: { days: Day[] }) {
  const max = Math.max(1, ...days.map((d) => d.clicks));
  if (!days.length) return null;
  return (
    <figure>
      <div className="flex h-20 items-end gap-px" role="img" aria-label={`Clicks per day, highest ${max}`}>
        {days.map((d) => (
          <div key={d.day} title={`${fmtDay(d.day, { day: "numeric", month: "short" })}: ${d.clicks}`}
               className={cn("min-h-px flex-1 rounded-t-sm", d.clicks ? "bg-brand" : "bg-hover")}
               style={{ height: `${Math.max(2, (d.clicks / max) * 100)}%` }} />
        ))}
      </div>
      <figcaption className="mt-1 flex justify-between text-xs text-ink-2">
        <span>{fmtDay(days[0].day, { day: "numeric", month: "short" })}</span>
        <span>{fmtDay(days[days.length - 1].day, { day: "numeric", month: "short" })}</span>
      </figcaption>
    </figure>
  );
}

function Counts({ title, rows, total, platforms = false }: { title: string; rows: Count[]; total: number; platforms?: boolean }) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      {!rows.length ? <p className="text-sm text-ink-2">No clicks yet.</p> : (
        <ul className="space-y-1.5 text-sm">
          {rows.slice(0, 8).map((r) => (
            <li key={r.key} className="flex items-center gap-2">
              {platforms && r.key in PLATFORMS && <PlatformMark platform={r.key} size={14} />}
              <span className="min-w-0 flex-1 truncate">{platforms && r.key in PLATFORMS ? platformLabel(r.key) : r.key}</span>
              <span className="tnum font-medium">{r.clicks}</span>
              <span className="w-10 text-right text-xs text-ink-2 tnum">{Math.round((r.clicks / Math.max(1, total)) * 100)}%</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function QrBlock({ link }: { link: LinkOut }) {
  const big = useRef<HTMLCanvasElement>(null);
  const download = () => {
    const url = big.current?.toDataURL("image/png");
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `qr-${link.code}.png`;
    a.click();
  };
  return (
    <div className="flex items-center gap-4">
      <div className="rounded-control border border-line bg-white p-2"><QRCodeSVG value={link.short_url} size={96} marginSize={0} title={`QR code for ${link.short_url}`} /></div>
      <div className="space-y-2 text-sm text-ink-2">
        <p>Scans count as clicks, so print and posters show up here too.</p>
        <Button type="button" variant="outline" size="sm" onClick={download}><Download className="size-4" />Download QR code</Button>
      </div>
      <QRCodeCanvas ref={big} value={link.short_url} size={1024} marginSize={4} className="hidden" aria-hidden />
    </div>
  );
}

function ExpiryForm({ link }: { link: LinkOut }) {
  const brand = useBrand();
  const update = useUpdateLink(brand.id);
  const [day, setDay] = useState(link.expires_at ? zonedDateKey(link.expires_at, brand.timezone) : "");
  const save = (value: string) => update.mutate({ id: link.id, body: { expires_at: value ? fromLocalInput(`${value}T23:59`, brand.timezone) : null } });
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); save(day); }}>
      <div className="space-y-1.5"><Label htmlFor={`exp-${link.id}`}>Stops working after</Label><Input id={`exp-${link.id}`} type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-44" /></div>
      <Button type="submit" size="sm" variant="outline" disabled={update.isPending}>Save</Button>
      {link.expires_at && <Button type="button" size="sm" variant="ghost" onClick={() => { setDay(""); save(""); }}>Never expire</Button>}
    </form>
  );
}

export function LinkDetails({ link, onClose }: { link: LinkOut | null; onClose: () => void }) {
  const brand = useBrand();
  const { canEdit } = usePerms();
  const [days, setDays] = useState(30);
  const { data, isPending } = useLinkStats(brand.id, link?.id ?? null, days);
  return (
    <Dialog open={link !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        {link && (
          <>
            <DialogHeader>
              <DialogTitle>{link.title || link.short_url.replace(/^https?:\/\//, "")}</DialogTitle>
              <DialogDescription className="break-all">{link.destination}</DialogDescription>
            </DialogHeader>
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-sm"><span className="text-2xl font-semibold tnum">{data?.total ?? "–"}</span> <span className="text-ink-2">clicks in the last {days} days · {link.clicks} all time</span></p>
              <div role="group" aria-label="Period" className="flex gap-1">
                {[30, 90].map((d) => <Button key={d} type="button" size="sm" variant={d === days ? "secondary" : "ghost"} aria-pressed={d === days} onClick={() => setDays(d)}>{d} days</Button>)}
              </div>
            </div>
            {isPending || !data ? <Skeleton className="h-40" /> : (
              <div className="space-y-5">
                <ClickBars days={data.by_day} />
                <div className="grid gap-5 sm:grid-cols-2">
                  <Counts title="By channel" rows={data.by_platform} total={data.total} platforms />
                  <Counts title="By referrer" rows={data.by_referrer} total={data.total} />
                </div>
                {data.by_post.length > 0 && (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold">By post</h3>
                    <ul className="space-y-1.5 text-sm">
                      {data.by_post.map((p) => <li key={p.post_id} className="flex gap-2"><span className="min-w-0 flex-1 truncate" title={p.excerpt}>{p.excerpt || `Post ${p.post_id}`}</span><span className="tnum font-medium">{p.clicks}</span></li>)}
                    </ul>
                  </section>
                )}
              </div>
            )}
            <div className="space-y-4 border-t border-line pt-4">
              <QrBlock link={link} />
              {canEdit && <ExpiryForm key={link.expires_at ?? "none"} link={link} />}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function CampaignResults({ campaign, onClose }: { campaign: CampaignFull | null; onClose: () => void }) {
  const brand = useBrand();
  const { data, isPending } = useCampaignSummary(brand.id, campaign?.id ?? null);
  return (
    <Dialog open={campaign !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        {campaign && (
          <>
            <DialogHeader>
              <DialogTitle>{campaign.name}: results</DialogTitle>
              <DialogDescription>All time, from the campaign's published posts and its links.</DialogDescription>
            </DialogHeader>
            {isPending || !data ? <Skeleton className="h-48" /> : (
              <div className="space-y-5">
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    ["Posts published", `${data.published} of ${data.posts}`],
                    ["Seen", data.seen.toLocaleString()],
                    ["Engagement rate", data.engagement_rate_pct == null ? "–" : `${data.engagement_rate_pct}%`],
                    ["Link clicks", data.link_clicks.toLocaleString()],
                  ].map(([k, v]) => <div key={k} className="rounded-control border border-line p-3"><dt className="text-xs text-ink-2">{k}</dt><dd className="mt-0.5 text-lg font-semibold tnum">{v}</dd></div>)}
                </dl>
                <ClickBars days={data.by_day} />
                <div className="grid gap-5 sm:grid-cols-2">
                  <Counts title="Clicks by channel" rows={data.by_platform} total={data.link_clicks} platforms />
                  <section>
                    <h3 className="mb-2 text-sm font-semibold">Links</h3>
                    {!data.links.length ? <p className="text-sm text-ink-2">No links in this campaign yet. Pick the campaign when you create a short link, or turn on link shortening for the brand.</p> : (
                      <ul className="space-y-1.5 text-sm">
                        {data.links.slice(0, 8).map((l) => <li key={l.id} className="flex gap-2"><span className="min-w-0 flex-1 truncate" title={l.destination}>{l.title || l.short_url.replace(/^https?:\/\//, "")}</span><span className="tnum font-medium">{l.clicks}</span></li>)}
                      </ul>
                    )}
                  </section>
                </div>
                <Button asChild size="sm" variant="outline"><a href={campaignCsvUrl(brand.id, campaign.id)}><Download className="size-4" />Download CSV</a></Button>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
