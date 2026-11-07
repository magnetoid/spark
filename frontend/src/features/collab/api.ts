/** Working together: brand members, the activity log, post comments and review links (phase 6). */
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";

type S = components["schemas"];
export type MemberOut = S["MemberOut"];
export type MemberRole = S["MemberIn"]["role"];
export type ActivityOut = S["ActivityOut"];
export type CommentOut = S["CommentOut"];
export type ShareLinkOut = S["ShareLinkOut"];
export type ShareLinkCreated = S["ShareLinkCreated"];
export type ReviewPage = S["ReviewPage"];
export type ReviewPost = S["ReviewPost"];

const bp = (brand_id: number) => ({ params: { path: { brand_id } } });

// ---- members -----------------------------------------------------------------------------
export const useMembers = (b: number) => useQuery({ queryKey: ["members", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/members", bp(b))) });
export const useAddBrandMember = (b: number) => useAction(async (body: S["MemberIn"]) => unwrap(await api.POST("/brands/{brand_id}/members", { ...bp(b), body })),
  [["members", b], ["activity", b]], (r) => `${r.name} added as ${r.role}`);
export const useUpdateBrandMember = (b: number) => useAction(async ({ user_id, role }: { user_id: number; role: MemberRole }) =>
  unwrap(await api.PATCH("/brands/{brand_id}/members/{user_id}", { params: { path: { brand_id: b, user_id } }, body: { role } })), [["members", b], ["activity", b]], "Role changed");
export const useRemoveBrandMember = (b: number) => useAction(async (user_id: number) =>
  unwrap(await api.DELETE("/brands/{brand_id}/members/{user_id}", { params: { path: { brand_id: b, user_id } } })), [["members", b], ["activity", b]], "Removed from the brand");

// ---- activity ------------------------------------------------------------------------------
export const useActivity = (b: number, limit = 30) => useQuery({
  queryKey: ["activity", b, limit],
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/activity", { params: { path: { brand_id: b }, query: { limit } } })),
});

// ---- comments --------------------------------------------------------------------------------
export const useComments = (b: number, postId: number | null) => useQuery({
  queryKey: ["comments", b, postId],
  enabled: postId != null,
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/posts/{post_id}/comments", { params: { path: { brand_id: b, post_id: postId! } } })),
});
export const useAddComment = (b: number, postId: number) => useAction(async (body: string) =>
  unwrap(await api.POST("/brands/{brand_id}/posts/{post_id}/comments", { params: { path: { brand_id: b, post_id: postId } }, body: { body } })),
  [["comments", b, postId], ["activity", b], ["posts", b]]);

// ---- review links ------------------------------------------------------------------------------
export const useShareLinks = (b: number) => useQuery({ queryKey: ["share-links", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/share-links", bp(b))) });
export const useCreateShareLink = (b: number) => useAction(async (body: S["ShareLinkIn"]) => unwrap(await api.POST("/brands/{brand_id}/share-links", { ...bp(b), body })),
  [["share-links", b], ["activity", b]]);
export const useRevokeShareLink = (b: number) => useAction(async (link_id: number) =>
  unwrap(await api.DELETE("/brands/{brand_id}/share-links/{link_id}", { params: { path: { brand_id: b, link_id } } })), [["share-links", b], ["activity", b]], "Link revoked");

// ---- the public review page (no account) -----------------------------------------------------------
export const useReview = (token: string) => useQuery({
  queryKey: ["review", token],
  queryFn: async () => unwrap(await api.GET("/public/review/{token}", { params: { path: { token } } })),
  retry: false,
});
export const useReviewAction = (token: string, kind: "approve" | "request-changes") => useAction(
  async ({ post_id, name, body }: { post_id: number; name: string; body?: string }) => {
    const opts = { params: { path: { token, post_id } }, body: { name, body: body ?? null } };
    return unwrap(kind === "approve"
      ? await api.POST("/public/review/{token}/posts/{post_id}/approve", opts)
      : await api.POST("/public/review/{token}/posts/{post_id}/request-changes", opts));
  },
  [["review", token]],
);
