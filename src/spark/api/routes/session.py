"""Who am I, sign in, sign out, first-run setup, my preferences."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError
from spark.api.schemas import (
    BrandOut,
    LoginIn,
    MeUpdate,
    PasswordChange,
    RecoveryCodes,
    SessionOut,
    SetupIn,
    TwoFactorCode,
    TwoFactorDisable,
    TwoFactorPassword,
    TwoFactorSetup,
    UserOut,
)
from spark.config import get_settings
from spark.db import get_db
from spark.models import Role, User
from spark.security import hash_password, verify_password
from spark.services import access, twofactor

router = APIRouter(tags=["session"])
ALLOWED_PREFS = {
    "onboarding_dismissed",
    "default_action",
    "shortcuts",
    "notify_failed",
    "notify_approvals",
    "notify_channels",
    "digest_weekly",
    "theme",
    "sidebar_collapsed",
}


async def _check_code(db: AsyncSession, user: User, code: str, status: int) -> None:
    """An authenticator or recovery code, or the error the SPA shows for a wrong or paused one."""
    try:
        ok = await twofactor.check(db, user, code)
    except twofactor.Locked:
        raise ApiError(
            429, "too_many_attempts", "Too many wrong codes. Wait 15 minutes and try again."
        ) from None
    if not ok:
        raise ApiError(status, "invalid_code", "That code is not right. Try the next one.")


async def _session(request: Request, db: AsyncSession, user: User | None) -> SessionOut:
    brands = await access.visible_brands(db, user) if user else []
    needs_setup = not await db.scalar(select(func.count(User.id)))
    s = get_settings()
    return SessionOut(
        user=UserOut.of(user) if user else None,
        csrf_token=deps.new_csrf(request),
        brands=[BrandOut.of(b, role) for b, role in brands],
        needs_setup=needs_setup,
        two_factor_setup_required=bool(
            user and deps.needs_two_factor_setup(user, getattr(request.state, "auth", None))
        ),
        features={
            "ai": bool(s.anthropic_api_key),
            "require_two_factor": bool(user and s.require_two_factor),
            "zernio": bool(s.zernio_api_key),
            "email": s.email_backend != "console",
            "images": bool(s.openai_api_key),
            "janus": bool(s.janus_base_url and s.janus_api_key),
        },
    )


@router.get("/session", response_model=SessionOut)
async def session(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(deps.optional_user),
):
    return await _session(request, db, user)


@router.post("/auth/login", response_model=SessionOut, dependencies=[Depends(deps.check_csrf)])
async def login(body: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if not user or not user.is_active or not verify_password(user.password_hash, body.password):
        raise ApiError(401, "invalid_credentials", "Invalid email or password")
    if user.totp_enabled:
        # the second step is the same request again with a code: nothing is kept in between
        if not (body.code or "").strip():
            raise ApiError(401, "two_factor_required", "Enter the code from your authenticator app")
        await _check_code(db, user, body.code, 401)
    request.session.clear()  # a fresh session (and CSRF token) on every sign-in
    request.session["user_id"] = user.id
    return await _session(request, db, user)


@router.post("/auth/logout", response_model=SessionOut, dependencies=[Depends(deps.check_csrf)])
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    request.session.clear()
    return await _session(request, db, None)


@router.post("/auth/setup", response_model=SessionOut, dependencies=[Depends(deps.check_csrf)])
async def setup(body: SetupIn, request: Request, db: AsyncSession = Depends(get_db)):
    """First run only: create the owner account."""
    if await db.scalar(select(func.count(User.id))):
        raise ApiError(409, "already_set_up", "Spark already has an owner; sign in instead")
    user = User(
        name=body.name.strip(),
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=Role.owner,
    )
    db.add(user)
    await db.commit()
    request.session.clear()
    request.session["user_id"] = user.id
    return await _session(request, db, user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(deps.signed_in)):
    return UserOut.of(user)


@router.patch("/me", response_model=UserOut)
async def me_update(
    body: MeUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(deps.signed_in)
):
    if body.name is not None:
        user.name = body.name.strip()
    if body.email is not None:
        email = body.email.lower()
        if await db.scalar(select(User.id).where(User.email == email, User.id != user.id)):
            raise ApiError(409, "email_taken", "That email belongs to another team member")
        user.email = email
    if body.prefs is not None:
        user.prefs = {
            **(user.prefs or {}),
            **{k: v for k, v in body.prefs.items() if k in ALLOWED_PREFS},
        }
    await db.commit()
    return UserOut.of(user)


@router.post("/me/password", response_model=UserOut)
async def me_password(
    body: PasswordChange,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.signed_in),
):
    if not verify_password(user.password_hash, body.current):
        raise ApiError(400, "wrong_password", "Current password is wrong")
    user.password_hash = hash_password(body.new)
    await db.commit()
    return UserOut.of(user)


# ---- two-factor sign-in ---------------------------------------------------------------------
def _password_or_400(user: User, password: str) -> None:
    if not verify_password(user.password_hash, password):
        raise ApiError(400, "wrong_password", "That password is wrong")


@router.post("/me/two-factor/setup", response_model=TwoFactorSetup)
async def two_factor_setup(
    body: TwoFactorPassword,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.signed_in),
):
    """Step 1: a secret for the authenticator app. Nothing changes at sign-in until step 2."""
    _password_or_400(user, body.password)
    if user.totp_enabled:
        raise ApiError(409, "already_enabled", "Two-factor is already on for your account")
    secret = twofactor.begin(user)
    await db.commit()
    return TwoFactorSetup(secret=secret, otpauth_uri=twofactor.otpauth_uri(secret, user.email))


@router.post("/me/two-factor/enable", response_model=RecoveryCodes)
async def two_factor_enable(
    body: TwoFactorCode,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.signed_in),
):
    """Step 2: a code from the app proves it was set up. Recovery codes are shown this once."""
    if user.totp_enabled:
        raise ApiError(409, "already_enabled", "Two-factor is already on for your account")
    if not user.totp_secret:
        raise ApiError(409, "not_started", "Start the setup first")
    codes = await twofactor.confirm(db, user, body.code)
    if not codes:
        raise ApiError(400, "invalid_code", "That code is not right. Try the next one.")
    return RecoveryCodes(recovery_codes=codes)


@router.post("/me/two-factor/disable", response_model=UserOut)
async def two_factor_disable(
    body: TwoFactorDisable,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.signed_in),
):
    _password_or_400(user, body.password)
    if not user.totp_enabled:
        raise ApiError(409, "not_enabled", "Two-factor is not on for your account")
    await _check_code(db, user, body.code, 400)
    twofactor.clear(user)
    await db.commit()
    return UserOut.of(user)


@router.post("/me/two-factor/recovery-codes", response_model=RecoveryCodes)
async def two_factor_recovery_codes(
    body: TwoFactorPassword,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.signed_in),
):
    """A new set of ten; the old ones stop working."""
    _password_or_400(user, body.password)
    if not user.totp_enabled:
        raise ApiError(409, "not_enabled", "Two-factor is not on for your account")
    codes = twofactor.new_recovery_codes(user)
    await db.commit()
    return RecoveryCodes(recovery_codes=codes)
