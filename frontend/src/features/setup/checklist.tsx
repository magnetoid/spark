/** First-run checklist on Today, for owners: what this install still needs. Hidden once every
 * required step is done, or when the owner dismisses it. */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { CheckCircle2, Circle, X } from "lucide-react";
import { useSession } from "@/app/session";
import { Button } from "@/components/ui/button";
import { useUpdateMe } from "@/features/api4";
import { api, unwrap } from "@/lib/api";
import { cn } from "@/lib/utils";

export function SetupChecklist() {
  const { data: session } = useSession();
  const user = session?.user;
  const dismissed = Boolean((user?.prefs as Record<string, unknown> | undefined)?.onboarding_dismissed);
  const show = user?.role === "owner" && !dismissed;
  const { data } = useQuery({
    queryKey: ["setup-checklist"],
    queryFn: async () => unwrap(await api.GET("/setup/checklist")),
    enabled: show,
    staleTime: 60_000,
  });
  const update = useUpdateMe();
  const navigate = useNavigate();
  if (!show || !data || data.complete) return null;
  const open = (url: string) => (url.startsWith("http") ? window.open(url, "_blank", "noopener") : navigate({ href: url }));

  return (
    <section aria-labelledby="setup-h" className="rounded-card border border-line bg-surface p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 id="setup-h" className="text-base font-semibold">Finish setting up Spark</h2>
          <p className="text-sm text-ink-2 tnum">{data.done} of {data.total} done</p>
        </div>
        <Button variant="ghost" size="icon" className="size-8 text-ink-2" aria-label="Hide the setup list"
                onClick={() => update.mutate({ prefs: { onboarding_dismissed: true } })}><X className="size-4" /></Button>
      </div>
      <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-line" aria-hidden>
        <div className="h-full rounded-full bg-brand" style={{ width: `${Math.round((100 * data.done) / data.total)}%` }} />
      </div>
      <ul className="divide-y divide-line">
        {data.steps.map((s) => (
          <li key={s.key} className="flex items-start gap-3 py-2.5">
            {s.done ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-st-published" aria-label="Done" /> : <Circle className="mt-0.5 size-4 shrink-0 text-ink-2" aria-label="Not done" />}
            <div className="min-w-0 flex-1">
              <div className={cn("text-sm font-medium", s.done && "text-ink-2 line-through decoration-line")}>{s.title}{s.optional && !s.done && <span className="ml-2 font-normal text-ink-2">optional</span>}</div>
              {!s.done && <p className="text-xs text-ink-2">{s.detail}</p>}
            </div>
            {!s.done && <Button size="sm" variant="outline" className="shrink-0" onClick={() => open(s.action_url)}>{s.action_label}</Button>}
          </li>
        ))}
      </ul>
    </section>
  );
}
