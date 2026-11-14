"""Evergreen posts: published posts marked to come back every N days, into empty queue slots.

A copy is made only when the original (or its latest copy) went out more than `recycle_every_days`
ago and no copy is already waiting. The copy follows the brand's approval setting.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.models import Brand, Post, PostStatus, PostTarget
from spark.services import scheduler
from spark.services.publisher import as_utc

log = logging.getLogger("spark.evergreen")
WAITING = (PostStatus.scheduled, PostStatus.pending_approval, PostStatus.publishing)


async def due_posts(db: AsyncSession, brand: Brand, now: datetime) -> list[Post]:
    rows = (
        (
            await db.execute(
                select(Post)
                .options(selectinload(Post.targets))
                .where(
                    Post.brand_id == brand.id,
                    Post.evergreen.is_(True),
                    Post.status == PostStatus.published,
                    Post.recycled_from_id.is_(None),
                    Post.is_autosave.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    due = []
    for p in rows:
        every = p.recycle_every_days or 0
        if every <= 0:
            continue
        copies = (
            (await db.execute(select(Post).where(Post.recycled_from_id == p.id))).scalars().all()
        )
        if any(c.status in WAITING or c.status == PostStatus.draft for c in copies):
            continue
        last = max(
            [as_utc(p.scheduled_at) or as_utc(p.created_at)]
            + [as_utc(c.scheduled_at) for c in copies if c.scheduled_at]
        )
        if last and now - last >= timedelta(days=every):
            due.append(p)
    return due


async def recycle(db: AsyncSession, now: datetime | None = None, per_brand: int = 3) -> int:
    """Make copies for every brand's due evergreen posts. Returns how many were made."""
    now = now or datetime.now(UTC)
    made = 0
    for brand in (await db.execute(select(Brand))).scalars().all():
        for src in (await due_posts(db, brand, now))[:per_brand]:
            copy = Post(
                brand_id=brand.id,
                author_id=src.author_id,
                content=src.content,
                link=src.link,
                media_ids=list(src.media_ids or []),
                campaign_id=src.campaign_id,
                pillar_id=src.pillar_id,
                source="evergreen",
                recycled_from_id=src.id,
            )
            copy.targets = [
                PostTarget(
                    account_id=t.account_id,
                    content_override=t.content_override,
                    first_comment=t.first_comment,
                    thread=list(t.thread or []),
                    post_type=t.post_type or "post",
                    options=dict(t.options or {}),
                )
                for t in src.targets
            ]
            db.add(copy)
            await db.flush()
            when = await scheduler.next_free_slot(
                db, brand, now, account_ids=[t.account_id for t in copy.targets]
            )
            status = PostStatus.pending_approval if brand.require_approval else PostStatus.scheduled
            copy.scheduled_at = when
            copy.status = status
            for t in copy.targets:
                t.status, t.scheduled_at = status, when
            made += 1
            log.info(
                "Evergreen: recycled post %s of %s for %s", src.id, brand.slug, when.isoformat()
            )
    await db.commit()
    return made
