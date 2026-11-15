"""For people who run several brands: one overview of every client, and copying a brand's setup."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import BrandOut, CopySetupIn, CopySetupOut, OverviewOut
from spark.db import get_db
from spark.models import Brand, User
from spark.services import access, activity, agency

router = APIRouter(tags=["agency"])


@router.get("/overview", response_model=OverviewOut)
async def overview(db: AsyncSession = Depends(get_db), user: User = Depends(deps.current_user)):
    """Every brand you can see and what needs you there, the most urgent first."""
    return await agency.overview(db, user)


@router.post("/brands/{brand_id}/copy-setup", response_model=CopySetupOut)
async def copy_setup(
    body: CopySetupIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.owner_brand),
):
    """Copy pillars, posting times, guardrails, saved replies, templates, hashtag groups or the
    brand voice from another brand you work on into this one."""
    if body.from_brand_id == ctx.brand.id:
        raise ApiError(422, "same_brand", "Pick another brand to copy from")
    role = await access.role_for(db, ctx.user, body.from_brand_id)
    source = await db.get(Brand, body.from_brand_id) if role in ("owner", "editor") else None
    if source is None:
        raise not_found("Brand not found")
    copied = await agency.copy_setup(db, source, ctx.brand, list(body.parts))
    activity.record(
        db,
        ctx.brand.id,
        ctx.user,
        "copied setup",
        "brand",
        ctx.brand.id,
        f"From {source.name}: " + ", ".join(k.replace("_", " ") for k in copied),
    )
    await db.commit()
    await db.refresh(ctx.brand)
    return CopySetupOut(copied=copied, brand=BrandOut.of(ctx.brand, ctx.role))
