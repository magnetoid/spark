/**
 * Connect links: an owner sends a client a link; the client connects their own channels through
 * Zernio without a Spark account. The full link is shown once, like review links.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Link2, X } from "lucide-react";
import type { components } from "@/api/schema";
import { useBrand } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";
import { PlatformMark } from "@/lib/platforms";
import { fmtDateTime } from "@/lib/time";

type S = components["schemas"];
export type ConnectLinkCreated = S["ConnectLinkCreated"];
const bp = (brand_id: number) => ({ params: { path: { brand_id } } });

export const useConnectLinks = (b: number) => useQuery({ queryKey: ["connect-links", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/connect-links", bp(b))) });
export const useCreateConnectLink = (b: number) => useAction(async (body: S["ConnectLinkIn"]) => unwrap(await api.POST("/brands/{brand_id}/connect-links", { ...bp(b), body })),
  [["connect-links", b], ["activity", b]]);
export const useRevokeConnectLink = (b: number) => useAction(async (link_id: number) =>
  unwrap(await api.DELETE("/brands/{brand_id}/connect-links/{link_id}", { params: { path: { brand_id: b, link_id } } })), [["connect-links", b], ["activity", b]], "Link revoked");
export const useConnectPage = (token: string) => useQuery({
  queryKey: ["connect-page", token],
  queryFn: async () => unwrap(await api.GET("/public/connect/{token}", { params: { path: { token } } })),
  retry: false,
});

const DAYS = [1, 3, 7, 14, 30];

/** Channels page, owners only: make and revoke links for clients. `networks` maps key → label. */
export function ClientConnectLinks({ networks }: { networks: Record<string, string> }) {
  const brand = useBrand();
  const { data: links = [] } = useConnectLinks(brand.id);
  const create = useCreateConnectLink(brand.id);
  const revoke = useRevokeConnectLink(brand.id);
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [days, setDays] = useState("7");
  const [created, setCreated] = useState<ConnectLinkCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const toggle = (k: string) => setPicked((v) => (v.includes(k) ? v.filter((x) => x !== k) : [...v, k]));
  const close = () => { setOpen(false); setCreated(null); setPicked([]); setCopied(false); };
  const label = (k: string) => networks[k] ?? k;
  return (
    <section aria-labelledby="ccl-h">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="ccl-h" className="font-semibold">Let a client connect</h2>
          <p className="text-sm text-ink-2">Send a link. The client signs in on the network's own page and the channel joins {brand.name}. No Spark account, and you never see a password.</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}><Link2 className="size-4" />New connect link</Button>
      </div>
      {links.length > 0 && (
        <ul className="divide-y divide-line rounded-card border border-line bg-surface text-sm">
          {links.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
              <span className="tnum font-medium">{l.prefix}…</span>
              <span className="text-ink-2">{l.platforms.length ? l.platforms.map(label).join(", ") : "Any network"}</span>
              {l.connected > 0 && <span className="text-ink-2">{l.connected} connected</span>}
              {l.expires_at && <span className="ml-auto text-xs text-ink-2">until {fmtDateTime(l.expires_at, brand.timezone)}</span>}
              <button type="button" aria-label={`Revoke link ${l.prefix}`} className="text-ink-2 hover:text-st-failed" onClick={() => revoke.mutate(l.id)}><X className="size-4" /></button>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={open} onOpenChange={(o) => !o && close()}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{created ? "Connect link ready" : "New connect link"}</DialogTitle></DialogHeader>
          {created ? (
            <div className="space-y-3 text-sm">
              <p className="text-ink-2">Anyone with this link can connect {created.platforms.length ? created.platforms.map(label).join(", ") : "channels"} to {brand.name}. It is shown only now; you'll get an email when a channel is connected.</p>
              <div className="flex items-center gap-2">
                <Input readOnly value={created.url} onFocus={(e) => e.currentTarget.select()} aria-label="Connect link" />
                <Button size="sm" onClick={() => { void navigator.clipboard.writeText(created.url); setCopied(true); }}>{copied ? <Check className="size-4" /> : <Copy className="size-4" />}{copied ? "Copied" : "Copy"}</Button>
              </div>
              <DialogFooter><Button onClick={close}>Done</Button></DialogFooter>
            </div>
          ) : (
            <form className="space-y-4 text-sm" onSubmit={(e) => { e.preventDefault(); create.mutate({ platforms: picked, days: Number(days) }, { onSuccess: (r) => setCreated(r) }); }}>
              <fieldset>
                <legend className="mb-2 font-medium">Networks <span className="font-normal text-ink-2">(none picked: any)</span></legend>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {Object.entries(networks).map(([key, name]) => (
                    <label key={key} htmlFor={`ccl-${key}`} className="flex items-center gap-2 rounded-control border border-line px-3 py-2 has-[:checked]:border-brand">
                      <input id={`ccl-${key}`} type="checkbox" className="accent-[var(--brand)]" checked={picked.includes(key)} onChange={() => toggle(key)} />
                      <PlatformMark platform={key} size={14} />{name}
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="max-w-48 space-y-1.5">
                <Label htmlFor="ccl-days">Works for</Label>
                <Select value={days} onValueChange={setDays}>
                  <SelectTrigger id="ccl-days"><SelectValue /></SelectTrigger>
                  <SelectContent>{DAYS.map((d) => <SelectItem key={d} value={String(d)}>{d === 1 ? "1 day" : `${d} days`}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <DialogFooter><Button type="button" variant="ghost" onClick={close}>Cancel</Button><Button type="submit" disabled={create.isPending}>{create.isPending ? "Making…" : "Make link"}</Button></DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
