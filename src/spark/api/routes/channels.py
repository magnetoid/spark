"""Channels: what can be connected, credential connects, Zernio import, pause, remove.
OAuth connects stay on the server routes (/accounts/connect/{platform}) because providers
redirect back there."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    AccountOut,
    ConnectResult,
    CredentialField,
    ImportResult,
    PlatformOut,
    PlatformsOut,
)
from spark.config import get_settings
from spark.db import get_db
from spark.models import SocialAccount
from spark.platforms import PlatformError, adapter_for, get_adapter, registry
from spark.platforms.zernio import ZERNIO_PLATFORMS, ZernioAdapter
from spark.services import accounts as svc

router = APIRouter(tags=["channels"])
B = "/brands/{brand_id}"


@router.get(B + "/platforms", response_model=PlatformsOut)
async def platforms(ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    direct = []
    for name in registry():
        ad = get_adapter(name)
        direct.append(PlatformOut(name=name, label=ad.label, connect_mode=ad.connect_mode,
                                  credential_fields=[CredentialField(name=n, label=lbl) for n, lbl in ad.credential_fields],
                                  configured=ad.is_configured(), docs_url=ad.docs_url))
    return PlatformsOut(direct=direct, zernio={k: v.label for k, v in ZERNIO_PLATFORMS.items()},
                        zernio_ready=ZernioAdapter().is_configured(), force_dry_run=get_settings().force_dry_run)


@router.post(B + "/accounts/connect/{platform}", response_model=ConnectResult, status_code=201)
async def connect_with_credentials(platform: str, body: dict, db: AsyncSession = Depends(get_db),
                                   ctx: deps.BrandCtx = Depends(deps.editor_brand)):
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
    return ConnectResult(message=f"Connected {len(rows)} {adapter.label} account(s)", accounts=[AccountOut.of(a) for a in rows])


@router.post(B + "/accounts/zernio/import", response_model=ImportResult)
async def zernio_import(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    adapter = ZernioAdapter()
    if not adapter.is_configured():
        raise ApiError(400, "not_configured", "Add the Zernio API key under Settings → Connectors first")
    try:
        pairs = await adapter.list_accounts(None)
    except PlatformError as e:
        raise ApiError(502, "zernio", f"Zernio: {e}")
    rows = []
    for platform, acc in pairs:
        rows += await svc.save_connected(db, ctx.brand, platform, [acc], provider="zernio")
    await db.commit()
    return ImportResult(imported=len(rows), accounts=[AccountOut.of(a) for a in rows])


async def _account(db: AsyncSession, ctx: deps.BrandCtx, account_id: int) -> SocialAccount:
    acc = await db.get(SocialAccount, account_id)
    if not acc or acc.brand_id != ctx.brand.id:
        raise not_found("No such channel")
    return acc


@router.post(B + "/accounts/{account_id}/toggle", response_model=AccountOut)
async def toggle(account_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    acc = await _account(db, ctx, account_id)
    acc.is_active = not acc.is_active
    await db.commit()
    return AccountOut.of(acc)


@router.delete(B + "/accounts/{account_id}", status_code=204)
async def remove(account_id: int, disconnect: bool = False, db: AsyncSession = Depends(get_db),
                 ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    acc = await _account(db, ctx, account_id)
    if disconnect and acc.provider == "zernio":
        try:
            await adapter_for(acc).disconnect(acc.external_id)
        except PlatformError as e:
            raise ApiError(502, "zernio", f"Zernio: {e}")
    await db.delete(acc)
    await db.commit()
    return Response(status_code=204)
