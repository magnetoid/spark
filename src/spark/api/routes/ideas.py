"""The Ideas board."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import IdeaBoard, IdeaIn, IdeaMove, IdeaOut, IdeaUpdate, PostOut, PostResult
from spark.db import get_db
from spark.models import Idea
from spark.services import ideas as svc
from spark.services.ai import AIUnavailable

router = APIRouter(tags=["ideas"])
B = "/brands/{brand_id}"


async def _idea(db: AsyncSession, ctx: deps.BrandCtx, idea_id: int) -> Idea:
    idea = await db.get(Idea, idea_id)
    if not idea or idea.brand_id != ctx.brand.id:
        raise not_found("No such idea")
    return idea


@router.get(B + "/ideas", response_model=IdeaBoard)
async def board(
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
    tag: str | None = None,
):
    ideas = await svc.list_ideas(db, ctx.brand)
    tags = sorted({t for i in ideas for t in (i.tags or [])})
    if tag:
        ideas = [i for i in ideas if tag in (i.tags or [])]
    return IdeaBoard(items=[IdeaOut.of(i) for i in ideas], tags=tags)


@router.post(B + "/ideas", response_model=IdeaOut, status_code=201)
async def create(
    body: IdeaIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    idea = await svc.create(
        db,
        ctx.brand,
        ctx.user,
        title=body.title,
        body=body.body,
        tags=body.tags,
        source_url=body.source_url,
        status=body.status,
    )
    return IdeaOut.of(idea)


@router.patch(B + "/ideas/{idea_id}", response_model=IdeaOut)
async def update(
    idea_id: int,
    body: IdeaUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    idea = await _idea(db, ctx, idea_id)
    svc.update(idea, **body.model_dump(exclude_unset=True))
    await db.commit()
    return IdeaOut.of(idea)


@router.post(B + "/ideas/{idea_id}/move", response_model=IdeaOut)
async def move(
    idea_id: int,
    body: IdeaMove,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    idea = await _idea(db, ctx, idea_id)
    try:
        svc.move(idea, body.status, body.position)
    except ValueError as e:
        raise ApiError(422, "validation", str(e))
    await db.commit()
    return IdeaOut.of(idea)


@router.delete(B + "/ideas/{idea_id}", status_code=204)
async def delete(
    idea_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    idea = await _idea(db, ctx, idea_id)
    await db.delete(idea)
    await db.commit()
    return Response(status_code=204)


@router.post(B + "/ideas/{idea_id}/to-post", response_model=PostResult, status_code=201)
async def to_post(
    idea_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    idea = await _idea(db, ctx, idea_id)
    post, created = await svc.to_post(db, ctx.brand, ctx.user, idea)
    return PostResult(
        message="Draft created from your idea" if created else "This idea already has a post",
        post=PostOut.of(post),
    )


@router.post(B + "/ideas/{idea_id}/ai", response_model=IdeaOut)
async def ai_expand(
    idea_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    idea = await _idea(db, ctx, idea_id)
    try:
        await svc.ai_expand(db, ctx.brand, idea)
    except AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e))
    return IdeaOut.of(idea)
