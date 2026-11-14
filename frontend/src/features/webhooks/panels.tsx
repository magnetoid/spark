/** Settings → Webhooks: addresses Spark calls when something happens, with the delivery log. */
import { useState, type FormEvent } from "react";
import { ChevronDown, Copy, Pencil, Send, Trash2, Webhook } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  useCreateWebhook, useDeleteWebhook, useTestWebhook, useUpdateWebhook, useWebhookDeliveries, useWebhooks, type WebhookOut,
} from "@/features/api4";
import { fmtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";
import { secretAfterDelete, type FreshSecret } from "./secret";

const ALL_BRANDS = "all";
const copy = (t: string) => { void navigator.clipboard.writeText(t); toast.success("Copied"); };

const VERIFY = `import hashlib, hmac, time

def is_from_spark(secret: str, header: str, raw_body: bytes) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    if abs(time.time() - int(parts["t"])) > 300:   # older than 5 minutes: refuse
        return False
    signed = parts["t"].encode() + b"." + raw_body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])`;

export function WebhooksSection() {
  const { brands, brand } = useWorkspace();
  const tz = brand?.timezone ?? "UTC";
  const { data, isPending } = useWebhooks();
  const create = useCreateWebhook();
  const update = useUpdateWebhook();
  const remove = useDeleteWebhook();
  const test = useTestWebhook();
  const [editing, setEditing] = useState<WebhookOut | "new" | null>(null);
  const [fresh, setFresh] = useState<FreshSecret | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const items = data?.items ?? [];
  const events = data?.events ?? [];
  const brandName = (id: number | null) => id === null ? "All brands" : brands.find((b) => b.id === id)?.name ?? "A brand you cannot see";

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const scope = String(fd.get("brand_id") ?? ALL_BRANDS);
    const body = {
      url: String(fd.get("url")).trim(),
      description: String(fd.get("description") ?? "").trim(),
      brand_id: scope === ALL_BRANDS ? null : Number(scope),
      events: events.map((ev) => ev.name).filter((name) => fd.get(`ev-${name}`) === "on"),
    };
    if (editing === "new") create.mutate(body, { onSuccess: (r) => { setFresh({ id: r.id, url: r.url, secret: r.secret }); setEditing(null); } });
    else if (editing) update.mutate({ id: editing.id, body }, { onSuccess: () => setEditing(null) });
  };
  const sendTest = (w: WebhookOut) => test.mutate(w.id, {
    onSuccess: (r) => { setOpen(w.id); if (r.status !== "delivered") toast.error(`Test not delivered: ${r.error ?? "no answer"}`); },
  });

  return (
    <div className="grid gap-8 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <section className="rounded-card border border-line bg-surface">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
            <div><h3 className="font-semibold">Webhooks</h3><p className="text-xs text-ink-2">Spark sends a signed POST request to your address when a post goes out, fails or needs approval, and when something new lands in the inbox.</p></div>
            <Button size="sm" onClick={() => setEditing("new")}>Add webhook</Button>
          </header>
          {fresh && (
            <div className="m-5 space-y-2 rounded-card border border-st-published/40 bg-brand-soft/50 p-3 text-sm">
              <p className="font-medium">Copy the signing secret for {fresh.url} now. It won't be shown again.</p>
              <div className="flex gap-2"><Input readOnly value={fresh.secret} className="font-mono text-xs" onClick={(e) => e.currentTarget.select()} /><Button size="sm" onClick={() => copy(fresh.secret)}><Copy className="size-4" />Copy</Button></div>
              <p className="text-xs text-ink-2">Your server uses it to check that a request really comes from this Spark.</p>
            </div>
          )}
          {isPending ? <div className="p-5"><Skeleton className="h-20" /></div> : items.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-5 py-10 text-center text-sm text-ink-2">
              <Webhook className="size-6" />
              <p className="max-w-sm">No webhooks yet. Add the address of your automation (n8n, Make, Zapier, your own server) and pick what it should hear about.</p>
              <Button size="sm" variant="outline" onClick={() => setEditing("new")}>Add webhook</Button>
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {items.map((w) => (
                <li key={w.id} className="px-5 py-4 text-sm">
                  <div className="flex flex-wrap items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="break-all font-mono text-xs font-medium text-ink">{w.url}</div>
                      <div className="mt-1 text-xs text-ink-2">{w.description && <>{w.description}, </>}{brandName(w.brand_id)}, {w.events.length === 0 ? "every event" : w.events.join(", ")}</div>
                      <div className={cn("mt-1 flex items-center gap-1.5 text-xs font-medium", !w.enabled || w.last_error ? "text-st-failed" : w.last_delivery_at ? "text-st-published" : "text-ink-2")}>
                        <span className="status-dot" />
                        {!w.enabled ? (w.disabled_reason ? `Switched off: ${w.disabled_reason}` : "Paused")
                          : w.last_error ? `Last try failed: ${w.last_error}`
                          : w.last_delivery_at ? `Delivered ${fmtDateTime(w.last_delivery_at, tz)}${w.last_status ? `, answered ${w.last_status}` : ""}`
                          : "Nothing sent yet"}
                      </div>
                    </div>
                    <label className="flex items-center gap-2 text-xs text-ink-2"><Switch checked={w.enabled} onCheckedChange={(v) => update.mutate({ id: w.id, body: { enabled: v } })} aria-label={`Send events to ${w.url}`} />{w.enabled ? "On" : "Off"}</label>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1">
                    <Button size="sm" variant="outline" onClick={() => sendTest(w)} disabled={test.isPending}><Send className="size-4" />Send test</Button>
                    <Button size="sm" variant="ghost" onClick={() => setOpen(open === w.id ? null : w.id)} aria-expanded={open === w.id}><ChevronDown className={cn("size-4 transition-transform", open === w.id && "rotate-180")} />Recent deliveries</Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(w)}><Pencil className="size-4" />Edit</Button>
                    <Button size="sm" variant="ghost" onClick={() => confirm(`Delete the webhook to ${w.url}? Its delivery log goes with it.`) && remove.mutate(w.id, { onSuccess: () => setFresh((f) => secretAfterDelete(f, w.id)) })}><Trash2 className="size-4" />Delete</Button>
                  </div>
                  {open === w.id && <Deliveries id={w.id} tz={tz} />}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <aside className="space-y-3 self-start rounded-card border border-line bg-surface p-4 text-sm text-ink-2 lg:col-span-1">
        <h3 className="font-semibold text-ink">How deliveries work</h3>
        <p>Answer with any 2xx status within 10 seconds. Anything else is tried again after 1 minute, 5 minutes, 30 minutes, 2 hours and 6 hours.</p>
        <p>After 20 failed tries in a row Spark switches the webhook off. Switch it back on here once your address works.</p>
        <p>A delivery can arrive more than once. The <code>X-Spark-Delivery</code> header stays the same on every retry, so use it to skip repeats.</p>
        <h3 className="pt-1 font-semibold text-ink">Check the signature</h3>
        <p><code>X-Spark-Signature</code> is <code>t=&lt;time&gt;,v1=&lt;hex&gt;</code>: HMAC-SHA256 of <code>&lt;time&gt;.&lt;raw body&gt;</code> with the signing secret.</p>
        <pre className="overflow-x-auto rounded-control bg-paper p-2 text-[11px] leading-relaxed text-ink">{VERIFY}</pre>
        <Button size="sm" variant="outline" onClick={() => copy(VERIFY)}><Copy className="size-4" />Copy example</Button>
      </aside>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing === "new" ? "Add webhook" : "Edit webhook"}</DialogTitle></DialogHeader>
          {editing !== null && (
            <form onSubmit={submit} className="space-y-4" key={editing === "new" ? "new" : editing.id}>
              <div className="space-y-1.5"><Label htmlFor="wh-url">Address</Label><Input id="wh-url" name="url" type="url" required maxLength={2000} placeholder="https://example.com/hooks/spark" defaultValue={editing === "new" ? "" : editing.url} className="font-mono text-xs" /><p className="text-xs text-ink-2">A public http(s) address. Redirects are not followed.</p></div>
              <div className="space-y-1.5"><Label htmlFor="wh-desc">Note</Label><Input id="wh-desc" name="description" maxLength={200} placeholder="What listens here, e.g. n8n approvals flow" defaultValue={editing === "new" ? "" : editing.description} /></div>
              <div className="space-y-1.5"><Label htmlFor="wh-brand">Brand</Label>
                <Select name="brand_id" defaultValue={editing === "new" || editing.brand_id === null ? ALL_BRANDS : String(editing.brand_id)}>
                  <SelectTrigger id="wh-brand"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value={ALL_BRANDS}>All brands</SelectItem>{brands.map((b) => <SelectItem key={b.id} value={String(b.id)}>{b.name}</SelectItem>)}</SelectContent>
                </Select></div>
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">Events</legend>
                <p className="text-xs text-ink-2">Leave all unticked to receive every event, including ones Spark adds later.</p>
                {events.map((ev) => (
                  <label key={ev.name} className="flex items-start gap-2 text-sm">
                    <input type="checkbox" name={`ev-${ev.name}`} defaultChecked={editing !== "new" && editing.events.includes(ev.name)} className="mt-1 accent-[var(--brand)]" />
                    <span><code className="text-xs">{ev.name}</code><span className="block text-xs text-ink-2">{ev.description}</span></span>
                  </label>
                ))}
              </fieldset>
              <DialogFooter><Button type="button" variant="outline" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" disabled={create.isPending || update.isPending}>{editing === "new" ? "Add webhook" : "Save webhook"}</Button></DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

const STATUS: Record<string, [string, string]> = { delivered: ["Delivered", "text-st-published"], failed: ["Failed", "text-st-failed"], pending: ["Waiting", "text-st-scheduled"] };

function Deliveries({ id, tz }: { id: number; tz: string }) {
  const { data, isPending } = useWebhookDeliveries(id);
  if (isPending) return <Skeleton className="mt-3 h-16" />;
  const rows = data?.items ?? [];
  if (rows.length === 0) return <p className="mt-3 text-xs text-ink-2">Nothing sent here yet. Send a test to see what a delivery looks like.</p>;
  return (
    <ul className="mt-3 divide-y divide-line rounded-control border border-line text-xs">
      {rows.map((d) => {
        const [label, tone] = STATUS[d.status] ?? [d.status, "text-ink-2"];
        return (
          <li key={d.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-2">
            <span className={cn("w-16 font-medium", tone)}>{label}</span>
            <code className="text-ink">{d.event}</code>
            <span className="text-ink-2">{d.created_at ? fmtDateTime(d.created_at, tz) : ""}</span>
            <span className="text-ink-2">{d.attempts} {d.attempts === 1 ? "try" : "tries"}{d.response_status ? `, answered ${d.response_status}` : ""}</span>
            {d.status === "pending" && d.next_attempt_at && d.attempts > 0 && <span className="text-ink-2">next try {fmtDateTime(d.next_attempt_at, tz)}</span>}
            {d.error && d.status !== "delivered" && <span className="basis-full break-words text-st-failed">{d.error}</span>}
          </li>
        );
      })}
    </ul>
  );
}
