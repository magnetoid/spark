"""The activity log: one line per thing that happened, in words a teammate would use."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import ActivityLog, User


def record(
    db: AsyncSession,
    brand_id: int,
    actor: User | None,
    verb: str,
    object_type: str,
    object_id: int | None = None,
    summary: str = "",
    data: dict | None = None,
    actor_name: str | None = None,
) -> ActivityLog:
    """Add a log line to the session (the caller commits)."""
    row = ActivityLog(
        brand_id=brand_id,
        actor_id=actor.id if actor else None,
        actor_name=actor_name or (actor.name if actor else "Spark"),
        verb=verb,
        object_type=object_type,
        object_id=object_id,
        summary=summary[:500],
        data=data or {},
        created_at=datetime.now(UTC),
    )
    db.add(row)
    return row


async def recent(
    db: AsyncSession, brand_id: int, limit: int = 50, offset: int = 0
) -> list[ActivityLog]:
    return (
        (
            await db.execute(
                select(ActivityLog)
                .where(ActivityLog.brand_id == brand_id)
                .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
