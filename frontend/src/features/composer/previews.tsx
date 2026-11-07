/**
 * How the post will look on each network. One frame per family of networks: the shapes
 * people recognise (X's compact card, LinkedIn's document feel, Instagram's square media)
 * without pretending to be pixel-perfect. Phase 8 deepens these.
 */
import { Heart, MessageCircle, Repeat2 } from "lucide-react";
import type { AccountOut, MediaOut } from "@/features/posts/api";
import { PlatformMark, platformLabel } from "@/lib/platforms";
import { cn } from "@/lib/utils";

export interface PreviewData {
  account: AccountOut;
  text: string;
  thread: string[];
  firstComment: string;
  media: MediaOut[];
  link: string;
  brandColor: string;
}

export function PostPreview({ account, text, thread, firstComment, media, link, brandColor }: PreviewData) {
  const square = account.platform === "instagram";
  const compact = ["x", "bluesky", "mastodon", "threads"].includes(account.platform);
  return (
    <article className="rounded-card border border-line bg-surface text-sm" aria-label={`${platformLabel(account.platform)} preview`}>
      <header className="flex items-center gap-2.5 px-3 pt-3">
        <Avatar account={account} color={brandColor} />
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate font-medium">{account.display_name || account.handle}</div>
          <div className="truncate text-xs text-ink-2">@{account.handle.replace(/^@/, "")} · now</div>
        </div>
        <PlatformMark platform={account.platform} size={16} />
      </header>
      <div className={cn("px-3 pt-2", compact ? "text-[14px]" : "text-[14px] leading-relaxed")}>
        <Text text={text} />
      </div>
      {media.length > 0 && <MediaGrid media={media} square={square} />}
      {!media.length && link && (
        <div className="mx-3 mt-2 overflow-hidden rounded-control border border-line">
          <div className="h-20 bg-hover" aria-hidden />
          <div className="px-2.5 py-1.5 text-xs text-ink-2 truncate">{host(link)}</div>
        </div>
      )}
      <footer className="flex items-center gap-5 px-3 py-2.5 text-ink-2">
        <MessageCircle className="size-4" aria-hidden /><Repeat2 className="size-4" aria-hidden /><Heart className="size-4" aria-hidden />
      </footer>
      {thread.map((item, i) => (
        <div key={i} className="border-t border-line px-3 py-2.5">
          <div className="mb-1 text-[11px] text-ink-2">Reply {i + 2}</div>
          <Text text={item} />
        </div>
      ))}
      {firstComment && (
        <div className="border-t border-line px-3 py-2.5">
          <div className="mb-1 text-[11px] text-ink-2">First comment</div>
          <Text text={firstComment} />
        </div>
      )}
    </article>
  );
}

function Avatar({ account, color }: { account: AccountOut; color: string }) {
  if (account.avatar_url) return <img src={account.avatar_url} alt="" className="size-9 rounded-full object-cover" />;
  return <span className="grid size-9 place-items-center rounded-full text-xs font-semibold text-white" style={{ background: color }}>{account.handle.replace(/^@/, "").slice(0, 1).toUpperCase()}</span>;
}

function Text({ text }: { text: string }) {
  if (!text) return <p className="text-ink-2">Your text shows up here…</p>;
  const parts = text.split(/(#[\p{L}\p{N}_]+|https?:\/\/\S+)/u);
  return (
    <p className="whitespace-pre-wrap break-words">
      {parts.map((p, i) => /^#|^https?:/.test(p) ? <span key={i} className="text-st-scheduled">{p}</span> : <span key={i}>{p}</span>)}
    </p>
  );
}

function MediaGrid({ media, square }: { media: MediaOut[]; square: boolean }) {
  const shown = media.slice(0, 4);
  return (
    <div className={cn("mt-2 grid gap-0.5 overflow-hidden", shown.length > 1 ? "grid-cols-2" : "grid-cols-1", square ? "" : "mx-3 rounded-control")}>
      {shown.map((m, i) => (
        <div key={m.id} className={cn("relative bg-hover", square ? "aspect-square" : "aspect-video")}>
          {m.is_video ? <div className="grid h-full place-items-center text-xs text-ink-2">▶ video</div>
                      : <img src={m.url} alt={m.alt_text ?? ""} className="h-full w-full object-cover" />}
          {i === 3 && media.length > 4 && <div className="absolute inset-0 grid place-items-center bg-black/50 text-white">+{media.length - 4}</div>}
        </div>
      ))}
    </div>
  );
}

function host(url: string) {
  try { return new URL(url).host; } catch { return url; }
}
