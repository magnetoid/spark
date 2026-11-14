"""Planning: content pillars and importing posts from a CSV."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    ImportRowError,
    PillarIn,
    PillarOut,
    PillarUpdate,
    PostImportIn,
    PostImportOut,
)
from spark.db import get_db
from spark.models import ContentPillar, Post
from spark.services import activity
from spark.services import posts as svc

router = APIRouter(prefix="/brands/{brand_id}", tags=["planning"])


# ---- pillars -------------------------------------------------------------------------------
async def _counts(db: AsyncSession, brand_id: int) -> dict[int, int]:
    since = datetime.now(UTC) - timedelta(days=30)
    rows = (
        await db.execute(
            select(Post.pillar_id, func.count(Post.id))
            .where(
                Post.brand_id == brand_id,
                Post.pillar_id.is_not(None),
                Post.is_autosave.is_(False),
                Post.created_at >= since,
            )
            .group_by(Post.pillar_id)
        )
    ).all()
    return {pid: n for pid, n in rows}


def _out(p: ContentPillar, counts: dict[int, int]) -> PillarOut:
    return PillarOut(
        id=p.id,
        name=p.name,
        color=p.color,
        target_share=p.target_share,
        description=p.description,
        position=p.position,
        posts_30d=counts.get(p.id, 0),
    )


async def _pillar(db: AsyncSession, brand_id: int, pillar_id: int) -> ContentPillar:
    p = await db.get(ContentPillar, pillar_id)
    if p is None or p.brand_id != brand_id:
        raise not_found("No such pillar")
    return p


@router.get("/pillars", response_model=list[PillarOut])
async def list_pillars(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    rows = (
        (
            await db.execute(
                select(ContentPillar)
                .where(ContentPillar.brand_id == ctx.brand.id)
                .order_by(ContentPillar.position, ContentPillar.id)
            )
        )
        .scalars()
        .all()
    )
    counts = await _counts(db, ctx.brand.id)
    return [_out(p, counts) for p in rows]


@router.post("/pillars", response_model=PillarOut, status_code=201)
async def create_pillar(
    body: PillarIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    last = (
        await db.scalar(
            select(func.max(ContentPillar.position)).where(ContentPillar.brand_id == ctx.brand.id)
        )
        or 0
    )
    p = ContentPillar(
        brand_id=ctx.brand.id,
        name=body.name.strip(),
        color=body.color,
        target_share=body.target_share,
        description=(body.description or "").strip() or None,
        position=last + 1,
    )
    db.add(p)
    await db.flush()
    activity.record(db, ctx.brand.id, ctx.user, "added", "pillar", p.id, p.name)
    await db.commit()
    return _out(p, {})


@router.patch("/pillars/{pillar_id}", response_model=PillarOut)
async def update_pillar(
    pillar_id: int,
    body: PillarUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    p = await _pillar(db, ctx.brand.id, pillar_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v.strip() if isinstance(v, str) and k == "name" else v)
    await db.commit()
    return _out(p, await _counts(db, ctx.brand.id))


@router.delete("/pillars/{pillar_id}", status_code=204)
async def delete_pillar(
    pillar_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    p = await _pillar(db, ctx.brand.id, pillar_id)
    activity.record(db, ctx.brand.id, ctx.user, "removed", "pillar", p.id, p.name)
    await db.execute(
        update(Post).where(Post.pillar_id == p.id).values(pillar_id=None)
    )  # SQLite may not cascade SET NULL
    await db.delete(p)
    await db.commit()
    return Response(status_code=204)


# ---- CSV import ------------------------------------------------------------------------------
COLUMNS = {
    "content",
    "text",
    "link",
    "url",
    "when",
    "scheduled_at",
    "date",
    "channels",
    "channel",
    "pillar",
}


def _col(row: dict, *names: str) -> str:
    for n in names:
        v = row.get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _parse_when(raw: str, tz: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace(" ", "T"))
    except ValueError as e:
        raise ValueError(f"Could not read the date {raw!r}; use YYYY-MM-DD HH:MM") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(UTC)


@router.post("/posts/import", response_model=PostImportOut)
async def import_posts(
    body: PostImportIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    """Rows of `content, link, when, channels, pillar`: a `when` schedules the post (brand timezone),
    otherwise it is a draft. Channels are handles or platforms separated by `;`, empty = every channel."""
    reader = csv.DictReader(io.StringIO(body.csv.lstrip("﻿")))
    fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
    if not fields & {"content", "text"}:
        raise ApiError(
            422, "no_content_column", "The first line must name the columns and include `content`"
        )
    accounts = await svc.active_accounts(db, ctx.brand)
    pillars = {
        p.name.lower(): p
        for p in (
            await db.execute(select(ContentPillar).where(ContentPillar.brand_id == ctx.brand.id))
        ).scalars()
    }
    created, errors = 0, []
    for i, raw in enumerate(reader, start=1):
        row = {(k or "").strip().lower(): v for k, v in raw.items()}
        content = _col(row, "content", "text")
        if not content:
            errors.append(ImportRowError(row=i, error="Empty content"))
            continue
        wanted = [
            c.strip().lower()
            for c in _col(row, "channels", "channel").replace("|", ";").replace(",", ";").split(";")
            if c.strip()
        ]
        if wanted:
            targets, missing = [], []
            for w in wanted:
                hit = [
                    a
                    for a in accounts
                    if a.handle.lower() == w
                    or a.platform.lower() == w
                    or (a.display_name or "").lower() == w
                ]
                targets += hit or []
                if not hit:
                    missing.append(w)
            if missing:
                errors.append(ImportRowError(row=i, error="Unknown channel: " + ", ".join(missing)))
                continue
        else:
            targets = list(accounts)
        if not targets:
            errors.append(ImportRowError(row=i, error="No channel to post to"))
            continue
        try:
            when = _parse_when(_col(row, "when", "scheduled_at", "date"), ctx.brand.timezone)
        except ValueError as e:
            errors.append(ImportRowError(row=i, error=str(e)))
            continue
        pillar = pillars.get(_col(row, "pillar").lower())
        seen: set[int] = set()
        post = await svc.save_post(
            db,
            ctx.brand,
            ctx.user,
            None,
            content=content,
            link=_col(row, "link", "url") or None,
            media_ids=[],
            campaign_id=None,
            notes=None,
            source="import",
            targets=[
                svc.TargetInput(account_id=a.id)
                for a in targets
                if not (a.id in seen or seen.add(a.id))
            ],
            pillar_id=pillar.id if pillar else None,
        )
        if when is not None and when < datetime.now(UTC) - timedelta(minutes=1):
            errors.append(
                ImportRowError(
                    row=i, error=f"The date {when:%Y-%m-%d %H:%M} is in the past; kept as a draft"
                )
            )
        elif when is not None:
            try:
                await svc.place_post(db, ctx.brand, ctx.user, post, "schedule", when)
            except svc.PlaceError as e:
                errors.append(
                    ImportRowError(row=i, error="Kept as a draft: " + "; ".join(e.problems))
                )
        created += 1
    if created:
        activity.record(
            db, ctx.brand.id, ctx.user, "imported", "post", None, f"{created} posts from CSV"
        )
    await db.commit()
    return PostImportOut(created=created, errors=errors)
