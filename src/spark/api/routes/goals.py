"""Posting goals (a weekly target per channel and the weeks in a row it was met) and follower
goals with a forecast."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    FollowerGoalsIn,
    FollowerGoalsOut,
    GoalsIn,
    GoalsOut,
    WeeklyReviewOut,
)
from spark.db import get_db
from spark.models import SocialAccount
from spark.services import activity, follower_goals, goals, review

router = APIRouter(prefix="/brands/{brand_id}", tags=["goals"])


@router.get("/goals", response_model=GoalsOut)
async def get_goals(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    """This week per channel (published, planned, still needed) and the streak of weeks met."""
    return await goals.channel_goals(db, ctx.brand)


@router.put("/goals", response_model=GoalsOut)
async def set_goals(
    body: GoalsIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    """Set or clear weekly goals. A changed goal starts its streak again; an unchanged one keeps it."""
    accounts = []
    for g in body.goals:
        acc = await db.get(SocialAccount, g.account_id)
        if acc is None or acc.brand_id != ctx.brand.id:
            raise not_found("No such channel")
        accounts.append((acc, g.posts_per_week))
    now = datetime.now(UTC)
    changed = []
    for acc, goal in accounts:
        if acc.posting_goal == goal:
            continue
        acc.posting_goal = goal
        acc.posting_goal_since = now if goal else None
        changed.append(f"@{acc.handle} {f'{goal} a week' if goal else 'off'}")
    if changed:
        activity.record(
            db, ctx.brand.id, ctx.user, "set goals", "channel", None, "; ".join(changed)
        )
    await db.commit()
    return await goals.channel_goals(db, ctx.brand, now)


@router.get("/follower-goals", response_model=FollowerGoalsOut)
async def get_follower_goals(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    """Followers per channel, the goal and its forecast from the channel's own history."""
    return {"channels": await follower_goals.brand_goals(db, ctx.brand)}


@router.put("/follower-goals", response_model=FollowerGoalsOut)
async def set_follower_goals(
    body: FollowerGoalsIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    """Set or clear follower goals. A changed goal remembers today's followers as its start."""
    today = datetime.now(UTC).date()
    accounts = []
    for g in body.goals:
        acc = await db.get(SocialAccount, g.account_id)
        if acc is None or acc.brand_id != ctx.brand.id:
            raise not_found("No such channel")
        if g.target and g.by is not None and g.by <= today:
            raise ApiError(422, "date_in_past", "Pick a date after today")
        accounts.append((acc, g.target, g.by if g.target else None))
    changed = []
    for acc, target, by in accounts:
        if (acc.follower_goal, acc.follower_goal_by) == (target, by):
            continue
        acc.follower_goal, acc.follower_goal_by = target, by
        acc.follower_goal_start = acc.followers if target else None
        acc.follower_goal_since = today if target else None
        changed.append(
            f"@{acc.handle} "
            + (f"{target:,} followers" + (f" by {by:%b %d, %Y}" if by else "") if target else "off")
        )
    if changed:
        activity.record(
            db, ctx.brand.id, ctx.user, "set follower goals", "channel", None, "; ".join(changed)
        )
    await db.commit()
    return {"channels": await follower_goals.brand_goals(db, ctx.brand, today)}


@router.get("/weekly-review", response_model=WeeklyReviewOut)
async def weekly_review(
    week: date | None = None,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
):
    """A week's posts against each channel's own usual, with plain findings. `week` is any day
    of the week wanted; without it, last week."""
    return await review.weekly_review(db, ctx.brand, week)
