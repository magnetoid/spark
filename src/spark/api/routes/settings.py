"""Settings: posting slots, team, brand deletion, connectors, personal tokens, Zernio webhooks."""

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    ConnectorCard,
    ConnectorFieldOut,
    ConnectorOut,
    ConnectorSave,
    SecuritySettings,
    SlotIn,
    SlotRow,
    TeamIn,
    TeamOut,
    TeamUpdate,
    TokenCreated,
    TokenOut,
)
from spark.config import get_settings
from spark.db import get_db
from spark.models import ApiToken, Brand, QueueSlot, Role, SocialAccount, User
from spark.security import hash_password
from spark.services import connectors as conn
from spark.services import tokens, twofactor
from spark.services.publisher import as_utc

log = logging.getLogger("spark.settings")
router = APIRouter(tags=["settings"])
B = "/brands/{brand_id}"


# ---- slots ---------------------------------------------------------------------------------
@router.get(B + "/slots", response_model=list[SlotRow])
async def slots(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    rows = (
        (
            await db.execute(
                select(QueueSlot)
                .where(QueueSlot.brand_id == ctx.brand.id)
                .order_by(QueueSlot.weekday, QueueSlot.time)
            )
        )
        .scalars()
        .all()
    )
    return [SlotRow.model_validate(s) for s in rows]


@router.post(B + "/slots", response_model=list[SlotRow], status_code=201)
async def add_slots(
    body: SlotIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    h, m = (int(x) for x in body.time.split(":"))
    if not (0 <= h < 24 and 0 <= m < 60) or not all(0 <= d <= 6 for d in body.weekdays):
        raise ApiError(422, "validation", "Weekdays are 0–6 and the time is HH:MM")
    if body.account_id is not None:
        acc = await db.get(SocialAccount, body.account_id)
        if acc is None or acc.brand_id != ctx.brand.id:
            raise ApiError(422, "validation", "That channel is not part of this brand")
    existing = {
        (s.weekday, s.time, s.account_id)
        for s in (
            await db.execute(select(QueueSlot).where(QueueSlot.brand_id == ctx.brand.id))
        ).scalars()
    }
    created = []
    for d in sorted(set(body.weekdays)):
        if (d, body.time, body.account_id) not in existing:
            s = QueueSlot(
                brand_id=ctx.brand.id, weekday=d, time=body.time, account_id=body.account_id
            )
            db.add(s)
            created.append(s)
    await db.commit()
    return [SlotRow.model_validate(s) for s in created]


@router.delete(B + "/slots/{slot_id}", status_code=204)
async def delete_slot(
    slot_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    await db.execute(
        delete(QueueSlot).where(QueueSlot.id == slot_id, QueueSlot.brand_id == ctx.brand.id)
    )
    await db.commit()
    return Response(status_code=204)


@router.delete("/brands/{brand_id}", status_code=204)
async def delete_brand(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.owner_brand)
):
    if await db.scalar(select(Brand.id).where(Brand.id != ctx.brand.id).limit(1)) is None:
        raise ApiError(
            409,
            "last_brand",
            "Spark needs at least one brand; create another before deleting this one",
        )
    await db.delete(ctx.brand)
    await db.commit()
    return Response(status_code=204)


# ---- team ----------------------------------------------------------------------------------
def _member(u: User) -> TeamOut:
    return TeamOut(
        id=u.id,
        name=u.name,
        email=u.email,
        role=u.role.value,
        is_active=u.is_active,
        created_at=as_utc(u.created_at) if u.created_at else None,
        two_factor=bool(u.totp_enabled),
    )


@router.get("/team", response_model=list[TeamOut])
async def team(db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)):
    rows = (
        (await db.execute(select(User).where(User.role != Role.agent).order_by(User.name)))
        .scalars()
        .all()
    )
    return [_member(u) for u in rows]


@router.post("/team", response_model=TeamOut, status_code=201)
async def team_add(
    body: TeamIn, db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)
):
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise ApiError(409, "email_taken", "A user with that email already exists")
    member = User(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        role=Role(body.role),
    )
    db.add(member)
    await db.commit()
    return _member(member)


@router.patch("/team/{user_id}", response_model=TeamOut)
async def team_update(
    user_id: int,
    body: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.owner),
):
    member = await db.get(User, user_id)
    if not member:
        raise not_found("No such team member")
    if member.id == user.id:
        raise ApiError(409, "self", "Ask another owner to change your own role or access")
    if body.role is not None:
        member.role = Role(body.role)
    if body.is_active is not None:
        member.is_active = body.is_active
    await db.commit()
    return _member(member)


@router.delete("/team/{user_id}/two-factor", status_code=204)
async def team_two_factor_off(
    user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)
):
    """For a member who lost their phone and their recovery codes. They sign in with the password
    alone until they set two-factor up again (at once, when the workspace requires it)."""
    member = await db.get(User, user_id)
    if not member:
        raise not_found("No such team member")
    if member.id == user.id:
        raise ApiError(409, "self", "Turn off your own two-factor under Settings → You")
    twofactor.clear(member)
    await db.commit()
    return Response(status_code=204)


# ---- workspace security ---------------------------------------------------------------------
@router.get("/settings/security", response_model=SecuritySettings)
async def security(user: User = Depends(deps.owner)):
    return SecuritySettings(require_two_factor=get_settings().require_two_factor)


@router.put("/settings/security", response_model=SecuritySettings)
async def security_save(
    body: SecuritySettings, db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)
):
    if body.require_two_factor and not user.totp_enabled:
        raise ApiError(409, "two_factor_first", "Turn on two-factor for your own account first")
    await conn.save_value(db, "require_two_factor", body.require_two_factor, user.id)
    return SecuritySettings(require_two_factor=get_settings().require_two_factor)


# ---- connectors -----------------------------------------------------------------------------
def _field_rows(c: conn.Connector) -> list[ConnectorFieldOut]:
    s = get_settings()
    rows = []
    for f in c.fields:
        value = getattr(s, f.name)
        rows.append(
            ConnectorFieldOut(
                name=f.name,
                label=f.label,
                kind=f.kind,
                options=[list(o) for o in f.options],
                help=f.help,
                placeholder=f.placeholder,
                value=None if f.kind == "secret" else value,
                masked=conn.mask(value) if f.kind == "secret" else "",
                source=conn.source(f.name),
                has_value=value not in (None, ""),
            )
        )
    return rows


async def _connector_out(db: AsyncSession, c: conn.Connector, user: User) -> ConnectorOut:
    extra: dict = {}
    hidden: set[str] = set()
    if c.key == "mcp":
        extra = {"mcp_url": get_settings().base_url.rstrip("/") + "/mcp"}
    elif c.key == "janus":
        from spark.services import agent as agent_svc

        st = await agent_svc.status()
        extra = {
            "janus": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in st.items()}
        }
        if (
            get_settings().janus_managed
        ):  # the wiring comes from compose; only Janus's own options are shown
            hidden = {
                "janus_base_url",
                "janus_api_key",
                "janus_update_webhook",
                "janus_update_token",
            }
        from spark.mcp_server import TOOLS_FOR_UI

        extra["tools"] = [{"name": n, "summary": s} for n, s in TOOLS_FOR_UI]
    if c.key == "direct":
        s = get_settings()
        extra = {
            "apps": [
                {
                    "label": label,
                    "configured": bool(getattr(s, cid) and getattr(s, sec)),
                    "env": f"SPARK_{cid.upper()} / SPARK_{sec.upper()}",
                }
                for label, cid, sec in conn.DIRECT_APPS
            ],
            "redirect_base": s.base_url.rstrip("/") + "/accounts/callback/",
        }
    if c.key == "zernio" and conn.is_configured(c):
        extra["accounts"] = len(
            (
                await db.execute(select(SocialAccount.id).where(SocialAccount.provider == "zernio"))
            ).all()
        )
        if user.can_approve():
            from spark.services.webhooks import webhook_status

            extra["webhook"] = await webhook_status()
    return ConnectorOut(
        key=c.key,
        name=c.name,
        tagline=c.tagline,
        description=c.description,
        docs=c.docs,
        kind=c.kind,
        configured=conn.is_configured(c),
        fields=[f for f in _field_rows(c) if f.name not in hidden],
        extra=extra,
    )


@router.get("/settings/connectors", response_model=list[ConnectorCard])
async def connectors(db: AsyncSession = Depends(get_db), user: User = Depends(deps.current_user)):
    zernio_accounts = len(
        (await db.execute(select(SocialAccount.id).where(SocialAccount.provider == "zernio"))).all()
    )
    tokens_n = len((await db.execute(select(ApiToken.id).where(ApiToken.user_id == user.id))).all())
    s = get_settings()
    out = []
    for c in conn.CONNECTORS:
        configured = conn.is_configured(c)
        if c.key == "mcp":
            status = (
                f"{tokens_n} token{'s' if tokens_n != 1 else ''}" if tokens_n else "No token yet"
            )
            configured = tokens_n > 0
        elif c.key == "zernio":
            status = (
                f"Connected · {zernio_accounts} account{'s' if zernio_accounts != 1 else ''}"
                if configured
                else "Not connected"
            )
        elif c.key == "email":
            status = s.email_backend.upper() if configured else "Console only"
        elif c.key == "chat":
            from spark.services import chat

            status = ", ".join(chat.destinations()) if configured else "Not connected"
        elif c.key == "direct":
            n = sum(1 for _l, cid, _s in conn.DIRECT_APPS if getattr(s, cid))
            status = f"{n} app{'s' if n != 1 else ''}" if n else "Optional"
        else:
            status = "Connected" if configured else "Not connected"
        out.append(
            ConnectorCard(
                key=c.key,
                name=c.name,
                tagline=c.tagline,
                kind=c.kind,
                tags=list(c.tags),
                configured=configured,
                status=status,
            )
        )
    return out


def _connector(key: str) -> conn.Connector:
    c = conn.BY_KEY.get(key)
    if not c:
        raise not_found("No such connector")
    return c


@router.get("/settings/connectors/{key}", response_model=ConnectorOut)
async def connector(key: str, db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)):
    return await _connector_out(db, _connector(key), user)


@router.put("/settings/connectors/{key}", response_model=ConnectorOut)
async def connector_save(
    key: str,
    body: ConnectorSave,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.owner),
):
    c = _connector(key)
    form: dict = {}
    for f in c.fields:
        if f.name in body.values and body.values[f.name] is not None:
            v = body.values[f.name]
            form[f.name] = ("true" if v else "false") if isinstance(v, bool) else str(v)
        elif f.kind == "bool":  # a switch the request does not mention stays as it is
            form[f.name] = "true" if getattr(get_settings(), f.name) else "false"
    for name in body.clear:
        form[f"clear_{name}"] = "1"
    await conn.save(db, c, form, user.id)
    if key == "janus" and get_settings().janus_managed:
        from spark.services import janus_setup

        out = await janus_setup.sync(
            db, force=True
        )  # best effort: the connector page shows the result
        if out["result"] in ("unreachable", "failed"):
            log.warning("Janus configuration not pushed after save: %s", out["detail"])
    return await _connector_out(db, c, user)


@router.post("/settings/connectors/{key}/test")
async def connector_test(key: str, user: User = Depends(deps.owner)):
    ok, msg = await conn.test(_connector(key), user.email)
    if not ok:
        raise ApiError(400, "test_failed", msg)
    return {"message": msg}


@router.post("/settings/janus/sync")
async def janus_sync(db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)):
    """Push Spark's configuration to the built-in Janus now."""
    from spark.services import janus_setup

    out = await janus_setup.sync(db, force=True)
    if out["result"] in ("unreachable", "failed", "unconfigured"):
        raise ApiError(502, "janus_sync_failed", out["detail"])
    return {"message": out["detail"], **out}


@router.post("/settings/janus/update")
async def janus_update(user: User = Depends(deps.owner)):
    """Built in: restart the gateway, which pulls the latest Janus on its way back up.
    Elsewhere: ask the deploy hook to rebuild the Janus service."""
    import httpx

    from spark.services import agent as agent_svc
    from spark.services import janus_setup
    from spark.services.janus import JanusError

    s = get_settings()
    if s.janus_managed:
        try:
            await janus_setup.restart_for_update()
        except JanusError as e:
            raise ApiError(502, "update_failed", str(e)) from e
        return {
            "message": "Janus is restarting and picks up the latest version on the way back up."
        }
    if not s.janus_update_webhook:
        raise ApiError(409, "no_webhook", "Add the update webhook under Connectors → Janus first")
    headers = {"Authorization": f"Bearer {s.janus_update_token}"} if s.janus_update_token else {}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(s.janus_update_webhook, headers=headers)
        if r.status_code >= 400:
            raise ApiError(
                502, "update_failed", f"The webhook answered {r.status_code}: {r.text[:200]}"
            )
    except httpx.HTTPError as e:
        raise ApiError(502, "update_failed", f"Could not reach the webhook: {e}") from e
    agent_svc.forget_status()
    return {"message": "Update started. Janus restarts with the latest build in a few minutes."}


@router.post("/settings/zernio/webhook")
async def zernio_webhook_register(user: User = Depends(deps.owner)):
    from spark.platforms.zernio import ZernioAdapter
    from spark.services.webhooks import ZERNIO_EVENTS, webhook_secret
    from spark.services.webhooks import webhook_url as _webhook_url

    try:
        w = await ZernioAdapter().upsert_webhook(_webhook_url(), webhook_secret(), ZERNIO_EVENTS)
    except Exception as e:
        raise ApiError(502, "zernio", f"Zernio: could not register the webhook ({e})")
    return {
        "message": f"Zernio will notify {_webhook_url()} ({len(w.get('events') or ZERNIO_EVENTS)} events)"
    }


@router.post("/settings/zernio/webhook/test")
async def zernio_webhook_test(user: User = Depends(deps.owner)):
    from spark.platforms.zernio import ZernioAdapter
    from spark.services.webhooks import webhook_url as _webhook_url

    try:
        adapter = ZernioAdapter()
        hooks = await adapter.list_webhooks()
        w = next((w for w in hooks if w.get("url") == _webhook_url()), None)
        if not w:
            raise ApiError(409, "not_registered", "Enable webhooks first")
        await adapter.test_webhook(w.get("_id"))
    except ApiError:
        raise
    except Exception as e:
        raise ApiError(502, "zernio", f"Zernio: test failed ({e})")
    return {"message": "Test event sent; Zernio reports deliveries on its webhooks page"}


# ---- personal tokens --------------------------------------------------------------------------
def _token(t: ApiToken) -> TokenOut:
    return TokenOut(
        id=t.id,
        name=t.name,
        prefix=t.prefix,
        last_used_at=as_utc(t.last_used_at) if t.last_used_at else None,
        created_at=as_utc(t.created_at) if t.created_at else None,
    )


@router.get("/me/tokens", response_model=list[TokenOut])
async def my_tokens(db: AsyncSession = Depends(get_db), user: User = Depends(deps.current_user)):
    rows = (
        (
            await db.execute(
                select(ApiToken)
                .where(ApiToken.user_id == user.id)
                .order_by(ApiToken.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_token(t) for t in rows]


@router.post("/me/tokens", response_model=TokenCreated, status_code=201)
async def create_token(
    body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(deps.current_user)
):
    raw, row = await tokens.create_token(db, user, str(body.get("name") or "API client"))
    return TokenCreated(**_token(row).model_dump(), token=raw)


@router.delete("/me/tokens/{token_id}", status_code=204)
async def delete_token(
    token_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(deps.current_user)
):
    t = await db.get(ApiToken, token_id)
    if not t or t.user_id != user.id:
        raise not_found("No such token")
    await db.delete(t)
    await db.commit()
    return Response(status_code=204)
