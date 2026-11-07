"""What the few remaining server-rendered pages need: templates, session helpers, CSRF."""

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.models import User

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _localtime(dt: datetime | None, tz: str = "UTC", fmt: str = "%b %d, %H:%M") -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ZoneInfo(tz)).strftime(fmt)


templates.env.filters["localtime"] = _localtime

# ---- CSRF (shared with the JSON API) ------------------------------------------------------
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


class LoginRequired(Exception):
    pass


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
