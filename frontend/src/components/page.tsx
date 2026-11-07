import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** One header pattern for every page: title, optional description, actions on the right. */
export function PageHeader({ title, description, actions, className }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("mb-6 flex flex-wrap items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/** An empty screen is an invitation to act, never a blank chart. */
export function EmptyState({ icon: Icon, title, body, action, className }: {
  icon?: LucideIcon; title: string; body?: ReactNode; action?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center rounded-card border border-dashed border-line-strong px-6 py-10 text-center", className)}>
      {Icon && <Icon className="mb-3 size-6 text-ink-2" aria-hidden />}
      <h3 className="font-medium">{title}</h3>
      {body && <p className="mt-1 max-w-sm text-sm text-ink-2">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

const STATUS: Record<string, { label: string; cls: string }> = {
  draft: { label: "Draft", cls: "text-st-draft" },
  pending_approval: { label: "Awaiting approval", cls: "text-st-pending" },
  scheduled: { label: "Scheduled", cls: "text-st-scheduled" },
  publishing: { label: "Publishing", cls: "text-st-publishing" },
  published: { label: "Published", cls: "text-st-published" },
  failed: { label: "Failed", cls: "text-st-failed" },
};

/** Status always shows a dot and a word: colour alone is never the message. */
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const s = STATUS[status] ?? { label: status, cls: "text-ink-2" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", s.cls, className)}>
      <span className="status-dot" aria-hidden />{s.label}
    </span>
  );
}

export function statusColorVar(status: string) {
  return `var(--st-${status === "pending_approval" ? "pending" : status})`;
}
