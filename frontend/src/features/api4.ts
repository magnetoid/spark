/** Queries and mutations for the phase-4 pages: analytics, campaigns, links, audience, channels, settings, inbox. */
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import type { components } from "@/api/schema";
import { api, unwrap } from "@/lib/api";

type S = components["schemas"];
export type AnalyticsOut = S["AnalyticsOut"];
export type CampaignFull = S["CampaignFull"];
export type LinkOut = S["LinkOut"];
export type FeedOut = S["FeedOut"];
export type ContactOut = S["ContactOut"];
export type ListOut = S["ListOut"];
export type EmailOut = S["EmailOut"];
export type BioOut = S["BioOut"];
export type PlatformsOut = S["PlatformsOut"];
export type SlotRow = S["SlotRow"];
export type TeamOut = S["TeamOut"];
export type ConnectorCard = S["ConnectorCard"];
export type ConnectorOut = S["ConnectorOut"];
export type TokenOut = S["TokenOut"];
export type InboxOut = S["InboxOut"];
export type PaletteItem = S["PaletteItem"];

const bp = (brand_id: number) => ({ params: { path: { brand_id } } });

/** A mutation that invalidates the given keys and toasts the result. */
export function useAction<TVars, TRes>(fn: (v: TVars) => Promise<TRes>, keys: QueryKey[], message?: string | ((r: TRes) => string | undefined)) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      for (const k of keys) void qc.invalidateQueries({ queryKey: k });
      const m = typeof message === "function" ? message(r) : message ?? (r as { message?: string } | null)?.message;
      if (m) toast.success(m);
    },
    onError: (e) => toast.error(e.message),
  });
}

// ---- analytics -------------------------------------------------------------------------
export const useAnalytics = (b: number, days: number) => useQuery({
  queryKey: ["analytics", b, days],
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/analytics", { params: { path: { brand_id: b }, query: { days } } })),
});
export const useRefreshAnalytics = (b: number) => useAction(async () => unwrap(await api.POST("/brands/{brand_id}/analytics/refresh", bp(b))), [["analytics", b], ["today", b]]);

// ---- campaigns ---------------------------------------------------------------------------
export const useCampaignsFull = (b: number) => useQuery({ queryKey: ["campaigns", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/campaigns", bp(b))) });
export const useCreateCampaign = (b: number) => useAction(async (body: S["CampaignIn"]) => unwrap(await api.POST("/brands/{brand_id}/campaigns", { ...bp(b), body })), [["campaigns", b], ["posts", b]],
  (r) => r.planned ? `Campaign created with ${r.planned} draft posts` : "Campaign created");
export const useUpdateCampaign = (b: number) => useAction(async ({ id, body }: { id: number; body: S["CampaignUpdate"] }) =>
  unwrap(await api.PATCH("/brands/{brand_id}/campaigns/{campaign_id}", { params: { path: { brand_id: b, campaign_id: id } }, body })), [["campaigns", b]], "Campaign saved");
export const useDeleteCampaign = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/campaigns/{campaign_id}", { params: { path: { brand_id: b, campaign_id: id } } })), [["campaigns", b], ["posts", b]], "Campaign deleted");

// ---- links + feeds -------------------------------------------------------------------------
export const useLinks = (b: number) => useQuery({ queryKey: ["links", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/links", bp(b))) });
export const useCreateLink = (b: number) => useAction(async (body: S["LinkIn"]) => unwrap(await api.POST("/brands/{brand_id}/links", { ...bp(b), body })), [["links", b]], "Short link created");
export const useDeleteLink = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/links/{link_id}", { params: { path: { brand_id: b, link_id: id } } })), [["links", b]], "Link deleted");
export const useFeeds = (b: number) => useQuery({ queryKey: ["feeds", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/feeds", bp(b))) });
export const useCreateFeed = (b: number) => useAction(async (body: S["FeedIn"]) => unwrap(await api.POST("/brands/{brand_id}/feeds", { ...bp(b), body })), [["feeds", b]], "Feed added. New items create drafts from the next check on.");
export const useUpdateFeed = (b: number) => useAction(async ({ id, body }: { id: number; body: S["FeedUpdate"] }) => unwrap(await api.PATCH("/brands/{brand_id}/feeds/{feed_id}", { params: { path: { brand_id: b, feed_id: id } }, body })), [["feeds", b]]);
export const useDeleteFeed = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/feeds/{feed_id}", { params: { path: { brand_id: b, feed_id: id } } })), [["feeds", b]], "Feed removed");

// ---- audience -----------------------------------------------------------------------------
export const useContacts = (b: number, q: string, list_id?: number) => useQuery({
  queryKey: ["contacts", b, q, list_id ?? 0],
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/contacts", { params: { path: { brand_id: b }, query: { q, list_id } } })),
});
export const useLists = (b: number) => useQuery({ queryKey: ["lists", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/lists", bp(b))) });
export const useAddContact = (b: number) => useAction(async (body: S["ContactIn"]) => unwrap(await api.POST("/brands/{brand_id}/contacts", { ...bp(b), body })), [["contacts", b], ["lists", b]], "Contact saved");
export const useDeleteContact = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/contacts/{contact_id}", { params: { path: { brand_id: b, contact_id: id } } })), [["contacts", b], ["lists", b]], "Contact deleted");
export const useCreateList = (b: number) => useAction(async (body: S["ListIn"]) => unwrap(await api.POST("/brands/{brand_id}/lists", { ...bp(b), body })), [["lists", b]], "List created");
export const useDeleteList = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/lists/{list_id}", { params: { path: { brand_id: b, list_id: id } } })), [["lists", b], ["contacts", b]], "List deleted");
export async function importContacts(b: number, file: File, listIds: number[]) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("list_ids", listIds.join(","));
  return unwrap(await api.POST("/brands/{brand_id}/contacts/import", { ...bp(b), body: fd as unknown as { file: string; list_ids: string } })) as { imported: number; message: string };
}
export const useEmails = (b: number) => useQuery({ queryKey: ["email", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/email", bp(b))) });
export const useEmail = (b: number, id: number | null) => useQuery({
  queryKey: ["email", b, id], enabled: id !== null,
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/email/{cid}", { params: { path: { brand_id: b, cid: id! } } })),
});
export const useCreateEmail = (b: number) => useAction(async (body: S["EmailCreate"]) => unwrap(await api.POST("/brands/{brand_id}/email", { ...bp(b), body })), [["email", b]], "Email campaign created");
export const useUpdateEmail = (b: number) => useAction(async ({ id, body }: { id: number; body: S["EmailUpdate"] }) =>
  unwrap(await api.PATCH("/brands/{brand_id}/email/{cid}", { params: { path: { brand_id: b, cid: id } }, body })), [["email", b]],
  (r) => ({ scheduled: r.sent_at ? undefined : "Email scheduled", draft: "Saved" }[r.status] ?? "Saved"));
export const useDeleteEmail = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/email/{cid}", { params: { path: { brand_id: b, cid: id } } })), [["email", b]], "Email campaign deleted");
export const useTestEmail = (b: number) => useAction(async (id: number) => unwrap(await api.POST("/brands/{brand_id}/email/{cid}/test", { params: { path: { brand_id: b, cid: id } } })) as Promise<{ message: string }>, []);
export async function emailAi(b: number, id: number, brief: string) {
  return unwrap(await api.POST("/brands/{brand_id}/email/{cid}/ai", { params: { path: { brand_id: b, cid: id } }, body: { brief } })) as { subject: string; preheader?: string; body_html: string };
}

// ---- bio ------------------------------------------------------------------------------------
export const useBio = (b: number) => useQuery({ queryKey: ["bio", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/bio", bp(b))) });
export const useSaveBio = (b: number) => useAction(async (body: S["BioIn"]) => unwrap(await api.PUT("/brands/{brand_id}/bio", { ...bp(b), body })), [["bio", b], ["links", b]], "Bio page saved");

// ---- channels -------------------------------------------------------------------------------
export const usePlatforms = (b: number) => useQuery({ queryKey: ["platforms", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/platforms", bp(b))), staleTime: 300_000 });
export const useConnectCredentials = (b: number) => useAction(async ({ platform, data }: { platform: string; data: Record<string, string> }) =>
  unwrap(await api.POST("/brands/{brand_id}/accounts/connect/{platform}", { params: { path: { brand_id: b, platform } }, body: data })), [["accounts", b], ["queue", b], ["platforms", b]]);
export const useZernioImport = (b: number) => useAction(async () => unwrap(await api.POST("/brands/{brand_id}/accounts/zernio/import", bp(b))), [["accounts", b], ["queue", b]],
  (r) => r.imported ? `Imported ${r.imported} account(s) from Zernio` : "Zernio has no connected accounts yet");
export const useToggleAccount = (b: number) => useAction(async (id: number) => unwrap(await api.POST("/brands/{brand_id}/accounts/{account_id}/toggle", { params: { path: { brand_id: b, account_id: id } } })), [["accounts", b], ["queue", b]],
  (r) => r.is_active ? `${r.handle} resumed` : `${r.handle} paused`);
export const useRemoveAccount = (b: number) => useAction(async ({ id, disconnect }: { id: number; disconnect?: boolean }) =>
  unwrap(await api.DELETE("/brands/{brand_id}/accounts/{account_id}", { params: { path: { brand_id: b, account_id: id }, query: { disconnect } } })), [["accounts", b], ["queue", b]], "Channel removed");

// ---- settings --------------------------------------------------------------------------------
export const useSlots = (b: number) => useQuery({ queryKey: ["slots", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/slots", bp(b))) });
export const useAddSlots = (b: number) => useAction(async (body: S["SlotIn"]) => unwrap(await api.POST("/brands/{brand_id}/slots", { ...bp(b), body })), [["slots", b], ["queue", b]], "Posting times added");
export const useDeleteSlot = (b: number) => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}/slots/{slot_id}", { params: { path: { brand_id: b, slot_id: id } } })), [["slots", b], ["queue", b]]);
export const useUpdateBrand = (b: number) => useAction(async (body: S["BrandUpdate"]) => unwrap(await api.PATCH("/brands/{brand_id}", { ...bp(b), body })), [["session"]], "Brand settings saved");
export const useDeleteBrand = () => useAction(async (id: number) => unwrap(await api.DELETE("/brands/{brand_id}", { params: { path: { brand_id: id } } })), [["session"]], "Brand deleted");
export const useTeam = () => useQuery({ queryKey: ["team"], queryFn: async () => unwrap(await api.GET("/team")) });
export const useAddMember = () => useAction(async (body: S["TeamIn"]) => unwrap(await api.POST("/team", { body })), [["team"]], (r) => `Added ${r.name}`);
export const useUpdateMember = () => useAction(async ({ id, body }: { id: number; body: S["TeamUpdate"] }) => unwrap(await api.PATCH("/team/{user_id}", { params: { path: { user_id: id } }, body })), [["team"]], (r) => `Updated ${r.name}`);
export const useConnectors = () => useQuery({ queryKey: ["connectors"], queryFn: async () => unwrap(await api.GET("/settings/connectors")) });
export const useConnector = (key: string | null) => useQuery({
  queryKey: ["connector", key], enabled: key !== null,
  queryFn: async () => unwrap(await api.GET("/settings/connectors/{key}", { params: { path: { key: key! } } })),
});
export const useSaveConnector = () => useAction(async ({ key, body }: { key: string; body: S["ConnectorSave"] }) =>
  unwrap(await api.PUT("/settings/connectors/{key}", { params: { path: { key } }, body })), [["connectors"], ["connector"], ["session"]], (r) => `${r.name} saved`);
export const useTestConnector = () => useAction(async (key: string) => unwrap(await api.POST("/settings/connectors/{key}/test", { params: { path: { key } } })) as Promise<{ message: string }>, []);
export const useZernioWebhook = () => useAction(async (what: "register" | "test") =>
  unwrap(await (what === "register" ? api.POST("/settings/zernio/webhook") : api.POST("/settings/zernio/webhook/test"))) as Promise<{ message: string }>, [["connector"]]);
export const useTokens = () => useQuery({ queryKey: ["tokens"], queryFn: async () => unwrap(await api.GET("/me/tokens")) });
export const useCreateToken = () => useAction(async (name: string) => unwrap(await api.POST("/me/tokens", { body: { name } })), [["tokens"], ["connectors"]]);
export const useDeleteToken = () => useAction(async (id: number) => unwrap(await api.DELETE("/me/tokens/{token_id}", { params: { path: { token_id: id } } })), [["tokens"], ["connectors"]], "Token revoked");
export const useUpdateMe = () => useAction(async (body: S["MeUpdate"]) => unwrap(await api.PATCH("/me", { body })), [["session"]], "Preferences saved");
export const useChangePassword = () => useAction(async (body: S["PasswordChange"]) => unwrap(await api.POST("/me/password", { body })), [], "Password changed");

// ---- inbox ------------------------------------------------------------------------------------
export const useInbox = (b: number, account?: string, days = 30) => useQuery({
  queryKey: ["inbox", b, account ?? "", days],
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/inbox", { params: { path: { brand_id: b }, query: { account, days } } })),
  refetchInterval: 120_000,
});
export const useComments = (b: number, postId: string | null, account: string | null) => useQuery({
  queryKey: ["comments", b, postId, account], enabled: !!postId && !!account,
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/inbox/{post_id}/comments", { params: { path: { brand_id: b, post_id: postId! }, query: { account: account! } } })) as Promise<{ comments: Record<string, unknown>[]; pagination: Record<string, unknown> }>,
});
export const useReply = (b: number) => useAction(async ({ postId, body }: { postId: string; body: S["ReplyIn"] }) =>
  unwrap(await api.POST("/brands/{brand_id}/inbox/{post_id}/reply", { params: { path: { brand_id: b, post_id: postId } }, body })) as Promise<{ message: string }>, [["comments", b]]);
export const useLike = (b: number) => useAction(async ({ postId, body }: { postId: string; body: S["LikeIn"] }) =>
  unwrap(await api.POST("/brands/{brand_id}/inbox/{post_id}/like", { params: { path: { brand_id: b, post_id: postId } }, body })), [["comments", b]]);

// ---- palette ------------------------------------------------------------------------------------
export const usePalette = (b: number, enabled: boolean) => useQuery({ queryKey: ["palette", b], enabled, staleTime: 30_000, queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/palette", bp(b))) });
