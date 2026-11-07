"""The engagement inbox, read live from Zernio (persisted items arrive in phase 9)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import InboxAccount, InboxItem, InboxOut, LikeIn, ReplyIn
from spark.db import get_db
from spark.models import SocialAccount
from spark.platforms import PlatformError
from spark.platforms.zernio import ZernioAdapter

router = APIRouter(tags=["inbox"])
B = "/brands/{brand_id}"


async def _accounts(db: AsyncSession, ctx: deps.BrandCtx) -> list[SocialAccount]:
    return (await db.execute(select(SocialAccount).where(
        SocialAccount.brand_id == ctx.brand.id, SocialAccount.provider == "zernio", SocialAccount.is_active.is_(True))
        .order_by(SocialAccount.platform))).scalars().all()


def _owned(accounts: list[SocialAccount], external_id: str) -> SocialAccount:
    for a in accounts:
        if a.external_id == external_id:
            return a
    raise not_found("That channel isn't connected to this brand")


def _acc(a: SocialAccount) -> InboxAccount:
    return InboxAccount(id=a.id, external_id=a.external_id, platform=a.platform, handle=a.handle)


@router.get(B + "/inbox", response_model=InboxOut)
async def inbox(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx),
                account: str | None = None, days: int = Query(30, ge=1, le=90)):
    accounts = await _accounts(db, ctx)
    adapter = ZernioAdapter()
    items, error = [], None
    if accounts and adapter.is_configured():
        wanted = {a.external_id for a in accounts if not account or a.external_id == account}
        since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
        try:
            rows = await adapter.commented_posts(wanted, since=since)
        except PlatformError as e:
            rows, error = [], str(e)
        by_id = {a.external_id: a for a in accounts}
        for r in rows:
            a = by_id.get(r.get("accountId"))
            if not a:
                continue
            items.append(InboxItem(post_id=str(r.get("id")), account=_acc(a), platform=r.get("platform") or a.platform,
                                   content=r.get("content"), picture=r.get("picture"), permalink=r.get("permalink"),
                                   created_at=r.get("createdTime"), comment_count=int(r.get("commentCount") or 0),
                                   like_count=int(r.get("likeCount") or 0)))
    return InboxOut(ready=adapter.is_configured(), error=error, accounts=[_acc(a) for a in accounts], items=items)


@router.get(B + "/inbox/{post_id}/comments")
async def comments(post_id: str, account: str, cursor: str | None = None, db: AsyncSession = Depends(get_db),
                   ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    _owned(await _accounts(db, ctx), account)
    try:
        data = await ZernioAdapter().post_comments(post_id, account, cursor)
    except PlatformError as e:
        raise ApiError(502, "zernio", str(e))
    return {"comments": data.get("comments", []), "pagination": data.get("pagination") or {}}


@router.post(B + "/inbox/{post_id}/reply")
async def reply(post_id: str, body: ReplyIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    acc = _owned(await _accounts(db, ctx), body.account)
    bluesky = {"rootUri": body.root_uri, "rootCid": body.root_cid, "parentCid": body.parent_cid} if acc.platform == "bluesky" else None
    try:
        await ZernioAdapter().reply(post_id, body.account, body.message.strip(), body.comment_id or None, bluesky=bluesky)
    except PlatformError as e:
        raise ApiError(502, "zernio", f"Reply failed: {e}")
    return {"message": "Reply posted"}


@router.post(B + "/inbox/{post_id}/like")
async def like(post_id: str, body: LikeIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    _owned(await _accounts(db, ctx), body.account)
    try:
        await ZernioAdapter().like_comment(post_id, body.comment_id, body.account, body.liked)
    except PlatformError as e:
        raise ApiError(502, "zernio", str(e))
    return {"liked": body.liked}
