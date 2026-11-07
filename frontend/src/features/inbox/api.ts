/** The smart inbox (phase 9): items, triage, replies, saved replies, rules. */
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";

type S = components["schemas"];
export type InboxItem = S["InboxItemOut"];
export type InboxPage = S["InboxPage"];
export type InboxCounts = S["InboxCounts"];
export type SavedReply = S["SavedReplyOut"];
export type InboxRule = S["InboxRuleOut"];
export type InboxFilters = { status?: string; kind?: string; account?: number; assignee?: string; sentiment?: string; intent?: string; q?: string; has_draft?: boolean };

const bp = (brand_id: number) => ({ params: { path: { brand_id } } });
const ip = (brand_id: number, item_id: number) => ({ params: { path: { brand_id, item_id } } });
const KEYS = (b: number) => [["inbox", b], ["inbox-item", b], ["today", b], ["activity", b]];

export const useInboxItems = (b: number, f: InboxFilters) => useQuery({
  queryKey: ["inbox", b, f],
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/inbox", { params: { path: { brand_id: b }, query: { ...f, has_draft: f.has_draft || undefined } } })),
  refetchInterval: 120_000,
});
export const useInboxItem = (b: number, id: number | null) => useQuery({
  queryKey: ["inbox-item", b, id], enabled: id != null,
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/inbox/items/{item_id}", ip(b, id!))),
});
export const useReplyItem = (b: number) => useAction(async ({ id, body }: { id: number; body: S["ItemReplyIn"] }) =>
  unwrap(await api.POST("/brands/{brand_id}/inbox/items/{item_id}/reply", { ...ip(b, id), body })), KEYS(b), "Reply sent");
export const useSetItemStatus = (b: number) => useAction(async ({ id, status }: { id: number; status: S["InboxStatusIn"]["status"] }) =>
  unwrap(await api.POST("/brands/{brand_id}/inbox/items/{item_id}/status", { ...ip(b, id), body: { status } })), KEYS(b),
  (r) => r.status === "resolved" ? "Resolved" : r.status === "archived" ? "Archived" : "Reopened");
export const useAssignItem = (b: number) => useAction(async ({ id, user_id }: { id: number; user_id: number | null }) =>
  unwrap(await api.POST("/brands/{brand_id}/inbox/items/{item_id}/assign", { ...ip(b, id), body: { user_id } })), KEYS(b),
  (r) => r.assignee ? `Assigned to ${r.assignee.name}` : "Unassigned");
export const useSuggestReplies = (b: number) => useAction(async (id: number) =>
  unwrap(await api.POST("/brands/{brand_id}/inbox/items/{item_id}/suggest", ip(b, id))), [["inbox-item", b], ["inbox", b]]);
export const useLikeItem = (b: number) => useAction(async ({ id, liked }: { id: number; liked: boolean }) =>
  unwrap(await api.POST("/brands/{brand_id}/inbox/items/{item_id}/like", { ...ip(b, id), body: { liked } })), [], (r) => (r as { liked: boolean }).liked ? "Liked" : "Like removed");
export const useSyncInbox = (b: number) => useAction(async () => unwrap(await api.POST("/brands/{brand_id}/inbox/sync", bp(b))), KEYS(b),
  (r) => r.errors.length ? `Synced with ${r.errors.length} ${r.errors.length === 1 ? "problem" : "problems"}: ${r.errors[0]}` : `${r.new} new, ${r.updated} refreshed`);

export const useSavedReplies = (b: number) => useQuery({ queryKey: ["saved-replies", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/inbox/saved-replies", bp(b))) });
export const useCreateSavedReply = (b: number) => useAction(async (body: S["SavedReplyIn"]) => unwrap(await api.POST("/brands/{brand_id}/inbox/saved-replies", { ...bp(b), body })), [["saved-replies", b]], "Saved reply added");
export const useUpdateSavedReply = (b: number) => useAction(async ({ id, body }: { id: number; body: S["SavedReplyUpdate"] }) =>
  unwrap(await api.PATCH("/brands/{brand_id}/inbox/saved-replies/{reply_id}", { params: { path: { brand_id: b, reply_id: id } }, body })), [["saved-replies", b]], "Saved");
export const useDeleteSavedReply = (b: number) => useAction(async (id: number) =>
  unwrap(await api.DELETE("/brands/{brand_id}/inbox/saved-replies/{reply_id}", { params: { path: { brand_id: b, reply_id: id } } })), [["saved-replies", b]], "Saved reply removed");

export const useInboxRules = (b: number) => useQuery({ queryKey: ["inbox-rules", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/inbox/rules", bp(b))) });
export const useCreateRule = (b: number) => useAction(async (body: S["InboxRuleIn"]) => unwrap(await api.POST("/brands/{brand_id}/inbox/rules", { ...bp(b), body })), [["inbox-rules", b]], "Rule added");
export const useUpdateRule = (b: number) => useAction(async ({ id, body }: { id: number; body: S["InboxRuleUpdate"] }) =>
  unwrap(await api.PATCH("/brands/{brand_id}/inbox/rules/{rule_id}", { params: { path: { brand_id: b, rule_id: id } }, body })), [["inbox-rules", b]]);
export const useDeleteRule = (b: number) => useAction(async (id: number) =>
  unwrap(await api.DELETE("/brands/{brand_id}/inbox/rules/{rule_id}", { params: { path: { brand_id: b, rule_id: id } } })), [["inbox-rules", b]], "Rule removed");

export const KIND_LABEL: Record<string, string> = { comment: "Comments", message: "Messages", review: "Reviews", mention: "Mentions" };
export const KIND_ONE: Record<string, string> = { comment: "comment", message: "message", review: "review", mention: "mention" };
export const INTENT_LABEL: Record<string, string> = { question: "Question", complaint: "Complaint", praise: "Praise", lead: "Lead", spam: "Spam", other: "Other" };
