"""Posts of a brand: list, read, create, edit, place, approve, retry, move, autosave, validate.

Every write goes through `spark.services.posts`, the same code the MCP tools use, so a
post made by an assistant and a post made in the composer obey the same rules.
"""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    AutosaveIn,
    AutosaveOut,
    MoveIn,
    PlaceIn,
    PostOut,
    PostPage,
    PostResult,
    PostStatusName,
    PostWrite,
    RetryResult,
    ValidateIn,
)
from spark.db import get_db
from spark.models import Idea, Post, PostStatus, PostTarget
from spark.services import events, scheduler
from spark.services import posts as svc
from spark.services.publisher import as_utc

router = APIRouter(tags=["posts"])
B = "/brands/{brand_id}"


async def _post(db: AsyncSession, ctx: deps.BrandCtx, post_id: int, allow_autosave: bool = False) -> Post:
    post = await db.get(Post, post_id)
    if not post or post.brand_id != ctx.brand.id or (post.is_autosave and not allow_autosave):
        raise not_found("No such post")
    return post


def _targets(items) -> list[svc.TargetInput]:
    return [svc.TargetInput(account_id=t.account_id, override=t.override, first_comment=t.first_comment,
                            thread=list(t.thread or [])) for t in items]


def _cannot_place(e: svc.PlaceError, post: Post) -> JSONResponse:
    return JSONResponse({"code": "cannot_place", "detail": " · ".join(e.problems), "problems": e.problems,
                         "post": PostOut.of(post).model_dump(mode="json")}, 422)


def _when(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# ---- autosave (declared before /{post_id} so "autosave" is not parsed as an id) --------------
@router.get(B + "/posts/autosave", response_model=PostOut | None)
async def get_autosave(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    post = await svc.latest_autosave(db, ctx.brand, ctx.user)
    return PostOut.of(post) if post else None


@router.put(B + "/posts/autosave", response_model=AutosaveOut)
async def put_autosave(body: AutosaveIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    post = await svc.autosave(db, ctx.brand, ctx.user, body.post_id, content=body.content, link=body.link,
                              media_ids=body.media_ids, source=body.source, targets=_targets(body.targets))
    return AutosaveOut(post_id=post.id if post else None, saved_at=datetime.now(UTC))


@router.post(B + "/posts/validate", response_model=dict[str, list[str]])
async def validate(body: ValidateIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    return await svc.validate_targets(db, ctx.brand, body.targets, body.media_ids, body.link)


# ---- read -----------------------------------------------------------------------------------
@router.get(B + "/posts", response_model=PostPage)
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
    if status in ("scheduled", "pending_approval", "publishing") or (since or until):
        stmt = stmt.order_by(Post.scheduled_at.asc())
    else:
        stmt = stmt.order_by(Post.scheduled_at.desc().nulls_first(), Post.id.desc())
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return PostPage(items=[PostOut.of(p) for p in rows], total=total or 0, limit=limit, offset=offset)


@router.get(B + "/posts/{post_id}", response_model=PostOut)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    return PostOut.of(await _post(db, ctx, post_id, allow_autosave=True))


# ---- write ----------------------------------------------------------------------------------
async def _save_and_place(db: AsyncSession, ctx: deps.BrandCtx, post: Post | None, body: PostWrite, status_code: int):
    if post is not None and post.status == PostStatus.publishing:
        raise ApiError(409, "publishing", "This post is publishing right now and can't be edited")
    post = await svc.save_post(db, ctx.brand, ctx.user, post, content=body.content, link=body.link,
                               media_ids=body.media_ids, campaign_id=body.campaign_id, notes=body.notes,
                               source=body.source, targets=_targets(body.targets))
    try:
        msg = await svc.place_post(db, ctx.brand, ctx.user, post, body.action, _when(body.scheduled_at))
    except svc.PlaceError as e:
        await db.commit()
        await db.refresh(post, ["targets"])
        return _cannot_place(e, post)
    if body.idea_id:
        idea = await db.get(Idea, body.idea_id)
        if idea and idea.brand_id == ctx.brand.id:
            idea.post_id = post.id
            if idea.status in ("idea", "drafting"):
                idea.status = "ready"
    await db.commit()
    await svc.enqueue_due(post)
    await events.publish("posts", ctx.brand.id, ids=[post.id])
    await db.refresh(post, ["targets"])
    return JSONResponse(PostResult(message=msg, post=PostOut.of(post)).model_dump(mode="json"), status_code)


@router.post(B + "/posts", response_model=PostResult, status_code=201,
             responses={422: {"description": "cannot_place: saved as a draft, with problems"}})
async def create_post(body: PostWrite, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    return await _save_and_place(db, ctx, None, body, 201)


@router.patch(B + "/posts/{post_id}", response_model=PostResult)
async def update_post(post_id: int, body: PostWrite, db: AsyncSession = Depends(get_db),
                      ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    post = await _post(db, ctx, post_id, allow_autosave=True)
    return await _save_and_place(db, ctx, post, body, 200)


@router.delete(B + "/posts/{post_id}", status_code=204)
async def delete_post(post_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    post = await _post(db, ctx, post_id, allow_autosave=True)
    await db.delete(post)
    await db.commit()
    return Response(status_code=204)


@router.post(B + "/posts/{post_id}/place", response_model=PostResult)
async def place(post_id: int, body: PlaceIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    post = await _post(db, ctx, post_id)
    if post.status in (PostStatus.publishing, PostStatus.published):
        raise ApiError(409, "already_published", f"This post is {post.status.value}")
    try:
        msg = await svc.place_post(db, ctx.brand, ctx.user, post, body.action, _when(body.scheduled_at))
    except svc.PlaceError as e:
        await db.commit()
        return _cannot_place(e, post)
    await db.commit()
    await svc.enqueue_due(post)
    await events.publish("posts", ctx.brand.id, ids=[post.id])
    return PostResult(message=msg, post=PostOut.of(post))


@router.post(B + "/posts/{post_id}/unschedule", response_model=PostResult)
async def unschedule(post_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    post = await _post(db, ctx, post_id)
    if post.status in (PostStatus.publishing, PostStatus.published):
        raise ApiError(409, "already_published", f"This post is {post.status.value}")
    scheduler.unschedule(post)
    await db.commit()
    return PostResult(message="Moved back to drafts", post=PostOut.of(post))


@router.post(B + "/posts/{post_id}/approve", response_model=PostResult)
async def approve(post_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.owner_brand)):
    post = await _post(db, ctx, post_id)
    if post.status != PostStatus.pending_approval:
        raise ApiError(409, "not_pending", f"This post is {post.status.value}, not waiting for approval")
    scheduler.approve(post)
    await db.commit()
    await svc.enqueue_due(post)
    return PostResult(message="Approved and scheduled", post=PostOut.of(post))


@router.post(B + "/posts/{post_id}/retry", response_model=RetryResult)
async def retry(post_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    post = await _post(db, ctx, post_id)
    n = svc.retry_failed(post)
    await db.commit()
    await svc.enqueue_due(post)
    return RetryResult(message=f"Retrying {n} channel(s)" if n else "Nothing failed on this post", post=PostOut.of(post), retried=n)


@router.post(B + "/posts/{post_id}/duplicate", response_model=PostResult, status_code=201)
async def duplicate(post_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    src = await _post(db, ctx, post_id)
    post = await svc.duplicate_post(db, ctx.brand, ctx.user, src)
    return PostResult(message="Duplicated as a draft", post=PostOut.of(post))


@router.post(B + "/posts/{post_id}/move", response_model=PostResult)
async def move(post_id: int, body: MoveIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    """Drag and drop: onto a calendar day (keeps the time) or onto an exact queue slot."""
    post = await _post(db, ctx, post_id)
    if post.status in (PostStatus.publishing, PostStatus.published):
        raise ApiError(409, "already_published", f"This post is {post.status.value}")
    if body.when is not None:
        when = _when(body.when)
        if when < datetime.now(UTC):
            raise ApiError(422, "in_the_past", "That slot is in the past")
        status = scheduler.schedule(post, when.astimezone(UTC), ctx.user, ctx.brand)
        msg = f"Moved to {svc._fmt(when, ctx.brand)}" + (" (awaiting approval)" if status == PostStatus.pending_approval else "")
    elif body.day:
        try:
            when = svc.move_to_day(post, date.fromisoformat(body.day), ctx.brand)
        except svc.PlaceError as e:
            raise ApiError(422, "in_the_past" if "past" in e.problems[0] else "cannot_move", e.problems[0])
        msg = f"Moved to {svc._fmt(when, ctx.brand)}"
    else:
        raise ApiError(422, "validation", "Pass day or when")
    await db.commit()
    return PostResult(message=msg, post=PostOut.of(post))


__all__ = ["router", "as_utc"]
