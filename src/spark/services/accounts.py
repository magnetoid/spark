"""Connected social accounts: save what an adapter found, toggle, remove."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, SocialAccount
from spark.platforms.base import ConnectedAccount


async def save_connected(
    db: AsyncSession,
    brand: Brand,
    platform: str,
    found: list[ConnectedAccount],
    provider: str = "direct",
    skipped: list[str] | None = None,
) -> list[SocialAccount]:
    """Upsert accounts an adapter returned; returns the rows (new or refreshed), not yet committed.
    A channel already connected to another brand is left there (its handle goes to `skipped`)."""
    out: list[SocialAccount] = []
    for c in found:
        elsewhere = await db.scalar(
            select(SocialAccount).where(
                SocialAccount.brand_id != brand.id,
                SocialAccount.platform == platform,
                SocialAccount.external_id == c.external_id,
            )
        )
        if elsewhere is not None:
            if skipped is not None:
                skipped.append(f"{c.handle} (connected to another brand)")
            continue
        acc = await db.scalar(
            select(SocialAccount).where(
                SocialAccount.brand_id == brand.id,
                SocialAccount.platform == platform,
                SocialAccount.external_id == c.external_id,
            )
        )
        if acc is None:
            acc = SocialAccount(
                brand_id=brand.id, platform=platform, external_id=c.external_id, provider=provider
            )
            db.add(acc)
        acc.handle = c.handle
        acc.display_name = c.display_name
        acc.avatar_url = c.avatar_url
        acc.access_token = c.access_token
        acc.refresh_token = c.refresh_token
        acc.token_expires_at = c.expires_at
        acc.extra = {**(acc.extra or {}), **c.extra}
        acc.followers = c.followers
        acc.is_active = True
        acc.last_error = None
        out.append(acc)
    await db.flush()
    return out
