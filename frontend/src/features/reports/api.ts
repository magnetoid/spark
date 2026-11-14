/** Reports (phase 10): a period's numbers, CSV, AI summary. */
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";

type S = components["schemas"];
export type ReportOut = S["ReportOut"];
export type ReportData = {
  period: { start: string; end: string; days: number };
  generated_at: string;
  // seen, reach, views, saves and link_clicks: reports made before November 2026 lack them
  totals: { published: number; impressions: number; likes: number; comments: number; shares: number; clicks: number; engagements: number; engagement_rate_pct: number; seen?: number; reach?: number | null; views?: number | null; saves?: number | null; link_clicks?: number };
  channels: { account_id: number; platform: string; handle: string; posts: number; impressions: number; seen?: number; engagements: number; engagement_rate_pct: number }[];
  series: { day: string; impressions: number; engagements: number; posts: number }[];
  top_posts: { post_id: number; content: string; platform: string; handle: string; published_at: string; url: string | null; impressions: number; seen?: number; engagements: number; link_clicks?: number }[];
  pillars: { name: string; color: string; target_share: number; posts: number; share_pct: number }[];
  compare: Record<string, { current: number; previous: number; pct: number | null }>;
  followers: { start: number; end: number; delta: number; series: { day: string; followers: number }[]; by_channel?: { account_id: number; platform: string; handle: string; start: number; end: number; delta: number }[] };
  inbox: { received: number; replied: number; negative: number; by_kind: Record<string, number>; median_reply_minutes?: number | null };
};
export type ReportSummary = { headline: string; worked: string[]; next: string[]; written_at?: string };

const bp = (brand_id: number) => ({ params: { path: { brand_id } } });
const rp = (brand_id: number, report_id: number) => ({ params: { path: { brand_id, report_id } } });

export const useReports = (b: number) => useQuery({ queryKey: ["reports", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/reports", bp(b))) });
export const useReport = (b: number, id: number) => useQuery({ queryKey: ["report", b, id], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/reports/{report_id}", rp(b, id))) });
export const useCreateReport = (b: number) => useAction(async (body: S["ReportIn"]) => unwrap(await api.POST("/brands/{brand_id}/reports", { ...bp(b), body })), [["reports", b], ["activity", b]], "Report ready");
export const useDeleteReport = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/reports/{report_id}", rp(b, id))), [["reports", b]], "Report deleted");
export const useSummarizeReport = (b: number, id: number) => useAction(async () => unwrap(await api.POST("/brands/{brand_id}/reports/{report_id}/summary", rp(b, id))), [["report", b, id], ["reports", b]], "Summary written");
export type ReportScheduleOut = S["ReportScheduleOut"];
export const useShareReport = (b: number, id: number) => useAction(async (days: number) => unwrap(await api.POST("/brands/{brand_id}/reports/{report_id}/share", { ...rp(b, id), body: { days } })), [["share-links", b]]);
export const usePublicReport = (token: string) => useQuery({
  queryKey: ["public-report", token], retry: false,
  queryFn: async () => unwrap(await api.GET("/public/reports/{token}", { params: { path: { token } } })),
});
export const useReportSchedules = (b: number, enabled = true) => useQuery({ queryKey: ["report-schedules", b], enabled, queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/report-schedules", bp(b))) });
export const useCreateReportSchedule = (b: number) => useAction(async (body: S["ReportScheduleIn"]) => unwrap(await api.POST("/brands/{brand_id}/report-schedules", { ...bp(b), body })), [["report-schedules", b]], "Report scheduled");
export const useUpdateReportSchedule = (b: number) => useAction(async ({ id, body }: { id: number; body: S["ReportScheduleUpdate"] }) => unwrap(await api.PATCH("/brands/{brand_id}/report-schedules/{schedule_id}", { params: { path: { brand_id: b, schedule_id: id } }, body })), [["report-schedules", b]], "Schedule saved");
export const useDeleteReportSchedule = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/report-schedules/{schedule_id}", { params: { path: { brand_id: b, schedule_id: id } } })), [["report-schedules", b]], "Schedule removed");
export const csvUrl = (b: number, id: number) => `/api/v1/brands/${b}/reports/${id}/csv`;
export const reportPath = (b: number, id: number) => `/brands/${b}/reports/${id}`;
