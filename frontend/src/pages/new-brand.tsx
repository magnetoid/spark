/** Create a brand: the first thing a new workspace needs, and one more for agencies. */
import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { sessionQuery, useSession } from "@/app/session";
import { AuthFrame } from "@/pages/login";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, unwrap } from "@/lib/api";

const TIMEZONES: string[] = (() => { try { return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf("timeZone"); } catch { return ["UTC"]; } })();
const GUESS_TZ = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return "UTC"; } })();

export function NewBrandPage() {
  const { data: session } = useSession();
  const first = (session?.brands.length ?? 0) === 0;
  const form = <BrandForm />;
  if (first) return <AuthFrame title="Create your first brand">{form}</AuthFrame>;
  return <><PageHeader title="New brand" description="Each brand has its own channels, queue, voice and colour." /><div className="max-w-lg rounded-card border border-line bg-surface p-5">{form}</div></>;
}

function BrandForm() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [color, setColor] = useState("#F2A516");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    try {
      const b = unwrap(await api.POST("/brands", { body: { name: String(fd.get("name")), website: String(fd.get("website")) || null, timezone: String(fd.get("timezone")), color } }));
      await qc.invalidateQueries({ queryKey: sessionQuery.queryKey });
      toast.success(`Brand “${b.name}” created. Connect a channel next.`);
      void navigate({ to: "/channels", search: { brand: b.slug } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not create the brand");
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-1.5"><Label htmlFor="nb-name">Name</Label><Input id="nb-name" name="name" required autoFocus placeholder="Acme Studio" /></div>
      <div className="space-y-1.5"><Label htmlFor="nb-web">Website</Label><Input id="nb-web" name="website" type="url" placeholder="https://" /></div>
      <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
        <div className="space-y-1.5"><Label>Timezone</Label><Select name="timezone" defaultValue={TIMEZONES.includes(GUESS_TZ) ? GUESS_TZ : "UTC"}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent className="max-h-72">{TIMEZONES.map((tz) => <SelectItem key={tz} value={tz}>{tz}</SelectItem>)}</SelectContent></Select></div>
        <div className="space-y-1.5"><Label htmlFor="nb-color">Colour</Label><input id="nb-color" type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-9 w-14 rounded-control border border-line bg-surface p-1" /></div>
      </div>
      <p className="text-xs text-ink-2">Posting slots start at 09:00, 12:30 and 17:00 on weekdays; change them under Settings.</p>
      <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating…" : "Create brand"}</Button>
    </form>
  );
}
