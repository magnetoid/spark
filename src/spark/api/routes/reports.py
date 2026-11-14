"""Reports for a period: make, list, read, export as CSV, summarise with AI, delete."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    PublicBrand,
    PublicReport,
    ReportIn,
    ReportOut,
    ReportScheduleIn,
    ReportScheduleOut,
    ReportScheduleUpdate,
    ReportShareIn,
    ReportSummaryOut,
    ShareLinkCreated,
)
from spark.db import get_db
from spark.models import Brand, Report, ReportSchedule, ShareLink
from spark.services import activity, report_schedules
from spark.services import ai as ai_svc
from spark.services import reports as svc
from spark.services.publisher import as_utc

router = APIRouter(prefix="/brands/{brand_id}/reports", tags=["reports"])
schedules = APIRouter(prefix="/brands/{brand_id}/report-schedules", tags=["reports"])
public = APIRouter(prefix="/public/reports", tags=["reports"])


def _out(r: Report) -> ReportOut:
    return ReportOut(
        id=r.id,
        title=r.title,
        start=r.start,
        end=r.end,
        data=r.data or {},
        summary=r.summary,
        created_at=as_utc(r.created_at),
    )


async def _report(db: AsyncSession, ctx: deps.BrandCtx, report_id: int) -> Report:
    r = await db.get(Report, report_id)
    if r is None or r.brand_id != ctx.brand.id:
        raise not_found("No such report")
    return r


@router.get("", response_model=list[ReportOut])
async def list_reports(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    rows = (
        (
            await db.execute(
                select(Report)
                .where(Report.brand_id == ctx.brand.id)
                .order_by(Report.id.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return [
        ReportOut(
            id=r.id,
            title=r.title,
            start=r.start,
            end=r.end,
            data={
                "totals": (r.data or {}).get("totals", {}),
                "period": (r.data or {}).get("period", {}),
            },
            summary=r.summary,
            created_at=as_utc(r.created_at),
        )
        for r in rows
    ]


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(
    body: ReportIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    if body.end < body.start:
        raise ApiError(422, "bad_period", "The end comes before the start")
    if (body.end - body.start).days > 366:
        raise ApiError(422, "bad_period", "A report covers at most a year")
    if body.end > date.today():
        body.end = date.today()
    return _out(await svc.create(db, ctx.brand, ctx.user, body.start, body.end, body.title))


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    return _out(await _report(db, ctx, report_id))


@router.get("/{report_id}/csv")
async def report_csv(
    report_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    r = await _report(db, ctx, report_id)
    name = f"{ctx.brand.slug}-report-{r.start.isoformat()}-{r.end.isoformat()}.csv"
    return Response(
        svc.to_csv(r),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/{report_id}/summary", response_model=ReportSummaryOut)
async def write_summary(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    r = await _report(db, ctx, report_id)
    try:
        return ReportSummaryOut(summary=await svc.summarize(db, ctx.brand, r))
    except ai_svc.AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e)) from e


@router.delete("/{report_id}", status_code=204)
async def delete_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    r = await _report(db, ctx, report_id)
    # Its public links stop working with it
    for link in (
        await db.execute(
            select(ShareLink).where(
                ShareLink.brand_id == ctx.brand.id,
                ShareLink.kind == "report",
                ShareLink.revoked_at.is_(None),
            )
        )
    ).scalars():
        if (link.scope or {}).get("report_id") == r.id:
            link.revoked_at = datetime.now(UTC)
    await db.delete(r)
    await db.commit()
    return Response(status_code=204)


@router.post("/{report_id}/share", response_model=ShareLinkCreated, status_code=201)
async def share_report(
    report_id: int,
    body: ReportShareIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    """A link to this report that opens without an account, until it expires or is revoked
    under the brand's share links."""
    from spark.api.routes.collab import _link_out

    r = await _report(db, ctx, report_id)
    link, token = await svc.share(db, ctx.brand, r, ctx.user, body.days)
    await db.commit()
    return ShareLinkCreated(**_link_out(link).model_dump(), token=token, url=svc.report_url(token))


# ---- the public report page (no login) ---------------------------------------------------------
@public.get("/{token}", response_model=PublicReport)
async def public_report(token: str, db: AsyncSession = Depends(get_db)):
    link = await db.scalar(select(ShareLink).where(ShareLink.token_hash == svc.token_hash(token)))
    now = datetime.now(UTC)
    gone = not_found("This report link is no longer valid")
    if (
        link is None
        or link.kind != "report"
        or link.revoked_at is not None
        or (link.expires_at and as_utc(link.expires_at) < now)
    ):
        raise gone
    r = await db.get(Report, (link.scope or {}).get("report_id") or 0)
    if r is None or r.brand_id != link.brand_id:
        raise gone
    brand = await db.get(Brand, link.brand_id)
    link.last_used_at = now
    await db.commit()
    return PublicReport(
        title=r.title,
        start=r.start,
        end=r.end,
        data=r.data or {},
        summary=r.summary,
        brand=PublicBrand(name=brand.name, color=brand.color),
        expires_at=as_utc(link.expires_at),
    )


# ---- schedules ----------------------------------------------------------------------------------
def _schedule_out(s: ReportSchedule, brand: Brand) -> ReportScheduleOut:
    return ReportScheduleOut(
        id=s.id,
        cadence=s.cadence,
        hour=s.hour,
        recipients=list(s.recipients or []),
        with_summary=s.with_summary,
        share_days=s.share_days,
        is_active=s.is_active,
        last_sent_at=as_utc(s.last_sent_at),
        last_error=s.last_error,
        next_period=report_schedules.next_period(s, brand),
    )


async def _schedule(db: AsyncSession, ctx: deps.BrandCtx, schedule_id: int) -> ReportSchedule:
    s = await db.get(ReportSchedule, schedule_id)
    if s is None or s.brand_id != ctx.brand.id:
        raise not_found("No such schedule")
    return s


@schedules.get("", response_model=list[ReportScheduleOut])
async def list_schedules(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)
):
    rows = (
        await db.execute(
            select(ReportSchedule)
            .where(ReportSchedule.brand_id == ctx.brand.id)
            .order_by(ReportSchedule.id)
        )
    ).scalars()
    return [_schedule_out(s, ctx.brand) for s in rows]


@schedules.post("", response_model=ReportScheduleOut, status_code=201)
async def create_schedule(
    body: ReportScheduleIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    s = ReportSchedule(
        brand_id=ctx.brand.id,
        **{**body.model_dump(), "recipients": [str(e).lower() for e in body.recipients]},
        created_by=ctx.user.id,
    )
    report_schedules.start_from_next(s, ctx.brand)
    db.add(s)
    await db.flush()
    activity.record(
        db,
        ctx.brand.id,
        ctx.user,
        "scheduled",
        "report",
        s.id,
        f"{s.cadence} report to {', '.join(s.recipients)}",
    )
    await db.commit()
    return _schedule_out(s, ctx.brand)


@schedules.patch("/{schedule_id}", response_model=ReportScheduleOut)
async def update_schedule(
    schedule_id: int,
    body: ReportScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    s = await _schedule(db, ctx, schedule_id)
    cadence = s.cadence
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        setattr(s, k, [str(e).lower() for e in v] if k == "recipients" else v)
    if s.cadence != cadence:
        report_schedules.start_from_next(s, ctx.brand)
    activity.record(db, ctx.brand.id, ctx.user, "changed", "report schedule", s.id, s.cadence)
    await db.commit()
    return _schedule_out(s, ctx.brand)


@schedules.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    s = await _schedule(db, ctx, schedule_id)
    activity.record(db, ctx.brand.id, ctx.user, "removed", "report schedule", s.id, s.cadence)
    await db.delete(s)
    await db.commit()
    return Response(status_code=204)
