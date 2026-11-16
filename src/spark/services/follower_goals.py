"""Follower goals with a forecast.

A channel can have a follower target and, optionally, a date. The forecast is a straight line
through the channel's own daily follower counts (the last 60 days, at least 7 readings over two
weeks): its slope is the growth per day. From it come the expected count on the date, when the
target is reached at this pace, and what a week needs to reach it in time.

Next to it, the channel's posting rate and growth over the last twelve full weeks: the weeks with
more posts against the others, with how many weeks each average rests on. It shows what went
together, not a cause, and is left out below six weeks.
"""

from __future__ import annotations

import math
import statistics
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Post, PostStatus, PostTarget, SocialAccount
from spark.models.reports import FollowerSnapshot

WINDOW_DAYS = 60
MIN_READINGS = 7
MIN_SPAN_DAYS = 14
DRIVER_WEEKS = 12
MIN_DRIVER_WEEKS = 6


def slope_per_day(points: list[tuple[date, int]]) -> float | None:
    """Least-squares growth per day, or None when the history is too short to trust."""
    if len(points) < MIN_READINGS or (points[-1][0] - points[0][0]).days < MIN_SPAN_DAYS:
        return None
    xs = [(d - points[0][0]).days for d, _ in points]
    ys = [n for _, n in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / den if den else None


def _forecast(acc: SocialAccount, current: int | None, slope: float | None, today: date) -> dict:
    goal, by = acc.follower_goal, acc.follower_goal_by
    out = {
        "per_week": round(slope * 7) if slope is not None else None,
        "eta": None,
        "expected_by_date": None,
        "needed_per_week": None,
        "status": None,
    }
    if slope is not None and by is not None and current is not None:
        out["expected_by_date"] = current + round(slope * max(0, (by - today).days))
    if not goal or current is None:
        return out
    left = goal - current
    if left <= 0:
        out["status"] = "reached"
        return out
    if by is not None and by > today:
        out["needed_per_week"] = math.ceil(left / ((by - today).days / 7))
    if slope is None:
        out["status"] = "learning"
        return out
    if slope <= 0:
        out["status"] = "stalled"
        return out
    out["eta"] = today + timedelta(days=math.ceil(left / slope - 1e-9))
    out["status"] = "behind" if by is not None and out["eta"] > by else "on_track"
    return out


def _driver(snaps: list[tuple[date, int]], posts: list[date], today: date) -> dict | None:
    """Weekly follower gain in the weeks with more posts against the others."""
    this_monday = today - timedelta(days=today.weekday())
    ends: dict[date, int] = {}  # week's Monday -> last reading that week
    for d, n in snaps:
        ends[d - timedelta(days=d.weekday())] = n  # snaps are in day order
    weeks = []
    for k in range(DRIVER_WEEKS, 0, -1):
        monday = this_monday - timedelta(weeks=k)
        prev = monday - timedelta(weeks=1)
        if monday in ends and prev in ends:
            count = sum(1 for p in posts if monday <= p < monday + timedelta(weeks=1))
            weeks.append((count, ends[monday] - ends[prev]))
    if len(weeks) < MIN_DRIVER_WEEKS:
        return None
    threshold = max(1, math.ceil(statistics.median(c for c, _ in weeks)))
    more = [g for c, g in weeks if c >= threshold]
    less = [g for c, g in weeks if c < threshold]
    if not more or not less:
        return None
    return {
        "threshold": threshold,
        "gain_more": round(sum(more) / len(more)),
        "gain_less": round(sum(less) / len(less)),
        "weeks_more": len(more),
        "weeks_less": len(less),
    }


async def brand_goals(db: AsyncSession, brand: Brand, today: date | None = None) -> list[dict]:
    """Every active channel: followers now, its goal and forecast, and the posting-rate comparison."""
    today = today or datetime.now(UTC).date()
    accounts = list(
        (
            await db.execute(
                select(SocialAccount)
                .where(SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True))
                .order_by(SocialAccount.platform, SocialAccount.handle)
            )
        ).scalars()
    )
    oldest = today - timedelta(weeks=DRIVER_WEEKS + 2)
    out = []
    for acc in accounts:
        snaps = [
            (d, n)
            for d, n in (
                await db.execute(
                    select(FollowerSnapshot.day, FollowerSnapshot.followers)
                    .where(
                        FollowerSnapshot.account_id == acc.id,
                        FollowerSnapshot.day >= min(oldest, today - timedelta(days=WINDOW_DAYS)),
                        FollowerSnapshot.day <= today,
                    )
                    .order_by(FollowerSnapshot.day)
                )
            ).all()
        ]
        recent = [(d, n) for d, n in snaps if d > today - timedelta(days=WINDOW_DAYS)]
        posts = [
            at.astimezone(UTC).date() if at.tzinfo else at.date()
            for (at,) in (
                await db.execute(
                    select(PostTarget.published_at)
                    .join(Post, Post.id == PostTarget.post_id)
                    .where(
                        PostTarget.account_id == acc.id,
                        PostTarget.status == PostStatus.published,
                        PostTarget.published_at >= datetime.combine(oldest, time(0), UTC),
                    )
                )
            ).all()
            if at is not None
        ]
        current = acc.followers if acc.followers is not None else (snaps[-1][1] if snaps else None)
        out.append(
            {
                "account_id": acc.id,
                "platform": acc.platform,
                "handle": acc.handle,
                "followers": current,
                "goal": acc.follower_goal,
                "by": acc.follower_goal_by,
                "start": acc.follower_goal_start,
                "since": acc.follower_goal_since,
                "history_days": len(recent),
                **_forecast(acc, current, slope_per_day(recent), today),
                "driver": _driver(snaps, posts, today),
            }
        )
    return out
