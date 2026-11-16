"""The weekly review: each post of a week against its own channel's usual, not industry averages.

"Usual" is the median engagements (and median impressions, views or reach) of the channel's
posts in the 90 days before the week, from at least five posts with numbers. A post at 1.5 times
the usual or more is "above", at half or less "below". The findings are plain sentences: the
best and quietest post, formats and pillars that beat or trailed the usual (two posts or more),
and the posting volume against the week before. The weekly plan run reads them.
"""

from __future__ import annotations

import statistics
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.models import Brand, ContentPillar, Post, PostStatus, PostTarget, SocialAccount
from spark.services.analytics import _latest_metrics, rate

BASELINE_DAYS = 90
MIN_BASELINE = 5
ABOVE, BELOW = 1.5, 0.5
GROUP_UP, GROUP_DOWN = 1.3, 0.7
MAX_FINDINGS = 5
FORMATS = {
    "post": "Regular posts",
    "reel": "Reels",
    "story": "Stories",
    "carousel": "Carousels",
    "document": "Documents",
}


def _today(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def _utc(d: date, tz: str) -> datetime:
    return datetime.combine(d, time(0), ZoneInfo(tz)).astimezone(UTC)


def _x(r: float) -> str:
    return f"{r:.1f}×"


def _short(text: str, n: int = 60) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


async def weekly_review(
    db: AsyncSession, brand: Brand, week: date | None = None, today: date | None = None
) -> dict:
    """The week containing `week` (default: last full week, Monday to Sunday in the brand's zone)."""
    tz = brand.timezone
    today = today or _today(tz)
    ws = (
        week - timedelta(days=week.weekday())
        if week
        else today - timedelta(days=today.weekday() + 7)
    )
    start, end = _utc(ws, tz), _utc(ws + timedelta(days=7), tz)

    metrics = await _latest_metrics(db, brand.id, start - timedelta(days=BASELINE_DAYS), end)
    by_target = {t.id: m for m, t, _a in metrics}
    earlier: dict[int, list] = {}
    for m, t, a in metrics:
        at = t.published_at
        if at is not None and (at if at.tzinfo else at.replace(tzinfo=UTC)) < start:
            earlier.setdefault(a.id, []).append(m)

    rows = (
        await db.execute(
            select(PostTarget, SocialAccount)
            .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
            .join(Post, Post.id == PostTarget.post_id)
            .where(
                SocialAccount.brand_id == brand.id,
                PostTarget.status == PostStatus.published,
                PostTarget.published_at >= start,
                PostTarget.published_at < end,
                Post.is_autosave.is_(False),
            )
            .options(selectinload(PostTarget.post))
            .order_by(PostTarget.published_at)
        )
    ).all()
    pillars = {
        p.id: p.name
        for p in (
            await db.execute(select(ContentPillar).where(ContentPillar.brand_id == brand.id))
        ).scalars()
    }

    baselines = {}
    for acc_id, ms in earlier.items():
        if len(ms) >= MIN_BASELINE:
            baselines[acc_id] = {
                "median_engagements": statistics.median(m.engagements for m in ms),
                "median_seen": statistics.median(m.seen for m in ms),
                "posts": len(ms),
            }

    posts = []
    for t, a in rows:
        m = by_target.get(t.id)
        base = baselines.get(a.id)
        vs, vs_seen, verdict = None, None, "unrated"
        if m is not None and base is not None:
            med = base["median_engagements"]
            if med:
                vs = round(m.engagements / med, 1)
                verdict = "above" if vs >= ABOVE else "below" if vs <= BELOW else "usual"
            else:
                verdict = "above" if m.engagements else "usual"
            if base["median_seen"]:
                vs_seen = round(m.seen / base["median_seen"], 1)
        posts.append(
            {
                "post_id": t.post_id,
                "target_id": t.id,
                "account_id": a.id,
                "handle": a.handle,
                "platform": a.platform,
                "text": _short(t.content_override or (t.post.content if t.post else "")),
                "post_type": t.post_type or "post",
                "pillar": pillars.get(t.post.pillar_id) if t.post else None,
                "published_at": t.published_at,
                "engagements": m.engagements if m else None,
                "seen": m.seen if m else None,
                "engagement_rate_pct": rate(m.engagements, m.seen) if m else None,
                "vs_usual": vs,
                "vs_usual_seen": vs_seen,
                "verdict": verdict,
            }
        )

    counts = {"posts": len(posts), "above": 0, "usual": 0, "below": 0, "unrated": 0}
    for p in posts:
        counts[p["verdict"]] += 1

    prev_count = (
        await db.scalar(
            select(func.count(PostTarget.id))
            .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
            .where(
                SocialAccount.brand_id == brand.id,
                PostTarget.status == PostStatus.published,
                PostTarget.published_at >= _utc(ws - timedelta(days=7), tz),
                PostTarget.published_at < start,
            )
        )
        or 0
    )

    return {
        "week_start": ws,
        "week_end": ws + timedelta(days=6),
        "posts": posts,
        "counts": counts,
        "baselines": [
            {
                "account_id": a_id,
                "handle": next((p["handle"] for p in posts if p["account_id"] == a_id), ""),
                **b,
            }
            for a_id, b in baselines.items()
        ],
        "findings": _findings(posts, prev_count),
        "previous_week_posts": prev_count,
    }


def _findings(posts: list[dict], prev_count: int) -> list[str]:
    out: list[str] = []
    rated = [p for p in posts if p["vs_usual"] is not None]
    if rated:
        best = max(rated, key=lambda p: p["vs_usual"])
        if best["verdict"] == "above":
            out.append(
                f"Best: “{best['text']}” on @{best['handle']} got {_x(best['vs_usual'])} "
                "its channel's usual engagements."
            )
        worst = min(rated, key=lambda p: p["vs_usual"])
        if worst["verdict"] == "below":
            out.append(
                f"Quietest: “{worst['text']}” on @{worst['handle']}, {_x(worst['vs_usual'])} "
                "its channel's usual."
            )
    for label, key in (("type", "post_type"), ("pillar", "pillar")):
        groups: dict[str, list[float]] = {}
        for p in rated:
            if p[key]:
                groups.setdefault(p[key], []).append(p["vs_usual"])
        for name, vals in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            if len(vals) < 2:
                continue
            med = statistics.median(vals)
            what = (
                FORMATS.get(name, f"{name.capitalize()} posts")
                if label == "type"
                else f"“{name}” posts"
            )
            if med >= GROUP_UP:
                out.append(f"{what} did {_x(med)} their channel's usual ({len(vals)} posts).")
            elif med <= GROUP_DOWN:
                out.append(f"{what} did only {_x(med)} their channel's usual ({len(vals)} posts).")
    if posts and prev_count and len(posts) != prev_count:
        out.append(f"{len(posts)} posts went out, against {prev_count} the week before.")
    elif not posts:
        out.append("Nothing was published that week.")
    return out[:MAX_FINDINGS]
