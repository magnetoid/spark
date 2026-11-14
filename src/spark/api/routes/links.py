"""Tracked short links and RSS feeds."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    FeedIn,
    FeedOut,
    FeedUpdate,
    LinkIn,
    LinkOut,
    LinkPage,
    LinkStats,
    LinkUpdate,
)
from spark.db import get_db
from spark.models import Campaign, RssFeed, ShortLink
from spark.services import tracking
from spark.services.links import add_utm, code_taken, create_short_link, short_url
from spark.services.publisher import as_utc

router = APIRouter(tags=["links"])
B = "/brands/{brand_id}"


def _link(l: ShortLink) -> LinkOut:
    expires = as_utc(l.expires_at)
    return LinkOut(
        id=l.id,
        code=l.code,
        destination=l.destination,
        title=l.title,
        campaign_id=l.campaign_id,
        post_id=l.post_id,
        clicks=l.clicks,
        short_url=short_url(l),
        expires_at=expires,
        expired=bool(expires and expires <= datetime.now(UTC)),
        created_at=as_utc(l.created_at) if l.created_at else None,
    )


async def _campaign(db: AsyncSession, ctx: deps.BrandCtx, campaign_id: int | None):
    if campaign_id is None:
        return None
    camp = await db.get(Campaign, campaign_id)
    if not camp or camp.brand_id != ctx.brand.id:
        raise not_found("No such campaign")
    return camp


async def _own_link(db: AsyncSession, ctx: deps.BrandCtx, link_id: int) -> ShortLink:
    link = await db.get(ShortLink, link_id)
    if not link or link.brand_id != ctx.brand.id:
        raise not_found("No such link")
    return link


@router.get(B + "/links", response_model=LinkPage)
async def list_links(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    rows = (
        (
            await db.execute(
                select(ShortLink)
                .where(ShortLink.brand_id == ctx.brand.id)
                .order_by(ShortLink.id.desc())
                .limit(500)
            )
        )
        .scalars()
        .all()
    )
    return LinkPage(items=[_link(l) for l in rows])


@router.post(B + "/links", response_model=LinkOut, status_code=201)
async def create_link(
    body: LinkIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    camp = await _campaign(db, ctx, body.campaign_id)
    destination = body.destination.strip()
    if not destination.startswith(("http://", "https://")):
        destination = "https://" + destination
    if body.code and await code_taken(db, body.code):
        raise ApiError(409, "code_taken", f"/l/{body.code} is already used by another link")
    # What the person typed wins, then the campaign's name, then the brand's default
    campaign_tag = (
        (body.utm_campaign or "").strip()
        or (camp.utm_campaign if camp else None)
        or (ctx.brand.utm_defaults or {}).get("campaign")
    )
    dest = add_utm(
        destination,
        source=(body.utm_source or "").strip() or None,
        medium=(body.utm_medium or "").strip() or None,
        campaign=campaign_tag or None,
        content=(body.utm_content or "").strip() or None,
        term=(body.utm_term or "").strip() or None,
    )
    link = await create_short_link(
        db,
        ctx.brand,
        dest,
        title=(body.title or "").strip() or None,
        campaign_id=camp.id if camp else None,
        code=body.code or None,
        expires_at=body.expires_at,
    )
    await db.commit()
    return _link(link)


@router.patch(B + "/links/{link_id}", response_model=LinkOut)
async def update_link(
    link_id: int,
    body: LinkUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    link = await _own_link(db, ctx, link_id)
    fields = body.model_dump(exclude_unset=True)
    if "title" in fields:
        link.title = (body.title or "").strip() or None
    if "expires_at" in fields:
        link.expires_at = body.expires_at
    if "campaign_id" in fields:
        camp = await _campaign(db, ctx, body.campaign_id)
        link.campaign_id = camp.id if camp else None
    await db.commit()
    return _link(link)


@router.get(B + "/links/{link_id}/stats", response_model=LinkStats)
async def link_stats(
    link_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
):
    link = await _own_link(db, ctx, link_id)
    stats = await tracking.link_stats(db, ctx.brand, link, days)
    return LinkStats(link=_link(link), **stats)


@router.delete(B + "/links/{link_id}", status_code=204)
async def delete_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    link = await _own_link(db, ctx, link_id)
    await db.delete(link)
    await db.commit()
    return Response(status_code=204)


# ---- RSS feeds ------------------------------------------------------------------------------
def _feed(f: RssFeed) -> FeedOut:
    return FeedOut(
        id=f.id,
        url=f.url,
        name=f.name,
        use_ai=f.use_ai,
        auto_queue=f.auto_queue,
        account_ids=list(f.account_ids or []),
        is_active=f.is_active,
        last_checked_at=as_utc(f.last_checked_at) if f.last_checked_at else None,
    )


@router.get(B + "/feeds", response_model=list[FeedOut])
async def list_feeds(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    rows = (
        (
            await db.execute(
                select(RssFeed).where(RssFeed.brand_id == ctx.brand.id).order_by(RssFeed.id)
            )
        )
        .scalars()
        .all()
    )
    return [_feed(f) for f in rows]


@router.post(B + "/feeds", response_model=FeedOut, status_code=201)
async def create_feed(
    body: FeedIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    f = RssFeed(
        brand_id=ctx.brand.id,
        url=body.url.strip(),
        name=(body.name or "").strip() or None,
        use_ai=body.use_ai,
        auto_queue=body.auto_queue,
        account_ids=body.account_ids,
    )
    db.add(f)
    await db.commit()
    return _feed(f)


@router.patch(B + "/feeds/{feed_id}", response_model=FeedOut)
async def update_feed(
    feed_id: int,
    body: FeedUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    f = await db.get(RssFeed, feed_id)
    if not f or f.brand_id != ctx.brand.id:
        raise not_found("No such feed")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(f, k, (v or "").strip() or None if k == "name" else v)
    await db.commit()
    return _feed(f)


@router.delete(B + "/feeds/{feed_id}", status_code=204)
async def delete_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    f = await db.get(RssFeed, feed_id)
    if not f or f.brand_id != ctx.brand.id:
        raise not_found("No such feed")
    await db.delete(f)
    await db.commit()
    return Response(status_code=204)
