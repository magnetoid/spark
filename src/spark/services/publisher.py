"""Turns scheduled PostTargets into live posts."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.config import get_settings
from spark.models import Media, Post, PostStatus, PostTarget, SocialAccount
from spark.platforms import AuthExpired, PlatformError, PublishPayload, adapter_for

log = logging.getLogger(__name__)

BACKOFF_MINUTES = (2, 10, 30, 60)
REFRESH_WINDOW = timedelta(minutes=10)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def build_payload(db: AsyncSession, target: PostTarget) -> PublishPayload:
    post = target.post
    media: list[Media] = []
    if post.media_ids:
        rows = (await db.execute(select(Media).where(Media.id.in_(post.media_ids)))).scalars().all()
        by_id = {m.id: m for m in rows}
        media = [by_id[i] for i in post.media_ids if i in by_id]
    return PublishPayload(text=target.text, media=media, link=post.link,
                          first_comment=(target.first_comment or "").strip() or None,
                          thread=[t for t in (target.thread or []) if str(t).strip()])


async def validate_post(db: AsyncSession, post: Post) -> list[str]:
    problems: list[str] = []
    for t in post.targets:
        # New targets haven't loaded .account yet; db.get hits the identity map when it has.
        account = await db.get(SocialAccount, t.account_id)
        adapter = adapter_for(account)
        payload = await build_payload(db, t)
        problems += adapter.validate(payload)
        for i, item in enumerate(payload.thread, start=2):
            if len(item) > adapter.limits.max_chars:
                problems.append(f"{adapter.label}: thread item {i} is {len(item)}/{adapter.limits.max_chars} characters")
    return problems


async def claim_due(db: AsyncSession, now: datetime | None = None, limit: int = 20) -> list[int]:
    """Lock due targets and flip them to `publishing`. Safe with several workers."""
    now = now or datetime.now(UTC)
    stmt = (
        select(PostTarget)
        .where(
            PostTarget.status == PostStatus.scheduled,
            PostTarget.scheduled_at <= now,
            or_(PostTarget.next_attempt_at.is_(None), PostTarget.next_attempt_at <= now),
        )
        .order_by(PostTarget.scheduled_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    targets = (await db.execute(stmt)).scalars().all()
    for t in targets:
        t.status = PostStatus.publishing
    await db.commit()
    return [t.id for t in targets]


async def publish_target(db: AsyncSession, target_id: int) -> PostTarget:
    stmt = (
        select(PostTarget)
        .where(PostTarget.id == target_id)
        .options(selectinload(PostTarget.post).selectinload(Post.targets), selectinload(PostTarget.account))
    )
    target = (await db.execute(stmt)).scalar_one()
    account = target.account
    adapter = adapter_for(account)
    target.attempts += 1
    try:
        if not account.is_active:
            raise PlatformError("Account is disconnected", retryable=False)
        exp = as_utc(account.token_expires_at)
        if exp and exp - REFRESH_WINDOW < datetime.now(UTC):
            if await adapter.refresh(account):
                await db.commit()
        payload = await build_payload(db, target)
        if problems := adapter.validate(payload):
            raise PlatformError("; ".join(problems), retryable=False)
        try:
            result = await adapter.publish(account, payload)
        except AuthExpired:
            # One forced refresh + retry before giving up on the token
            if not await adapter.refresh(account):
                raise
            result = await adapter.publish(account, payload)
        target.status = PostStatus.published
        target.published_at = datetime.now(UTC)
        target.remote_id = result.remote_id
        target.remote_url = result.url
        target.error = None
        target.next_attempt_at = None
        account.last_error = None
    except AuthExpired as e:
        _fail(target, str(e))
        account.last_error = f"Reconnect needed: {e}"
    except PlatformError as e:
        _retry_or_fail(target, str(e), e.retryable)
    except Exception as e:  # network errors, bugs in adapters
        log.exception("Publishing target %s failed", target_id)
        _retry_or_fail(target, f"{type(e).__name__}: {e}", True)
    target.post.refresh_status()
    await db.commit()
    return target


def _fail(target: PostTarget, error: str) -> None:
    target.status = PostStatus.failed
    target.error = error[:2000]
    target.next_attempt_at = None


def _retry_or_fail(target: PostTarget, error: str, retryable: bool) -> None:
    if retryable and target.attempts < get_settings().publish_max_attempts:
        delay = BACKOFF_MINUTES[min(target.attempts - 1, len(BACKOFF_MINUTES) - 1)]
        target.status = PostStatus.scheduled
        target.error = f"Attempt {target.attempts} failed, retrying in {delay}m: {error}"[:2000]
        target.next_attempt_at = datetime.now(UTC) + timedelta(minutes=delay)
    else:
        _fail(target, error)


async def publish_due(db_factory) -> int:
    async with db_factory() as db:
        ids = await claim_due(db)
    for tid in ids:
        async with db_factory() as db:
            await publish_target(db, tid)
    return len(ids)


async def recover_stuck(db: AsyncSession, older_than: timedelta = timedelta(minutes=30)) -> int:
    """Targets stuck in `publishing` (worker crashed) go back to the queue."""
    cutoff = datetime.now(UTC) - older_than
    rows = (
        await db.execute(
            select(PostTarget).where(
                PostTarget.status == PostStatus.publishing, PostTarget.updated_at < cutoff
            )
        )
    ).scalars().all()
    for t in rows:
        t.status = PostStatus.scheduled
    await db.commit()
    return len(rows)
