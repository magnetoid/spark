"""How publishing is going for one brand: success rates, why posts fail, what is next per channel."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, PostStatus, PostTarget, SocialAccount

STUCK_AFTER = timedelta(minutes=30)
_ATTEMPT = re.compile(r"^Attempt \d+ failed, retrying in \d+m: ")


def reason(error: str | None) -> str:
    """One failure reason, comparable across posts: no retry preamble, first line, 120 chars."""
    text = _ATTEMPT.sub("", (error or "Unknown error").strip())
    return (text.splitlines() or ["Unknown error"])[0][:120]


def _rate(published: int, failed: int) -> dict:
    total = published + failed
    return {
        "published": published,
        "failed": failed,
        "success_rate_pct": round(100 * published / total, 1) if total else None,
    }


async def summary(db: AsyncSession, brand: Brand, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    accounts = (
        (
            await db.execute(
                select(SocialAccount)
                .where(SocialAccount.brand_id == brand.id)
                .order_by(SocialAccount.platform, SocialAccount.handle)
            )
        )
        .scalars()
        .all()
    )
    ids = [a.id for a in accounts]
    by_id = {a.id: a for a in accounts}
    if not ids:
        return {
            "week": _rate(0, 0),
            "month": _rate(0, 0),
            "failures_by_reason": [],
            "failures_by_channel": [],
            "channels": [],
            "stuck": 0,
        }

    async def published_since(days: int) -> int:
        return (
            await db.scalar(
                select(func.count(PostTarget.id)).where(
                    PostTarget.account_id.in_(ids),
                    PostTarget.status == PostStatus.published,
                    PostTarget.published_at >= now - timedelta(days=days),
                )
            )
            or 0
        )

    month_failed = (
        (
            await db.execute(
                select(PostTarget).where(
                    PostTarget.account_id.in_(ids),
                    PostTarget.status == PostStatus.failed,
                    PostTarget.updated_at >= now - timedelta(days=30),
                )
            )
        )
        .scalars()
        .all()
    )

    def aware(dt):
        return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)

    week_failed = [t for t in month_failed if aware(t.updated_at) >= now - timedelta(days=7)]
    reasons = Counter(reason(t.error) for t in month_failed)
    per_channel = Counter(t.account_id for t in month_failed)
    next_rows = await db.execute(
        select(PostTarget.account_id, func.min(PostTarget.scheduled_at))
        .where(
            PostTarget.account_id.in_(ids),
            PostTarget.status == PostStatus.scheduled,
            PostTarget.scheduled_at >= now,
        )
        .group_by(PostTarget.account_id)
    )
    next_at = {aid: aware(when) for aid, when in next_rows}
    stuck = (
        await db.scalar(
            select(func.count(PostTarget.id)).where(
                PostTarget.account_id.in_(ids),
                PostTarget.status == PostStatus.publishing,
                PostTarget.updated_at < now - STUCK_AFTER,
            )
        )
        or 0
    )
    return {
        "week": _rate(await published_since(7), len(week_failed)),
        "month": _rate(await published_since(30), len(month_failed)),
        "failures_by_reason": [{"reason": r, "count": n} for r, n in reasons.most_common(10)],
        "failures_by_channel": [
            {
                "account_id": aid,
                "handle": by_id[aid].handle,
                "platform": by_id[aid].platform,
                "failed": n,
            }
            for aid, n in per_channel.most_common()
        ],
        "channels": [{"account": a, "next_scheduled_at": next_at.get(a.id)} for a in accounts],
        "stuck": stuck,
    }
