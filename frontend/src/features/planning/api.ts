/** Planning (phase 7): content pillars, CSV import. */
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";

type S = components["schemas"];
export type PillarOut = S["PillarOut"];
export type PillarIn = S["PillarIn"];
export type PostImportOut = S["PostImportOut"];

const bp = (brand_id: number) => ({ params: { path: { brand_id } } });

export const usePillars = (b: number) => useQuery({ queryKey: ["pillars", b], queryFn: async () => unwrap(await api.GET("/brands/{brand_id}/pillars", bp(b))) });
export const useCreatePillar = (b: number) => useAction(async (body: PillarIn) => unwrap(await api.POST("/brands/{brand_id}/pillars", { ...bp(b), body })), [["pillars", b]], "Pillar added");
export const useUpdatePillar = (b: number) => useAction(async ({ id, body }: { id: number; body: S["PillarUpdate"] }) =>
  unwrap(await api.PATCH("/brands/{brand_id}/pillars/{pillar_id}", { params: { path: { brand_id: b, pillar_id: id } }, body })), [["pillars", b]]);
export const useDeletePillar = (b: number) => useAction(async (id: number) =>
  unwrap(await api.DELETE("/brands/{brand_id}/pillars/{pillar_id}", { params: { path: { brand_id: b, pillar_id: id } } })), [["pillars", b], ["posts", b]], "Pillar removed");

export const useImportPosts = (b: number) => useAction(async (csv: string) => unwrap(await api.POST("/brands/{brand_id}/posts/import", { ...bp(b), body: { csv } })),
  [["posts", b], ["queue", b], ["today", b], ["activity", b]],
  (r) => `${r.created} ${r.created === 1 ? "post" : "posts"} imported${r.errors.length ? `, ${r.errors.length} ${r.errors.length === 1 ? "row" : "rows"} skipped` : ""}`);
