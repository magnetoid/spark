"""One channel's queue: upcoming slots merged with the posts that fill them."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import not_found
from spark.api.schemas import AccountOut, PostOut, QueueItem, QueueOut, SlotOut
from spark.db import get_db
from spark.models import Post, PostStatus, PostTarget, SocialAccount
from spark.services import scheduler

router = APIRouter(tags=["queue"])


@router.get("/brands/{brand_id}/queue", response_model=QueueOut)
async def channel_queue(
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
    account: int | None = None,
    days: int = Query(14, ge=1, le=60),
):
    accounts = (
        (
            await db.execute(
                select(SocialAccount)
                .where(SocialAccount.brand_id == ctx.brand.id)
                .order_by(
                    SocialAccount.is_active.desc(), SocialAccount.platform, SocialAccount.handle
                )
            )
        )
        .scalars()
        .all()
    )
    current = (
        next((a for a in accounts if a.id == account), None)
        if account
        else (accounts[0] if accounts else None)
    )
    if current is None:
        raise not_found("No such channel" if account else "This brand has no channels yet")
    items = await scheduler.channel_queue(db, ctx.brand, current, days=days)

    async def count(*statuses: PostStatus) -> int:
        return (
            await db.scalar(
                select(func.count(PostTarget.id))
                .join(Post, Post.id == PostTarget.post_id)
                .where(
                    PostTarget.account_id == current.id,
                    PostTarget.status.in_(statuses),
                    Post.is_autosave.is_(False),
                )
            )
            or 0
        )

    counts = {
        "queue": await count(
            PostStatus.scheduled, PostStatus.pending_approval, PostStatus.publishing
        ),
        "drafts": await count(PostStatus.draft),
        "approvals": await count(PostStatus.pending_approval),
    }
    slots = await scheduler.brand_slots(db, ctx.brand, [current.id])
    return QueueOut(
        account=AccountOut.of(current),
        items=[
            QueueItem(
                when=i["when"],
                post=PostOut.of(i["post"]) if i["post"] else None,
                target_id=i["target"].id if i["target"] else None,
            )
            for i in items
        ],
        slots=[
            SlotOut(weekday=s.weekday, time=s.time)
            for s in sorted(slots, key=lambda s: (s.weekday, s.time))
        ],
        counts=counts,
    )
