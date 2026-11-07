/** Queries and mutations for posts, channels, queue and the library, keyed per brand. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { components } from "@/api/schema";
import { api, ApiError, getCsrfToken, unwrap, type ApiPaths } from "@/lib/api";

export type PostOut = components["schemas"]["PostOut"];
export type AccountOut = components["schemas"]["AccountOut"];
export type PostWrite = components["schemas"]["PostWrite"];
export type PostResult = components["schemas"]["PostResult"];
export type QueueOut = components["schemas"]["QueueOut"];
export type MediaOut = components["schemas"]["MediaOut"];
export type TemplateOut = components["schemas"]["TemplateOut"];
export type HashtagGroupOut = components["schemas"]["HashtagGroupOut"];
export type CampaignOut = components["schemas"]["CampaignOut"];
export type IdeaOut = components["schemas"]["IdeaOut"];
export type PostStatus = PostOut["status"];

export const keys = {
  accounts: (b: number) => ["accounts", b] as const,
  posts: (b: number, f?: object) => ["posts", b, f ?? {}] as const,
  post: (b: number, id: number) => ["post", b, id] as const,
  queue: (b: number, account?: number | null) => ["queue", b, account ?? null] as const,
  autosave: (b: number) => ["autosave", b] as const,
  media: (b: number) => ["media", b] as const,
  templates: (b: number) => ["templates", b] as const,
  hashtags: (b: number) => ["hashtags", b] as const,
  campaigns: (b: number) => ["campaigns", b] as const,
  ideas: (b: number) => ["ideas", b] as const,
  today: (b: number) => ["today", b] as const,
};

const path = (brand_id: number) => ({ params: { path: { brand_id } } });
const ppath = (brand_id: number, post_id: number) => ({ params: { path: { brand_id, post_id } } });

export function useAccounts(brandId: number) {
  return useQuery({ queryKey: keys.accounts(brandId), queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/accounts", path(brandId))), staleTime: 60_000 });
}

export type PostFilters = NonNullable<ApiPaths["/brands/{brand_id}/posts"]["get"]["parameters"]["query"]>;

export function usePosts(brandId: number, filters: PostFilters = {}, enabled = true) {
  return useQuery({
    queryKey: keys.posts(brandId, filters),
    queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/posts", { params: { path: { brand_id: brandId }, query: filters } })),
    enabled,
  });
}

export function usePost(brandId: number, id: number | null) {
  return useQuery({
    queryKey: keys.post(brandId, id ?? 0),
    queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/posts/{post_id}", ppath(brandId, id!))),
    enabled: id !== null,
  });
}

export function useQueue(brandId: number, account: number | null, days = 14, enabled = true) {
  return useQuery({
    queryKey: keys.queue(brandId, account),
    queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/queue", { params: { path: { brand_id: brandId }, query: { account: account ?? undefined, days } } })),
    enabled,
    retry: false,
  });
}

export function useMedia(brandId: number, enabled = true) {
  return useQuery({ queryKey: keys.media(brandId), queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/media", path(brandId))), enabled });
}
export function useTemplates(brandId: number) {
  return useQuery({ queryKey: keys.templates(brandId), queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/templates", path(brandId))), staleTime: 60_000 });
}
export function useHashtagGroups(brandId: number) {
  return useQuery({ queryKey: keys.hashtags(brandId), queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/hashtag-groups", path(brandId))), staleTime: 60_000 });
}
export function useCampaigns(brandId: number) {
  return useQuery({ queryKey: keys.campaigns(brandId), queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/campaigns", path(brandId))), staleTime: 60_000 });
}
export function useIdeas(brandId: number, tag?: string) {
  return useQuery({ queryKey: [...keys.ideas(brandId), tag ?? ""], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/ideas", { params: { path: { brand_id: brandId }, query: { tag } } })) });
}

/** Every post-changing mutation invalidates the lists that could show the post. */
export function useInvalidatePosts(brandId: number) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["posts", brandId] });
    void qc.invalidateQueries({ queryKey: ["post", brandId] });
    void qc.invalidateQueries({ queryKey: ["queue", brandId] });
    void qc.invalidateQueries({ queryKey: keys.today(brandId) });
    void qc.invalidateQueries({ queryKey: ["ideas", brandId] });
  };
}

export class CannotPlace extends Error {
  constructor(public problems: string[], public post: PostOut) {
    super(problems.join(" · "));
  }
}

async function postResult(result: { data?: PostResult; error?: unknown; response: Response }): Promise<PostResult> {
  if (result.response.status === 422) {
    const body = (result.error ?? {}) as { code?: string; problems?: string[]; post?: PostOut };
    if (body.code === "cannot_place" && body.post) throw new CannotPlace(body.problems ?? [], body.post);
  }
  return unwrap(result);
}

export function usePostActions(brandId: number) {
  const invalidate = useInvalidatePosts(brandId);
  const p = (post_id: number) => ppath(brandId, post_id);
  return {
    invalidate,
    save: useMutation({
      mutationFn: async ({ id, body }: { id?: number; body: PostWrite }) =>
        id ? postResult(await api.PATCH("/brands/{brand_id}/posts/{post_id}", { ...p(id), body }))
           : postResult(await api.POST("/brands/{brand_id}/posts", { ...path(brandId), body })),
      onSuccess: () => invalidate(),
    }),
    place: useMutation({
      mutationFn: async ({ id, action, scheduled_at }: { id: number; action: PostWrite["action"]; scheduled_at?: string }) =>
        postResult(await api.POST("/brands/{brand_id}/posts/{post_id}/place", { ...p(id), body: { action, scheduled_at } })),
      onSuccess: (r) => { invalidate(); toast.success(r.message); },
      onError: (e) => toast.error(e.message),
    }),
    approve: useMutation({
      mutationFn: async (id: number) => unwrap(await api.POST("/brands/{brand_id}/posts/{post_id}/approve", p(id))),
      onSuccess: (r) => { invalidate(); toast.success(r.message); }, onError: (e) => toast.error(e.message),
    }),
    retry: useMutation({
      mutationFn: async (id: number) => unwrap(await api.POST("/brands/{brand_id}/posts/{post_id}/retry", p(id))),
      onSuccess: (r) => { invalidate(); toast.success(r.message); }, onError: (e) => toast.error(e.message),
    }),
    unschedule: useMutation({
      mutationFn: async (id: number) => unwrap(await api.POST("/brands/{brand_id}/posts/{post_id}/unschedule", p(id))),
      onSuccess: (r) => { invalidate(); toast.success(r.message); }, onError: (e) => toast.error(e.message),
    }),
    duplicate: useMutation({
      mutationFn: async (id: number) => unwrap(await api.POST("/brands/{brand_id}/posts/{post_id}/duplicate", p(id))),
      onSuccess: () => invalidate(), onError: (e) => toast.error(e.message),
    }),
    remove: useMutation({
      mutationFn: async (id: number) => { unwrap(await api.DELETE("/brands/{brand_id}/posts/{post_id}", p(id))); return { message: "Post deleted" }; },
      onSuccess: (r) => { invalidate(); toast.success(r.message); }, onError: (e) => toast.error(e.message),
    }),
    move: useMutation({
      mutationFn: async ({ id, day, when }: { id: number; day?: string; when?: string }) =>
        unwrap(await api.POST("/brands/{brand_id}/posts/{post_id}/move", { ...p(id), body: { day, when } })),
      onSuccess: (r) => { invalidate(); toast.success(r.message); }, onError: (e) => toast.error(e.message),
    }),
  };
}

export async function validateTargets(brandId: number, targets: Record<string, string>, media_ids: number[], link: string | null) {
  return unwrap(await api.POST("/brands/{brand_id}/posts/validate", { ...path(brandId), body: { targets, media_ids, link } }));
}

export async function autosavePost(brandId: number, body: components["schemas"]["AutosaveIn"]) {
  return unwrap(await api.PUT("/brands/{brand_id}/posts/autosave", { ...path(brandId), body }));
}

export async function fetchAutosave(brandId: number) {
  return unwrap(await api.GET("/brands/{brand_id}/posts/autosave", path(brandId)));
}

/** Upload with progress (fetch has no upload progress), returning the saved media. */
export function uploadMedia(brandId: number, file: File, onProgress: (pct: number) => void): Promise<MediaOut[]> {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append("files", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/v1/brands/${brandId}/media`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-CSRF-Token", getCsrfToken());
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) onProgress(Math.round((ev.loaded / ev.total) * 100)); };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const body = JSON.parse(xhr.responseText) as { items: MediaOut[]; rejected: { name: string; reason: string }[] };
        for (const r of body.rejected) toast.error(`${r.name}: ${r.reason}`);
        resolve(body.items);
      } else {
        let detail = `Upload failed (${xhr.status})`;
        try { detail = JSON.parse(xhr.responseText).detail ?? detail; } catch { /* keep */ }
        reject(new ApiError(xhr.status, "upload", detail));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "network", "Upload failed"));
    xhr.send(fd);
  });
}

export async function aiGenerate(brandId: number, body: components["schemas"]["GenerateIn"]) {
  return unwrap(await api.POST("/brands/{brand_id}/ai/generate", { ...path(brandId), body })) as { drafts: { platform: string; text: string; hashtags: string[] }[] };
}
export async function aiRewrite(brandId: number, body: components["schemas"]["RewriteIn"]) {
  return unwrap(await api.POST("/brands/{brand_id}/ai/rewrite", { ...path(brandId), body })) as { text: string };
}
export async function aiHashtags(brandId: number, text: string) {
  return unwrap(await api.POST("/brands/{brand_id}/ai/hashtags", { ...path(brandId), body: { text } })) as { hashtags: string[] };
}
