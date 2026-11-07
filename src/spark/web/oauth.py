"""OAuth round trips that must stay on the server: providers redirect back to these URLs.

Everything else about channels lives in the JSON API. These routes start the dance, take
the callback, save what came back and send the browser to the Channels page with a notice.
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.models import Brand, User
from spark.platforms import PlatformError, get_adapter
from spark.platforms.zernio import ZernioAdapter
from spark.security import token
from spark.services.accounts import save_connected
from spark.web.deps import editor

router = APIRouter()
log = logging.getLogger(__name__)


def _back(notice: str, kind: str = "success", brand: Brand | None = None) -> RedirectResponse:
    q = {"notice": notice, "kind": kind}
    if brand:
        q["brand"] = brand.slug
    return RedirectResponse(f"/channels?{urlencode(q)}", 303)


async def _brand(request: Request, db: AsyncSession, user: User | None = None) -> Brand | None:
    """The brand the SPA passed as ?brand=<id>, else the first one the user can see. None when the
    user is not a member of the brand they asked for."""
    from spark.services import access

    raw = request.query_params.get("brand")
    if raw and raw.isdigit():
        b = await db.get(Brand, int(raw))
        if b is None or (user is not None and await access.role_for(db, user, b.id) is None):
            return None
        return b
    if user is not None:
        visible = await access.visible_brands(db, user)
        return visible[0][0] if visible else None
    return await db.scalar(select(Brand).order_by(Brand.id).limit(1))


@router.get("/accounts/connect/{platform}")
async def connect(platform: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(editor)):
    brand = await _brand(request, db, user)
    if brand is None:
        return _back("You are not a member of that brand", "error")
    if brand is None:
        return _back("Create a brand first", "error")
    try:
        adapter = get_adapter(platform)
    except KeyError:
        return _back("Unknown platform", "error", brand)
    if adapter.connect_mode != "oauth":
        return _back(f"{adapter.label} connects with credentials on the Channels page", "error", brand)
    if not adapter.is_configured():
        return _back(f"{adapter.label} developer app is not configured on this server", "error", brand)
    state = token(16)
    start = adapter.oauth_start(state)
    request.session["oauth"] = {"state": state, "platform": platform, "brand_id": brand.id, "data": start.session_data}
    return RedirectResponse(start.url, 303)


@router.get("/accounts/callback/{platform}")
async def callback(platform: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(editor)):
    pending = request.session.pop("oauth", None)
    params = request.query_params
    brand = await db.get(Brand, pending["brand_id"]) if pending else None
    if params.get("error"):
        return _back(f"Connection cancelled: {params.get('error_description') or params['error']}", "error", brand)
    if not pending or pending["platform"] != platform or pending["state"] != params.get("state") or brand is None:
        return _back("OAuth state mismatch; please try again", "error", brand)
    adapter = get_adapter(platform)
    try:
        found = await adapter.oauth_callback(params.get("code", ""), pending["data"])
    except PlatformError as e:
        log.warning("OAuth callback for %s failed: %s", platform, e)
        return _back(f"{adapter.label}: {e}", "error", brand)
    rows = await save_connected(db, brand, platform, found)
    await db.commit()
    return _back(f"Connected {len(rows)} {adapter.label} account(s)", "success", brand)


@router.get("/accounts/zernio/connect/{platform}")
async def zernio_connect(platform: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(editor)):
    brand = await _brand(request, db, user)
    if brand is None:
        return _back("You are not a member of that brand", "error")
    if brand is None:
        return _back("Create a brand first", "error")
    adapter = ZernioAdapter.for_platform(platform)
    if not adapter.is_configured():
        return _back("Add the Zernio API key under Settings → Connectors first", "error", brand)
    state = token(16)
    try:
        profile_id = await adapter.ensure_profile(brand)
        await db.commit()
        url = await adapter.connect_url(profile_id, state)
    except PlatformError as e:
        return _back(f"Zernio: {e}", "error", brand)
    request.session["zernio_oauth"] = {"state": state, "platform": platform, "brand_id": brand.id}
    return RedirectResponse(url, 303)


@router.get("/accounts/zernio/callback")
async def zernio_callback(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(editor)):
    pending = request.session.pop("zernio_oauth", None)
    q = request.query_params
    brand = await db.get(Brand, pending["brand_id"]) if pending else None
    if q.get("error"):
        return _back(f"Zernio connection failed: {q.get('error_description') or q['error']}", "error", brand)
    if not pending or pending["state"] != q.get("state") or brand is None:
        return _back("Connection state mismatch; please try again", "error", brand)
    adapter = ZernioAdapter.for_platform(pending["platform"])
    try:
        if account_id := q.get("accountId"):
            found = await adapter.get_account(account_id)
            pairs = [(pending["platform"], found)] if found else []
        else:
            pairs = await adapter.list_accounts(None)
    except PlatformError as e:
        return _back(f"Zernio: {e}", "error", brand)
    n = 0
    for platform, acc in pairs:
        n += len(await save_connected(db, brand, platform, [acc], provider="zernio"))
    await db.commit()
    if n:
        return _back(f"Connected {n} account(s) through Zernio", "success", brand)
    return _back("Zernio did not return the connected account yet; use “Import from Zernio”", "error", brand)
