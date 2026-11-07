/**
 * Live updates: an EventSource on /api/v1/events. The server only says what kind of thing
 * changed; the browser refetches the queries that could show it. Polling and refetch-on-focus
 * stay, so a dropped stream never loses data.
 */
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

const KINDS: Record<string, string[][]> = {
  posts: [["posts"], ["post"], ["queue"], ["today"], ["campaigns"], ["ideas"]],
  accounts: [["accounts"], ["queue"], ["session"], ["platforms"]],
  inbox: [["inbox"], ["comments"]],
};

export function useLiveUpdates(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const es = new EventSource("/api/v1/events", { withCredentials: true });
    let timer: number | null = null;
    const pending = new Set<string>();
    const flush = () => {
      timer = null;
      for (const kind of pending) for (const key of KINDS[kind] ?? []) void qc.invalidateQueries({ queryKey: key });
      pending.clear();
    };
    es.addEventListener("update", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data) as { kind: string };
        pending.add(data.kind);
        if (timer === null) timer = window.setTimeout(flush, 400); // coalesce bursts
      } catch { /* malformed: ignore */ }
    });
    return () => { es.close(); if (timer !== null) window.clearTimeout(timer); };
  }, [enabled, qc]);
}
