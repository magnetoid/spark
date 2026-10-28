import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.models import Brand, User
from spark.platforms import registry

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _localtime(dt: datetime | None, tz: str = "UTC", fmt: str = "%b %d, %H:%M") -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ZoneInfo(tz)).strftime(fmt)


def _compact(n: int | float | None) -> str:
    n = n or 0
    for unit, div in (("M", 1_000_000), ("K", 1_000)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}".replace(".0", "")
    return f"{n:,.0f}"


templates.env.filters["localtime"] = _localtime
templates.env.filters["compact"] = _compact
templates.env.globals["platforms"] = registry
# Cache-buster for /static assets: changes on every process start (deploys, dev reloads)
templates.env.globals["static_v"] = int(datetime.now(UTC).timestamp())


# ---- CSRF -------------------------------------------------------------------
CSRF_KEY = "csrf"


def csrf_token(request: Request) -> str:
    tok = request.session.get(CSRF_KEY)
    if not tok:
        from spark.security import token as _token

        tok = request.session[CSRF_KEY] = _token(24)
    return tok


def csrf_field(request: Request) -> Markup:
    return Markup(f'<input type="hidden" name="{CSRF_KEY}" value="{csrf_token(request)}">')


templates.env.globals["csrf_token"] = csrf_token
templates.env.globals["csrf_field"] = csrf_field


# ---- HTMX helpers -----------------------------------------------------------
def is_hx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def hx_trigger_headers(trigger: dict | None) -> dict:
    return {"HX-Trigger": json.dumps(trigger)} if trigger else {}


def toast(message: str, kind: str = "success") -> dict:
    """An HX-Trigger payload the page turns into a toast (see static/app.js)."""
    return {"toast": {"message": message, "kind": kind}}


def hx_render(request: Request, name: str, ctx: dict, *, trigger: dict | None = None, status_code: int = 200):
    """Render a partial for an HTMX request, optionally firing client events."""
    return templates.TemplateResponse(request, name, ctx, status_code=status_code,
                                      headers=hx_trigger_headers(trigger))


def hx_none(trigger: dict | None = None, status_code: int = 204) -> Response:
    """No content to swap; just fire events (toast, post-saved, ...)."""
    return Response(status_code=status_code, headers={"HX-Reswap": "none", **hx_trigger_headers(trigger)})


class LoginRequired(Exception):
    pass


def flash(request: Request, message: str, kind: str = "success") -> None:
    request.session.setdefault("flash", []).append({"message": message, "kind": kind})


def pop_flash(request: Request) -> list[dict]:
    return request.session.pop("flash", [])


templates.env.globals["pop_flash"] = pop_flash


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    uid = request.session.get("user_id")
    user = await db.get(User, uid) if uid else None
    if not user or not user.is_active:
        raise LoginRequired()
    return user


async def editor(user: User = Depends(current_user)) -> User:
    if not user.can_edit():
        raise HTTPException(403, "Editors only")
    return user


async def owner(user: User = Depends(current_user)) -> User:
    if not user.can_approve():
        raise HTTPException(403, "Owners only")
    return user


async def current_brand(
    request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
) -> Brand | None:
    bid = request.session.get("brand_id")
    brand = await db.get(Brand, bid) if bid else None
    if brand is None:
        brand = await db.scalar(select(Brand).order_by(Brand.id).limit(1))
        if brand:
            request.session["brand_id"] = brand.id
    return brand


async def require_brand(brand: Brand | None = Depends(current_brand)) -> Brand:
    if brand is None:
        raise HTTPException(303, headers={"Location": "/brands/new"})
    return brand


async def render(
    request: Request,
    name: str,
    db: AsyncSession,
    user: User | None = None,
    brand: Brand | None = None,
    status_code: int = 200,
    **ctx,
):
    brands = (await db.execute(select(Brand).order_by(Brand.name))).scalars().all() if user else []
    return templates.TemplateResponse(
        request,
        name,
        {"user": user, "brand": brand, "brands": brands, "path": request.url.path, **ctx},
        status_code=status_code,
    )
