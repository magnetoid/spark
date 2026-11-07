/** The agent (phase 7): Janus runs, their proposals, the plan tray, the Janus connector status. */
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";

type S = components["schemas"];
export type AgentRunOut = S["AgentRunOut"];
export type AgentStatusOut = S["AgentStatusOut"];
export type RunKind = S["AgentRunIn"]["kind"];
export type PlanOut = S["PlanOut"];
export type ProposalPost = { content: string; link?: string | null; channels: string[]; channel_ids: number[]; when: string | null; pillar?: string | null; pillar_id?: number | null };
export type VoiceProfile = { tone: string; audience: string; rules: string; examples: string; summary: string };

const bp = (brand_id: number) => ({ params: { path: { brand_id } } });
const rp = (brand_id: number, run_id: number) => ({ params: { path: { brand_id, run_id } } });

export const useAgentStatus = (b: number, enabled = true) => useQuery({
  queryKey: ["agent-status", b],
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/agent/status", bp(b))),
  enabled, staleTime: 60_000,
});
export const useAgentRuns = (b: number) => useQuery({ queryKey: ["agent-runs", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/agent/runs", bp(b))) });
export const useAgentRun = (b: number, id: number | null) => useQuery({
  queryKey: ["agent-run", b, id],
  enabled: id != null,
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/agent/runs/{run_id}", rp(b, id!))),
  refetchInterval: (q) => (q.state.data && ["queued", "running", "waiting_approval"].includes(q.state.data.status) ? 2000 : false),
});
export const useStartRun = (b: number) => useAction(async (body: S["AgentRunIn"]) => unwrap(await api.POST("/brands/{brand_id}/agent/runs", { ...bp(b), body })),
  [["agent-runs", b], ["activity", b]]);
export const useStopRun = (b: number) => useAction(async (id: number) => unwrap(await api.POST("/brands/{brand_id}/agent/runs/{run_id}/stop", rp(b, id))), [["agent-runs", b]], "Stopping the run");
export const useApplyRun = (b: number) => useAction(async ({ id, body }: { id: number; body: S["AgentApplyIn"] }) =>
  unwrap(await api.POST("/brands/{brand_id}/agent/runs/{run_id}/apply", { ...rp(b, id), body })),
  [["agent-runs", b], ["agent-run", b], ["posts", b], ["queue", b], ["today", b], ["plan", b], ["activity", b], ["session"]],
  (r) => r.voice_applied ? "Brand voice updated" : `${r.created} ${r.created === 1 ? "draft" : "drafts"} added to the plan`);
export const usePlan = (b: number) => useQuery({ queryKey: ["plan", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/agent/plan", bp(b))) });
export const useSchedulePlan = (b: number) => useAction(async (post_ids: number[] | null) => unwrap(await api.POST("/brands/{brand_id}/agent/plan/schedule", { ...bp(b), body: { post_ids } })),
  [["plan", b], ["posts", b], ["queue", b], ["today", b], ["activity", b]]);
export const useJanusUpdate = () => useAction(async () => unwrap(await api.POST("/settings/janus/update")), [["agent-status"], ["connector", "janus"]]);

export function proposalPosts(run: AgentRunOut | undefined): ProposalPost[] {
  return ((run?.proposal as { posts?: ProposalPost[] } | undefined)?.posts ?? []) as ProposalPost[];
}
export function proposalVoice(run: AgentRunOut | undefined): VoiceProfile | null {
  return ((run?.proposal as { voice_profile?: VoiceProfile } | undefined)?.voice_profile ?? null);
}
