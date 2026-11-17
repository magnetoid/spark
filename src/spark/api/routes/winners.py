"""Winners: posts in the top tenth of their channel's own rate, and two offers for each (a new
angle written by the AI, or a copy for the channels that missed it). Both make drafts only."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import WinnerAngleIn, WinnerDraftOut, WinnerShareIn, WinnersOut
from spark.db import get_db
from spark.models import Post, PostStatus, PostTarget, SocialAccount
from spark.platforms import adapter_for
from spark.services import activity, winners
from spark.services.ai import AIUnavailable, ContentAI
from spark.services.posts import active_accounts

router = APIRouter(prefix="/brands/{brand_id}", tags=["analytics"])

ANGLE = (
    "Write a fresh post on the same core idea from a new angle: a different hook and opening, "
    "a different example or point of view. Keep the brand's voice and any link. Do not repeat "
    "the original's first sentence."
)


def _ai() -> ContentAI:
    return ContentAI()


async def _published_target(db: AsyncSession, brand_id: int, target_id: int) -> PostTarget:
    t = await db.get(PostTarget, target_id, options=[selectinload(PostTarget.post)])
    acc = await db.get(SocialAccount, t.account_id) if t else None
    if t is None or acc is None or acc.brand_id != brand_id or t.status != PostStatus.published:
        raise not_found("No such published post")
    return t


def _copy(src: Post, user_id: int | None, content: str, source: str) -> Post:
    return Post(
        brand_id=src.brand_id,
        author_id=user_id,
        content=content,
        link=src.link,
        media_ids=list(src.media_ids or []),
        campaign_id=src.campaign_id,
        pillar_id=src.pillar_id,
        source=source,
        recycled_from_id=src.id,
        status=PostStatus.draft,
    )


def _target_for(acc: SocialAccount, t: PostTarget) -> PostTarget:
    ad = adapter_for(acc)
    kind = t.post_type or "post"
    return PostTarget(
        account_id=acc.id,
        status=PostStatus.draft,
        post_type=kind if kind in ad.post_types else "post",
        first_comment=t.first_comment if ad.supports_first_comment else None,
    )


@router.get("/winners", response_model=WinnersOut)
async def get_winners(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    """Recent posts in the top tenth of their own channel's engagement rate, with what to do next."""
    return await winners.find(db, ctx.brand)


@router.post("/winners/{target_id}/share", response_model=WinnerDraftOut)
async def share_winner(
    target_id: int,
    body: WinnerShareIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    """A draft of the winning post for channels it did not go to. A person schedules it."""
    t = await _published_target(db, ctx.brand.id, target_id)
    src = t.post
    await db.refresh(src, ["targets"])
    went = {x.account_id for x in src.targets}
    active = {a.id: a for a in await active_accounts(db, ctx.brand)}
    picked = []
    for acc_id in dict.fromkeys(body.account_ids):
        if acc_id not in active or acc_id in went:
            raise ApiError(422, "unknown_channel", "Pick active channels the post did not go to")
        picked.append(active[acc_id])
    draft = _copy(src, ctx.user.id, winners.target_text(t), "winner_share")
    draft.targets = [_target_for(a, t) for a in picked]
    db.add(draft)
    await db.flush()
    names = ", ".join(f"@{a.handle}" for a in picked)
    activity.record(
        db,
        ctx.brand.id,
        ctx.user,
        "drafted",
        "post",
        draft.id,
        f"A copy of a winning post for {names}",
    )
    await db.commit()
    return {"post_id": draft.id, "message": f"Draft made for {names}"}


@router.post("/winners/{target_id}/new-angle", response_model=WinnerDraftOut)
async def new_angle(
    target_id: int,
    body: WinnerAngleIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    """The AI writes the winning idea from a new angle for the same channel, as a draft."""
    t = await _published_target(db, ctx.brand.id, target_id)
    acc = await db.get(SocialAccount, t.account_id)
    instruction = ANGLE + (f" Also: {body.instruction}" if body.instruction else "")
    try:
        text = await _ai().rewrite(ctx.brand, winners.target_text(t), instruction, acc.platform)
    except AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e))
    draft = _copy(t.post, ctx.user.id, text, "winner_angle")
    draft.targets = [_target_for(acc, t)]
    db.add(draft)
    await db.flush()
    activity.record(
        db,
        ctx.brand.id,
        ctx.user,
        "drafted",
        "post",
        draft.id,
        f"A new angle on a winning post for @{acc.handle}",
    )
    await db.commit()
    return {"post_id": draft.id, "message": f"New angle drafted for @{acc.handle}"}
