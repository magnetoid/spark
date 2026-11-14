"""Audience: contacts, lists and email campaigns."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    ContactIn,
    ContactOut,
    ContactPage,
    EmailCreate,
    EmailOut,
    EmailUpdate,
    ListIn,
    ListOut,
)
from spark.db import get_db
from spark.models import Contact, ContactList, EmailCampaign, EmailSend
from spark.services import contacts as svc
from spark.services import jobs
from spark.services.ai import AIUnavailable, ContentAI
from spark.services.publisher import as_utc

router = APIRouter(tags=["audience"])
B = "/brands/{brand_id}"


def _contact(c: Contact) -> ContactOut:
    return ContactOut(
        id=c.id,
        email=c.email,
        first_name=c.first_name,
        last_name=c.last_name,
        source=c.source,
        subscribed=c.subscribed,
        lists=[lst.id for lst in c.lists],
        created_at=as_utc(c.created_at) if c.created_at else None,
    )


@router.get(B + "/contacts", response_model=ContactPage)
async def list_contacts(
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
    q: str = "",
    list_id: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = 0,
):
    rows, total, subscribed = await svc.search(db, ctx.brand, q, list_id, limit, offset)
    return ContactPage(items=[_contact(c) for c in rows], total=total, subscribed=subscribed)


@router.post(B + "/contacts", response_model=ContactOut, status_code=201)
async def add_contact(
    body: ContactIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    lists = await svc.lists_for(db, ctx.brand, body.list_ids)
    c = await svc.upsert(
        db, ctx.brand, body.email, body.first_name or "", body.last_name or "", "manual", lists
    )
    if c is None:
        raise ApiError(422, "validation", "That is not an email address")
    await db.commit()
    return _contact(c)


@router.post(B + "/contacts/import")
async def import_contacts(
    file: UploadFile = File(...),
    list_ids: str = Form(""),
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    ids = [int(x) for x in list_ids.split(",") if x.strip().isdigit()]
    n = await svc.import_csv(
        db, ctx.brand, await file.read(), await svc.lists_for(db, ctx.brand, ids)
    )
    return {"imported": n, "message": f"Imported {n} contact(s)"}


@router.get(B + "/contacts/export")
async def export_contacts(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    return PlainTextResponse(
        await svc.export_csv(db, ctx.brand),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={ctx.brand.slug}-contacts.csv"},
    )


@router.delete(B + "/contacts/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    c = await db.get(Contact, contact_id)
    if not c or c.brand_id != ctx.brand.id:
        raise not_found("No such contact")
    await db.delete(c)
    await db.commit()
    return Response(status_code=204)


# ---- lists ---------------------------------------------------------------------------------
@router.get(B + "/lists", response_model=list[ListOut])
async def lists(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    rows = (
        (
            await db.execute(
                select(ContactList)
                .where(ContactList.brand_id == ctx.brand.id)
                .order_by(ContactList.name)
            )
        )
        .scalars()
        .all()
    )
    return [
        ListOut(id=lst.id, name=lst.name, description=lst.description, contacts=len(lst.contacts))
        for lst in rows
    ]


@router.post(B + "/lists", response_model=ListOut, status_code=201)
async def create_list(
    body: ListIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    lst = ContactList(
        brand_id=ctx.brand.id,
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
    )
    db.add(lst)
    await db.commit()
    return ListOut(id=lst.id, name=lst.name, description=lst.description, contacts=0)


@router.delete(B + "/lists/{list_id}", status_code=204)
async def delete_list(
    list_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    lst = await db.get(ContactList, list_id)
    if not lst or lst.brand_id != ctx.brand.id:
        raise not_found("No such list")
    await db.delete(lst)
    await db.commit()
    return Response(status_code=204)


# ---- email campaigns -------------------------------------------------------------------------
async def _campaign(db: AsyncSession, ctx: deps.BrandCtx, cid: int) -> EmailCampaign:
    c = await db.get(EmailCampaign, cid)
    if not c or c.brand_id != ctx.brand.id:
        raise not_found("No such email campaign")
    return c


async def _email_out(db: AsyncSession, c: EmailCampaign) -> EmailOut:
    recipients = 0
    if c.list_id:
        lst = await db.get(ContactList, c.list_id)
        recipients = sum(1 for x in lst.contacts if x.subscribed) if lst else 0
    sends = (
        (await db.execute(select(EmailSend).where(EmailSend.campaign_id == c.id))).scalars().all()
    )
    stats = {
        "sent": sum(1 for s in sends if s.sent_at),
        "opened": sum(1 for s in sends if s.opened_at),
        "clicked": sum(1 for s in sends if s.clicked_at),
        "failed": sum(1 for s in sends if s.error),
    }
    return EmailOut(
        id=c.id,
        name=c.name,
        subject=c.subject,
        preheader=c.preheader,
        body_html=c.body_html,
        status=c.status,
        list_id=c.list_id,
        scheduled_at=as_utc(c.scheduled_at) if c.scheduled_at else None,
        sent_at=as_utc(c.sent_at) if c.sent_at else None,
        sent_count=c.sent_count,
        recipients=recipients,
        stats=stats,
        created_at=as_utc(c.created_at) if c.created_at else None,
    )


@router.get(B + "/email", response_model=list[EmailOut])
async def list_email(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    rows = (
        (
            await db.execute(
                select(EmailCampaign)
                .where(EmailCampaign.brand_id == ctx.brand.id)
                .order_by(EmailCampaign.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _email_out(db, c) for c in rows]


@router.post(B + "/email", response_model=EmailOut, status_code=201)
async def create_email(
    body: EmailCreate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    if body.list_id is not None and not await svc.lists_for(db, ctx.brand, [body.list_id]):
        raise not_found("No such list in this brand")
    c = EmailCampaign(
        brand_id=ctx.brand.id,
        name=body.name.strip(),
        list_id=body.list_id,
        body_html="<p>Hi {{first_name}},</p><p>…</p>",
    )
    db.add(c)
    await db.commit()
    return await _email_out(db, c)


@router.get(B + "/email/{cid}", response_model=EmailOut)
async def get_email(
    cid: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    return await _email_out(db, await _campaign(db, ctx, cid))


@router.patch(B + "/email/{cid}", response_model=EmailOut)
async def update_email(
    cid: int,
    body: EmailUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    c = await _campaign(db, ctx, cid)
    if c.status in ("sending", "sent"):
        raise ApiError(409, "already_sent", "Sent campaigns can't be edited")
    data = body.model_dump(exclude_unset=True)
    if data.get("list_id") is not None and not await svc.lists_for(
        db, ctx.brand, [data["list_id"]]
    ):
        raise not_found("No such list in this brand")
    for k in ("name", "subject", "preheader", "body_html", "list_id"):
        if k in data:
            setattr(c, k, data[k] if k != "preheader" else (data[k] or None))
    if body.action in ("send", "schedule"):
        if not c.list_id or not c.subject or not (c.body_html or "").strip():
            await db.commit()
            raise ApiError(422, "validation", "Pick a list, add a subject and a body first")
        if body.action == "send":
            c.status, c.scheduled_at = "scheduled", datetime.now(UTC)
            await db.commit()
            await jobs.enqueue("send_email_campaign", c.id)
            return await _email_out(db, c)
        if not body.scheduled_at:
            await db.commit()
            raise ApiError(422, "validation", "Pick a date and time")
        when = (
            body.scheduled_at if body.scheduled_at.tzinfo else body.scheduled_at.replace(tzinfo=UTC)
        )
        c.scheduled_at, c.status = when.astimezone(UTC), "scheduled"
    elif body.action == "unschedule":
        c.status = "draft"
    await db.commit()
    return await _email_out(db, c)


@router.post(B + "/email/{cid}/ai")
async def email_ai(
    cid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    await _campaign(db, ctx, cid)
    try:
        draft = await ContentAI().email(ctx.brand, str(body.get("brief", "")))
    except AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e))
    return draft.model_dump()


@router.post(B + "/email/{cid}/test")
async def email_test(
    cid: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)
):
    from spark.config import get_settings
    from spark.services.email import get_sender
    from spark.services.email import render as render_email

    c = await _campaign(db, ctx, cid)
    fake = Contact(
        brand_id=ctx.brand.id,
        email=ctx.user.email,
        first_name=ctx.user.name,
        unsubscribe_token="test",
    )
    send = EmailSend(campaign_id=c.id, contact_id=0, token="test")
    await get_sender().send(
        ctx.user.email, f"[TEST] {c.subject}", render_email(c, ctx.brand, fake, send)
    )
    return {"message": f"Test sent to {ctx.user.email} (backend: {get_settings().email_backend})"}


@router.delete(B + "/email/{cid}", status_code=204)
async def delete_email(
    cid: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)
):
    c = await _campaign(db, ctx, cid)
    await db.delete(c)
    await db.commit()
    return Response(status_code=204)


__all__ = ["router", "func"]
