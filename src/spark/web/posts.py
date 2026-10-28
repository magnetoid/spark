"""Composer, post list, calendar, approvals and campaigns."""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.db import get_db
from spark.models import (
    Brand,
    Campaign,
    HashtagGroup,
    Media,
    Post,
    PostStatus,
    PostTarget,
    PostTemplate,
    SocialAccount,
    User,
)
from spark.platforms import PublishPayload, adapter_for
from spark.services import scheduler
from spark.services.ai import AIUnavailable, ContentAI
from spark.services.links import shorten_in_text
from spark.services.publisher import as_utc, validate_post
from spark.web.deps import current_user, editor, flash, owner, render, require_brand

router = APIRouter()
log = logging.getLogger(__name__)
# Platforms where a "first comment" is posted right after publishing (direct adapters and Zernio)
FIRST_COMMENT_PLATFORMS = {"x", "mastodon", "bluesky", "threads", "facebook", "instagram", "linkedin",
                           "youtube", "dry_run"}
# Platforms where long text can be split into a thread of replies
THREAD_PLATFORMS = {"x", "threads", "bluesky", "mastodon", "dry_run"}


async def enqueue(job: str, *args) -> bool:
    """Best-effort immediate job; the worker's cron picks it up anyway."""
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        await pool.enqueue_job(job, *args)
        await pool.aclose()
        return True
    except Exception as e:
        log.info("Could not enqueue %s (%s); cron will handle it", job, e)
        return False


async def _accounts(db: AsyncSession, brand: Brand) -> list[SocialAccount]:
    return (await db.execute(
        select(SocialAccount).where(SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True))
        .order_by(SocialAccount.platform)
    )).scalars().all()


async def _campaigns(db: AsyncSession, brand: Brand) -> list[Campaign]:
    return (await db.execute(
        select(Campaign).where(Campaign.brand_id == brand.id).order_by(Campaign.id.desc())
    )).scalars().all()


async def _get_post(db: AsyncSession, brand: Brand, post_id: int) -> Post:
    post = await db.get(Post, post_id)
    if not post or post.brand_id != brand.id:
        raise HTTPException(404)
    return post


def parse_local(value: str, tz: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(tz)).astimezone(UTC)


# ---- composer ----------------------------------------------------------------

@router.get("/compose")
@router.get("/posts/{post_id}/edit")
async def compose(request: Request, post_id: int | None = None, date_: str | None = None,
                  db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                  brand: Brand = Depends(require_brand)):
    post = await _get_post(db, brand, post_id) if post_id else None
    media = []
    if post and post.media_ids:
        rows = (await db.execute(select(Media).where(Media.id.in_(post.media_ids)))).scalars().all()
        media = sorted(rows, key=lambda m: post.media_ids.index(m.id))
    accounts = await _accounts(db, brand)
    limits = {}
    for a in accounts:
        ad = adapter_for(a)
        limits[a.id] = {"max": ad.limits.max_chars, "label": ad.label, "platform": a.platform,
                        "handle": a.handle, "requires_media": ad.limits.requires_media,
                        "provider": a.provider, "avatar": a.avatar_url,
                        "display_name": a.display_name or a.handle,
                        "first_comment": a.platform in FIRST_COMMENT_PLATFORMS,
                        "threadable": a.platform in THREAD_PLATFORMS}
    prefill_at = request.query_params.get("at")
    ai_enabled = bool(get_settings().anthropic_api_key)
    preselect = request.query_params.get("account")
    selected = [t.account_id for t in post.targets] if post else (
        [int(preselect)] if preselect and preselect.isdigit() and int(preselect) in limits else [])
    composer_state = {
        "content": post.content if post else "",
        "link": post.link if post else "",
        "mediaIds": list(post.media_ids) if post else [],
        "media": [{"id": m.id, "url": m.url, "video": m.is_video, "name": m.filename} for m in media],
        "selected": selected,
        "overrides": {str(t.account_id): t.content_override or "" for t in post.targets} if post else {},
        "firstComments": {str(t.account_id): t.first_comment or "" for t in post.targets} if post else {},
        "threads": {str(t.account_id): list(t.thread or []) for t in post.targets} if post else {},
        "brand": {"name": brand.name, "color": brand.color},
        "templates": [{"id": t.id, "name": t.name, "body": t.body, "category": t.category}
                      for t in (await db.execute(select(PostTemplate).where(PostTemplate.brand_id == brand.id)
                                                 .order_by(PostTemplate.name))).scalars()],
        "hashtagGroups": [{"id": g.id, "name": g.name, "tags": g.tags}
                          for g in (await db.execute(select(HashtagGroup).where(HashtagGroup.brand_id == brand.id)
                                                     .order_by(HashtagGroup.name))).scalars()],
        "limits": {str(k): v for k, v in limits.items()},
        "ai": ai_enabled,
    }
    return await render(
        request, "compose.html", db, user, brand, post=post, media=media, accounts=accounts,
        limits=limits, campaigns=await _campaigns(db, brand), prefill_at=prefill_at,
        ai_enabled=ai_enabled, composer_state=composer_state,
    )


@router.post("/compose")
@router.post("/posts/{post_id}/edit")
async def compose_save(request: Request, post_id: int | None = None,
                       db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                       brand: Brand = Depends(require_brand)):
    form = await request.form()
    action = form.get("action", "draft")
    account_ids = [int(a) for a in form.getlist("account_ids")]
    media_ids = [int(m) for m in str(form.get("media_ids", "")).split(",") if m.strip().isdigit()]
    campaign_id = int(form["campaign_id"]) if str(form.get("campaign_id", "")).isdigit() else None
    content = str(form.get("content", "")).strip()
    link = str(form.get("link", "")).strip() or None

    post = await _get_post(db, brand, post_id) if post_id else None
    if post is None:
        post = Post(brand_id=brand.id, author_id=user.id, source=str(form.get("source", "manual")))
        post.targets = []
        db.add(post)
    if post.status in (PostStatus.publishing,):
        flash(request, "This post is publishing right now and can't be edited", "error")
        return RedirectResponse("/posts", 303)

    campaign = await db.get(Campaign, campaign_id) if campaign_id else None
    if brand.auto_shorten_links and content:
        content = await shorten_in_text(
            db, brand, content, source="spark", campaign=campaign.utm_campaign if campaign else None,
            campaign_id=campaign_id,
        )
    post.content, post.link, post.media_ids, post.campaign_id = content, link, media_ids, campaign_id
    post.notes = str(form.get("notes", "")) or None

    valid_accounts = {a.id for a in await _accounts(db, brand)}
    existing = {t.account_id: t for t in post.targets}
    keep = []
    for aid in account_ids:
        if aid not in valid_accounts:
            continue
        t = existing.get(aid) or PostTarget(account_id=aid)
        override = str(form.get(f"override_{aid}", "")).strip()
        t.content_override = override if override and override != content else None
        t.first_comment = str(form.get(f"first_comment_{aid}", "")).strip() or None
        try:
            raw_thread = json.loads(str(form.get(f"thread_{aid}", "") or "[]"))
        except ValueError:
            raw_thread = []
        t.thread = [str(x).strip() for x in raw_thread if str(x).strip()][:25] if isinstance(raw_thread, list) else []
        if t.status in (PostStatus.failed,):
            t.status = PostStatus.draft
        keep.append(t)
    post.targets = keep
    await db.flush()
    await db.refresh(post, ["targets"])

    if action != "draft":
        if not post.targets:
            flash(request, "Pick at least one account to publish to", "error")
            await db.commit()
            return RedirectResponse(f"/posts/{post.id}/edit", 303)
        problems = await validate_post(db, post)
        if problems:
            await db.commit()
            for p in problems:
                flash(request, p, "error")
            return RedirectResponse(f"/posts/{post.id}/edit", 303)

    if action == "draft":
        scheduler.unschedule(post)
        msg = "Draft saved"
    elif action == "now":
        scheduler.schedule(post, datetime.now(UTC), user, brand)
        msg = "Publishing now…" if post.status == PostStatus.scheduled else "Sent for approval"
    elif action == "queue":
        when = await scheduler.next_free_slot(db, brand)
        status = scheduler.schedule(post, when, user, brand)
        msg = f"Queued for {when.astimezone(ZoneInfo(brand.timezone)):%a %b %d, %H:%M}"
        if status == PostStatus.pending_approval:
            msg += " (awaiting approval)"
    elif action == "next":
        status = await scheduler.prioritize(db, brand, post, user)
        msg = f"Sharing next, at {post.scheduled_at.astimezone(ZoneInfo(brand.timezone)):%a %b %d, %H:%M}"
        if status == PostStatus.pending_approval:
            msg += " (awaiting approval)"
    else:
        raw = str(form.get("scheduled_at", ""))
        if not raw:
            flash(request, "Pick a date and time", "error")
            await db.commit()
            return RedirectResponse(f"/posts/{post.id}/edit", 303)
        when = parse_local(raw, brand.timezone)
        status = scheduler.schedule(post, when, user, brand)
        msg = "Scheduled" if status == PostStatus.scheduled else "Scheduled — awaiting approval"
    await db.commit()
    if action == "now" and post.status == PostStatus.scheduled:
        for t in post.targets:
            await enqueue("publish_now", t.id)
    flash(request, msg)
    if action == "draft":
        return RedirectResponse(f"/posts/{post.id}/edit", 303)
    first = post.targets[0].account_id if post.targets else None
    return RedirectResponse(f"/queue?account={first}" if first else "/posts", 303)


@router.post("/compose/preview")
async def compose_validate(request: Request, db: AsyncSession = Depends(get_db),
                           user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    body = await request.json()
    media = []
    if body.get("media_ids"):
        media = (await db.execute(select(Media).where(
            Media.id.in_(body["media_ids"]), Media.brand_id == brand.id))).scalars().all()
    problems = {}
    for aid, text in body.get("targets", {}).items():
        acc = await db.get(SocialAccount, int(aid))
        if acc and acc.brand_id == brand.id:
            problems[aid] = adapter_for(acc).validate(
                PublishPayload(text=text, media=list(media), link=body.get("link")))
    return JSONResponse(problems)


# ---- AI endpoints (JSON, used by the composer) ----------------------------------

def _ai() -> ContentAI:
    try:
        return ContentAI()
    except AIUnavailable as e:
        raise HTTPException(400, str(e))


@router.post("/ai/generate")
async def ai_generate(request: Request, user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    body = await request.json()
    platforms = body.get("platforms") or ["x", "linkedin"]
    source = None
    if url := body.get("url"):
        source = await _fetch_page_text(url)
    try:
        drafts = await _ai().generate(brand, body.get("brief", ""), platforms,
                                      source_text=source, link=body.get("link") or body.get("url"),
                                      variants=int(body.get("variants", 1)))
    except AIUnavailable as e:
        raise HTTPException(400, str(e))
    return {"drafts": [d.model_dump() for d in drafts]}


@router.post("/ai/rewrite")
async def ai_rewrite(request: Request, user: User = Depends(editor),
                     brand: Brand = Depends(require_brand)):
    body = await request.json()
    try:
        text = await _ai().rewrite(brand, body["text"], body.get("instruction", "Improve it"),
                                   body.get("platform"))
    except AIUnavailable as e:
        raise HTTPException(400, str(e))
    return {"text": text}


@router.post("/ai/hashtags")
async def ai_hashtags(request: Request, user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    body = await request.json()
    try:
        tags = await _ai().hashtags(brand, body["text"])
    except AIUnavailable as e:
        raise HTTPException(400, str(e))
    return {"hashtags": tags}


async def _fetch_page_text(url: str) -> str | None:
    import re

    import httpx

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
            resp = await http.get(url, headers={"User-Agent": "Spark/1.0"})
        html = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", resp.text)
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()[:20000]
    except httpx.HTTPError:
        return None


# ---- list / actions -----------------------------------------------------------

@router.get("/posts")
async def post_list(request: Request, status: str | None = None,
                    db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                    brand: Brand = Depends(require_brand)):
    stmt = select(Post).where(Post.brand_id == brand.id)
    if status:
        stmt = stmt.where(Post.status == status)
    stmt = stmt.order_by(Post.scheduled_at.desc().nulls_first(), Post.id.desc()).limit(200)
    posts = (await db.execute(stmt)).scalars().all()
    return await render(request, "posts.html", db, user, brand, posts=posts, status=status,
                        statuses=list(PostStatus))


@router.post("/posts/{post_id}/approve")
async def post_approve(post_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       user: User = Depends(owner), brand: Brand = Depends(require_brand)):
    post = await _get_post(db, brand, post_id)
    scheduler.approve(post)
    await db.commit()
    flash(request, "Approved and scheduled")
    return RedirectResponse(request.headers.get("referer") or "/posts", 303)


@router.post("/posts/{post_id}/unschedule")
async def post_unschedule(post_id: int, request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    post = await _get_post(db, brand, post_id)
    scheduler.unschedule(post)
    await db.commit()
    flash(request, "Moved back to drafts")
    return RedirectResponse(request.headers.get("referer") or "/posts", 303)


@router.post("/posts/{post_id}/retry")
async def post_retry(post_id: int, request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    post = await _get_post(db, brand, post_id)
    now = datetime.now(UTC)
    for t in post.targets:
        if t.status == PostStatus.failed:
            t.status, t.scheduled_at, t.attempts, t.next_attempt_at = PostStatus.scheduled, now, 0, None
    post.refresh_status()
    await db.commit()
    for t in post.targets:
        if t.status == PostStatus.scheduled:
            await enqueue("publish_now", t.id)
    flash(request, "Retrying failed targets")
    return RedirectResponse(request.headers.get("referer") or "/posts", 303)


@router.post("/posts/{post_id}/duplicate")
async def post_duplicate(post_id: int, request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    src = await _get_post(db, brand, post_id)
    post = Post(brand_id=brand.id, author_id=user.id, content=src.content, link=src.link,
                media_ids=list(src.media_ids), campaign_id=src.campaign_id)
    post.targets = [PostTarget(account_id=t.account_id, content_override=t.content_override)
                    for t in src.targets]
    db.add(post)
    await db.commit()
    return RedirectResponse(f"/posts/{post.id}/edit", 303)


@router.post("/posts/{post_id}/delete")
async def post_delete(post_id: int, request: Request, db: AsyncSession = Depends(get_db),
                      user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    post = await _get_post(db, brand, post_id)
    await db.delete(post)
    await db.commit()
    flash(request, "Post deleted")
    return RedirectResponse("/posts", 303)


# ---- calendar -------------------------------------------------------------------

@router.get("/calendar")
async def calendar(request: Request, month: str | None = None, week: str | None = None,
                   view: str = "month", account: int | None = None, campaign: int | None = None,
                   db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                   brand: Brand = Depends(require_brand)):
    """Month or week grid (Buffer has both), filterable by channel and campaign."""
    zone = ZoneInfo(brand.timezone)
    today = datetime.now(zone).date()
    view = "week" if view == "week" else "month"
    if view == "week":
        anchor = date.fromisoformat(week) if week else today
        grid_start = anchor - timedelta(days=anchor.weekday())
        weeks = 1
        first = grid_start
        prev_link = f"/calendar?view=week&week={(grid_start - timedelta(days=7)).isoformat()}"
        next_link = f"/calendar?view=week&week={(grid_start + timedelta(days=7)).isoformat()}"
        title = f"{grid_start:%b %d} – {(grid_start + timedelta(days=6)):%b %d, %Y}"
    else:
        first = date.fromisoformat(f"{month}-01") if month else today.replace(day=1)
        grid_start = first - timedelta(days=first.weekday())
        weeks = 6
        prev_link = f"/calendar?month={(first - timedelta(days=1)):%Y-%m}"
        next_link = f"/calendar?month={(first + timedelta(days=32)):%Y-%m}"
        title = first.strftime("%B %Y")
    grid_end = grid_start + timedelta(days=7 * weeks)
    start_utc = datetime.combine(grid_start, datetime.min.time(), zone).astimezone(UTC)
    end_utc = datetime.combine(grid_end, datetime.min.time(), zone).astimezone(UTC)
    stmt = select(Post).where(Post.brand_id == brand.id, Post.scheduled_at >= start_utc,
                              Post.scheduled_at < end_utc)
    if campaign:
        stmt = stmt.where(Post.campaign_id == campaign)
    if account:
        stmt = stmt.where(Post.id.in_(select(PostTarget.post_id).where(PostTarget.account_id == account)))
    posts = (await db.execute(stmt.order_by(Post.scheduled_at))).scalars().all()
    by_day: dict[date, list[Post]] = {}
    for p in posts:
        by_day.setdefault(as_utc(p.scheduled_at).astimezone(zone).date(), []).append(p)
    days = [grid_start + timedelta(days=i) for i in range(7 * weeks)]
    filters = f"&account={account}" if account else ""
    filters += f"&campaign={campaign}" if campaign else ""
    return await render(request, "calendar.html", db, user, brand, days=days, by_day=by_day,
                        first=first, today=today, view=view, title=title,
                        prev_link=prev_link + filters, next_link=next_link + filters,
                        accounts=await _accounts(db, brand), campaigns=await _campaigns(db, brand),
                        account=account, campaign=campaign)


@router.post("/calendar/move")
async def calendar_move(request: Request, post_id: int = Form(...), day: str = Form(...),
                        db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                        brand: Brand = Depends(require_brand)):
    """Drag & drop: keep time of day, change date."""
    post = await _get_post(db, brand, post_id)
    if post.status not in (PostStatus.scheduled, PostStatus.pending_approval, PostStatus.draft):
        raise HTTPException(400, "Only unpublished posts can be moved")
    zone = ZoneInfo(brand.timezone)
    current = as_utc(post.scheduled_at).astimezone(zone) if post.scheduled_at else \
        datetime.now(zone).replace(hour=9, minute=0)
    new_day = date.fromisoformat(day)
    when = current.replace(year=new_day.year, month=new_day.month, day=new_day.day).astimezone(UTC)
    if when < datetime.now(UTC):
        raise HTTPException(400, "Can't move a post into the past")
    post.scheduled_at = when
    for t in post.targets:
        if t.status != PostStatus.published:
            t.scheduled_at = when
    await db.commit()
    return JSONResponse({"ok": True})


# ---- campaigns ----------------------------------------------------------------

@router.get("/campaigns")
async def campaigns(request: Request, db: AsyncSession = Depends(get_db),
                    user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    rows = await _campaigns(db, brand)
    counts = {}
    for c in rows:
        posts = (await db.execute(select(Post).where(Post.campaign_id == c.id))).scalars().all()
        counts[c.id] = {s: sum(1 for p in posts if p.status == s) for s in PostStatus} | {"total": len(posts)}
    return await render(request, "campaigns.html", db, user, brand, campaigns=rows, counts=counts,
                        accounts=await _accounts(db, brand),
                        ai_enabled=bool(get_settings().anthropic_api_key))


@router.post("/campaigns")
async def campaign_create(request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    form = await request.form()
    zone = ZoneInfo(brand.timezone)
    starts = date.fromisoformat(str(form["starts_on"])) if form.get("starts_on") else None
    ends = date.fromisoformat(str(form["ends_on"])) if form.get("ends_on") else None
    c = Campaign(
        brand_id=brand.id, name=str(form["name"]), goal=str(form.get("goal", "")) or None,
        starts_on=datetime.combine(starts, datetime.min.time(), zone) if starts else None,
        ends_on=datetime.combine(ends, datetime.min.time(), zone) if ends else None,
        utm_campaign=str(form.get("utm_campaign", "")) or None,
        color=str(form.get("color", "#6366f1")),
    )
    db.add(c)
    await db.flush()
    created = 0
    if form.get("ai_plan") and starts and ends and c.goal:
        account_ids = [int(a) for a in form.getlist("account_ids")]
        accounts = [a for a in await _accounts(db, brand) if a.id in account_ids]
        if not accounts:
            flash(request, "Pick accounts for the AI plan", "error")
        else:
            try:
                plan = await _ai().plan_campaign(
                    brand, c.goal, starts, ends, sorted({a.platform for a in accounts}),
                    int(form.get("per_week", 3)),
                )
                for pp in plan.posts:
                    targets = [PostTarget(account_id=a.id) for a in accounts if a.platform in pp.platforms]
                    if not targets:
                        continue
                    hour = datetime.combine(date.fromisoformat(pp.date), datetime.min.time(), zone)
                    post = Post(brand_id=brand.id, author_id=user.id, campaign_id=c.id,
                                content=pp.text, source="ai", notes=f"Theme: {pp.theme}",
                                scheduled_at=(hour + timedelta(hours=10)).astimezone(UTC))
                    post.targets = targets
                    db.add(post)
                    created += 1
            except (AIUnavailable, HTTPException) as e:
                flash(request, f"AI plan failed: {getattr(e, 'detail', e)}", "error")
    await db.commit()
    flash(request, "Campaign created" + (f" with {created} draft posts — review them in Posts" if created else ""))
    return RedirectResponse("/campaigns", 303)


@router.post("/campaigns/{campaign_id}/delete")
async def campaign_delete(campaign_id: int, request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    c = await db.get(Campaign, campaign_id)
    if c and c.brand_id == brand.id:
        await db.delete(c)
        await db.commit()
    return RedirectResponse("/campaigns", 303)
