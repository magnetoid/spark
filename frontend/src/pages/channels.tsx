/** Channels: connected accounts, and the ways to connect more. */
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { Pause, Play, Plug, Trash2 } from "lucide-react";
import { useBrand, useSession } from "@/app/session";
import { EmptyState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useConnectCredentials, usePlatforms, useRemoveAccount, useToggleAccount, useZernioImport, type PlatformsOut } from "@/features/api4";
import { useAccounts } from "@/features/posts/api";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { cn } from "@/lib/utils";

export function ChannelsPage() {
  const brand = useBrand();
  const { data: accounts = [], isPending } = useAccounts(brand.id);
  const { data: platforms } = usePlatforms(brand.id);
  const toggle = useToggleAccount(brand.id);
  const remove = useRemoveAccount(brand.id);
  const zernioImport = useZernioImport(brand.id);
  const { data: session } = useSession();
  const canEdit = session?.user?.role !== "viewer";
  const isOwner = session?.user?.role === "owner";
  const [credFor, setCredFor] = useState<PlatformsOut["direct"][number] | null>(null);
  const search = useSearch({ strict: false }) as { notice?: string; kind?: string };
  const navigate = useNavigate();
  useEffect(() => {
    if (!search.notice) return;
    (search.kind === "error" ? toast.error : toast.success)(search.notice);
    void navigate({ to: ".", search: (p: Record<string, unknown>) => { const rest = { ...p }; delete rest.notice; delete rest.kind; return rest; }, replace: true });
  }, [search.notice, search.kind, navigate]);

  return (
    <>
      <PageHeader title="Channels" description={`Social accounts ${brand.name} publishes to.`} />
      <section className="mb-8 overflow-hidden rounded-card border border-line bg-surface">
        {isPending ? <Skeleton className="h-32" /> : accounts.length === 0 ? (
          <EmptyState icon={Plug} title="No channels yet" body="Connect one below. Through Zernio you get 14 networks with one key." className="border-0" />
        ) : (
          <ul className="divide-y divide-line">
            {accounts.map((a) => (
              <li key={a.id} className={cn("flex items-center gap-3 px-4 py-3 text-sm", !a.is_active && "opacity-70")}>
                {a.avatar_url ? <img src={a.avatar_url} alt="" className="size-8 rounded-full object-cover" /> : <span className="grid size-8 place-items-center rounded-full border border-line"><PlatformMark platform={a.platform} size={16} /></span>}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 font-medium"><PlatformMark platform={a.platform} size={12} />{a.display_name || a.handle}<span className="font-normal text-ink-2">@{a.handle.replace(/^@/, "")}</span></div>
                  <div className="text-xs text-ink-2">{platformLabel(a.platform)} · {a.provider === "zernio" ? "via Zernio" : "direct"}{a.followers != null && ` · ${a.followers.toLocaleString()} followers`}{!a.is_active && " · paused"}</div>
                  {a.last_error && <div className="mt-0.5 text-xs text-st-failed">{a.last_error}</div>}
                </div>
                {canEdit && (
                  <div className="flex items-center gap-1">
                    {a.provider === "zernio" && a.last_error && <Button asChild size="sm" variant="outline"><a href={`/accounts/zernio/connect/${a.platform}?brand=${brand.id}`}>Reconnect</a></Button>}
                    <Button variant="ghost" size="sm" onClick={() => toggle.mutate(a.id)}>{a.is_active ? <><Pause className="size-4" />Pause</> : <><Play className="size-4" />Resume</>}</Button>
                    <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label={`Remove ${a.handle}`}
                            onClick={() => { if (!confirm(`Remove ${a.handle} from ${brand.name}? Scheduled posts to it are dropped.`)) return;
                              const disconnect = a.provider === "zernio" && confirm("Also disconnect it in Zernio? Cancel keeps it connected there."); remove.mutate({ id: a.id, disconnect }); }}><Trash2 className="size-4" /></Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {canEdit && platforms && (
        <div className="space-y-8">
          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div><h2 className="font-semibold">Connect through Zernio</h2><p className="text-sm text-ink-2">One API key, Zernio hosts the platform apps.</p></div>
              {platforms.zernio_ready ? <Button variant="outline" size="sm" onClick={() => zernioImport.mutate()} disabled={zernioImport.isPending}>Import from Zernio</Button>
                : isOwner ? <Button asChild size="sm"><Link to="/settings" search={(p) => ({ ...p, tab: "connectors", connector: "zernio" })}>Set up Zernio</Link></Button>
                : <span className="text-xs text-ink-2">An owner adds the key under Settings → Connectors.</span>}
            </div>
            {platforms.zernio_ready && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {Object.entries(platforms.zernio).map(([key, label]) => (
                  <a key={key} href={`/accounts/zernio/connect/${key}?brand=${brand.id}`} className="flex items-center justify-between rounded-card border border-line bg-surface px-3 py-2.5 text-sm hover:border-brand"><span className="flex items-center gap-2"><PlatformMark platform={key} size={16} />{label}</span><span className="text-xs text-ink-2">Connect</span></a>
                ))}
              </div>
            )}
          </section>
          <section>
            <h2 className="font-semibold">Connect directly</h2>
            <p className="mb-3 text-sm text-ink-2">With your own developer app per network. Bluesky, Mastodon and Telegram need only credentials.{platforms.force_dry_run && " This server is in dry-run mode: every network connects as a test channel."}</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {platforms.direct.map((p) => (
                p.connect_mode === "credentials" || platforms.force_dry_run
                  ? <button key={p.name} type="button" onClick={() => setCredFor(p)} className="flex items-center justify-between rounded-card border border-line bg-surface px-3 py-2.5 text-left text-sm hover:border-brand"><span className="flex items-center gap-2"><PlatformMark platform={p.name} size={16} />{p.label}</span><span className="text-xs text-ink-2">Connect</span></button>
                  : <a key={p.name} href={p.configured ? `/accounts/connect/${p.name}?brand=${brand.id}` : undefined} aria-disabled={!p.configured} title={p.configured ? undefined : "Developer app not configured on this server"}
                       className={cn("flex items-center justify-between rounded-card border border-line bg-surface px-3 py-2.5 text-sm", p.configured ? "hover:border-brand" : "opacity-50")}><span className="flex items-center gap-2"><PlatformMark platform={p.name} size={16} />{p.label}</span><span className="text-xs text-ink-2">{p.configured ? "Connect" : "Not set up"}</span></a>
              ))}
            </div>
          </section>
        </div>
      )}
      <CredentialsDialog platform={credFor} onClose={() => setCredFor(null)} />
    </>
  );
}

function CredentialsDialog({ platform, onClose }: { platform: PlatformsOut["direct"][number] | null; onClose: () => void }) {
  const brand = useBrand();
  const connect = useConnectCredentials(brand.id);
  const fields = platform?.credential_fields.length ? platform.credential_fields : [{ name: "handle", label: "Handle to display" }];
  return (
    <Dialog open={platform !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Connect {platform?.label}</DialogTitle></DialogHeader>
        <form key={platform?.name} className="space-y-4" onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget);
          connect.mutate({ platform: platform!.name, data: Object.fromEntries([...fd.entries()].map(([k, v]) => [k, String(v)])) }, { onSuccess: onClose }); }}>
          {fields.map((f) => <div key={f.name} className="space-y-1.5"><Label htmlFor={`cf-${f.name}`}>{f.label}</Label><Input id={`cf-${f.name}`} name={f.name} required type={/password|token|secret/i.test(f.name) ? "password" : "text"} autoComplete="off" /></div>)}
          {platform?.docs_url && <p className="text-xs text-ink-2"><a href={platform.docs_url} target="_blank" rel="noopener" className="underline">Where to find these</a></p>}
          <DialogFooter><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={connect.isPending}>{connect.isPending ? "Connecting…" : "Save and connect"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
