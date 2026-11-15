/** All-clients overview and copying one brand's setup to another. */
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { sessionQuery } from "@/app/session";
import { useAction } from "@/features/api4";
import { api, unwrap } from "@/lib/api";

type S = components["schemas"];
export type OverviewOut = S["OverviewOut"];
export type OverviewBrand = S["OverviewBrand"];
export type SetupPart = S["CopySetupIn"]["parts"][number];

export const SETUP_PARTS: { key: SetupPart; label: string; hint: string }[] = [
  { key: "voice", label: "Brand voice", hint: "Tone, audience, rules, examples, default hashtags" },
  { key: "pillars", label: "Content pillars", hint: "Themes and the share of posts each gets" },
  { key: "slots", label: "Posting times", hint: "Replaces this brand's brand-wide times" },
  { key: "guardrails", label: "Guardrails", hint: "Words never to say, topics to avoid, keywords" },
  { key: "saved_replies", label: "Saved replies", hint: "Inbox answers" },
  { key: "templates", label: "Post templates", hint: "Reusable post skeletons" },
  { key: "hashtags", label: "Hashtag groups", hint: "Sets of hashtags for the composer" },
];

export function useOverview() {
  return useQuery({
    queryKey: ["overview"],
    queryFn: async () => unwrap(await api.GET("/overview")),
    refetchInterval: 60_000,
  });
}

export async function copySetup(brandId: number, fromBrandId: number, parts: SetupPart[]) {
  return unwrap(await api.POST("/brands/{brand_id}/copy-setup", {
    params: { path: { brand_id: brandId } }, body: { from_brand_id: fromBrandId, parts },
  }));
}

export function useCopySetup(brandId: number) {
  return useAction(
    (v: { from: number; parts: SetupPart[] }) => copySetup(brandId, v.from, v.parts),
    [sessionQuery.queryKey, ["overview"]],
    (r) => {
      const n = Object.values(r.copied).reduce((a, b) => a + b, 0);
      return n ? `Copied ${n} item${n === 1 ? "" : "s"}` : "Nothing new to copy: this brand already has it all";
    },
  );
}
