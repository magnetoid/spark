"""The inbox: comments, messages, reviews and mentions, triage, replies, saved replies and rules."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    Actor,
    AssignIn,
    InboxAccount,
    InboxCounts,
    InboxItemOut,
    InboxPage,
    InboxRuleIn,
    InboxRuleOut,
    InboxRuleUpdate,
    InboxStatusIn,
    InboxSyncOut,
    InboxThreadOut,
    ItemLikeIn,
    ItemReplyIn,
    SavedReplyIn,
    SavedReplyOut,
    SavedReplyUpdate,
    SuggestionsOut,
)
from spark.db import get_db
from spark.models import InboxItem, InboxRule, SavedReply, SocialAccount, User
from spark.platforms.base import PlatformError
from spark.platforms.zernio import ZernioAdapter
from spark.services import access, activity, events
from spark.services import ai as ai_svc
from spark.services import inbox as svc
from spark.services.publisher import as_utc

router = APIRouter(prefix="/brands/{brand_id}/inbox", tags=["inbox"])


def _acc(a: SocialAccount) -> InboxAccount:
    return InboxAccount(
        id=a.id,
        external_id=a.external_id,
        platform=a.platform,
        handle=a.handle,
        avatar=a.avatar_url,
    )


def _out(
    it: InboxItem, accounts: dict[int, SocialAccount], rules: dict[int, InboxRule]
) -> InboxItemOut:
    a = accounts.get(it.account_id)
    rule = rules.get(it.draft_rule_id) if it.draft_rule_id else None
    return InboxItemOut(
        id=it.id,
        kind=it.kind,
        direction=it.direction,
        status=it.status,
        external_id=it.external_id,
        thread_id=it.thread_id,
        parent_external_id=it.parent_external_id,
        account=_acc(a)
        if a
        else InboxAccount(id=it.account_id, external_id="", platform="", handle="?", avatar=None),
        author={"name": it.author_name, "handle": it.author_handle, "picture": it.author_picture},
        text=it.text,
        rating=it.rating,
        permalink=it.permalink,
        post=it.post or {},
        attachments=it.attachments or [],
        received_at=as_utc(it.received_at),
        sentiment=it.sentiment,
        intent=it.intent,
        suggestions=list(it.suggestions or []),
        draft_reply=it.draft_reply,
        draft_rule={"id": rule.id, "name": rule.name} if rule else None,
        assignee=Actor(id=it.assignee.id, name=it.assignee.name) if it.assignee else None,
        replied_at=as_utc(it.replied_at),
        reply_text=it.reply_text,
    )


async def _ctx_maps(
    db: AsyncSession, brand_id: int
) -> tuple[dict[int, SocialAccount], dict[int, InboxRule]]:
    accounts = {
        a.id: a
        for a in (
            await db.execute(select(SocialAccount).where(SocialAccount.brand_id == brand_id))
        ).scalars()
    }
    rules = {
        r.id: r
        for r in (
            await db.execute(select(InboxRule).where(InboxRule.brand_id == brand_id))
        ).scalars()
    }
    return accounts, rules


async def _item(db: AsyncSession, ctx: deps.BrandCtx, item_id: int) -> InboxItem:
    it = await db.get(InboxItem, item_id)
    if it is None or it.brand_id != ctx.brand.id:
        raise not_found("No such inbox item")
    return it


# ---- listing ---------------------------------------------------------------------------------
@router.get("", response_model=InboxPage)
async def list_items(
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
    status: str = "open",
    kind: str | None = None,
    account: int | None = None,
    assignee: str | None = None,
    sentiment: str | None = None,
    intent: str | None = None,
    q: str | None = None,
    has_draft: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = 0,
):
    stmt = select(InboxItem).where(InboxItem.brand_id == ctx.brand.id)
    if status != "all":
        stmt = stmt.where(InboxItem.status == status, InboxItem.direction == "incoming")
    if kind:
        stmt = stmt.where(InboxItem.kind == kind)
    if account:
        stmt = stmt.where(InboxItem.account_id == account)
    if assignee == "me":
        stmt = stmt.where(InboxItem.assignee_id == ctx.user.id)
    elif assignee == "none":
        stmt = stmt.where(InboxItem.assignee_id.is_(None))
    elif assignee and assignee.isdigit():
        stmt = stmt.where(InboxItem.assignee_id == int(assignee))
    if sentiment:
        stmt = stmt.where(InboxItem.sentiment == sentiment)
    if intent:
        stmt = stmt.where(InboxItem.intent == intent)
    if has_draft:
        stmt = stmt.where(InboxItem.draft_reply.is_not(None))
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                InboxItem.text.ilike(needle),
                InboxItem.author_name.ilike(needle),
                InboxItem.author_handle.ilike(needle),
            )
        )
    rows = (
        (
            await db.execute(
                stmt.order_by(InboxItem.received_at.desc(), InboxItem.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    accounts, rules = await _ctx_maps(db, ctx.brand.id)
    zernio = [a for a in accounts.values() if a.provider == "zernio"]
    return InboxPage(
        items=[_out(it, accounts, rules) for it in rows],
        counts=InboxCounts(**await svc.counts(db, ctx.brand.id)),
        accounts=[_acc(a) for a in zernio],
        ready=bool(zernio) and ZernioAdapter().is_configured(),
    )


@router.get("/items/{item_id}", response_model=InboxThreadOut)
async def get_item(
    item_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    it = await _item(db, ctx, item_id)
    accounts, rules = await _ctx_maps(db, ctx.brand.id)
    return InboxThreadOut(
        item=_out(it, accounts, rules),
        thread=[_out(t, accounts, rules) for t in await svc.thread_of(db, it)],
    )


# ---- actions -----------------------------------------------------------------------------------
@router.post("/items/{item_id}/reply", response_model=InboxItemOut)
async def reply_item(
    item_id: int,
    body: ItemReplyIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    it = await _item(db, ctx, item_id)
    try:
        await svc.reply(db, ctx.brand, it, body.text, ctx.user)
    except svc.CannotReply as e:
        raise ApiError(502 if "failed" in str(e).lower() else 409, "cannot_reply", str(e)) from e
    if body.saved_reply_id:
        sr = await db.get(SavedReply, body.saved_reply_id)
        if sr and sr.brand_id == ctx.brand.id:
            sr.uses = (sr.uses or 0) + 1
            await db.commit()
    accounts, rules = await _ctx_maps(db, ctx.brand.id)
    return _out(it, accounts, rules)


@router.post("/items/{item_id}/status", response_model=InboxItemOut)
async def set_status(
    item_id: int,
    body: InboxStatusIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    it = await _item(db, ctx, item_id)
    it.status = body.status
    if body.status != "open":
        it.draft_reply, it.draft_rule_id = None, None
    await db.commit()
    await events.publish("inbox", ctx.brand.id)
    accounts, rules = await _ctx_maps(db, ctx.brand.id)
    return _out(it, accounts, rules)


@router.post("/items/{item_id}/assign", response_model=InboxItemOut)
async def assign(
    item_id: int,
    body: AssignIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    it = await _item(db, ctx, item_id)
    if body.user_id is not None:
        u = await db.get(User, body.user_id)
        if u is None or await access.role_for(db, u, ctx.brand.id) is None:
            raise not_found("That person is not a member of this brand")
    it.assignee_id = body.user_id
    await db.commit()
    await db.refresh(it, ["assignee"])
    await events.publish("inbox", ctx.brand.id)
    accounts, rules = await _ctx_maps(db, ctx.brand.id)
    return _out(it, accounts, rules)


@router.post("/items/{item_id}/suggest", response_model=SuggestionsOut)
async def suggest_replies(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    it = await _item(db, ctx, item_id)
    try:
        return SuggestionsOut(suggestions=await svc.suggest(db, ctx.brand, it))
    except ai_svc.AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e)) from e


@router.post("/items/{item_id}/like")
async def like_item(
    item_id: int,
    body: ItemLikeIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    it = await _item(db, ctx, item_id)
    if it.kind != "comment":
        raise ApiError(422, "not_a_comment", "Only comments can be liked")
    acc = await db.get(SocialAccount, it.account_id)
    if acc is None:
        raise ApiError(409, "no_channel", "This channel is no longer connected")
    try:
        await ZernioAdapter().like_comment(
            it.thread_id or "", it.external_id, acc.external_id, body.liked
        )
    except PlatformError as e:
        raise ApiError(502, "zernio", str(e)) from e
    return {"liked": body.liked}


@router.post("/sync", response_model=InboxSyncOut)
async def sync_now(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)
):
    out = await svc.sync_brand(db, ctx.brand)
    return InboxSyncOut(**out, synced_at=datetime.now(UTC))


# ---- saved replies ----------------------------------------------------------------------------------
def _sr(s: SavedReply) -> SavedReplyOut:
    return SavedReplyOut(id=s.id, title=s.title, body=s.body, shortcut=s.shortcut, uses=s.uses or 0)


@router.get("/saved-replies", response_model=list[SavedReplyOut])
async def saved_replies(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    rows = (
        (
            await db.execute(
                select(SavedReply)
                .where(SavedReply.brand_id == ctx.brand.id)
                .order_by(SavedReply.title)
            )
        )
        .scalars()
        .all()
    )
    return [_sr(s) for s in rows]


@router.post("/saved-replies", response_model=SavedReplyOut, status_code=201)
async def create_saved_reply(
    body: SavedReplyIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    s = SavedReply(
        brand_id=ctx.brand.id,
        title=body.title.strip(),
        body=body.body.strip(),
        shortcut=(body.shortcut or "").strip().lower() or None,
    )
    db.add(s)
    await db.commit()
    return _sr(s)


@router.patch("/saved-replies/{reply_id}", response_model=SavedReplyOut)
async def update_saved_reply(
    reply_id: int,
    body: SavedReplyUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    s = await db.get(SavedReply, reply_id)
    if s is None or s.brand_id != ctx.brand.id:
        raise not_found("No such saved reply")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(
            s,
            k,
            (v.strip() if isinstance(v, str) else v)
            if k != "shortcut"
            else ((v or "").strip().lower() or None),
        )
    await db.commit()
    return _sr(s)


@router.delete("/saved-replies/{reply_id}", status_code=204)
async def delete_saved_reply(
    reply_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    s = await db.get(SavedReply, reply_id)
    if s is None or s.brand_id != ctx.brand.id:
        raise not_found("No such saved reply")
    await db.delete(s)
    await db.commit()
    return Response(status_code=204)


# ---- rules ---------------------------------------------------------------------------------------------
def _rule(r: InboxRule) -> InboxRuleOut:
    return InboxRuleOut(
        id=r.id,
        name=r.name,
        enabled=r.enabled,
        kinds=list(r.kinds or []),
        platforms=list(r.platforms or []),
        keywords=list(r.keywords or []),
        intents=list(r.intents or []),
        sentiments=list(r.sentiments or []),
        saved_reply_id=r.saved_reply_id,
        reply_text=r.reply_text,
        assign_to_id=r.assign_to_id,
        hits=r.hits or 0,
    )


@router.get("/rules", response_model=list[InboxRuleOut])
async def rules(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    rows = (
        (
            await db.execute(
                select(InboxRule).where(InboxRule.brand_id == ctx.brand.id).order_by(InboxRule.id)
            )
        )
        .scalars()
        .all()
    )
    return [_rule(r) for r in rows]


@router.post("/rules", response_model=InboxRuleOut, status_code=201)
async def create_rule(
    body: InboxRuleIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.owner_brand),
):
    if not (body.saved_reply_id or (body.reply_text or "").strip() or body.assign_to_id):
        raise ApiError(
            422, "no_action", "A rule prepares a reply or assigns someone; pick at least one"
        )
    if body.saved_reply_id is not None:
        sr = await db.get(SavedReply, body.saved_reply_id)
        if sr is None or sr.brand_id != ctx.brand.id:
            raise not_found("No such saved reply in this brand")
    r = InboxRule(brand_id=ctx.brand.id, **body.model_dump())
    r.name = r.name.strip()
    db.add(r)
    await db.flush()
    activity.record(db, ctx.brand.id, ctx.user, "added", "inbox_rule", r.id, r.name)
    await db.commit()
    return _rule(r)


@router.patch("/rules/{rule_id}", response_model=InboxRuleOut)
async def update_rule(
    rule_id: int,
    body: InboxRuleUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.owner_brand),
):
    r = await db.get(InboxRule, rule_id)
    if r is None or r.brand_id != ctx.brand.id:
        raise not_found("No such rule")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    await db.commit()
    return _rule(r)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.owner_brand)
):
    r = await db.get(InboxRule, rule_id)
    if r is None or r.brand_id != ctx.brand.id:
        raise not_found("No such rule")
    await db.delete(r)
    await db.commit()
    return Response(status_code=204)
