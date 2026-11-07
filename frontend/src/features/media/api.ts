/** Media (phase 8): generated images, crops, alt text from vision, tags, the channel grid, repurposing. */
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";

type S = components["schemas"];
export type MediaOut = S["MediaOut"];
export type GridOut = S["GridOut"];
export type RepurposeOut = S["RepurposeOut"];
export type CropRatio = S["MediaCropIn"]["ratio"];
export type ImageSize = S["MediaGenerateIn"]["size"];

const bp = (brand_id: number) => ({ params: { path: { brand_id } } });
const mp = (brand_id: number, media_id: number) => ({ params: { path: { brand_id, media_id } } });
const MEDIA_KEYS = (b: number) => [["media", b], ["media-tags", b]];

export const useMediaTags = (b: number) => useQuery({ queryKey: ["media-tags", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/media/tags", bp(b))) });
export const useGenerateImage = (b: number) => useAction(async (body: S["MediaGenerateIn"]) => unwrap(await api.POST("/brands/{brand_id}/media/generate", { ...bp(b), body })),
  MEDIA_KEYS(b), "Image added to the library");
export const useCropMedia = (b: number) => useAction(async ({ id, body }: { id: number; body: S["MediaCropIn"] }) =>
  unwrap(await api.POST("/brands/{brand_id}/media/{media_id}/crop", { ...mp(b, id), body })), MEDIA_KEYS(b), (r) => `Saved ${r.name}`);
export const useWriteAltText = (b: number) => useAction(async (id: number) => unwrap(await api.POST("/brands/{brand_id}/media/{media_id}/alt-text", mp(b, id))),
  MEDIA_KEYS(b), "Alt text written");
export const useUpdateMedia = (b: number) => useAction(async ({ id, body }: { id: number; body: S["MediaUpdate"] }) =>
  unwrap(await api.PATCH("/brands/{brand_id}/media/{media_id}", { ...mp(b, id), body })), MEDIA_KEYS(b));
export const useChannelGrid = (b: number, accountId: number | null) => useQuery({
  queryKey: ["grid", b, accountId], enabled: accountId != null,
  queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/channels/{account_id}/grid", { params: { path: { brand_id: b, account_id: accountId! } } })),
});
export const useRepurpose = (b: number) => useAction(async (body: S["RepurposeIn"]) => unwrap(await api.POST("/brands/{brand_id}/ai/repurpose", { ...bp(b), body })),
  [["posts", b], ["queue", b], ["today", b], ["agent-runs", b], ["activity", b]]);

export const RATIOS: { value: CropRatio; label: string; hint: string }[] = [
  { value: "1:1", label: "1:1", hint: "Feed, square" },
  { value: "4:5", label: "4:5", hint: "Instagram portrait" },
  { value: "9:16", label: "9:16", hint: "Story, Reel, Short" },
  { value: "16:9", label: "16:9", hint: "YouTube, X" },
  { value: "2:3", label: "2:3", hint: "Pinterest" },
  { value: "1.91:1", label: "1.91:1", hint: "Link card" },
];
