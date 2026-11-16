"""Posting goals: a weekly target per channel and the weeks in a row it was met."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import not_found
from spark.api.schemas import GoalsIn, GoalsOut
from spark.db import get_db
from spark.models import SocialAccount
from spark.services import activity, goals

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
