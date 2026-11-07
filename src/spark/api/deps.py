"""Auth, CSRF and brand context for API routes.

Two ways in: the browser session cookie (plus an X-CSRF-Token header on writes), or a
personal `Bearer spk_…` token, which never touches the cookie and needs no CSRF token.
The brand always comes from the path, never from the session, so two tabs can show two
brands and scripts need no hidden state.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.errors import ApiError, forbidden, login_required, not_found
from spark.db import get_db
from spark.models import Brand, User
from spark.services import access, tokens
from spark.web.deps import (  # the session cookie's CSRF token, shared with the public bio form
    CSRF_KEY,
    csrf_token,
)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _bearer(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    return value[7:].strip() if value.lower().startswith("bearer ") else None


def check_csrf(request: Request) -> None:
    """Cookie-authenticated writes must echo the session's CSRF token in a header."""
    if request.method not in WRITE_METHODS:
        return
    expected = request.session.get(CSRF_KEY)
    sent = request.headers.get("X-CSRF-Token", "")
    if not expected or not hmac.compare_digest(expected, sent):
        raise ApiError(403, "csrf", "Missing or stale CSRF token; reload and try again")


async def optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    raw = _bearer(request)
    if raw is not None:
        user = await tokens.user_for_token(db, raw)
        if user is None:
            raise ApiError(401, "invalid_token", "Invalid or revoked API token",
                           headers={"WWW-Authenticate": 'Bearer realm="spark"'})
        request.state.auth = "bearer"
        return user
    check_csrf(request)
    uid = request.session.get("user_id")
    user = await db.get(User, uid) if uid else None
    if user is None or not user.is_active:
        return None
    request.state.auth = "cookie"
    return user


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise login_required()
    return user


async def editor(user: User = Depends(current_user)) -> User:
    if not user.can_edit():
        raise forbidden("Editors and owners only")
    return user


async def owner(user: User = Depends(current_user)) -> User:
    if not user.can_approve():
        raise forbidden("Owners only")
    return user


@dataclass
class BrandCtx:
    brand: Brand
    user: User
    role: str  # the user's role within this brand: owner, editor, viewer or client

    def can_edit(self) -> bool:
        return access.can_edit(self.role)

    def can_approve(self) -> bool:
        return access.can_approve(self.role)

    def can_manage(self) -> bool:
        return access.can_manage(self.role)


async def brand_ctx(brand_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)) -> BrandCtx:
    brand = await db.get(Brand, brand_id)
    role = await access.role_for(db, user, brand_id) if brand else None
    if brand is None or role is None:
        raise not_found("No such brand")  # not a member: the brand does not exist for this user
    return BrandCtx(brand=brand, user=user, role=role)


async def editor_brand(ctx: BrandCtx = Depends(brand_ctx)) -> BrandCtx:
    if not ctx.can_edit():
        raise forbidden("Editors and owners only")
    return ctx


async def approver_brand(ctx: BrandCtx = Depends(brand_ctx)) -> BrandCtx:
    if not ctx.can_approve():
        raise forbidden("Owners and clients approve")
    return ctx


async def owner_brand(ctx: BrandCtx = Depends(brand_ctx)) -> BrandCtx:
    if not ctx.can_manage():
        raise forbidden("Owners only")
    return ctx


def new_csrf(request: Request) -> str:
    return csrf_token(request)
