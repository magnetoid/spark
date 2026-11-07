"""Reports for a period: make, list, read, export as CSV, summarise with AI, delete."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import ReportIn, ReportOut, ReportSummaryOut
from spark.db import get_db
from spark.models import Report
from spark.services import ai as ai_svc
from spark.services import reports as svc
from spark.services.publisher import as_utc

router = APIRouter(prefix="/brands/{brand_id}/reports", tags=["reports"])


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
    await db.delete(r)
    await db.commit()
    return Response(status_code=204)
