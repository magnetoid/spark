"""Numbers and lists for the Today page."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Post, PostStatus, SocialAccount
from spark.services import analytics, channel_health, scheduler
from spark.services import inbox as inbox_svc
from spark.services.publisher import as_utc

LIVE = (
    PostStatus.scheduled,
    PostStatus.pending_approval,
    PostStatus.publishing,
    PostStatus.published,
    PostStatus.failed,
)


async def today(db: AsyncSession, brand: Brand) -> dict:
    zone = ZoneInfo(brand.timezone or "UTC")
    now = datetime.now(UTC)
    local = now.astimezone(zone)
    start = datetime.combine(local.date(), datetime.min.time(), zone).astimezone(UTC)
    end = start + timedelta(days=1)

    rows = (
        (
            await db.execute(
                select(Post)
                .where(
                    Post.brand_id == brand.id,
                    Post.is_autosave.is_(False),
                    Post.status.in_(LIVE),
                    Post.scheduled_at >= start,
                    Post.scheduled_at < end,
                )
                .order_by(Post.scheduled_at)
            )
        )
        .scalars()
        .all()
    )
    timeline = [
        {
            "post_id": p.id,
            "at": as_utc(p.scheduled_at),
            "status": p.status.value,
            "content": p.content[:160],
            "channels": [
                {
                    "account_id": t.account_id,
                    "platform": t.account.platform,
                    "handle": t.account.handle,
                    "status": t.status.value,
                }
                for t in p.targets
            ],
        }
        for p in rows
    ]
    taken = {as_utc(p.scheduled_at).replace(second=0, microsecond=0) for p in rows}
    slots = await scheduler.brand_slots(db, brand)
    free = sum(
        1
        for when in scheduler.next_slot_times(slots, brand.timezone, now, count=50)
        if when < end and when.replace(second=0, microsecond=0) not in taken
    )

    async def count(status: PostStatus) -> int:
        return (
            await db.scalar(
                select(func.count(Post.id)).where(
                    Post.brand_id == brand.id, Post.is_autosave.is_(False), Post.status == status
                )
            )
            or 0
        )

    needs_you = {
        "approvals": await count(PostStatus.pending_approval),
        "failed": await count(PostStatus.failed),
        # plan drafts have their own line ("plan_ready"); counting them here showed them twice
        "drafts": await db.scalar(
            select(func.count(Post.id)).where(
                Post.brand_id == brand.id,
                Post.is_autosave.is_(False),
                Post.status == PostStatus.draft,
                Post.agent_run_id.is_(None),
            )
        )
        or 0,
        "plan_ready": await db.scalar(
            select(func.count(Post.id)).where(
                Post.brand_id == brand.id,
                Post.is_autosave.is_(False),
                Post.status == PostStatus.draft,
                Post.agent_run_id.is_not(None),
            )
        )
        or 0,
        "replies": await inbox_svc.open_count(db, brand.id),
        "channels": sum(
            1
            for a in (
                await db.execute(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
            ).scalars()
            if channel_health.health(a) in ("reconnect", "expiring")
        ),
    }

    data = await analytics.overview(db, brand.id, days=7)
    prev = await analytics.compare(db, brand.id, days=7)
    series = data["series"]
    week = {
        "published": data["published"],
        "impressions": data["totals"]["impressions"],
        "engagements": data["engagements"],
        "engagement_rate_pct": round(data["engagement_rate"], 2),
        "change_pct": {"impressions": prev["impressions"], "engagements": prev["engagements"]},
        "series": [
            {"day": str(d), "impressions": i, "engagements": e}
            for d, i, e in zip(
                series["days"], series["impressions"], series["engagements"], strict=False
            )
        ][-7:],
    }
    return {
        "date": local.date().isoformat(),
        "timezone": brand.timezone,
        "now": now,
        "timeline": timeline,
        "free_slots_today": free,
        "needs_you": needs_you,
        "week": week,
    }
