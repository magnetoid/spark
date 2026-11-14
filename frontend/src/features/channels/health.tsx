/** Channel health on the Channels page: a badge when a channel needs attention, the reconnect
 * link, and the settings publishing reads (board, subreddit, who can see posts). */
import { useState, type FormEvent } from "react";
import { AlertTriangle, Clock, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useChannelSettings, useSaveChannelSettings } from "@/features/api4";
import type { AccountOut } from "@/features/posts/api";
import { fmtDateTime } from "@/lib/time";
import { platformLabel } from "@/lib/platforms";
import { cn } from "@/lib/utils";

/** Networks with settings publishing reads; matches the server's list. */
export const PLATFORMS_WITH_SETTINGS = new Set(["tiktok", "youtube", "pinterest", "reddit"]);

export function reconnectHref(a: AccountOut, brandId: number) {
  return a.provider === "zernio" ? `/accounts/zernio/connect/${a.platform}?brand=${brandId}` : `/accounts/connect/${a.platform}?brand=${brandId}`;
}

export function HealthBadge({ account, timezone, className }: { account: AccountOut; timezone: string; className?: string }) {
  if (account.health === "reconnect") {
    return <span className={cn("inline-flex items-center gap-1 rounded-full border border-st-failed/40 bg-st-failed/5 px-2 py-0.5 text-xs font-medium text-st-failed", className)}><AlertTriangle className="size-3" />Needs reconnecting</span>;
  }
  if (account.health === "expiring") {
    return (
      <span className={cn("inline-flex items-center gap-1 rounded-full border border-st-pending/40 bg-st-pending/5 px-2 py-0.5 text-xs font-medium text-st-pending", className)}>
        <Clock className="size-3" />{account.expires_at ? `Access ends ${fmtDateTime(account.expires_at, timezone)}` : "Access ends soon"}
      </span>
    );
  }
  return null;
}

export function ChannelSettingsDialog({ account, brandId, onClose }: { account: AccountOut | null; brandId: number; onClose: () => void }) {
  const { data, isPending } = useChannelSettings(brandId, account?.id ?? null);
  const save = useSaveChannelSettings(brandId);
  // what the person changed, laid over what is saved (the dialog remounts per channel)
  const [edits, setValues] = useState<Record<string, string>>({});
  const values: Record<string, string> = { ...(data?.values ?? {}), ...edits };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!account || !data) return;
    const settings = Object.fromEntries(data.fields.map((f) => [f.key, values[f.key]?.trim() ? values[f.key].trim() : null]));
    save.mutate({ id: account.id, settings }, { onSuccess: onClose });
  };

  return (
    <Dialog open={account !== null} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>{account ? `${platformLabel(account.platform)} settings for @${account.handle.replace(/^@/, "")}` : "Channel settings"}</DialogTitle></DialogHeader>
        {isPending || !data ? <div className="grid h-24 place-items-center"><Loader2 className="size-5 animate-spin text-ink-2" /></div> : (
          <form id="channel-settings" onSubmit={submit} className="space-y-4">
            {data.fields.map((f) => (
              <div key={f.key} className="space-y-1.5">
                <Label htmlFor={`cs-${f.key}`}>{f.label}</Label>
                {f.kind === "choice" && f.options.length > 0 ? (
                  <Select value={values[f.key] ?? f.default ?? ""} onValueChange={(v) => setValues((s) => ({ ...s, [f.key]: v }))}>
                    <SelectTrigger id={`cs-${f.key}`} className="w-full"><SelectValue placeholder="Choose…" /></SelectTrigger>
                    <SelectContent>{f.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                  </Select>
                ) : (
                  <Input id={`cs-${f.key}`} value={values[f.key] ?? ""} placeholder={f.key === "board_id" ? "Board ID" : f.default ?? ""} onChange={(e) => setValues((s) => ({ ...s, [f.key]: e.target.value }))} />
                )}
                {f.help && <p className="text-xs text-ink-2">{f.help}</p>}
                {f.key === "board_id" && f.options.length === 0 && <p className="text-xs text-ink-2">Spark could not read the boards from Zernio. Paste the board ID instead.</p>}
              </div>
            ))}
          </form>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="channel-settings" disabled={save.isPending || !data}>{save.isPending && <Loader2 className="size-4 animate-spin" />}Save settings</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
