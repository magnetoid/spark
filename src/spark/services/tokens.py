"""Personal API tokens (`spk_…`) for the MCP server and the JSON API. Only a SHA-256 hash is
stored; the raw token is shown once when it is created."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import ApiToken, User
from spark.security import token as new_secret

TOKEN_PREFIX = "spk_"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_token(db: AsyncSession, user: User, name: str) -> tuple[str, ApiToken]:
    """Create a token for `user`; returns (raw token, row). The raw token is not stored."""
    raw = TOKEN_PREFIX + new_secret(30)
    row = ApiToken(
        user_id=user.id,
        name=(name or "API client").strip()[:120] or "API client",
        token_hash=hash_token(raw),
        prefix=raw[:10],
    )
    db.add(row)
    await db.commit()
    return raw, row


async def user_for_token(db: AsyncSession, raw: str | None) -> User | None:
    """Resolve a bearer token to an active user and stamp last use (at most once a minute)."""
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None
    t = await db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(raw)))
    if not t or not t.user or not t.user.is_active:
        return None
    now = datetime.now(UTC)
    last = t.last_used_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    if not last or (now - last).total_seconds() > 60:
        t.last_used_at = now
        await db.commit()
    return t.user
