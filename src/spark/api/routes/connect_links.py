"""Connect links: owners make a link a client opens to connect their own channels through Zernio.
The public page lists what the link may connect; the connect itself runs on the server routes
`/c/{token}/go/{platform}` and `/accounts/zernio/client-callback` (spark.web.oauth)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    ConnectChannel,
    ConnectLinkCreated,
    ConnectLinkIn,
    ConnectLinkOut,
    ConnectPage,
    ConnectPlatform,
)
from spark.config import get_settings
from spark.db import get_db
from spark.models import ShareLink
from spark.platforms.zernio import ZERNIO_PLATFORMS
from spark.services import activity, channel_health
from spark.services import connect_links as svc
from spark.services.publisher import as_utc

router = APIRouter(prefix="/brands/{brand_id}", tags=["channels"])
public = APIRouter(prefix="/public/connect", tags=["channels"])


def _out(link: ShareLink) -> ConnectLinkOut:
    scope = link.scope or {}
    return ConnectLinkOut(
        id=link.id,
        prefix=link.prefix,
        url_hint=f"{get_settings().base_url}/c/{link.prefix}…",
        platforms=list(scope.get("platforms") or []),
        expires_at=as_utc(link.expires_at),
        created_at=as_utc(link.created_at),
        last_used_at=as_utc(link.last_used_at),
        connected=int(scope.get("connected") or 0),
    )


@router.get("/connect-links", response_model=list[ConnectLinkOut])
async def list_connect_links(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.owner_brand)
):
    now = datetime.now(UTC)
    rows = (
        await db.execute(
            select(ShareLink)
            .where(
                ShareLink.brand_id == ctx.brand.id,
                ShareLink.kind == svc.KIND,
                ShareLink.revoked_at.is_(None),
            )
            .order_by(ShareLink.created_at.desc())
        )
    ).scalars()
    return [_out(link) for link in rows if svc.is_live(link, now)]


@router.post("/connect-links", response_model=ConnectLinkCreated, status_code=201)
async def create_connect_link(
    body: ConnectLinkIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.owner_brand),
):
    """A link for a client to connect their channels without a Spark account. The full link is
    shown once; Spark keeps only its hash."""
    if not get_settings().zernio_api_key:
        raise ApiError(
            422, "zernio_not_configured", "Connect links use Zernio: add its API key first"
        )
    unknown = [p for p in body.platforms if p not in ZERNIO_PLATFORMS]
    if unknown:
        raise ApiError(422, "unknown_platform", "Unknown network: " + ", ".join(unknown))
    picked = [p for p in ZERNIO_PLATFORMS if p in body.platforms]  # Spark's order, no repeats
    token = secrets.token_urlsafe(24)
    link = ShareLink(
        brand_id=ctx.brand.id,
        token_hash=svc.token_hash(token),
        prefix=token[:8],
        kind=svc.KIND,
        scope={"platforms": picked} if picked else {},
        created_by=ctx.user.id,
        expires_at=datetime.now(UTC) + timedelta(days=body.days),
    )
    db.add(link)
    await db.flush()
    what = ", ".join(ZERNIO_PLATFORMS[p].label for p in picked) if picked else "any network"
    activity.record(
        db,
        ctx.brand.id,
        ctx.user,
        "created",
        "connect_link",
        link.id,
        f"for {what}, {body.days} days",
    )
    await db.commit()
    return ConnectLinkCreated(**_out(link).model_dump(), url=f"{get_settings().base_url}/c/{token}")


@router.delete("/connect-links/{link_id}", status_code=204)
async def revoke_connect_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.owner_brand),
):
    link = await db.get(ShareLink, link_id)
    if link is None or link.brand_id != ctx.brand.id or link.kind != svc.KIND:
        raise not_found("No such link")
    link.revoked_at = datetime.now(UTC)
    activity.record(db, ctx.brand.id, ctx.user, "revoked", "connect_link", link.id)
    await db.commit()
    return Response(status_code=204)


@public.get("/{token}", response_model=ConnectPage)
async def connect_page(token: str, db: AsyncSession = Depends(get_db)):
    """What a connect link may connect, and the brand's channels through Zernio with their state."""
    found = await svc.find(db, token)
    if found is None:
        raise not_found("This connect link is no longer valid")
    link, brand = found
    channels = await svc.zernio_channels(db, brand)
    await db.commit()
    return ConnectPage(
        brand={"name": brand.name, "color": brand.color or "", "slug": brand.slug},
        expires_at=as_utc(link.expires_at),
        platforms=[
            ConnectPlatform(platform=p, label=ZERNIO_PLATFORMS[p].label)
            for p in svc.platforms(link)
        ],
        channels=[
            ConnectChannel(platform=a.platform, handle=a.handle, health=channel_health.health(a))
            for a in channels
        ],
    )
