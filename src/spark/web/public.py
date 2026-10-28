"""Unauthenticated endpoints: short links, email tracking, unsubscribe, bio pages."""

import base64
from datetime import UTC, datetime
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.models import (
    BioPage,
    Brand,
    Contact,
    ContactList,
    EmailSend,
    LinkClick,
    Media,
    ShortLink,
)
from spark.security import token
from spark.web.deps import templates

router = APIRouter()
PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


@router.get("/l/{code}")
async def short_link(code: str, request: Request, db: AsyncSession = Depends(get_db)):
    link = await db.scalar(select(ShortLink).where(ShortLink.code == code))
    if not link:
        return HTMLResponse("<h1>Link not found</h1>", 404)
    link.clicks += 1
    db.add(LinkClick(link_id=link.id, clicked_at=datetime.now(UTC),
                     referrer=request.headers.get("referer", "")[:1000] or None,
                     user_agent=request.headers.get("user-agent", "")[:500] or None))
    await db.commit()
    return RedirectResponse(link.destination, 302)


@router.get("/e/o/{tok}.gif")
async def email_open(tok: str, db: AsyncSession = Depends(get_db)):
    send = await db.scalar(select(EmailSend).where(EmailSend.token == tok))
    if send and not send.opened_at:
        send.opened_at = datetime.now(UTC)
        await db.commit()
    return Response(PIXEL, media_type="image/gif", headers={"Cache-Control": "no-store"})


@router.get("/e/c/{tok}")
async def email_click(tok: str, u: str, db: AsyncSession = Depends(get_db)):
    send = await db.scalar(select(EmailSend).where(EmailSend.token == tok))
    if send:
        now = datetime.now(UTC)
        send.clicked_at = send.clicked_at or now
        send.opened_at = send.opened_at or now
        await db.commit()
    url = unquote(u)
    if not url.startswith(("http://", "https://")):
        url = "/"
    return RedirectResponse(url, 302)


@router.api_route("/e/u/{tok}", methods=["GET", "POST"])
async def unsubscribe(tok: str, db: AsyncSession = Depends(get_db)):
    contact = await db.scalar(select(Contact).where(Contact.unsubscribe_token == tok))
    if contact:
        contact.subscribed = False
        await db.commit()
    return HTMLResponse(
        "<!doctype html><meta name=viewport content='width=device-width'>"
        "<body style='font-family:system-ui;max-width:480px;margin:80px auto;text-align:center'>"
        "<h2>You're unsubscribed</h2><p>You won't receive further emails from this sender.</p></body>"
    )


async def _bio(db: AsyncSession, slug: str):
    brand = await db.scalar(select(Brand).where(Brand.slug == slug))
    if not brand:
        return None, None, None
    page = await db.scalar(select(BioPage).where(BioPage.brand_id == brand.id))
    if not page or not page.is_published:
        return brand, None, None
    avatar = await db.get(Media, page.avatar_media_id) if page.avatar_media_id else None
    return brand, page, avatar


@router.get("/b/{slug}")
async def bio_page(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    brand, page, avatar = await _bio(db, slug)
    if not page:
        return HTMLResponse("<h1>Page not found</h1>", 404)
    page.views += 1
    await db.commit()
    return templates.TemplateResponse(request, "public/bio.html",
                                      {"brand": brand, "page": page, "avatar": avatar, "done": False})


@router.post("/b/{slug}/subscribe")
async def bio_subscribe(slug: str, request: Request, email: str = Form(...), name: str = Form(""),
                        db: AsyncSession = Depends(get_db)):
    brand, page, avatar = await _bio(db, slug)
    if not page or not page.capture_email:
        return HTMLResponse("<h1>Not found</h1>", 404)
    email = email.strip().lower()
    if "@" in email:
        contact = await db.scalar(select(Contact).where(Contact.brand_id == brand.id, Contact.email == email))
        if contact is None:
            contact = Contact(brand_id=brand.id, email=email, first_name=name.strip() or None,
                              source="bio", unsubscribe_token=token(16))
            db.add(contact)
            await db.flush()
        contact.subscribed = True
        if page.capture_list_id:
            clist = await db.get(ContactList, page.capture_list_id)
            if clist and clist not in contact.lists:
                contact.lists.append(clist)
        await db.commit()
    return templates.TemplateResponse(request, "public/bio.html",
                                      {"brand": brand, "page": page, "avatar": avatar, "done": True})
