"""OAuth round trips that must stay on the server: providers redirect back to these URLs.

Everything else about channels lives in the JSON API. These routes start the dance, take
the callback, save what came back and send the browser to the Channels page with a notice.
"""

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.models import Brand, User
from spark.platforms import PlatformError, get_adapter
from spark.platforms.zernio import ZernioAdapter
from spark.security import token as token_
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


def _no_brand(request: Request):
    if request.query_params.get("brand"):
        return _back("You are not a member of that brand", "error")
    return _back("Create a brand first", "error")


@router.get("/accounts/connect/{platform}")
async def connect(
    platform: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(editor),
):
    brand = await _brand(request, db, user)
    if brand is None:
        return _no_brand(request)
    try:
        adapter = get_adapter(platform)
    except KeyError:
        return _back("Unknown platform", "error", brand)
    if adapter.connect_mode != "oauth":
        return _back(
            f"{adapter.label} connects with credentials on the Channels page", "error", brand
        )
    if not adapter.is_configured():
        return _back(
            f"{adapter.label} developer app is not configured on this server", "error", brand
        )
    state = token_(16)
    start = adapter.oauth_start(state)
    request.session["oauth"] = {
        "state": state,
        "platform": platform,
        "brand_id": brand.id,
        "data": start.session_data,
    }
    return RedirectResponse(start.url, 303)


@router.get("/accounts/callback/{platform}")
async def callback(
    platform: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(editor),
):
    pending = request.session.pop("oauth", None)
    params = request.query_params
    brand = await db.get(Brand, pending["brand_id"]) if pending else None
    if params.get("error"):
        return _back(
            f"Connection cancelled: {params.get('error_description') or params['error']}",
            "error",
            brand,
        )
    if (
        not pending
        or pending["platform"] != platform
        or pending["state"] != params.get("state")
        or brand is None
    ):
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
async def zernio_connect(
    platform: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(editor),
):
    brand = await _brand(request, db, user)
    if brand is None:
        return _no_brand(request)
    adapter = ZernioAdapter.for_platform(platform)
    if not adapter.is_configured():
        return _back("Add the Zernio API key under Settings → Connectors first", "error", brand)
    state = token_(16)
    try:
        profile_id = await adapter.ensure_profile(brand)
        await db.commit()
        url = await adapter.connect_url(profile_id, state)
    except PlatformError as e:
        return _back(f"Zernio: {e}", "error", brand)
    request.session["zernio_oauth"] = {"state": state, "platform": platform, "brand_id": brand.id}
    return RedirectResponse(url, 303)


@router.get("/accounts/zernio/callback")
async def zernio_callback(
    request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(editor)
):
    pending = request.session.pop("zernio_oauth", None)
    q = request.query_params
    brand = await db.get(Brand, pending["brand_id"]) if pending else None
    if q.get("error"):
        return _back(
            f"Zernio connection failed: {q.get('error_description') or q['error']}", "error", brand
        )
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
    return _back(
        "Zernio did not return the connected account yet; use “Import from Zernio”", "error", brand
    )


# ---- connect links: a client connects their own channels, no Spark account -------------------
CLIENT_CALLBACK = "/accounts/zernio/client-callback"
TEAM_NOTE = "This channel can't be connected right now. We've told the team that manages it."


def _client_back(token: str, **q: str) -> RedirectResponse:
    return RedirectResponse(f"/c/{token}?{urlencode(q)}", 303)


def _dead_link(status: int = 404) -> HTMLResponse:
    return HTMLResponse(
        "<p>This connect link is no longer valid. Ask the team that sent it for a new one.</p>",
        status,
    )


def _label(platform: str) -> str:
    from spark.platforms.zernio import ZERNIO_PLATFORMS

    meta = ZERNIO_PLATFORMS.get(platform)
    return meta.label if meta else platform


@router.get("/c/{token}/go/{platform}")
async def client_connect(
    token: str, platform: str, request: Request, db: AsyncSession = Depends(get_db)
):
    """Start Zernio's hosted connect for the brand behind a connect link."""
    from spark.services import activity, connect_links

    found = await connect_links.find(db, token)
    if found is None:
        return _dead_link()
    link, brand = found
    if platform not in connect_links.platforms(link):
        await db.commit()
        return _client_back(token, error="This link cannot connect that network.")
    adapter = ZernioAdapter.for_platform(platform)
    if not adapter.is_configured():
        await db.commit()
        return _client_back(token, error=TEAM_NOTE)
    state = token_(16)
    try:
        profile_id = await adapter.ensure_profile(brand)
        await db.commit()
        url = await adapter.connect_url(profile_id, state, CLIENT_CALLBACK)
    except (PlatformError, httpx.HTTPError) as e:
        activity.record(
            db,
            brand.id,
            None,
            "could not connect",
            "channel",
            None,
            f"{_label(platform)} through a client link: {e}",
            actor_name="Client (connect link)",
        )
        await db.commit()
        return _client_back(token, error=TEAM_NOTE)
    request.session["zernio_client"] = {
        "state": state,
        "platform": platform,
        "link_id": link.id,
        "token": token,
    }
    return RedirectResponse(url, 303)


@router.get(CLIENT_CALLBACK)
async def client_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Zernio sends the client back here; save the channel into the link's brand only."""
    from spark.services import activity, connect_links

    pending = request.session.pop("zernio_client", None)
    q = request.query_params
    if not pending:
        return HTMLResponse(
            "<p>This connection could not be finished. Open your connect link and try again.</p>",
            400,
        )
    token = pending["token"]
    if pending["state"] != q.get("state"):
        return _client_back(token, error="The connection expired. Please try again.")
    found = await connect_links.find(db, token)
    if found is None or found[0].id != pending["link_id"]:
        return _dead_link()
    link, brand = found
    platform = pending["platform"]
    who = "Client (connect link)"
    if q.get("error"):
        activity.record(
            db,
            brand.id,
            None,
            "could not connect",
            "channel",
            None,
            f"{_label(platform)} through a client link: {q['error']}",
            actor_name=who,
        )
        await db.commit()
        if q["error"] == "oauth_denied":
            return _client_back(token, error="The connection was cancelled. You can try again.")
        return _client_back(
            token,
            error="The network did not connect this channel. Please try again, or ask the team "
            "that manages it.",
        )
    if not brand.zernio_profile_id:  # never list every profile on Zernio for a client
        await db.commit()
        return _client_back(token, error=TEAM_NOTE)
    try:
        pairs = await ZernioAdapter.for_platform(platform).list_accounts(brand.zernio_profile_id)
    except (PlatformError, httpx.HTTPError) as e:
        log.warning("client connect callback for brand %s failed: %s", brand.id, e)
        await db.commit()
        return _client_back(token, error=TEAM_NOTE)
    if account_id := q.get("accountId"):
        pairs = [(p, a) for p, a in pairs if a.external_id == account_id]
    rows = []
    for plat, acc in pairs:
        rows += await save_connected(db, brand, plat, [acc], provider="zernio")
    for acc in rows:
        activity.record(
            db,
            brand.id,
            None,
            "connected",
            "channel",
            acc.id,
            f"@{acc.handle} ({_label(acc.platform)}) through a client link",
            actor_name=who,
        )
    connect_links.count_connected(link, len(rows))
    await db.commit()
    if not rows:
        return _client_back(
            token, error="The network has not confirmed the channel yet. Please try again shortly."
        )
    await connect_links.tell_team(db, brand, rows)
    return _client_back(token, connected=", ".join(f"@{a.handle}" for a in rows))
