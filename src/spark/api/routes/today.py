"""The Today page: what goes out today, what needs a person, how the week is going."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.schemas import TodayOut
from spark.db import get_db
from spark.services import dashboard

router = APIRouter(tags=["today"])


@router.get("/brands/{brand_id}/today", response_model=TodayOut)
async def today(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    return await dashboard.today(db, ctx.brand)
