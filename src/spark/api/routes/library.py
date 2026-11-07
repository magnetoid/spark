"""The Library: media, hashtag groups, templates. Plus the campaigns list the composer needs."""

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    HashtagGroupIn,
    HashtagGroupOut,
    HashtagGroupUpdate,
    MediaCropIn,
    MediaGenerateIn,
    MediaOut,
    MediaPage,
    MediaUpdate,
    MediaUploadOut,
    TagCount,
    TemplateIn,
    TemplateOut,
    TemplateUpdate,
)
from spark.config import get_settings
from spark.db import get_db
from spark.models import HashtagGroup, Media, PostTemplate
from spark.services import activity, images
from spark.services import ai as ai_svc
from spark.services import media as media_svc
from spark.services.text import parse_hashtags

router = APIRouter(tags=["library"])
B = "/brands/{brand_id}"


# ---- media ---------------------------------------------------------------------------------
@router.get(B + "/media", response_model=MediaPage)
async def list_media(tag: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    rows = await media_svc.list_media(db, ctx.brand)
    if tag:
        rows = [m for m in rows if tag.lower() in [t.lower() for t in (m.tags or [])]]
    if q:
        needle = q.lower()
        rows = [m for m in rows if needle in m.filename.lower() or needle in (m.alt_text or "").lower()]
    return MediaPage(items=[MediaOut.of(m) for m in rows])


@router.get(B + "/media/tags", response_model=list[TagCount])
async def media_tags(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    counts: dict[str, int] = {}
    for m in await media_svc.list_media(db, ctx.brand):
        for t in m.tags or []:
            counts[t] = counts.get(t, 0) + 1
    return [TagCount(tag=t, count=n) for t, n in sorted(counts.items())]


@router.post(B + "/media/generate", response_model=MediaOut, status_code=201)
async def generate_media(body: MediaGenerateIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    if not images.configured():
        raise ApiError(409, "images_not_configured", "Image generation is not set up. Add a key under Settings → Connectors → Image generation.")
    try:
        m = await images.generate(db, ctx.brand, body.prompt, body.size)
    except images.ImagesUnavailable as e:
        raise ApiError(502, "images_failed", str(e)) from e
    activity.record(db, ctx.brand.id, ctx.user, "generated", "media", m.id, body.prompt[:120])
    await db.commit()
    return MediaOut.of(m)


@router.post(B + "/media", response_model=MediaUploadOut, status_code=201)
async def upload_media(files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db),
                       ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    uploads = [media_svc.Upload(name=f.filename or "upload", content_type=f.content_type or "", data=await f.read()) for f in files]
    saved, rejected = await media_svc.save_uploads(db, ctx.brand, uploads)
    return MediaUploadOut(items=[MediaOut.of(m) for m in saved], rejected=rejected)


async def _media(db: AsyncSession, ctx: deps.BrandCtx, media_id: int) -> Media:
    m = await db.get(Media, media_id)
    if not m or m.brand_id != ctx.brand.id:
        raise not_found("No such file")
    return m


@router.patch(B + "/media/{media_id}", response_model=MediaOut)
async def update_media(media_id: int, body: MediaUpdate, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    m = await _media(db, ctx, media_id)
    if "alt_text" in body.model_fields_set:
        m.alt_text = (body.alt_text or "").strip() or None
    if body.tags is not None:
        seen: list[str] = []
        for t in body.tags:
            t = t.strip().lower()[:40]
            if t and t not in seen:
                seen.append(t)
        m.tags = seen[:30]
    await db.commit()
    return MediaOut.of(m)


@router.post(B + "/media/{media_id}/alt-text", response_model=MediaOut)
async def write_alt_text(media_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    m = await _media(db, ctx, media_id)
    if not m.content_type.startswith("image/"):
        raise ApiError(422, "not_an_image", "Alt text is for images")
    try:
        ai = ai_svc.ContentAI()
    except ai_svc.AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e)) from e
    try:
        data, ctype = await images.for_vision((get_settings().media_dir / m.path).read_bytes(), m.content_type)
    except images.BadImage as e:
        raise ApiError(422, "bad_image", str(e)) from e
    try:
        m.alt_text = await ai.describe_image(ctx.brand, data, ctype)
    except ai_svc.AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e)) from e
    await db.commit()
    return MediaOut.of(m)


@router.post(B + "/media/{media_id}/crop", response_model=MediaOut, status_code=201)
async def crop_media(media_id: int, body: MediaCropIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    m = await _media(db, ctx, media_id)
    if not m.content_type.startswith("image/"):
        raise ApiError(422, "not_an_image", "Only images can be cropped")
    try:
        return MediaOut.of(await images.crop(db, ctx.brand, m, body.ratio, body.x, body.y))
    except images.BadImage as e:
        raise ApiError(422, "bad_image", str(e)) from e


@router.delete(B + "/media/{media_id}", status_code=204)
async def delete_media(media_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    await media_svc.delete_media(db, await _media(db, ctx, media_id))
    return Response(status_code=204)


# ---- hashtag groups -------------------------------------------------------------------------
@router.get(B + "/hashtag-groups", response_model=list[HashtagGroupOut])
async def hashtag_groups(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    rows = (await db.execute(select(HashtagGroup).where(HashtagGroup.brand_id == ctx.brand.id).order_by(HashtagGroup.name))).scalars().all()
    return [HashtagGroupOut(id=g.id, name=g.name, tags=list(g.tags or [])) for g in rows]


@router.post(B + "/hashtag-groups", response_model=HashtagGroupOut, status_code=201)
async def create_hashtag_group(body: HashtagGroupIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    g = HashtagGroup(brand_id=ctx.brand.id, name=body.name.strip(), tags=parse_hashtags(" ".join(body.tags)))
    db.add(g)
    await db.commit()
    return HashtagGroupOut(id=g.id, name=g.name, tags=list(g.tags))


@router.patch(B + "/hashtag-groups/{group_id}", response_model=HashtagGroupOut)
async def update_hashtag_group(group_id: int, body: HashtagGroupUpdate, db: AsyncSession = Depends(get_db),
                               ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    g = await db.get(HashtagGroup, group_id)
    if not g or g.brand_id != ctx.brand.id:
        raise not_found("No such group")
    if body.name is not None:
        g.name = body.name.strip()
    if body.tags is not None:
        g.tags = parse_hashtags(" ".join(body.tags))
    await db.commit()
    return HashtagGroupOut(id=g.id, name=g.name, tags=list(g.tags))


@router.delete(B + "/hashtag-groups/{group_id}", status_code=204)
async def delete_hashtag_group(group_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    g = await db.get(HashtagGroup, group_id)
    if not g or g.brand_id != ctx.brand.id:
        raise not_found("No such group")
    await db.delete(g)
    await db.commit()
    return Response(status_code=204)


# ---- templates ------------------------------------------------------------------------------
@router.get(B + "/templates", response_model=list[TemplateOut])
async def templates(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    rows = (await db.execute(select(PostTemplate).where(PostTemplate.brand_id == ctx.brand.id).order_by(PostTemplate.name))).scalars().all()
    return [TemplateOut.model_validate(t) for t in rows]


@router.post(B + "/templates", response_model=TemplateOut, status_code=201)
async def create_template(body: TemplateIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    t = PostTemplate(brand_id=ctx.brand.id, name=body.name.strip(), body=body.body.strip(), category=(body.category or "").strip()[:40] or None)
    db.add(t)
    await db.commit()
    return TemplateOut.model_validate(t)


@router.patch(B + "/templates/{template_id}", response_model=TemplateOut)
async def update_template(template_id: int, body: TemplateUpdate, db: AsyncSession = Depends(get_db),
                          ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    t = await db.get(PostTemplate, template_id)
    if not t or t.brand_id != ctx.brand.id:
        raise not_found("No such template")
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        t.name = data["name"].strip()
    if "body" in data:
        t.body = (data["body"] or "").strip()
    if "category" in data:
        t.category = (data["category"] or "").strip()[:40] or None
    await db.commit()
    return TemplateOut.model_validate(t)


@router.delete(B + "/templates/{template_id}", status_code=204)
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    t = await db.get(PostTemplate, template_id)
    if not t or t.brand_id != ctx.brand.id:
        raise not_found("No such template")
    await db.delete(t)
    await db.commit()
    return Response(status_code=204)
