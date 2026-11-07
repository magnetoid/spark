/**
 * Network logos and labels. Logos come from simple-icons where it has them; LinkedIn and
 * Google Business are not in that set (trademark policy), so they are drawn here.
 * Colour is only ever applied to the logo itself: the rest of the UI stays neutral.
 */
import {
  siBluesky, siFacebook, siInstagram, siMastodon, siPinterest, siReddit, siTelegram, siThreads,
  siTiktok, siX, siYoutube, type SimpleIcon,
} from "simple-icons";
import { FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";

interface Mark { label: string; path: string; color: string }

const LINKEDIN_PATH = "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z";
const GOOGLE_BUSINESS_PATH = "M12 2 2 7v2h20V7zM4 11v9h4v-6h8v6h4v-9zm6 3h4v6h-4z";

const si = (icon: SimpleIcon, label = icon.title): Mark => ({ label, path: icon.path, color: `#${icon.hex}` });

export const PLATFORMS: Record<string, Mark> = {
  x: si(siX, "X"),
  linkedin: { label: "LinkedIn", path: LINKEDIN_PATH, color: "#0A66C2" },
  facebook: si(siFacebook),
  instagram: si(siInstagram),
  threads: si(siThreads),
  bluesky: si(siBluesky),
  mastodon: si(siMastodon),
  tiktok: si(siTiktok, "TikTok"),
  youtube: si(siYoutube, "YouTube"),
  pinterest: si(siPinterest),
  telegram: si(siTelegram),
  reddit: si(siReddit),
  google_business: { label: "Google Business", path: GOOGLE_BUSINESS_PATH, color: "#4285F4" },
  gbp: { label: "Google Business", path: GOOGLE_BUSINESS_PATH, color: "#4285F4" },
};

export function platformLabel(key: string) {
  return PLATFORMS[key]?.label ?? key.replace(/_/g, " ");
}

export function PlatformMark({ platform, size = 16, mono = false, className }: {
  platform: string; size?: number; mono?: boolean; className?: string;
}) {
  const mark = PLATFORMS[platform];
  if (!mark) {
    return <FlaskConical aria-label={platformLabel(platform)} width={size} height={size} className={cn("text-ink-2", className)} />;
  }
  return (
    <svg role="img" aria-label={mark.label} width={size} height={size} viewBox="0 0 24 24"
         className={cn("shrink-0", className)} style={mono ? undefined : { color: mark.color }}>
      <path fill="currentColor" d={mark.path} />
    </svg>
  );
}
