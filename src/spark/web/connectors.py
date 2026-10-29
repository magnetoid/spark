"""Settings → Connectors: Zernio first, then Claude AI, email delivery, MCP access, direct apps."""

import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.db import get_db
from spark.models import ApiToken, Brand, SocialAccount, User
from spark.security import token as new_secret
from spark.services import connectors as conn
from spark.web.deps import current_user, flash, hx_none, is_hx, owner, render, require_brand, toast

router = APIRouter()
TOKEN_PREFIX = "spk_"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def mcp_url() -> str:
    return get_settings().base_url.rstrip("/") + "/mcp"


def _connector(key: str) -> conn.Connector:
    c = conn.BY_KEY.get(key)
    if not c:
        raise HTTPException(404, "No such connector")
    return c


def _field_rows(c: conn.Connector) -> list[dict]:
    s = get_settings()
    rows = []
    for f in c.fields:
        value = getattr(s, f.name)
        rows.append({"f": f, "value": "" if f.kind == "secret" else ("" if value is None else value),
                     "masked": conn.mask(value) if f.kind == "secret" else "",
                     "source": conn.source(f.name), "has_value": value not in (None, "")})
    return rows


@router.get("/settings/connectors")
async def connectors_page(request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    zernio_accounts = len((await db.execute(select(SocialAccount.id).where(
        SocialAccount.provider == "zernio"))).all())
    tokens = len((await db.execute(select(ApiToken.id).where(ApiToken.user_id == user.id))).all())
    cards = []
    for c in conn.CONNECTORS:
        if c.key == "mcp":
            status = ("ok", f"{tokens} token{'s' if tokens != 1 else ''}") if tokens else ("idle", "No token yet")
        elif c.key == "zernio":
            status = (("ok", f"Connected · {zernio_accounts} account{'s' if zernio_accounts != 1 else ''}")
                      if conn.is_configured(c) else ("off", "Not connected"))
        elif c.key == "email":
            status = ("ok", get_settings().email_backend.upper()) if conn.is_configured(c) else ("off", "Console only")
        elif c.key == "direct":
            n = sum(1 for _l, cid, _s in conn.DIRECT_APPS if getattr(get_settings(), cid))
            status = ("ok", f"{n} app{'s' if n != 1 else ''}") if n else ("idle", "Optional")
        else:
            status = ("ok", "Connected") if conn.is_configured(c) else ("off", "Not connected")
        cards.append({"c": c, "status": status})
    return await render(request, "settings/connectors.html", db, user, brand, cards=cards, tab="connectors")


@router.get("/settings/connectors/{key}")
async def connector_page(key: str, request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    c = _connector(key)
    ctx: dict = {"c": c, "rows": _field_rows(c), "configured": conn.is_configured(c), "tab": "connectors",
                 "can_edit": user.can_approve()}
    if c.key == "mcp":
        ctx["tokens"] = (await db.execute(select(ApiToken).where(ApiToken.user_id == user.id)
                                          .order_by(ApiToken.created_at.desc()))).scalars().all()
        ctx["mcp_url"] = mcp_url()
        from spark.mcp_server import TOOLS_FOR_UI

        ctx["mcp_tools"] = TOOLS_FOR_UI
        ctx["new_token"] = request.session.pop("new_api_token", None)
    if c.key == "direct":
        s = get_settings()
        ctx["apps"] = [{"label": label, "configured": bool(getattr(s, cid) and getattr(s, sec)),
                        "env": f"SPARK_{cid.upper()} / SPARK_{sec.upper()}"} for label, cid, sec in conn.DIRECT_APPS]
        ctx["redirect_base"] = get_settings().base_url.rstrip("/") + "/accounts/callback/"
    if c.key == "zernio" and conn.is_configured(c) and user.can_approve():
        from spark.web.accounts import webhook_status

        ctx["webhook"] = await webhook_status()
        ctx["zernio_accounts"] = len((await db.execute(select(SocialAccount.id).where(
            SocialAccount.provider == "zernio"))).all())
    if c.key == "email":
        ctx["user_email"] = user.email
    return await render(request, "settings/connector.html", db, user, brand, **ctx)


@router.post("/settings/connectors/{key}")
async def connector_save(key: str, request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(owner)):
    c = _connector(key)
    if not c.fields:
        raise HTTPException(400, "This connector has nothing to save")
    form = dict(await request.form())
    changed = await conn.save(db, c, form, user.id)
    msg = f"{c.name} saved" if changed else "Nothing changed"
    if is_hx(request):
        return hx_none(toast(msg))
    flash(request, msg)
    return RedirectResponse(f"/settings/connectors/{key}", 303)


@router.post("/settings/connectors/{key}/test")
async def connector_test(key: str, request: Request, user: User = Depends(owner)):
    c = _connector(key)
    ok, msg = await conn.test(c, user.email)
    if is_hx(request):
        return hx_none(toast(msg, "success" if ok else "error"))
    flash(request, msg, "success" if ok else "error")
    return RedirectResponse(f"/settings/connectors/{key}", 303)


# ---- personal API tokens (MCP) ---------------------------------------------------------
@router.post("/settings/connectors/mcp/tokens")
async def token_create(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    form = await request.form()
    name = str(form.get("name", "")).strip()[:120] or "MCP client"
    raw = TOKEN_PREFIX + new_secret(30)
    db.add(ApiToken(user_id=user.id, name=name, token_hash=hash_token(raw), prefix=raw[:10]))
    await db.commit()
    # Shown exactly once, on the next page view; only the hash is stored.
    request.session["new_api_token"] = {"name": name, "token": raw}
    return RedirectResponse("/settings/connectors/mcp#tokens", 303)


@router.post("/settings/connectors/mcp/tokens/{token_id}/delete")
async def token_delete(token_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       user: User = Depends(current_user)):
    t = await db.get(ApiToken, token_id)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "No such token")
    await db.delete(t)
    await db.commit()
    flash(request, f"Revoked “{t.name}”. Clients using it lose access now.")
    return RedirectResponse("/settings/connectors/mcp#tokens", 303)


async def user_for_token(db: AsyncSession, raw: str | None) -> User | None:
    """Resolve a bearer token to an active user and stamp last use (at most once a minute)."""
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None
    t = await db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(raw)))
    if not t or not t.user or not t.user.is_active:
        return None
    now = datetime.now(UTC)
    last = t.last_used_at.replace(tzinfo=UTC) if t.last_used_at and t.last_used_at.tzinfo is None else t.last_used_at
    if not last or (now - last).total_seconds() > 60:
        t.last_used_at = now
        await db.commit()
    return t.user
