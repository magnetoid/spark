"""Connecting social accounts (OAuth redirect or credential forms)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.db import get_db
from spark.models import Brand, SocialAccount, User
from spark.platforms import PlatformError, adapter_for, get_adapter, registry
from spark.platforms.base import ConnectedAccount
from spark.platforms.zernio import ZERNIO_PLATFORMS, ZernioAdapter
from spark.security import token
from spark.web.deps import current_user, editor, flash, render, require_brand

router = APIRouter()
log = logging.getLogger(__name__)


async def _save(db: AsyncSession, brand: Brand, platform: str, found: list[ConnectedAccount],
                provider: str = "direct") -> int:
    n = 0
    for c in found:
        acc = await db.scalar(
            select(SocialAccount).where(
                SocialAccount.brand_id == brand.id,
                SocialAccount.platform == platform,
                SocialAccount.external_id == c.external_id,
            )
        )
        if acc is None:
            acc = SocialAccount(brand_id=brand.id, platform=platform, external_id=c.external_id,
                                provider=provider)
            db.add(acc)
        acc.handle = c.handle
        acc.display_name = c.display_name
        acc.avatar_url = c.avatar_url
        acc.access_token = c.access_token
        acc.refresh_token = c.refresh_token
        acc.token_expires_at = c.expires_at
        acc.extra = {**(acc.extra or {}), **c.extra}
        acc.followers = c.followers
        acc.is_active = True
        acc.last_error = None
        n += 1
    await db.commit()
    return n


@router.get("/accounts")
async def accounts(request: Request, db: AsyncSession = Depends(get_db),
                   user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    rows = (await db.execute(
        select(SocialAccount).where(SocialAccount.brand_id == brand.id).order_by(SocialAccount.platform)
    )).scalars().all()
    adapters = [(name, get_adapter(name)) for name in registry()]
    zernio = ZernioAdapter()
    return await render(request, "accounts.html", db, user, brand, accounts=rows, adapters=adapters,
                        force_dry_run=get_settings().force_dry_run,
                        zernio_ready=zernio.is_configured(), zernio_platforms=ZERNIO_PLATFORMS)


# ---- Zernio -------------------------------------------------------------------

@router.get("/accounts/zernio/connect/{platform}")
async def zernio_connect(platform: str, request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    if platform not in ZERNIO_PLATFORMS:
        raise HTTPException(404)
    adapter = ZernioAdapter.for_platform(platform)
    if not adapter.is_configured():
        flash(request, "Set SPARK_ZERNIO_API_KEY to connect accounts through Zernio", "error")
        return RedirectResponse("/accounts", 303)
    try:
        profile_id = await adapter.ensure_profile(brand)
        await db.commit()
        state = token(16)
        url = await adapter.connect_url(profile_id, state)
    except PlatformError as e:
        flash(request, f"Zernio: {e}", "error")
        return RedirectResponse("/accounts", 303)
    request.session["zernio_oauth"] = {"state": state, "platform": platform, "brand_id": brand.id}
    return RedirectResponse(url, 303)


@router.get("/accounts/zernio/callback")
async def zernio_callback(request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(editor)):
    pending = request.session.pop("zernio_oauth", None)
    q = request.query_params
    if q.get("error"):
        flash(request, f"Zernio connection failed: {q.get('error_description') or q['error']}", "error")
        return RedirectResponse("/accounts", 303)
    if not pending or pending["state"] != q.get("state"):
        flash(request, "Connection state mismatch — please try again", "error")
        return RedirectResponse("/accounts", 303)
    brand = await db.get(Brand, pending["brand_id"])
    adapter = ZernioAdapter.for_platform(pending["platform"])
    try:
        if account_id := q.get("accountId"):
            found = await adapter.get_account(account_id)
            pairs = [(pending["platform"], found)] if found else []
        else:
            pairs = await adapter.list_accounts(None)
    except PlatformError as e:
        flash(request, f"Zernio: {e}", "error")
        return RedirectResponse("/accounts", 303)
    n = 0
    for platform, acc in pairs:
        n += await _save(db, brand, platform, [acc], provider="zernio")
    flash(request, f"Connected {n} account(s) through Zernio" if n else
          "Zernio did not return the connected account yet — use “Import from Zernio”", "success" if n else "error")
    return RedirectResponse("/accounts", 303)


@router.post("/accounts/zernio/import")
async def zernio_import(request: Request, db: AsyncSession = Depends(get_db),
                        user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    """Pull every account connected in Zernio — from all profiles, since accounts
    connected in Zernio's own UI live in the Default profile."""
    adapter = ZernioAdapter()
    try:
        pairs = await adapter.list_accounts(None)
    except PlatformError as e:
        flash(request, f"Zernio: {e}", "error")
        return RedirectResponse("/accounts", 303)
    n = 0
    for platform, acc in pairs:
        n += await _save(db, brand, platform, [acc], provider="zernio")
    await db.commit()
    if n:
        names = ", ".join(f"{acc.handle} ({platform})" for platform, acc in pairs[:6])
        flash(request, f"Imported {n} account(s) from Zernio: {names}")
    else:
        flash(request, "Zernio has no connected accounts yet — connect one below or in Zernio", "error")
    return RedirectResponse("/accounts", 303)


@router.get("/accounts/connect/{platform}")
async def connect(platform: str, request: Request, user: User = Depends(editor),
                  brand: Brand = Depends(require_brand)):
    try:
        adapter = get_adapter(platform)
    except KeyError:
        raise HTTPException(404)
    if adapter.connect_mode != "oauth":
        raise HTTPException(400, "This platform connects with credentials")
    if not adapter.is_configured():
        flash(request, f"{adapter.label} developer app is not configured — see README", "error")
        return RedirectResponse("/accounts", 303)
    state = token(16)
    start = adapter.oauth_start(state)
    request.session["oauth"] = {"state": state, "platform": platform, "brand_id": brand.id,
                                "data": start.session_data}
    return RedirectResponse(start.url, 303)


@router.get("/accounts/callback/{platform}")
async def callback(platform: str, request: Request, db: AsyncSession = Depends(get_db),
                   user: User = Depends(editor)):
    pending = request.session.pop("oauth", None)
    params = request.query_params
    if params.get("error"):
        flash(request, f"Connection cancelled: {params.get('error_description') or params['error']}", "error")
        return RedirectResponse("/accounts", 303)
    if not pending or pending["platform"] != platform or pending["state"] != params.get("state"):
        flash(request, "OAuth state mismatch — please try again", "error")
        return RedirectResponse("/accounts", 303)
    brand = await db.get(Brand, pending["brand_id"])
    adapter = get_adapter(platform)
    try:
        found = await adapter.oauth_callback(params.get("code", ""), pending["data"])
    except PlatformError as e:
        log.warning("OAuth callback for %s failed: %s", platform, e)
        flash(request, f"{adapter.label}: {e}", "error")
        return RedirectResponse("/accounts", 303)
    n = await _save(db, brand, platform, found)
    flash(request, f"Connected {n} {adapter.label} account(s)")
    return RedirectResponse("/accounts", 303)


@router.post("/accounts/connect/{platform}")
async def connect_credentials(platform: str, request: Request, db: AsyncSession = Depends(get_db),
                              user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    try:
        adapter = get_adapter(platform)
    except KeyError:
        raise HTTPException(404)
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    try:
        found = await adapter.connect_with_credentials(data)
    except (PlatformError, KeyError) as e:
        flash(request, f"{adapter.label}: could not connect ({e})", "error")
        return RedirectResponse("/accounts", 303)
    # Under force_dry_run every platform connects via the dry-run form but keeps its own name.
    n = await _save(db, brand, platform, found)
    flash(request, f"Connected {n} {adapter.label} account(s)")
    return RedirectResponse("/accounts", 303)


@router.post("/accounts/{account_id}/toggle")
async def toggle(account_id: int, request: Request, db: AsyncSession = Depends(get_db),
                 user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    acc = await db.get(SocialAccount, account_id)
    if acc and acc.brand_id == brand.id:
        acc.is_active = not acc.is_active
        await db.commit()
    return RedirectResponse("/accounts", 303)


@router.post("/accounts/{account_id}/delete")
async def remove(account_id: int, request: Request, db: AsyncSession = Depends(get_db),
                 user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    acc = await db.get(SocialAccount, account_id)
    if acc and acc.brand_id == brand.id:
        if acc.provider == "zernio" and request.query_params.get("disconnect") == "1":
            await adapter_for(acc).disconnect(acc.external_id)
        await db.delete(acc)
        await db.commit()
        flash(request, f"Removed {acc.handle}")
    return RedirectResponse("/accounts", 303)
