"""Channel-first queue view (Buffer-style): pick a channel, see its upcoming slots,
drafts, approvals and sent posts."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.db import get_db
from spark.models import Brand, Post, PostStatus, PostTarget, SocialAccount, User
from spark.platforms.zernio import ZERNIO_PLATFORMS
from spark.services import scheduler
from spark.web.deps import current_user, editor, flash, render, require_brand
from spark.web.posts import enqueue

router = APIRouter()
TABS = ("queue", "drafts", "approvals", "sent")


def platform_label(platform: str) -> str:
    from spark.platforms import registry

    reg = registry()
    if platform in reg:
        return reg[platform].label
    return ZERNIO_PLATFORMS[platform].label if platform in ZERNIO_PLATFORMS else platform


@router.get("/queue")
async def queue(request: Request, account: int | None = None, tab: str = "queue",
                db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                brand: Brand = Depends(require_brand)):
    accounts = (await db.execute(
        select(SocialAccount).where(SocialAccount.brand_id == brand.id)
        .order_by(SocialAccount.is_active.desc(), SocialAccount.platform, SocialAccount.handle)
    )).scalars().all()
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
            if tab == "sent":
                stmt = stmt.order_by(PostTarget.published_at.desc()).limit(100)
            else:
                stmt = stmt.order_by(PostTarget.updated_at.desc()).limit(100)
            posts = (await db.execute(stmt)).scalars().all()
    counts = {}
    if current:
        for key, st in (("drafts", PostStatus.draft), ("approvals", PostStatus.pending_approval)):
            counts[key] = len((await db.execute(select(PostTarget.id).where(
                PostTarget.account_id == current.id, PostTarget.status == st))).all())
        counts["queue"] = sum(1 for i in items if i["target"]) if tab == "queue" else len(
            (await db.execute(select(PostTarget.id).where(
                PostTarget.account_id == current.id,
                PostTarget.status.in_([PostStatus.scheduled, PostStatus.pending_approval])))).all())
    return await render(request, "queue.html", db, user, brand, accounts=accounts, current=current,
                        tab=tab, days=days, posts=posts, counts=counts, platform_label=platform_label,
                        today=datetime.now(zone).date())


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
    flash(request, "Moved to the top of the queue" if status == PostStatus.scheduled
          else "Moved to the top — awaiting approval")
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
        flash(request, "Publishing now…")
    else:
        flash(request, "Sent for approval")
    return RedirectResponse(request.headers.get("referer") or "/queue", 303)
