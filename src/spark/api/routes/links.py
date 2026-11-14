"""Tracked short links and RSS feeds."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import not_found
from spark.api.schemas import FeedIn, FeedOut, FeedUpdate, LinkIn, LinkOut, LinkPage
from spark.db import get_db
from spark.models import RssFeed, ShortLink
from spark.services.links import add_utm, create_short_link, short_url
from spark.services.publisher import as_utc

router = APIRouter(tags=["links"])
B = "/brands/{brand_id}"


def _link(l: ShortLink) -> LinkOut:
    return LinkOut(
        id=l.id,
        code=l.code,
        destination=l.destination,
        title=l.title,
        campaign_id=l.campaign_id,
        clicks=l.clicks,
        short_url=short_url(l),
        created_at=as_utc(l.created_at) if l.created_at else None,
    )


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
    destination = body.destination.strip()
    if not destination.startswith(("http://", "https://")):
        destination = "https://" + destination
    dest = add_utm(
        destination,
        source=body.utm_source or None,
        medium=body.utm_medium or None,
        campaign=body.utm_campaign or None,
        content=body.utm_content or None,
    )
    link = await create_short_link(
        db, ctx.brand, dest, title=(body.title or "").strip() or None, campaign_id=body.campaign_id
    )
    await db.commit()
    return _link(link)


@router.delete(B + "/links/{link_id}", status_code=204)
async def delete_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    link = await db.get(ShortLink, link_id)
    if not link or link.brand_id != ctx.brand.id:
        raise not_found("No such link")
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
