"""The link-in-bio page settings."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.schemas import BioIn, BioLink, BioOut
from spark.config import get_settings
from spark.db import get_db
from spark.services import bio as svc

router = APIRouter(tags=["bio"])
B = "/brands/{brand_id}"


async def _out(db: AsyncSession, ctx: deps.BrandCtx) -> BioOut:
    page = await svc.get_or_create(db, ctx.brand)
    links = await svc.links_with_clicks(db, page)
    return BioOut(title=page.title, bio=page.bio, theme=page.theme, capture_email=page.capture_email,
                  capture_list_id=page.capture_list_id, avatar_media_id=page.avatar_media_id, is_published=page.is_published,
                  views=page.views, links=[BioLink(**l) for l in links], total_clicks=sum(l["clicks"] for l in links),
                  public_url=f"{get_settings().base_url.rstrip('/')}/b/{ctx.brand.slug}")


@router.get(B + "/bio", response_model=BioOut)
async def get_bio(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    return await _out(db, ctx)


@router.put(B + "/bio", response_model=BioOut)
async def save_bio(body: BioIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    page = await svc.get_or_create(db, ctx.brand)
    page.title = body.title.strip() or ctx.brand.name
    page.bio = (body.bio or "").strip() or None
    page.theme = body.theme if body.theme in ("light", "dark") else "light"
    page.capture_email, page.is_published = body.capture_email, body.is_published
    page.capture_list_id, page.avatar_media_id = body.capture_list_id, body.avatar_media_id
    await svc.set_links(db, ctx.brand, page, [l.model_dump() for l in body.links])
    await db.commit()
    return await _out(db, ctx)
