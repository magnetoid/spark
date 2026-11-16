/**
 * The public connect page. A client opens a link the team sent and connects their own channels;
 * the network's own sign-in runs on Zernio's hosted flow and brings them back here.
 */
import { useEffect, type ReactNode } from "react";
import { useParams, useSearch } from "@tanstack/react-router";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useConnectPage } from "@/features/channels/connect-links";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { applyBrandColor } from "@/lib/brand-color";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { fmtDateTime } from "@/lib/time";

const STATE: Record<string, string> = { ok: "Connected", expiring: "Connected, renew soon", reconnect: "Needs reconnecting", paused: "Paused by the team" };

export function ConnectPage() {
  const { token } = useParams({ from: "/c/$token" });
  const search = useSearch({ strict: false }) as { connected?: string; error?: string };
  const { data, isPending, error } = useConnectPage(token);
  useEffect(() => { if (data?.brand.color) applyBrandColor(data.brand.color); }, [data?.brand.color]);

  if (isPending) return <Frame><Skeleton className="h-10 w-64" /><Skeleton className="mt-6 h-40" /></Frame>;
  if (error || !data) {
    const gone = error instanceof ApiError && error.status === 404;
    return (
      <Frame>
        <div className="rounded-card border border-line bg-surface p-6 text-center">
          <h1 className="display text-2xl font-semibold">{gone ? "This connect link no longer works" : "Could not load the page"}</h1>
          <p className="mt-2 text-sm text-ink-2">{gone ? "It may have expired or been revoked. Ask the team that sent it for a new one." : error?.message}</p>
        </div>
      </Frame>
    );
  }
  const needs = new Set(data.channels.filter((c) => c.health === "reconnect").map((c) => c.platform));
  return (
    <Frame>
      <header className="mb-6">
        <p className="text-sm text-ink-2">Connect your channels to</p>
        <h1 className="display text-3xl font-semibold leading-tight"><span className="mr-2 inline-block size-3 rounded-full bg-brand align-middle" aria-hidden />{data.brand.name}</h1>
        <p className="mt-2 text-sm text-ink-2">
          Pick a network and sign in on its own page. {data.brand.name}'s team can then post for you; they never see your password. On the way back you may see a short Zernio page: press Continue.
          {data.expires_at && ` This link works until ${fmtDateTime(data.expires_at, Intl.DateTimeFormat().resolvedOptions().timeZone)}.`}
        </p>
      </header>
      {search.connected && (
        <p role="status" className="mb-4 flex items-start gap-2 rounded-card border border-st-published/40 bg-surface p-4 text-sm"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-st-published" aria-hidden />Connected {search.connected}. Thank you. You can connect another one or close this page.</p>
      )}
      {search.error && (
        <p role="alert" className="mb-4 flex items-start gap-2 rounded-card border border-st-failed/40 bg-surface p-4 text-sm"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-st-failed" aria-hidden />{search.error}</p>
      )}
      <section aria-labelledby="nets-h">
        <h2 id="nets-h" className="mb-3 text-base font-semibold">Networks</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {data.platforms.map((p) => (
            <a key={p.platform} href={`/c/${encodeURIComponent(token)}/go/${p.platform}`} className="flex items-center justify-between rounded-card border border-line bg-surface px-4 py-3 text-sm hover:border-brand">
              <span className="flex items-center gap-2"><PlatformMark platform={p.platform} size={18} />{p.label}</span>
              <span className="text-xs text-ink-2">{needs.has(p.platform) ? "Reconnect" : "Connect"}</span>
            </a>
          ))}
        </div>
      </section>
      {data.channels.length > 0 && (
        <section aria-labelledby="chan-h" className="mt-8">
          <h2 id="chan-h" className="mb-3 text-base font-semibold">Already connected</h2>
          <ul className="divide-y divide-line rounded-card border border-line bg-surface text-sm">
            {data.channels.map((c) => (
              <li key={`${c.platform}-${c.handle}`} className="flex items-center gap-2 px-4 py-2.5">
                <PlatformMark platform={c.platform} size={16} /><span className="font-medium">@{c.handle}</span>
                <span className="text-ink-2">{platformLabel(c.platform)}</span>
                <span className={c.health === "reconnect" ? "ml-auto text-xs text-st-failed" : "ml-auto text-xs text-ink-2"}>{STATE[c.health] ?? c.health}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Frame>
  );
}

function Frame({ children }: { children: ReactNode }) {
  return <main className="min-h-dvh bg-paper px-4 py-10 text-ink"><div className="mx-auto w-full max-w-2xl">{children}</div></main>;
}
