"""Queues, scheduling transitions and best-time suggestions."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import (
    Brand,
    Metric,
    Post,
    PostStatus,
    PostTarget,
    QueueSlot,
    SocialAccount,
    User,
)
from spark.services.publisher import as_utc

DEFAULT_SLOTS = ("09:00", "12:30", "17:00")


def next_slot_times(slots: list[QueueSlot], tz: str, after: datetime, count: int = 50):
    """Yield upcoming slot datetimes (UTC) after `after`, in order."""
    zone = ZoneInfo(tz)
    local = after.astimezone(zone)
    by_day: dict[int, list[str]] = defaultdict(list)
    for s in slots:
        by_day[s.weekday].append(s.time)
    out = []
    for offset in range(0, 7 * 8):
        day = (local + timedelta(days=offset)).date()
        for t in sorted(by_day.get(day.weekday(), [])):
            h, m = map(int, t.split(":"))
            dt = datetime(day.year, day.month, day.day, h, m, tzinfo=zone)
            if dt > local:
                out.append(dt.astimezone(UTC))
                if len(out) >= count:
                    return out
    return out


async def next_free_slot(db: AsyncSession, brand: Brand, after: datetime | None = None) -> datetime:
    after = after or datetime.now(UTC)
    slots = (await db.execute(select(QueueSlot).where(QueueSlot.brand_id == brand.id))).scalars().all()
    if not slots:
        slots = [QueueSlot(weekday=d, time=t) for d in range(7) for t in DEFAULT_SLOTS]
    taken_rows = await db.execute(
        select(Post.scheduled_at).where(
            Post.brand_id == brand.id,
            Post.scheduled_at >= after,
            Post.status.in_([PostStatus.scheduled, PostStatus.pending_approval]),
        )
    )
    taken = {as_utc(r).replace(second=0, microsecond=0) for (r,) in taken_rows if r}
    for dt in next_slot_times(slots, brand.timezone, after, count=500):
        if dt not in taken:
            return dt
    return after + timedelta(hours=1)


def schedule(post: Post, when: datetime, user: User, brand: Brand) -> PostStatus:
    """Move a post (and its targets) into the queue, respecting approval."""
    needs_approval = brand.require_approval and not user.can_approve()
    status = PostStatus.pending_approval if needs_approval else PostStatus.scheduled
    post.scheduled_at = when
    post.status = status
    for t in post.targets:
        if t.status in (PostStatus.published,):
            continue
        t.status = status
        t.scheduled_at = when
        t.attempts = 0
        t.next_attempt_at = None
        t.error = None
    return status


def approve(post: Post) -> None:
    for t in post.targets:
        if t.status == PostStatus.pending_approval:
            t.status = PostStatus.scheduled
    post.status = PostStatus.scheduled


def unschedule(post: Post) -> None:
    for t in post.targets:
        if t.status in (PostStatus.scheduled, PostStatus.pending_approval, PostStatus.failed):
            t.status = PostStatus.draft
    post.status = PostStatus.draft


async def best_times(db: AsyncSession, brand_id: int, top: int = 5) -> list[dict]:
    """Rank (weekday, hour) by average engagement rate of past posts."""
    brand = await db.get(Brand, brand_id)
    zone = ZoneInfo(brand.timezone if brand else "UTC")
    rows = await db.execute(
        select(PostTarget.published_at, Metric)
        .join(Metric, Metric.target_id == PostTarget.id)
        .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
        .where(SocialAccount.brand_id == brand_id, PostTarget.published_at.is_not(None))
    )
    latest: dict[int, tuple[datetime, Metric]] = {}
    for published_at, metric in rows:
        cur = latest.get(metric.target_id)
        if cur is None or as_utc(metric.captured_at) > as_utc(cur[1].captured_at):
            latest[metric.target_id] = (published_at, metric)
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for published_at, m in latest.values():
        local = as_utc(published_at).astimezone(zone)
        rate = m.engagements / m.impressions if m.impressions else float(m.engagements)
        buckets[(local.weekday(), local.hour)].append(rate)
    ranked = sorted(
        ({"weekday": d, "hour": h, "score": sum(v) / len(v), "posts": len(v)} for (d, h), v in buckets.items()),
        key=lambda r: r["score"],
        reverse=True,
    )
    return ranked[:top]
