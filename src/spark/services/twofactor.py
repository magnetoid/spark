"""Two-factor sign-in: authenticator codes (RFC 6238 TOTP) and one-time recovery codes.

Standard library only. The secret is stored encrypted; recovery codes are stored as keyed
hashes, so a copy of the database alone gives neither.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import User
from spark.security import decrypt, encrypt

STEP = 30  # seconds one code lives
DIGITS = 6
WINDOW = 1  # steps of clock drift accepted on each side
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
RECOVERY_CODES = 10
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/i/l


class Locked(Exception):
    """Too many wrong codes in a row: the code step is paused for LOCK_SECONDS."""


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code_at(secret: str, at: float) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", int(at // STEP)), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    number = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def otpauth_uri(secret: str, email: str, issuer: str = "Spark") -> str:
    """What the QR code holds; every authenticator app reads this format."""
    query = urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": STEP}
    )
    return f"otpauth://totp/{quote(f'{issuer}:{email}', safe=':')}?{query}"


def matching_step(secret: str, code: str, now: float, after: int | None = None) -> int | None:
    """The time step `code` belongs to, or None. Steps up to `after` were used already."""
    code = "".join(code.split())
    if len(code) != DIGITS or not code.isdigit():
        return None
    current = int(now // STEP)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if after is not None and step <= after:
            continue
        if hmac.compare_digest(code_at(secret, step * STEP), code):
            return step
    return None


def _normal(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum())


def _hash(code: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, b"recovery:" + _normal(code).encode(), hashlib.sha256).hexdigest()


def new_recovery_codes(user: User) -> list[str]:
    """Replace the user's recovery codes. The plain codes are returned once and never stored."""
    plain = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        plain.append(f"{raw[:5]}-{raw[5:]}")
    user.recovery_codes = [_hash(c) for c in plain]
    return plain


def begin(user: User) -> str:
    """Start setup: a fresh secret that stays pending until a code confirms it."""
    secret = new_secret()
    user.totp_secret = encrypt(secret)
    return secret


def clear(user: User) -> None:
    user.totp_secret = None
    user.totp_enabled = False
    user.recovery_codes = []
    user.totp_last_step = None
    user.totp_failed = 0
    user.totp_locked_until = None


async def confirm(db: AsyncSession, user: User, code: str, now: float | None = None) -> list[str]:
    """Finish setup with a code from the app. Returns recovery codes, or [] for a wrong code."""
    secret = decrypt(user.totp_secret)
    step = matching_step(secret, code, now or time.time()) if secret else None
    if step is None:
        return []
    user.totp_enabled = True
    user.totp_last_step = step
    user.totp_failed, user.totp_locked_until = 0, None
    plain = new_recovery_codes(user)
    await db.commit()
    return plain


async def check(db: AsyncSession, user: User, code: str, now: float | None = None) -> bool:
    """True for the user's current authenticator code or an unused recovery code.

    A code works once. Five wrong ones in a row raise Locked for the next 15 minutes.
    """
    now = now or time.time()
    until = user.totp_locked_until
    if until is not None:
        until = until if until.tzinfo else until.replace(tzinfo=UTC)
        if until.timestamp() > now:
            raise Locked
    secret = decrypt(user.totp_secret) if user.totp_enabled else None
    ok = False
    step = matching_step(secret, code, now, after=user.totp_last_step) if secret else None
    if step is not None:
        # one UPDATE decides the race: two requests with the same code cannot both win
        won = await db.execute(
            update(User)
            .where(
                User.id == user.id,
                or_(User.totp_last_step.is_(None), User.totp_last_step < step),
            )
            .values(totp_last_step=step)
            .execution_options(synchronize_session=False)
        )
        ok = won.rowcount == 1
        if ok:
            user.totp_last_step = step
    elif secret and (hashed := _hash(code)) in (user.recovery_codes or []):
        user.recovery_codes = [c for c in user.recovery_codes if c != hashed]
        ok = True
    if ok:
        user.totp_failed, user.totp_locked_until = 0, None
    else:
        user.totp_failed = (user.totp_failed or 0) + 1
        if user.totp_failed >= MAX_FAILURES:
            user.totp_failed = 0
            user.totp_locked_until = datetime.fromtimestamp(now + LOCK_SECONDS, UTC)
    await db.commit()
    return ok


async def reset_by_email(db: AsyncSession, email: str) -> bool:
    """For someone locked out with no recovery codes left (`spark reset-two-factor <email>`)."""
    user = await db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if user is None:
        return False
    clear(user)
    await db.commit()
    return True
