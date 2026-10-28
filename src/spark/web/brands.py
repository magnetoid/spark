import re
from pathlib import Path
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.db import get_db
from spark.models import Brand, HashtagGroup, Media, PostTemplate, QueueSlot, Role, User
from spark.security import hash_password, token
from spark.web.deps import current_user, editor, flash, owner, render, require_brand

router = APIRouter()
TIMEZONES = sorted(available_timezones())
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ALLOWED_MEDIA = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4", "video/quicktime",
}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or token(4).lower()


@router.get("/brands")
async def brand_list(request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(current_user)):
    brands = (await db.execute(select(Brand).order_by(Brand.name))).scalars().all()
    return await render(request, "brands/list.html", db, user, None, all_brands=brands)


@router.get("/brands/new")
async def brand_new(request: Request, db: AsyncSession = Depends(get_db),
                    user: User = Depends(editor)):
    return await render(request, "brands/form.html", db, user, None, b=None, timezones=TIMEZONES)


@router.post("/brands/new")
async def brand_create(
    request: Request,
    name: str = Form(...),
    website: str = Form(""),
    timezone: str = Form("UTC"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(editor),
):
    slug = slugify(name)
    if await db.scalar(select(Brand.id).where(Brand.slug == slug)):
        slug = f"{slug}-{token(3).lower()}"
    brand = Brand(name=name.strip(), slug=slug, website=website or None,
                  timezone=timezone if timezone in TIMEZONES else "UTC")
    db.add(brand)
    await db.flush()
    for d in range(5):
        for t in ("09:00", "12:30", "17:00"):
            db.add(QueueSlot(brand_id=brand.id, weekday=d, time=t))
    await db.commit()
    request.session["brand_id"] = brand.id
    flash(request, f"Brand “{brand.name}” created. Connect a social account next.")
    return RedirectResponse("/accounts", 303)


@router.get("/brands/switch/{brand_id}")
async def brand_switch(brand_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       user: User = Depends(current_user)):
    if await db.get(Brand, brand_id):
        request.session["brand_id"] = brand_id
    return RedirectResponse(request.headers.get("referer") or "/", 303)


@router.get("/settings")
async def brand_settings(request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    slots = (await db.execute(
        select(QueueSlot).where(QueueSlot.brand_id == brand.id).order_by(QueueSlot.weekday, QueueSlot.time)
    )).scalars().all()
    users = (await db.execute(select(User).order_by(User.name))).scalars().all()
    groups = (await db.execute(select(HashtagGroup).where(HashtagGroup.brand_id == brand.id)
                               .order_by(HashtagGroup.name))).scalars().all()
    tpls = (await db.execute(select(PostTemplate).where(PostTemplate.brand_id == brand.id)
                             .order_by(PostTemplate.name))).scalars().all()
    return await render(request, "brands/settings.html", db, user, brand, b=brand, slots=slots,
                        weekdays=WEEKDAYS, timezones=TIMEZONES, users=users, roles=list(Role),
                        hashtag_groups=groups, post_templates=tpls)


# ---- content library: hashtag groups + templates ----------------------------

def _parse_tags(raw: str) -> list[str]:
    out, seen = [], set()
    for t in raw.replace(",", " ").split():
        t = t.strip().lstrip("#")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t[:50])
    return out[:30]


@router.post("/settings/hashtags")
async def hashtag_group_save(request: Request, name: str = Form(...), tags: str = Form(...),
                             group_id: str = Form(""), db: AsyncSession = Depends(get_db),
                             user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    g = await db.get(HashtagGroup, int(group_id)) if group_id.isdigit() else None
    if g is None or g.brand_id != brand.id:
        g = HashtagGroup(brand_id=brand.id)
        db.add(g)
    g.name, g.tags = name.strip()[:80], _parse_tags(tags)
    await db.commit()
    return RedirectResponse("/settings#library", 303)


@router.post("/settings/hashtags/{group_id}/delete")
async def hashtag_group_delete(group_id: int, db: AsyncSession = Depends(get_db),
                               user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    g = await db.get(HashtagGroup, group_id)
    if g and g.brand_id == brand.id:
        await db.delete(g)
        await db.commit()
    return RedirectResponse("/settings#library", 303)


@router.post("/settings/templates")
async def template_save(request: Request, name: str = Form(...), body: str = Form(...),
                        category: str = Form(""), template_id: str = Form(""),
                        db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                        brand: Brand = Depends(require_brand)):
    t = await db.get(PostTemplate, int(template_id)) if template_id.isdigit() else None
    if t is None or t.brand_id != brand.id:
        t = PostTemplate(brand_id=brand.id)
        db.add(t)
    t.name, t.body, t.category = name.strip()[:120], body.strip(), category.strip()[:40] or None
    await db.commit()
    return RedirectResponse("/settings#library", 303)


@router.post("/settings/templates/{template_id}/delete")
async def template_delete(template_id: int, db: AsyncSession = Depends(get_db),
                          user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    t = await db.get(PostTemplate, template_id)
    if t and t.brand_id == brand.id:
        await db.delete(t)
        await db.commit()
    return RedirectResponse("/settings#library", 303)


@router.post("/settings")
async def brand_update(
    request: Request,
    name: str = Form(...),
    website: str = Form(""),
    timezone: str = Form("UTC"),
    color: str = Form("#f97316"),
    voice_tone: str = Form(""),
    voice_audience: str = Form(""),
    voice_rules: str = Form(""),
    voice_examples: str = Form(""),
    default_hashtags: str = Form(""),
    require_approval: bool = Form(False),
    auto_shorten_links: bool = Form(False),
    utm_campaign: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(editor),
    brand: Brand = Depends(require_brand),
):
    brand.name = name.strip()
    brand.website = website or None
    brand.timezone = timezone if timezone in TIMEZONES else "UTC"
    brand.color = color
    brand.voice_tone = voice_tone or None
    brand.voice_audience = voice_audience or None
    brand.voice_rules = voice_rules or None
    brand.voice_examples = voice_examples or None
    brand.default_hashtags = default_hashtags or None
    brand.require_approval = require_approval
    brand.auto_shorten_links = auto_shorten_links
    brand.utm_defaults = {"campaign": utm_campaign} if utm_campaign else {}
    await db.commit()
    flash(request, "Brand settings saved")
    return RedirectResponse("/settings", 303)


@router.post("/settings/slots")
async def slot_add(request: Request, weekdays: list[int] = Form(...), time: str = Form(...),
                   db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                   brand: Brand = Depends(require_brand)):
    if not re.fullmatch(r"\d{2}:\d{2}", time):
        raise HTTPException(400, "Time must be HH:MM")
    existing = {
        (s.weekday, s.time)
        for s in (await db.execute(select(QueueSlot).where(QueueSlot.brand_id == brand.id))).scalars()
    }
    for d in weekdays:
        if (d, time) not in existing:
            db.add(QueueSlot(brand_id=brand.id, weekday=d, time=time))
    await db.commit()
    return RedirectResponse("/settings#queue", 303)


@router.post("/settings/slots/{slot_id}/delete")
async def slot_delete(slot_id: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    await db.execute(delete(QueueSlot).where(QueueSlot.id == slot_id, QueueSlot.brand_id == brand.id))
    await db.commit()
    return RedirectResponse("/settings#queue", 303)


@router.post("/settings/brand/delete")
async def brand_delete(request: Request, db: AsyncSession = Depends(get_db),
                       user: User = Depends(owner), brand: Brand = Depends(require_brand)):
    await db.delete(brand)
    await db.commit()
    request.session.pop("brand_id", None)
    flash(request, "Brand deleted")
    return RedirectResponse("/brands", 303)


# ---- team ------------------------------------------------------------------

@router.post("/team")
async def team_add(request: Request, name: str = Form(...), email: str = Form(...),
                   password: str = Form(..., min_length=8), role: Role = Form(Role.editor),
                   db: AsyncSession = Depends(get_db), user: User = Depends(owner)):
    email = email.strip().lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        flash(request, "A user with that email already exists", "error")
    else:
        db.add(User(name=name, email=email, password_hash=hash_password(password), role=role))
        await db.commit()
        flash(request, f"Added {name}")
    return RedirectResponse("/settings#team", 303)


@router.post("/team/{user_id}")
async def team_update(request: Request, user_id: int, role: Role = Form(...),
                      active: bool = Form(False), db: AsyncSession = Depends(get_db),
                      user: User = Depends(owner)):
    member = await db.get(User, user_id)
    if member and member.id != user.id:
        member.role, member.is_active = role, active
        await db.commit()
        flash(request, f"Updated {member.name}")
    return RedirectResponse("/settings#team", 303)


# ---- media -----------------------------------------------------------------

@router.get("/media")
async def media_library(request: Request, db: AsyncSession = Depends(get_db),
                        user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    items = (await db.execute(
        select(Media).where(Media.brand_id == brand.id).order_by(Media.id.desc())
    )).scalars().all()
    if request.headers.get("HX-Request"):
        return await render(request, "partials/media_picker.html", db, user, brand, items=items)
    return await render(request, "media.html", db, user, brand, items=items)


@router.post("/media")
async def media_upload(request: Request, files: list[UploadFile] = File(...),
                       db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                       brand: Brand = Depends(require_brand)):
    s = get_settings()
    uploaded = []
    for f in files:
        if f.content_type not in ALLOWED_MEDIA:
            flash(request, f"{f.filename}: unsupported type {f.content_type}", "error")
            continue
        data = await f.read()
        if len(data) > s.max_upload_mb * 1024 * 1024:
            flash(request, f"{f.filename}: larger than {s.max_upload_mb} MB", "error")
            continue
        ext = Path(f.filename or "").suffix.lower()[:8] or ".bin"
        rel = f"{brand.id}/{token(12)}{ext}"
        dest = s.media_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        m = Media(brand_id=brand.id, filename=f.filename or rel, path=rel,
                  content_type=f.content_type, size=len(data))
        db.add(m)
        uploaded.append(m)
    await db.commit()
    if "application/json" in request.headers.get("accept", ""):
        from fastapi.responses import JSONResponse

        return JSONResponse([{"id": m.id, "url": m.url, "video": m.is_video, "name": m.filename} for m in uploaded])
    if request.headers.get("HX-Request"):
        return await render(request, "partials/media_uploaded.html", db, user, brand, items=uploaded)
    return RedirectResponse("/media", 303)


@router.post("/media/{media_id}")
async def media_update(media_id: int, alt_text: str = Form(""), db: AsyncSession = Depends(get_db),
                       user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    m = await db.get(Media, media_id)
    if m and m.brand_id == brand.id:
        m.alt_text = alt_text or None
        await db.commit()
    return RedirectResponse("/media", 303)


@router.post("/media/{media_id}/delete")
async def media_delete(media_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    m = await db.get(Media, media_id)
    if m and m.brand_id == brand.id:
        (get_settings().media_dir / m.path).unlink(missing_ok=True)
        await db.delete(m)
        await db.commit()
    return RedirectResponse("/media", 303)
