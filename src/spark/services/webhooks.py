"""Inbound Zernio webhooks (https://docs.zernio.com/webhooks).

Zernio signs each delivery: lowercase hex HMAC-SHA256 of the raw body with the
subscription secret in `X-Zernio-Signature`; delivery is at least once, so we
record every event id and ignore repeats. Events replace polling for the
moments that matter: a post went out (or failed) and an account came or went.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.config import get_settings
from spark.models import Brand, Post, PostStatus, PostTarget, SocialAccount, WebhookEvent
from spark.platforms.zernio import from_zernio

log = logging.getLogger(__name__)

# What Spark subscribes to when it registers its endpoint
ZERNIO_EVENTS = [
    "post.published", "post.failed", "post.partial",
    "post.platform.published", "post.platform.failed", "post.platform.deleted",
    "account.connected", "account.disconnected", "account.permissions_changed",
]


def webhook_secret() -> str:
    """Explicit secret, else one derived from the app secret (stable across restarts)."""
    s = get_settings()
    if s.zernio_webhook_secret:
        return s.zernio_webhook_secret
    return hmac.new(s.secret_key.encode(), b"zernio-webhook", hashlib.sha256).hexdigest()


def verify_signature(raw: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(webhook_secret().encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


async def remember(db: AsyncSession, event_id: str, event: str) -> bool:
    """True the first time an event id is seen, False on a redelivery."""
    if not event_id:
        return True
    db.add(WebhookEvent(id=event_id[:64], event=event[:64], received_at=datetime.now(UTC)))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    return True


async def _account(db: AsyncSession, account_id: str | None) -> SocialAccount | None:
    if not account_id:
        return None
    return await db.scalar(select(SocialAccount).where(
        SocialAccount.provider == "zernio", SocialAccount.external_id == account_id))


async def _target(db: AsyncSession, account: SocialAccount, zernio_post_id: str | None) -> PostTarget | None:
    if not zernio_post_id:
        return None
    return await db.scalar(select(PostTarget).where(
        PostTarget.account_id == account.id, PostTarget.remote_id == zernio_post_id)
        .options(selectinload(PostTarget.post).selectinload(Post.targets)))


def _apply_platform_result(target: PostTarget, status: str, url: str | None, error: str | None) -> bool:
    """Mirror Zernio's per-platform outcome onto our target. Returns True when something changed."""
    if status == "published":
        changed = target.status != PostStatus.published or (url and target.remote_url != url)
        target.status = PostStatus.published
        target.published_at = target.published_at or datetime.now(UTC)
        target.remote_url = url or target.remote_url
        target.error = None
        target.next_attempt_at = None
        target.account.last_error = None
        return bool(changed)
    if status == "deleted":
        if target.status == PostStatus.published:
            # It went out and was removed on the platform later: still published, not a failure.
            target.remote_url = None
            target.error = (error or "Deleted on the platform after publishing")[:2000]
            return True
        status = "failed"
    if status == "failed":
        if target.status == PostStatus.published:
            return False  # we already saw it go out; a late failure report is noise
        if target.status == PostStatus.failed:
            return False  # already recorded (post.failed and post.platform.failed both arrive)
        target.status = PostStatus.failed
        target.error = (error or "Zernio reported the post as failed")[:2000]
        target.next_attempt_at = None
        target.notified_at = None
        return True
    return False


async def handle_zernio_event(db: AsyncSession, payload: dict) -> str:
    """Process one event. Returns a short word describing what happened (for logs/tests)."""
    event = payload.get("event", "")
    if payload.get("test") or event == "webhook.test":
        return "test"

    if event.startswith("post.platform."):
        acc = await _account(db, (payload.get("account") or {}).get("accountId"))
        if not acc:
            return "unknown-account"
        t = await _target(db, acc, (payload.get("post") or {}).get("id"))
        if not t:
            return "unknown-post"
        pl = payload.get("platform") or {}
        changed = _apply_platform_result(t, pl.get("status") or event.rsplit(".", 1)[-1],
                                         pl.get("publishedUrl"), pl.get("error"))
        t.post.refresh_status()
        await db.commit()
        return "updated" if changed else "unchanged"

    if event in ("post.published", "post.failed", "post.partial"):
        post = payload.get("post") or {}
        changed = 0
        for pl in post.get("platforms") or []:
            acc = await _account(db, pl.get("accountId"))
            if not acc:
                continue
            t = await _target(db, acc, post.get("id"))
            if not t:
                continue
            if _apply_platform_result(t, pl.get("status") or "", pl.get("publishedUrl"), pl.get("error")):
                changed += 1
            t.post.refresh_status()
        await db.commit()
        return "updated" if changed else "unchanged"

    if event == "account.disconnected":
        a = payload.get("account") or {}
        acc = await _account(db, a.get("accountId"))
        if not acc:
            return "unknown-account"
        acc.is_active = False
        acc.last_error = f"Disconnected in Zernio ({a.get('disconnectionType') or 'unknown'}{': ' + a['reason'] if a.get('reason') else ''}). Reconnect to resume."
        await db.commit()
        return "disconnected"

    if event == "account.permissions_changed":
        a = payload.get("account") or {}
        acc = await _account(db, a.get("accountId"))
        if acc:
            acc.last_error = "Permissions changed on the platform — check the account in Zernio"
            await db.commit()
            return "flagged"
        return "unknown-account"

    if event == "account.connected":
        a = payload.get("account") or {}
        brand = await db.scalar(select(Brand).where(Brand.zernio_profile_id == a.get("profileId"))) if a.get("profileId") else None
        if not brand:
            return "no-brand"
        platform = from_zernio(a.get("platform") or "")
        acc = await db.scalar(select(SocialAccount).where(
            SocialAccount.brand_id == brand.id, SocialAccount.platform == platform,
            SocialAccount.external_id == a.get("accountId")))
        if acc is None:
            acc = SocialAccount(brand_id=brand.id, platform=platform, external_id=a.get("accountId"),
                                provider="zernio", handle=a.get("username") or a.get("displayName") or platform)
            db.add(acc)
        acc.handle = a.get("username") or acc.handle
        acc.display_name = a.get("displayName") or acc.display_name
        acc.is_active = True
        acc.last_error = None
        await db.commit()
        return "connected"

    return "ignored"
