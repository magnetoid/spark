"""Channels: what can be connected, credential connects, Zernio import, pause, remove.
OAuth connects stay on the server routes (/accounts/connect/{platform}) because providers
redirect back there."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    AccountOut,
    ConnectResult,
    CredentialField,
    GridItem,
    GridOut,
    ImportResult,
    PlatformOut,
    PlatformsOut,
)
from spark.config import get_settings
from spark.db import get_db
from spark.models import Media, Post, PostStatus, PostTarget, SocialAccount
from spark.platforms import PlatformError, adapter_for, get_adapter, registry
from spark.platforms.zernio import ZERNIO_PLATFORMS, ZernioAdapter
from spark.services import accounts as svc
from spark.services.publisher import as_utc

router = APIRouter(tags=["channels"])
B = "/brands/{brand_id}"


@router.get(B + "/platforms", response_model=PlatformsOut)
async def platforms(ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    direct = []
    for name in registry():
        ad = get_adapter(name)
        direct.append(
            PlatformOut(
                name=name,
                label=ad.label,
                connect_mode=ad.connect_mode,
                credential_fields=[
                    CredentialField(name=n, label=lbl) for n, lbl in ad.credential_fields
                ],
                configured=ad.is_configured(),
                docs_url=ad.docs_url,
            )
        )
    return PlatformsOut(
        direct=direct,
        zernio={k: v.label for k, v in ZERNIO_PLATFORMS.items()},
        zernio_ready=ZernioAdapter().is_configured(),
        force_dry_run=get_settings().force_dry_run,
    )


@router.post(B + "/accounts/connect/{platform}", response_model=ConnectResult, status_code=201)
async def connect_with_credentials(
    platform: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    try:
        adapter = get_adapter(platform)
    except KeyError:
        raise not_found("No such platform")
    try:
        found = await adapter.connect_with_credentials({k: str(v) for k, v in body.items()})
    except (PlatformError, KeyError, NotImplementedError) as e:
        raise ApiError(400, "connect_failed", f"{adapter.label}: could not connect ({e})")
    rows = await svc.save_connected(db, ctx.brand, platform, found)
    await db.commit()
    return ConnectResult(
        message=f"Connected {len(rows)} {adapter.label} account(s)",
        accounts=[AccountOut.of(a) for a in rows],
    )


@router.post(B + "/accounts/zernio/import", response_model=ImportResult)
async def zernio_import(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)
):
    adapter = ZernioAdapter()
    if not adapter.is_configured():
        raise ApiError(
            400, "not_configured", "Add the Zernio API key under Settings → Connectors first"
        )
    try:
        pairs = await adapter.list_accounts(ctx.brand.zernio_profile_id)
    except PlatformError as e:
        raise ApiError(502, "zernio", f"Zernio: {e}")
    rows, skipped = [], []
    for platform, acc in pairs:
        rows += await svc.save_connected(
            db, ctx.brand, platform, [acc], provider="zernio", skipped=skipped
        )
    await db.commit()
    return ImportResult(
        imported=len(rows), accounts=[AccountOut.of(a) for a in rows], skipped=skipped
    )


async def _account(db: AsyncSession, ctx: deps.BrandCtx, account_id: int) -> SocialAccount:
    acc = await db.get(SocialAccount, account_id)
    if not acc or acc.brand_id != ctx.brand.id:
        raise not_found("No such channel")
    return acc


@router.get(B + "/channels/{account_id}/grid", response_model=GridOut)
async def channel_grid(
    account_id: int,
    limit: int = 18,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
):
    """The channel as a profile grid: newest first, scheduled posts ahead of published ones, each with its first image."""
    acc = await db.get(SocialAccount, account_id)
    if acc is None or acc.brand_id != ctx.brand.id:
        raise not_found("No such channel")
    rows = (
        (
            await db.execute(
                select(PostTarget)
                .options(selectinload(PostTarget.post))
                .join(Post, Post.id == PostTarget.post_id)
                .where(
                    PostTarget.account_id == acc.id,
                    Post.is_autosave.is_(False),
                    PostTarget.status.in_(
                        [
                            PostStatus.scheduled,
                            PostStatus.pending_approval,
                            PostStatus.publishing,
                            PostStatus.published,
                        ]
                    ),
                )
                .order_by(PostTarget.scheduled_at.desc().nulls_last())
                .limit(min(limit, 60))
            )
        )
        .scalars()
        .all()
    )
    media_ids = {(t.post.media_ids or [None])[0] for t in rows if t.post.media_ids}
    media = (
        {
            m.id: m
            for m in (await db.execute(select(Media).where(Media.id.in_(media_ids)))).scalars()
        }
        if media_ids
        else {}
    )
    items = []
    for t in rows:
        first = media.get((t.post.media_ids or [None])[0]) if t.post.media_ids else None
        items.append(
            GridItem(
                post_id=t.post_id,
                status=t.status.value,
                when=as_utc(t.scheduled_at),
                image=first.url if first else None,
                is_video=bool(first and first.is_video),
                content=t.post.content[:160],
            )
        )
    return GridOut(account=AccountOut.of(acc), items=items)


@router.post(B + "/accounts/{account_id}/toggle", response_model=AccountOut)
async def toggle(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    acc = await _account(db, ctx, account_id)
    acc.is_active = not acc.is_active
    await db.commit()
    return AccountOut.of(acc)


@router.delete(B + "/accounts/{account_id}", status_code=204)
async def remove(
    account_id: int,
    disconnect: bool = False,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    acc = await _account(db, ctx, account_id)
    if disconnect and acc.provider == "zernio":
        try:
            await adapter_for(acc).disconnect(acc.external_id)
        except PlatformError as e:
            raise ApiError(502, "zernio", f"Zernio: {e}")
    await db.delete(acc)
    await db.commit()
    return Response(status_code=204)
