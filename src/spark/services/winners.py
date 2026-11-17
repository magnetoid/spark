"""Winners: recent posts in the top tenth of their own channel's engagement rate.

A channel is rated once it has ten posts with numbers in the last 90 days (posts seen by fewer
than 20 people are left out, their rates mean little). A winner went out in the last 30 days, is
in the channel's top tenth and has at least 1.5 times the channel's median rate. Each winner lists
the active channels it did not go to and the drafts already made from it. Nothing here publishes:
the offers in the API make drafts that a person schedules.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Post, PostStatus
from spark.services.analytics import _latest_metrics, rate
from spark.services.posts import active_accounts
from spark.services.publisher import as_utc
from spark.services.review import _short

POOL_DAYS = 90
RECENT_DAYS = 30
MIN_POOL = 10
TOP_SHARE = 0.10
MIN_SEEN = 20
WIN_MIN = 1.5
MAX_WINNERS = 5
KINDS = {"winner_share": "share", "winner_angle": "angle"}


def target_text(t) -> str:
    return t.content_override or (t.post.content if t.post else "")


async def find(db: AsyncSession, brand: Brand, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    rows = [
        (m, t, a)
        for m, t, a in await _latest_metrics(db, brand.id, now - timedelta(days=POOL_DAYS))
        if m.seen >= MIN_SEEN
        and t.status == PostStatus.published
        and not (t.post and t.post.is_autosave)
    ]
    by_acc: dict[int, list] = {}
    for row in rows:
        by_acc.setdefault(row[2].id, []).append(row)

    channels, found = [], []
    for acc_id, items in by_acc.items():
        acc = items[0][2]
        rates = sorted((rate(m.engagements, m.seen) for m, _t, _a in items), reverse=True)
        rated = len(rates) >= MIN_POOL
        channels.append(
            {
                "account_id": acc_id,
                "handle": acc.handle,
                "platform": acc.platform,
                "posts": len(rates),
                "rated": rated,
            }
        )
        if not rated:
            continue
        threshold = rates[max(1, int(len(rates) * TOP_SHARE)) - 1]
        median = statistics.median(rates)
        for m, t, a in items:
            r = rate(m.engagements, m.seen)
            if as_utc(t.published_at) < now - timedelta(days=RECENT_DAYS) or r < threshold:
                continue
            if r <= median or (median and r / median < WIN_MIN):
                continue
            found.append(
                {
                    "post_id": t.post_id,
                    "target_id": t.id,
                    "account_id": a.id,
                    "handle": a.handle,
                    "platform": a.platform,
                    "text": _short(target_text(t), 120),
                    "post_type": t.post_type or "post",
                    "published_at": t.published_at,
                    "engagements": m.engagements,
                    "seen": m.seen,
                    "engagement_rate_pct": r,
                    "median_rate_pct": median,
                    "vs_usual": round(r / median, 1) if median else None,
                    "channel_posts": len(rates),
                }
            )
    found.sort(key=lambda w: (w["vs_usual"] is None, -(w["vs_usual"] or 0)))
    found = found[:MAX_WINNERS]

    active = await active_accounts(db, brand)
    post_ids = {w["post_id"] for w in found}
    copies = (
        (
            await db.execute(
                select(Post).where(
                    Post.recycled_from_id.in_(post_ids),
                    Post.source.in_(KINDS),
                    Post.is_autosave.is_(False),
                )
            )
        )
        .scalars()
        .all()
        if post_ids
        else []
    )
    originals = (
        {p.id: p for p in (await db.execute(select(Post).where(Post.id.in_(post_ids)))).scalars()}
        if post_ids
        else {}
    )
    for w in found:
        mine = [c for c in copies if c.recycled_from_id == w["post_id"]]
        went = {t.account_id for t in originals[w["post_id"]].targets}
        went |= {t.account_id for c in mine if c.source == "winner_share" for t in c.targets}
        w["missed"] = [
            {"account_id": a.id, "platform": a.platform, "handle": a.handle}
            for a in active
            if a.id not in went
        ]
        w["follow_ups"] = [
            {"post_id": c.id, "kind": KINDS[c.source], "status": c.status.value}
            for c in sorted(mine, key=lambda c: c.id)
        ]
    return {
        "winners": found,
        "channels": channels,
        "min_posts": MIN_POOL,
        "top_share_pct": round(TOP_SHARE * 100),
        "window_days": RECENT_DAYS,
    }
