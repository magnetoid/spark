"""Campaigns: a goal, a date range, a colour, and optionally an AI-planned set of draft posts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Campaign, Post, PostStatus, PostTarget, SocialAccount, User
from spark.services.ai import AIUnavailable, ContentAI


def _midnight(d: date | None, tz: str) -> datetime | None:
    return datetime.combine(d, datetime.min.time(), ZoneInfo(tz)) if d else None


async def create(
    db: AsyncSession,
    brand: Brand,
    *,
    name: str,
    goal: str | None,
    starts_on: date | None,
    ends_on: date | None,
    utm_campaign: str | None,
    color: str,
) -> Campaign:
    c = Campaign(
        brand_id=brand.id,
        name=name.strip(),
        goal=(goal or "").strip() or None,
        starts_on=_midnight(starts_on, brand.timezone),
        ends_on=_midnight(ends_on, brand.timezone),
        utm_campaign=(utm_campaign or "").strip() or None,
        color=color,
    )
    db.add(c)
    await db.flush()
    return c


async def plan_with_ai(
    db: AsyncSession,
    brand: Brand,
    user: User,
    campaign: Campaign,
    starts_on: date,
    ends_on: date,
    account_ids: list[int],
    per_week: int = 3,
) -> int:
    """Ask the AI for a post plan and create one draft per planned post. Raises AIUnavailable/ValueError."""
    accounts = (
        (
            await db.execute(
                select(SocialAccount).where(
                    SocialAccount.brand_id == brand.id,
                    SocialAccount.id.in_(account_ids),
                    SocialAccount.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if not accounts:
        raise ValueError("Pick at least one channel for the AI plan")
    if not campaign.goal:
        raise ValueError("The AI plan needs a goal")
    plan = await ContentAI().plan_campaign(
        brand, campaign.goal, starts_on, ends_on, sorted({a.platform for a in accounts}), per_week
    )
    zone = ZoneInfo(brand.timezone)
    created = 0
    for pp in plan.posts:
        targets = [PostTarget(account_id=a.id) for a in accounts if a.platform in pp.platforms]
        if not targets:
            continue
        try:
            day = date.fromisoformat(pp.date)
        except ValueError:
            continue
        post = Post(
            brand_id=brand.id,
            author_id=user.id,
            campaign_id=campaign.id,
            content=pp.text,
            source="ai",
            notes=f"Theme: {pp.theme}",
            scheduled_at=(
                datetime.combine(day, datetime.min.time(), zone) + timedelta(hours=10)
            ).astimezone(UTC),
        )
        post.targets = targets
        db.add(post)
        created += 1
    return created


async def counts(db: AsyncSession, brand: Brand) -> dict[int, dict[str, int]]:
    rows = (
        await db.execute(
            select(Post.campaign_id, Post.status, func.count(Post.id))
            .where(
                Post.brand_id == brand.id,
                Post.campaign_id.is_not(None),
                Post.is_autosave.is_(False),
            )
            .group_by(Post.campaign_id, Post.status)
        )
    ).all()
    out: dict[int, dict[str, int]] = {}
    for cid, status, n in rows:
        d = out.setdefault(cid, {"total": 0, **{s.value: 0 for s in PostStatus}})
        d[status.value] += n
        d["total"] += n
    return out


def empty_counts() -> dict[str, int]:
    return {"total": 0, **{s.value: 0 for s in PostStatus}}


__all__ = ["create", "plan_with_ai", "counts", "empty_counts", "AIUnavailable"]
