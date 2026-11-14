"""Campaigns: create (optionally with an AI plan), update, delete, list with post counts."""

from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import CampaignFull, CampaignIn, CampaignUpdate
from spark.db import get_db
from spark.models import Campaign
from spark.services import campaigns as svc
from spark.services.ai import AIUnavailable

router = APIRouter(tags=["campaigns"])
B = "/brands/{brand_id}"


def _date(v: str | None, name: str) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise ApiError(422, "validation", f"{name} must be YYYY-MM-DD")


def _out(c: Campaign, counts: dict[str, int], planned: int = 0) -> CampaignFull:
    return CampaignFull(
        id=c.id,
        name=c.name,
        color=c.color,
        goal=c.goal,
        utm_campaign=c.utm_campaign,
        starts_on=c.starts_on,
        ends_on=c.ends_on,
        counts=counts,
        planned=planned,
    )


@router.get(B + "/campaigns", response_model=list[CampaignFull])
async def list_campaigns(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    rows = (
        (
            await db.execute(
                select(Campaign)
                .where(Campaign.brand_id == ctx.brand.id)
                .order_by(Campaign.id.desc())
            )
        )
        .scalars()
        .all()
    )
    counts = await svc.counts(db, ctx.brand)
    return [_out(c, counts.get(c.id, svc.empty_counts())) for c in rows]


@router.post(B + "/campaigns", response_model=CampaignFull, status_code=201)
async def create_campaign(
    body: CampaignIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    starts, ends = _date(body.starts_on, "starts_on"), _date(body.ends_on, "ends_on")
    c = await svc.create(
        db,
        ctx.brand,
        name=body.name,
        goal=body.goal,
        starts_on=starts,
        ends_on=ends,
        utm_campaign=body.utm_campaign,
        color=body.color,
    )
    planned = 0
    if body.ai_plan:
        if not (starts and ends):
            raise ApiError(422, "validation", "An AI plan needs a start and an end date")
        try:
            planned = await svc.plan_with_ai(
                db,
                ctx.brand,
                ctx.user,
                c,
                starts,
                ends,
                body.ai_plan.account_ids,
                body.ai_plan.per_week,
            )
        except ValueError as e:
            raise ApiError(422, "validation", str(e))
        except AIUnavailable as e:
            raise ApiError(400, "ai_unavailable", str(e))
    await db.commit()
    counts = (await svc.counts(db, ctx.brand)).get(c.id, svc.empty_counts())
    return _out(c, counts, planned)


@router.patch(B + "/campaigns/{campaign_id}", response_model=CampaignFull)
async def update_campaign(
    campaign_id: int,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.brand_id != ctx.brand.id:
        raise not_found("No such campaign")
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        c.name = data["name"].strip()
    if "goal" in data:
        c.goal = (data["goal"] or "").strip() or None
    if "utm_campaign" in data:
        c.utm_campaign = (data["utm_campaign"] or "").strip() or None
    if "color" in data and data["color"]:
        c.color = data["color"]
    if "starts_on" in data:
        c.starts_on = svc._midnight(_date(data["starts_on"], "starts_on"), ctx.brand.timezone)
    if "ends_on" in data:
        c.ends_on = svc._midnight(_date(data["ends_on"], "ends_on"), ctx.brand.timezone)
    await db.commit()
    return _out(c, (await svc.counts(db, ctx.brand)).get(c.id, svc.empty_counts()))


@router.delete(B + "/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.brand_id != ctx.brand.id:
        raise not_found("No such campaign")
    await db.delete(c)
    await db.commit()
    return Response(status_code=204)
