"""Posts of a brand: list with filters, read one. Writes arrive in Phase 3."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import not_found
from spark.api.schemas import PostOut, PostPage, PostStatusName
from spark.db import get_db
from spark.models import Post, PostStatus, PostTarget

router = APIRouter(tags=["posts"])


@router.get("/brands/{brand_id}/posts", response_model=PostPage)
async def list_posts(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx),
    status: PostStatusName | None = None, account: int | None = None, campaign: int | None = None,
    q: str | None = None, since: datetime | None = None, until: datetime | None = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
):
    stmt = select(Post).where(Post.brand_id == ctx.brand.id, Post.is_autosave.is_(False))
    if status:
        stmt = stmt.where(Post.status == PostStatus(status))
    if account:
        stmt = stmt.where(Post.id.in_(select(PostTarget.post_id).where(PostTarget.account_id == account)))
    if campaign:
        stmt = stmt.where(Post.campaign_id == campaign)
    if q:
        stmt = stmt.where(Post.content.ilike(f"%{q}%"))
    if since:
        stmt = stmt.where(Post.scheduled_at >= since)
    if until:
        stmt = stmt.where(Post.scheduled_at < until)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    if status in ("scheduled", "pending_approval", "publishing"):
        stmt = stmt.order_by(Post.scheduled_at.asc())
    else:
        stmt = stmt.order_by(Post.scheduled_at.desc().nulls_first(), Post.id.desc())
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return PostPage(items=[PostOut.of(p) for p in rows], total=total or 0, limit=limit, offset=offset)


@router.get("/brands/{brand_id}/posts/{post_id}", response_model=PostOut)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    post = await db.get(Post, post_id)
    if not post or post.brand_id != ctx.brand.id or post.is_autosave:
        raise not_found("No such post")
    return PostOut.of(post)
