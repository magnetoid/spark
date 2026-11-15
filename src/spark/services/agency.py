"""Tools for people who run many brands: an overview of every client, and copying one brand's
setup (pillars, posting times, guardrails, saved replies, templates, hashtags, voice) to another."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import (
    Brand,
    ContentPillar,
    HashtagGroup,
    Post,
    PostStatus,
    PostTemplate,
    QueueSlot,
    SavedReply,
    SocialAccount,
    User,
)
from spark.services import access, approvals, channel_health
from spark.services import inbox as inbox_svc
from spark.services.publisher import as_utc

AHEAD_DAYS = 7
UPCOMING = (PostStatus.scheduled, PostStatus.pending_approval)


async def _brand_row(db: AsyncSession, brand: Brand, role: str, now: datetime) -> dict:
    async def count(*where) -> int:
        q = select(func.count(Post.id)).where(
            Post.brand_id == brand.id, Post.is_autosave.is_(False), *where
        )
        return await db.scalar(q) or 0

    waiting = (
        (
            await db.execute(
                select(Post).where(
                    Post.brand_id == brand.id,
                    Post.is_autosave.is_(False),
                    Post.status == PostStatus.pending_approval,
                )
            )
        )
        .scalars()
        .all()
    )
    horizon = now + timedelta(days=AHEAD_DAYS)
    upcoming = (
        (
            await db.execute(
                select(Post.scheduled_at).where(
                    Post.brand_id == brand.id,
                    Post.is_autosave.is_(False),
                    Post.status.in_(UPCOMING),
                    Post.scheduled_at >= now,
                    Post.scheduled_at < horizon,
                )
            )
        )
        .scalars()
        .all()
    )
    zone = ZoneInfo(brand.timezone or "UTC")
    today = now.astimezone(zone).date()
    days = {today + timedelta(days=i) for i in range(AHEAD_DAYS)}
    covered = {as_utc(t).astimezone(zone).date() for t in upcoming if t}
    accounts = (
        (await db.execute(select(SocialAccount).where(SocialAccount.brand_id == brand.id)))
        .scalars()
        .all()
    )
    channels = sum(1 for a in accounts if channel_health.health(a) in ("reconnect", "expiring"))
    row = {
        "brand_id": brand.id,
        "slug": brand.slug,
        "name": brand.name,
        "color": brand.color,
        "timezone": brand.timezone or "UTC",
        "role": role,
        "channels_total": len(accounts),
        "failed": await count(Post.status == PostStatus.failed),
        "channels": channels,
        "approvals": len(waiting),
        "approvals_overdue": sum(1 for p in waiting if approvals.overdue(p, now)),
        "replies": await inbox_svc.open_count(db, brand.id),
        "drafts": await count(Post.status == PostStatus.draft, Post.agent_run_id.is_(None)),
        "scheduled_week": len(upcoming),
        "empty_days": len(days - covered),
        "next_post_at": as_utc(min(upcoming)) if upcoming else None,
    }
    urgent = row["failed"] + row["channels"] + row["approvals_overdue"]
    row["attention"] = urgent + row["approvals"] + row["replies"] + (1 if row["empty_days"] else 0)
    row["_urgent"] = urgent
    return row


async def overview(db: AsyncSession, user: User, now: datetime | None = None) -> dict:
    """Every brand the person can see, what needs them there, the most urgent first."""
    now = now or datetime.now(UTC)
    rows = [await _brand_row(db, b, role, now) for b, role in await access.visible_brands(db, user)]
    rows.sort(key=lambda r: (-r["_urgent"], -r["attention"], r["name"].lower()))
    for r in rows:
        del r["_urgent"]
    keys = ("failed", "channels", "approvals", "approvals_overdue", "replies", "scheduled_week")
    return {
        "brands": rows,
        "totals": {k: sum(r[k] for r in rows) for k in keys},
        "now": now,
    }


# ---- copy setup ---------------------------------------------------------------------------------
PARTS = ("pillars", "slots", "guardrails", "saved_replies", "templates", "hashtags", "voice")
VOICE_FIELDS = ("voice_tone", "voice_audience", "voice_rules", "voice_examples", "default_hashtags")
GUARDRAIL_KEYS = ("never_say", "avoid_topics", "keywords")


async def _rows(db: AsyncSession, model, brand_id: int) -> list:
    return list((await db.execute(select(model).where(model.brand_id == brand_id))).scalars())


async def copy_setup(db: AsyncSession, source: Brand, target: Brand, parts: list[str]) -> dict:
    """Copy the chosen parts from `source` to `target`. Items the target already has (same name)
    are skipped, so copying twice adds nothing. Brand-wide posting times replace the target's;
    times set for one channel stay behind because the channels differ."""
    copied: dict[str, int] = {}
    for part in dict.fromkeys(parts):
        n = 0
        if part == "pillars":
            have = {p.name.lower() for p in await _rows(db, ContentPillar, target.id)}
            for p in sorted(await _rows(db, ContentPillar, source.id), key=lambda x: x.position):
                if p.name.lower() not in have:
                    db.add(
                        ContentPillar(
                            brand_id=target.id,
                            name=p.name,
                            color=p.color,
                            target_share=p.target_share,
                            description=p.description,
                            position=p.position,
                        )
                    )
                    n += 1
        elif part == "saved_replies":
            have = {r.title.lower() for r in await _rows(db, SavedReply, target.id)}
            for r in await _rows(db, SavedReply, source.id):
                if r.title.lower() not in have:
                    db.add(
                        SavedReply(
                            brand_id=target.id, title=r.title, body=r.body, shortcut=r.shortcut
                        )
                    )
                    n += 1
        elif part == "templates":
            have = {t.name.lower() for t in await _rows(db, PostTemplate, target.id)}
            for t in await _rows(db, PostTemplate, source.id):
                if t.name.lower() not in have:
                    db.add(
                        PostTemplate(
                            brand_id=target.id, name=t.name, body=t.body, category=t.category
                        )
                    )
                    n += 1
        elif part == "hashtags":
            have = {g.name.lower() for g in await _rows(db, HashtagGroup, target.id)}
            for g in await _rows(db, HashtagGroup, source.id):
                if g.name.lower() not in have:
                    db.add(HashtagGroup(brand_id=target.id, name=g.name, tags=list(g.tags or [])))
                    n += 1
        elif part == "slots":
            wide = [s for s in await _rows(db, QueueSlot, source.id) if s.account_id is None]
            if wide:
                for s in await _rows(db, QueueSlot, target.id):
                    if s.account_id is None:
                        await db.delete(s)
                await db.flush()
                for s in wide:
                    db.add(QueueSlot(brand_id=target.id, weekday=s.weekday, time=s.time))
                n = len(wide)
        elif part == "guardrails":
            src = source.agent_config or {}
            cfg = dict(target.agent_config or {})
            for key in GUARDRAIL_KEYS:
                if src.get(key):
                    cfg[key] = list(src[key])
                    n += 1
            target.agent_config = cfg
        elif part == "voice":
            for field in VOICE_FIELDS:
                value = getattr(source, field)
                if value:
                    setattr(target, field, value)
                    n += 1
        copied[part] = n
    return copied
