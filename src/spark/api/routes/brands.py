"""Brands: list, create, read, update. Channels (accounts) of a brand."""

from zoneinfo import available_timezones

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError
from spark.api.schemas import AccountOut, BrandCreate, BrandOut, BrandUpdate
from spark.db import get_db
from spark.models import Brand, QueueSlot, SocialAccount, User
from spark.security import token
from spark.web.brands import slugify

router = APIRouter(tags=["brands"])
TIMEZONES = available_timezones()


@router.get("/brands", response_model=list[BrandOut])
async def list_brands(db: AsyncSession = Depends(get_db), user: User = Depends(deps.current_user)):
    brands = (await db.execute(select(Brand).order_by(Brand.name))).scalars().all()
    return [BrandOut.of(b, user.role.value) for b in brands]


@router.post("/brands", response_model=BrandOut, status_code=201)
async def create_brand(body: BrandCreate, db: AsyncSession = Depends(get_db), user: User = Depends(deps.editor)):
    if body.timezone not in TIMEZONES:
        raise ApiError(422, "bad_timezone", f"Unknown timezone {body.timezone!r}")
    slug = slugify(body.name)
    if await db.scalar(select(Brand.id).where(Brand.slug == slug)):
        slug = f"{slug}-{token(3).lower()}"
    brand = Brand(name=body.name.strip(), slug=slug, website=body.website or None, timezone=body.timezone,
                  color=body.color or "#F2A516")
    db.add(brand)
    await db.flush()
    for d in range(5):
        for t in ("09:00", "12:30", "17:00"):
            db.add(QueueSlot(brand_id=brand.id, weekday=d, time=t))
    await db.commit()
    return BrandOut.of(brand, user.role.value)


@router.get("/brands/{brand_id}", response_model=BrandOut)
async def get_brand(ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    return BrandOut.of(ctx.brand, ctx.role.value)


@router.patch("/brands/{brand_id}", response_model=BrandOut)
async def update_brand(body: BrandUpdate, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.owner_brand)):
    data = body.model_dump(exclude_unset=True)
    if "timezone" in data and data["timezone"] not in TIMEZONES:
        raise ApiError(422, "bad_timezone", f"Unknown timezone {data['timezone']!r}")
    for key, value in data.items():
        setattr(ctx.brand, key, value.strip() if isinstance(value, str) and key == "name" else value)
    await db.commit()
    return BrandOut.of(ctx.brand, ctx.role.value)


@router.get("/brands/{brand_id}/accounts", response_model=list[AccountOut])
async def list_accounts(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    rows = (await db.execute(select(SocialAccount).where(SocialAccount.brand_id == ctx.brand.id)
                             .order_by(SocialAccount.platform, SocialAccount.handle))).scalars().all()
    return [AccountOut.of(a) for a in rows]
