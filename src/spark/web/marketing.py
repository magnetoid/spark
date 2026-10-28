"""Analytics, short links, RSS feeds, contacts, email campaigns, bio page."""

import csv
import io
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.db import get_db
from spark.models import (
    BioPage,
    Brand,
    Campaign,
    Contact,
    ContactList,
    EmailCampaign,
    EmailSend,
    Media,
    RssFeed,
    ShortLink,
    SocialAccount,
    User,
)
from spark.security import token
from spark.services import analytics, scheduler
from spark.services.ai import AIUnavailable, ContentAI
from spark.services.links import add_utm, create_short_link, short_url
from spark.web.deps import current_user, editor, flash, render, require_brand
from spark.web.posts import enqueue

router = APIRouter()


# ---- dashboard / analytics ----------------------------------------------------

@router.get("/")
async def dashboard(request: Request, days: int = 30, db: AsyncSession = Depends(get_db),
                    user: User = Depends(current_user), brand: Brand | None = Depends(require_brand)):
    """Overview after shadcn's dashboard block: section cards, chart, tabbed table."""
    from spark.models import Post, PostStatus

    days = days if days in (7, 30, 90) else 30
    data = await analytics.overview(db, brand.id, days=days)
    trend = await analytics.compare(db, brand.id, days=days)

    def q(*statuses, order=Post.scheduled_at, desc=False, limit=12):
        stmt = select(Post).where(Post.brand_id == brand.id, Post.status.in_(statuses))
        return stmt.order_by(order.desc() if desc else order).limit(limit)

    upcoming = (await db.execute(q(PostStatus.scheduled, PostStatus.pending_approval))).scalars().all()
    pending = [p for p in upcoming if p.status == PostStatus.pending_approval]
    failed = (await db.execute(q(PostStatus.failed, order=Post.updated_at, desc=True))).scalars().all()
    recent = (await db.execute(q(PostStatus.published, order=Post.scheduled_at, desc=True))).scalars().all()
    accounts = (await db.execute(
        select(SocialAccount).where(SocialAccount.brand_id == brand.id))).scalars().all()
    return await render(request, "dashboard.html", db, user, brand, data=data, trend=trend, days=days,
                        upcoming=upcoming, pending=pending, failed=failed, recent=recent, accounts=accounts,
                        ai_enabled=bool(get_settings().anthropic_api_key))


@router.get("/analytics")
async def analytics_page(request: Request, days: int = 30, db: AsyncSession = Depends(get_db),
                         user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    days = days if days in (7, 30, 90) else 30
    data = await analytics.overview(db, brand.id, days=days)
    clicks = await analytics.link_clicks_series(db, brand.id, days=days)
    best = await scheduler.best_times(db, brand.id)
    return await render(request, "analytics.html", db, user, brand, data=data, clicks=clicks,
                        best=best, days=days,
                        weekdays=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])


@router.post("/analytics/refresh")
async def analytics_refresh(request: Request, db: AsyncSession = Depends(get_db),
                            user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    n = await analytics.collect_metrics(db)
    flash(request, f"Pulled {n} metric snapshot(s)")
    return RedirectResponse("/analytics", 303)


# ---- links ----------------------------------------------------------------------

@router.get("/links")
async def links(request: Request, db: AsyncSession = Depends(get_db),
                user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    rows = (await db.execute(
        select(ShortLink).where(ShortLink.brand_id == brand.id).order_by(ShortLink.id.desc()).limit(200)
    )).scalars().all()
    campaigns = (await db.execute(
        select(Campaign).where(Campaign.brand_id == brand.id).order_by(Campaign.name))).scalars().all()
    return await render(request, "links.html", db, user, brand, links=rows, campaigns=campaigns,
                        short_url=short_url)


@router.post("/links")
async def link_create(request: Request, destination: str = Form(...), title: str = Form(""),
                      utm_source: str = Form(""), utm_medium: str = Form(""), utm_campaign: str = Form(""),
                      utm_content: str = Form(""), campaign_id: str = Form(""),
                      db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    if not destination.startswith(("http://", "https://")):
        destination = "https://" + destination
    dest = add_utm(destination, source=utm_source, medium=utm_medium, campaign=utm_campaign,
                   content=utm_content)
    await create_short_link(db, brand, dest, title=title or None,
                            campaign_id=int(campaign_id) if campaign_id.isdigit() else None)
    await db.commit()
    flash(request, "Short link created")
    return RedirectResponse("/links", 303)


@router.post("/links/{link_id}/delete")
async def link_delete(link_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    link = await db.get(ShortLink, link_id)
    if link and link.brand_id == brand.id:
        await db.delete(link)
        await db.commit()
    return RedirectResponse("/links", 303)


# ---- RSS feeds ------------------------------------------------------------------

@router.get("/feeds")
async def feeds(request: Request, db: AsyncSession = Depends(get_db),
                user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    rows = (await db.execute(select(RssFeed).where(RssFeed.brand_id == brand.id))).scalars().all()
    accounts = (await db.execute(select(SocialAccount).where(
        SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True)))).scalars().all()
    return await render(request, "feeds.html", db, user, brand, feeds=rows, accounts=accounts)


@router.post("/feeds")
async def feed_create(request: Request, url: str = Form(...), name: str = Form(""),
                      use_ai: bool = Form(False), auto_queue: bool = Form(False),
                      account_ids: list[int] = Form([]), db: AsyncSession = Depends(get_db),
                      user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    db.add(RssFeed(brand_id=brand.id, url=url.strip(), name=name or None, use_ai=use_ai,
                   auto_queue=auto_queue, account_ids=account_ids))
    await db.commit()
    flash(request, "Feed added — new items create drafts from the next check on")
    return RedirectResponse("/feeds", 303)


@router.post("/feeds/{feed_id}/toggle")
async def feed_toggle(feed_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    f = await db.get(RssFeed, feed_id)
    if f and f.brand_id == brand.id:
        f.is_active = not f.is_active
        await db.commit()
    return RedirectResponse("/feeds", 303)


@router.post("/feeds/{feed_id}/delete")
async def feed_delete(feed_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    f = await db.get(RssFeed, feed_id)
    if f and f.brand_id == brand.id:
        await db.delete(f)
        await db.commit()
    return RedirectResponse("/feeds", 303)


# ---- contacts -------------------------------------------------------------------

@router.get("/contacts")
async def contacts(request: Request, list_id: int | None = None, q: str = "",
                   db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                   brand: Brand = Depends(require_brand)):
    lists = (await db.execute(select(ContactList).where(ContactList.brand_id == brand.id)
                              .order_by(ContactList.name))).scalars().all()
    stmt = select(Contact).where(Contact.brand_id == brand.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Contact.email).like(like) | func.lower(Contact.first_name).like(like))
    rows = (await db.execute(stmt.order_by(Contact.id.desc()).limit(500))).scalars().all()
    if list_id:
        rows = [c for c in rows if any(l.id == list_id for l in c.lists)]
    total = await db.scalar(select(func.count(Contact.id)).where(Contact.brand_id == brand.id))
    subscribed = await db.scalar(select(func.count(Contact.id)).where(
        Contact.brand_id == brand.id, Contact.subscribed.is_(True)))
    return await render(request, "contacts.html", db, user, brand, contacts=rows, lists=lists,
                        list_id=list_id, q=q, total=total, subscribed=subscribed)


async def _upsert_contact(db: AsyncSession, brand: Brand, email: str, first: str = "", last: str = "",
                          source: str = "manual", lists: list[ContactList] | None = None) -> Contact | None:
    email = email.strip().lower()
    if "@" not in email:
        return None
    c = await db.scalar(select(Contact).where(Contact.brand_id == brand.id, Contact.email == email))
    if c is None:
        c = Contact(brand_id=brand.id, email=email, source=source, unsubscribe_token=token(16))
        db.add(c)
        await db.flush()
    c.first_name = first.strip() or c.first_name
    c.last_name = last.strip() or c.last_name
    for l in lists or []:
        if l not in c.lists:
            c.lists.append(l)
    return c


@router.post("/contacts")
async def contact_add(request: Request, email: str = Form(...), first_name: str = Form(""),
                      last_name: str = Form(""), list_ids: list[int] = Form([]),
                      db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    lists = (await db.execute(select(ContactList).where(ContactList.id.in_(list_ids),
                                                        ContactList.brand_id == brand.id))).scalars().all()
    if await _upsert_contact(db, brand, email, first_name, last_name, "manual", lists):
        await db.commit()
        flash(request, "Contact saved")
    else:
        flash(request, "Invalid email", "error")
    return RedirectResponse("/contacts", 303)


@router.post("/contacts/import")
async def contact_import(request: Request, file: UploadFile = File(...), list_ids: list[int] = Form([]),
                         db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                         brand: Brand = Depends(require_brand)):
    """CSV with an `email` column; optional first_name/last_name (or name)."""
    lists = (await db.execute(select(ContactList).where(ContactList.id.in_(list_ids),
                                                        ContactList.brand_id == brand.id))).scalars().all()
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    n = 0
    for row in reader:
        row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
        email = row.get("email") or row.get("e-mail") or ""
        first = row.get("first_name") or row.get("firstname") or ""
        last = row.get("last_name") or row.get("lastname") or ""
        if not first and row.get("name"):
            first, _, last = row["name"].partition(" ")
        if await _upsert_contact(db, brand, email, first, last, "import", lists):
            n += 1
    await db.commit()
    flash(request, f"Imported {n} contact(s)")
    return RedirectResponse("/contacts", 303)


@router.get("/contacts/export")
async def contact_export(db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                         brand: Brand = Depends(require_brand)):
    rows = (await db.execute(select(Contact).where(Contact.brand_id == brand.id))).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "first_name", "last_name", "subscribed", "source", "lists"])
    for c in rows:
        w.writerow([c.email, c.first_name or "", c.last_name or "", c.subscribed, c.source,
                    ";".join(l.name for l in c.lists)])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={brand.slug}-contacts.csv"})


@router.post("/contacts/{contact_id}/delete")
async def contact_delete(contact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                         brand: Brand = Depends(require_brand)):
    c = await db.get(Contact, contact_id)
    if c and c.brand_id == brand.id:
        await db.delete(c)
        await db.commit()
    return RedirectResponse("/contacts", 303)


@router.post("/lists")
async def list_create(request: Request, name: str = Form(...), description: str = Form(""),
                      db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    db.add(ContactList(brand_id=brand.id, name=name.strip(), description=description or None))
    await db.commit()
    return RedirectResponse("/contacts", 303)


@router.post("/lists/{list_id}/delete")
async def list_delete(list_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                      brand: Brand = Depends(require_brand)):
    l = await db.get(ContactList, list_id)
    if l and l.brand_id == brand.id:
        await db.delete(l)
        await db.commit()
    return RedirectResponse("/contacts", 303)


# ---- email campaigns ----------------------------------------------------------------

@router.get("/email")
async def email_list(request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    rows = (await db.execute(select(EmailCampaign).where(EmailCampaign.brand_id == brand.id)
                             .order_by(EmailCampaign.id.desc()))).scalars().all()
    stats = {}
    for c in rows:
        sends = (await db.execute(select(EmailSend).where(EmailSend.campaign_id == c.id))).scalars().all()
        stats[c.id] = {"sent": sum(1 for s in sends if s.sent_at), "opened": sum(1 for s in sends if s.opened_at),
                       "clicked": sum(1 for s in sends if s.clicked_at), "failed": sum(1 for s in sends if s.error)}
    lists = (await db.execute(select(ContactList).where(ContactList.brand_id == brand.id))).scalars().all()
    return await render(request, "email.html", db, user, brand, campaigns=rows, stats=stats, lists=lists,
                        backend=get_settings().email_backend)


@router.post("/email")
async def email_create(request: Request, name: str = Form(...), list_id: str = Form(""),
                       db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                       brand: Brand = Depends(require_brand)):
    c = EmailCampaign(brand_id=brand.id, name=name.strip(),
                      list_id=int(list_id) if list_id.isdigit() else None,
                      body_html="<p>Hi {{first_name}},</p><p>…</p>")
    db.add(c)
    await db.commit()
    return RedirectResponse(f"/email/{c.id}", 303)


async def _get_campaign(db, brand, cid) -> EmailCampaign:
    c = await db.get(EmailCampaign, cid)
    if not c or c.brand_id != brand.id:
        raise HTTPException(404)
    return c


@router.get("/email/{cid}")
async def email_edit(cid: int, request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    c = await _get_campaign(db, brand, cid)
    lists = (await db.execute(select(ContactList).where(ContactList.brand_id == brand.id))).scalars().all()
    recipients = 0
    if c.list_id:
        l = await db.get(ContactList, c.list_id)
        recipients = sum(1 for x in l.contacts if x.subscribed) if l else 0
    return await render(request, "email_edit.html", db, user, brand, c=c, lists=lists, recipients=recipients,
                        ai_enabled=bool(get_settings().anthropic_api_key))


@router.post("/email/{cid}")
async def email_save(cid: int, request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    c = await _get_campaign(db, brand, cid)
    if c.status in ("sending", "sent"):
        flash(request, "Sent campaigns can't be edited", "error")
        return RedirectResponse(f"/email/{cid}", 303)
    form = await request.form()
    c.name = str(form.get("name", c.name))
    c.subject = str(form.get("subject", ""))
    c.preheader = str(form.get("preheader", "")) or None
    c.body_html = str(form.get("body_html", ""))
    lid = str(form.get("list_id", ""))
    c.list_id = int(lid) if lid.isdigit() else None
    action = form.get("action", "save")
    if action in ("send", "schedule"):
        if not c.list_id or not c.subject or not c.body_html.strip():
            flash(request, "Pick a list, add a subject and a body first", "error")
            await db.commit()
            return RedirectResponse(f"/email/{cid}", 303)
        if action == "send":
            c.status, c.scheduled_at = "scheduled", datetime.now(UTC)
            await db.commit()
            await enqueue("send_email_campaign", c.id)
            flash(request, "Sending…")
            return RedirectResponse("/email", 303)
        raw = str(form.get("scheduled_at", ""))
        if not raw:
            flash(request, "Pick a date and time", "error")
        else:
            c.scheduled_at = datetime.fromisoformat(raw).replace(tzinfo=ZoneInfo(brand.timezone)).astimezone(UTC)
            c.status = "scheduled"
            flash(request, "Email scheduled")
    elif action == "unschedule":
        c.status = "draft"
    await db.commit()
    return RedirectResponse(f"/email/{cid}", 303)


@router.post("/email/{cid}/ai")
async def email_ai(cid: int, request: Request, db: AsyncSession = Depends(get_db),
                   user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    await _get_campaign(db, brand, cid)
    body = await request.json()
    try:
        draft = await ContentAI().email(brand, body.get("brief", ""))
    except AIUnavailable as e:
        raise HTTPException(400, str(e))
    return draft.model_dump()


@router.post("/email/{cid}/test")
async def email_test(cid: int, request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    from spark.services.email import get_sender
    from spark.services.email import render as render_email

    c = await _get_campaign(db, brand, cid)
    fake = Contact(brand_id=brand.id, email=user.email, first_name=user.name, unsubscribe_token="test")
    send = EmailSend(campaign_id=c.id, contact_id=0, token="test")
    await get_sender().send(user.email, f"[TEST] {c.subject}", render_email(c, brand, fake, send))
    flash(request, f"Test sent to {user.email} (backend: {get_settings().email_backend})")
    return RedirectResponse(f"/email/{cid}", 303)


@router.post("/email/{cid}/delete")
async def email_delete(cid: int, db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                       brand: Brand = Depends(require_brand)):
    c = await _get_campaign(db, brand, cid)
    await db.delete(c)
    await db.commit()
    return RedirectResponse("/email", 303)


# ---- bio page -------------------------------------------------------------------------

@router.get("/bio")
async def bio_edit(request: Request, db: AsyncSession = Depends(get_db),
                   user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    page = await db.scalar(select(BioPage).where(BioPage.brand_id == brand.id))
    if page is None:
        page = BioPage(brand_id=brand.id, title=brand.name, links=[])
        db.add(page)
        await db.commit()
    lists = (await db.execute(select(ContactList).where(ContactList.brand_id == brand.id))).scalars().all()
    images = (await db.execute(select(Media).where(Media.brand_id == brand.id,
                                                   Media.content_type.like("image/%")))).scalars().all()
    codes = [l.get("code") for l in (page.links or []) if l.get("code")]
    clicks = {}
    if codes:
        clicks = {l.code: l.clicks for l in (await db.execute(
            select(ShortLink).where(ShortLink.code.in_(codes)))).scalars()}
    page_links = [{**l, "clicks": clicks.get(l.get("code"), 0)} for l in (page.links or [])]
    return await render(request, "bio.html", db, user, brand, page=page, lists=lists, images=images,
                        page_links=page_links, total_clicks=sum(clicks.values()),
                        public_url=f"{get_settings().base_url.rstrip('/')}/b/{brand.slug}")


@router.post("/bio")
async def bio_save(request: Request, db: AsyncSession = Depends(get_db),
                   user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    page = await db.scalar(select(BioPage).where(BioPage.brand_id == brand.id))
    form = await request.form()
    page.title = str(form.get("title", brand.name))
    page.bio = str(form.get("bio", "")) or None
    page.theme = str(form.get("theme", "light"))
    page.capture_email = form.get("capture_email") == "on"
    page.is_published = form.get("is_published") == "on"
    lid, mid = str(form.get("capture_list_id", "")), str(form.get("avatar_media_id", ""))
    page.capture_list_id = int(lid) if lid.isdigit() else None
    page.avatar_media_id = int(mid) if mid.isdigit() else None
    labels, urls = form.getlist("link_label"), form.getlist("link_url")
    codes = form.getlist("link_code")
    codes += [""] * (len(labels) - len(codes))
    # Each bio link is a tracked short link, so clicks show up per link and in Analytics.
    existing = {l.code: l for l in (await db.execute(
        select(ShortLink).where(ShortLink.brand_id == brand.id,
                                ShortLink.code.in_([c for c in codes if c])))).scalars()}
    links = []
    for label, url, code in zip(labels, urls, codes, strict=False):
        label, url, code = str(label).strip(), str(url).strip(), str(code).strip()
        if not label or not url:
            continue
        tagged = add_utm(url, source="bio", medium="bio")
        link = existing.get(code)
        if link is None or link.destination != tagged:
            # New link, or the URL changed: start a fresh code so old click counts stay honest.
            link = await create_short_link(db, brand, tagged, title=label)
        else:
            link.title = label
        links.append({"label": label, "url": url, "code": link.code})
    page.links = links
    await db.commit()
    flash(request, "Bio page saved")
    return RedirectResponse("/bio", 303)
