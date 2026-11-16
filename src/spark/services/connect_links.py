"""Connect links: a login-free link a client opens to connect or reconnect their own channels.

The link is a `ShareLink` with kind "connect"; only its hash is stored. The connect itself is
Zernio's hosted flow, started by the server with the brand's Zernio profile, so the client never
needs a Spark account and the agency never sees a password. The link token never travels through
Zernio: the browser's session carries it between the start and the callback.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, ShareLink, SocialAccount
from spark.platforms.zernio import ZERNIO_PLATFORMS
from spark.services.email import EmailSender, get_sender
from spark.services.publisher import as_utc

log = logging.getLogger(__name__)
KIND = "connect"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def platforms(link: ShareLink) -> list[str]:
    """The networks this link may connect, in Spark's order; all of Zernio's when none were picked."""
    picked = (link.scope or {}).get("platforms") or []
    return [p for p in ZERNIO_PLATFORMS if not picked or p in picked]


def is_live(link: ShareLink | None, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return (
        link is not None
        and link.kind == KIND
        and link.revoked_at is None
        and not (link.expires_at and as_utc(link.expires_at) < now)
    )


async def find(db: AsyncSession, token: str) -> tuple[ShareLink, Brand] | None:
    """The live link for `token` and its brand, marking it used; None when it does not open."""
    link = await db.scalar(select(ShareLink).where(ShareLink.token_hash == token_hash(token)))
    if not is_live(link):
        return None
    link.last_used_at = datetime.now(UTC)
    return link, await db.get(Brand, link.brand_id)


def count_connected(link: ShareLink, n: int) -> None:
    scope = dict(link.scope or {})
    scope["connected"] = int(scope.get("connected") or 0) + n
    link.scope = scope  # a new dict, so the JSON column notices


async def zernio_channels(db: AsyncSession, brand: Brand) -> list[SocialAccount]:
    return list(
        (
            await db.execute(
                select(SocialAccount)
                .where(SocialAccount.brand_id == brand.id, SocialAccount.provider == "zernio")
                .order_by(SocialAccount.platform, SocialAccount.handle)
            )
        ).scalars()
    )


async def tell_team(
    db: AsyncSession, brand: Brand, rows: list[SocialAccount], sender: EmailSender | None = None
) -> int:
    """Email the brand's owners that a client connected channels through a link."""
    from spark.services import notify

    if not rows:
        return 0
    sender = sender or get_sender()
    names = ", ".join(f"@{a.handle}" for a in rows)
    label = {k: v.label for k, v in ZERNIO_PLATFORMS.items()}
    body = notify.layout(
        f"{brand.name}: channel connected",
        "Your client connected these channels through a connect link. They are ready to post to.",
        notify._rows([(f"@{a.handle}", label.get(a.platform, a.platform)) for a in rows]),
        f"{notify._base()}/channels?brand={brand.slug}",
        "Open Channels",
    )
    sent = 0
    for u, role in await notify._brand_people(db, brand.id):
        if role != "owner" or not notify.wants(u, "notify_channels"):
            continue
        try:
            await sender.send(u.email, f"[{brand.name}] Client connected {names}", body)
            sent += 1
        except Exception as e:  # email trouble must not undo the connect
            log.warning("connect link email to %s failed: %s", u.email, e)
    return sent
