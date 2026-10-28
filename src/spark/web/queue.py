"""Channel-first queue view (Buffer-style): pick a channel, see its upcoming slots,
drafts, approvals and sent posts."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.db import get_db
from spark.models import Brand, Post, PostStatus, PostTarget, SocialAccount, User
from spark.platforms.zernio import ZERNIO_PLATFORMS
from spark.services import scheduler
from spark.web.deps import (
    current_user,
    editor,
    flash,
    hx_none,
    is_hx,
    render,
    require_brand,
    templates,
    toast,
)
from spark.web.posts import enqueue

router = APIRouter()
TABS = ("queue", "drafts", "approvals", "sent")


def platform_label(platform: str) -> str:
    from spark.platforms import registry

    reg = registry()
    if platform in reg:
        return reg[platform].label
    return ZERNIO_PLATFORMS[platform].label if platform in ZERNIO_PLATFORMS else platform


async def _column_context(db: AsyncSession, brand: Brand, accounts, account: int | None, tab: str) -> dict:
    """Data for one channel's column (shared by the page and the htmx partial)."""
    tab = tab if tab in TABS else "queue"
    current = next((a for a in accounts if a.id == account), None) or (accounts[0] if accounts else None)
    zone = ZoneInfo(brand.timezone)
    items, days, posts = [], [], []
    if current:
        if tab == "queue":
            items = await scheduler.channel_queue(db, brand, current)
            grouped: dict = {}
            for it in items:
                grouped.setdefault(it["when"].astimezone(zone).date(), []).append(it)
            days = sorted(grouped.items())
        else:
            status = {"drafts": PostStatus.draft, "approvals": PostStatus.pending_approval,
                      "sent": PostStatus.published}[tab]
            stmt = (
                select(PostTarget)
                .options(selectinload(PostTarget.post).selectinload(Post.targets))
                .join(Post, Post.id == PostTarget.post_id)
                .where(PostTarget.account_id == current.id, PostTarget.status == status,
                       Post.is_autosave.is_(False))
            )
            stmt = stmt.order_by((PostTarget.published_at if tab == "sent" else PostTarget.updated_at).desc()).limit(100)
            posts = (await db.execute(stmt)).scalars().all()
    counts = {}
    if current:
        for key, st in (("drafts", PostStatus.draft), ("approvals", PostStatus.pending_approval)):
            counts[key] = len((await db.execute(select(PostTarget.id).join(Post, Post.id == PostTarget.post_id).where(
                PostTarget.account_id == current.id, PostTarget.status == st, Post.is_autosave.is_(False)))).all())
        counts["queue"] = sum(1 for i in items if i["target"]) if tab == "queue" else len(
            (await db.execute(select(PostTarget.id).where(
                PostTarget.account_id == current.id,
                PostTarget.status.in_([PostStatus.scheduled, PostStatus.pending_approval])))).all())
    return {"current": current, "tab": tab, "days": days, "posts": posts, "counts": counts,
            "today": datetime.now(zone).date(), "platform_label": platform_label}


async def _accounts(db: AsyncSession, brand: Brand):
    return (await db.execute(
        select(SocialAccount).where(SocialAccount.brand_id == brand.id)
        .order_by(SocialAccount.is_active.desc(), SocialAccount.platform, SocialAccount.handle)
    )).scalars().all()


@router.get("/queue/column")
async def queue_column(request: Request, account: int | None = None, tab: str = "queue",
                       db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                       brand: Brand = Depends(require_brand)):
    accounts = await _accounts(db, brand)
    ctx = await _column_context(db, brand, accounts, account, tab)
    return templates.TemplateResponse(request, "partials/queue_column.html",
                                      {"user": user, "brand": brand, "accounts": accounts, **ctx})


@router.get("/queue")
async def queue(request: Request, account: int | None = None, tab: str = "queue",
                db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                brand: Brand = Depends(require_brand)):
    accounts = await _accounts(db, brand)
    ctx = await _column_context(db, brand, accounts, account, tab)
    return await render(request, "queue.html", db, user, brand, accounts=accounts, **ctx)


async def _post(db, brand, post_id) -> Post:
    post = await db.get(Post, post_id)
    if not post or post.brand_id != brand.id:
        raise HTTPException(404)
    return post


@router.post("/posts/{post_id}/prioritize")
async def prioritize(post_id: int, request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    post = await _post(db, brand, post_id)
    if post.status in (PostStatus.published, PostStatus.publishing):
        raise HTTPException(400, "Already published")
    status = await scheduler.prioritize(db, brand, post, user)
    await db.commit()
    msg = "Moved to the top of the queue" if status == PostStatus.scheduled else "Moved to the top — awaiting approval"
    if is_hx(request):
        return hx_none({**toast(msg), "posts-changed": {"id": post.id}})
    flash(request, msg)
    return RedirectResponse(request.headers.get("referer") or "/queue", 303)


@router.post("/posts/{post_id}/share-now")
async def share_now(post_id: int, request: Request, db: AsyncSession = Depends(get_db),
                    user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    post = await _post(db, brand, post_id)
    if not post.targets:
        flash(request, "Pick at least one account first", "error")
        return RedirectResponse(f"/posts/{post.id}/edit", 303)
    status = scheduler.schedule(post, datetime.now(UTC), user, brand)
    await db.commit()
    if status == PostStatus.scheduled:
        for t in post.targets:
            if t.status == PostStatus.scheduled:
                await enqueue("publish_now", t.id)
        msg = "Publishing now…"
    else:
        msg = "Sent for approval"
    if is_hx(request):
        return hx_none({**toast(msg), "posts-changed": {"id": post.id}})
    flash(request, msg)
    return RedirectResponse(request.headers.get("referer") or "/queue", 303)


@router.post("/posts/{post_id}/move-slot")
async def move_slot(post_id: int, request: Request, when: str = Form(...),
                    db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                    brand: Brand = Depends(require_brand)):
    """Drag a queued post onto another slot."""
    post = await _post(db, brand, post_id)
    if post.status in (PostStatus.published, PostStatus.publishing):
        raise HTTPException(400, "Already published")
    target = datetime.fromisoformat(when)
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    if target < datetime.now(UTC):
        raise HTTPException(400, "That slot is in the past")
    status = scheduler.schedule(post, target.astimezone(UTC), user, brand)
    await db.commit()
    msg = f"Moved to {target.astimezone(ZoneInfo(brand.timezone)):%a %b %d, %H:%M}"
    if status == PostStatus.pending_approval:
        msg += " (awaiting approval)"
    if is_hx(request):
        return hx_none({**toast(msg), "posts-changed": {"id": post.id}})
    flash(request, msg)
    return RedirectResponse(request.headers.get("referer") or "/queue", 303)
