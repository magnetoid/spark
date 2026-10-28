"""Engagement inbox (Buffer's Community): comments on your posts across channels,
answered from one place. Backed by Zernio's inbox API, so it covers the
accounts connected through Zernio."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.models import Brand, SocialAccount, User
from spark.platforms import PlatformError
from spark.platforms.zernio import ZernioAdapter
from spark.web.deps import current_user, editor, flash, render, require_brand, templates

router = APIRouter()


async def _zernio_accounts(db: AsyncSession, brand: Brand) -> list[SocialAccount]:
    return (await db.execute(
        select(SocialAccount).where(SocialAccount.brand_id == brand.id, SocialAccount.provider == "zernio",
                                    SocialAccount.is_active.is_(True)).order_by(SocialAccount.platform)
    )).scalars().all()


def _owned(accounts: list[SocialAccount], account_id: str) -> SocialAccount:
    for a in accounts:
        if a.external_id == account_id:
            return a
    raise HTTPException(404, "That channel isn't connected to this brand")


@router.get("/inbox")
async def inbox(request: Request, account: str | None = None, days: int = 30,
                db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                brand: Brand = Depends(require_brand)):
    accounts = await _zernio_accounts(db, brand)
    adapter = ZernioAdapter()
    rows, error = [], None
    if accounts and adapter.is_configured():
        wanted = {a.external_id for a in accounts if not account or a.external_id == account}
        since = (datetime.now(UTC) - timedelta(days=days if days in (7, 30, 90) else 30)).date().isoformat()
        try:
            rows = await adapter.commented_posts(wanted, since=since)
        except PlatformError as e:
            error = str(e)
    by_id = {a.external_id: a for a in accounts}
    for r in rows:
        r["account"] = by_id.get(r.get("accountId"))
    return await render(request, "inbox.html", db, user, brand, rows=rows, accounts=accounts,
                        account=account, days=days, error=error, zernio_ready=adapter.is_configured())


@router.get("/inbox/{post_id}/comments")
async def comments(post_id: str, request: Request, account: str, cursor: str | None = None,
                   db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                   brand: Brand = Depends(require_brand)):
    """HTMX partial: the comment thread for one post."""
    acc = _owned(await _zernio_accounts(db, brand), account)
    try:
        data = await ZernioAdapter().post_comments(post_id, account, cursor)
    except PlatformError as e:
        return HTMLResponse(f'<div class="alert" data-variant="destructive"><h2>{e}</h2></div>')
    return templates.TemplateResponse(request, "partials/inbox_comments.html", {
        "post_id": post_id, "account": acc, "comments": data.get("comments", []),
        "pagination": data.get("pagination") or {}, "user": user,
    })


@router.post("/inbox/{post_id}/reply")
async def reply(post_id: str, request: Request, account: str = Form(...), message: str = Form(...),
                comment_id: str = Form(""), root_uri: str = Form(""), root_cid: str = Form(""),
                parent_cid: str = Form(""), db: AsyncSession = Depends(get_db),
                user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    acc = _owned(await _zernio_accounts(db, brand), account)
    message = message.strip()
    if not message:
        raise HTTPException(400, "Write a reply first")
    try:
        await ZernioAdapter().reply(post_id, account, message, comment_id or None,
                                    bluesky={"rootUri": root_uri, "rootCid": root_cid, "parentCid": parent_cid}
                                    if acc.platform == "bluesky" else None)
    except PlatformError as e:
        if request.headers.get("HX-Request"):
            return HTMLResponse(f'<div class="alert" data-variant="destructive"><h2>Reply failed: {e}</h2></div>')
        flash(request, f"Reply failed: {e}", "error")
        return RedirectResponse("/inbox", 303)
    if request.headers.get("HX-Request"):
        # Re-render the thread so the new reply shows up
        data = await ZernioAdapter().post_comments(post_id, account)
        return templates.TemplateResponse(request, "partials/inbox_comments.html", {
            "post_id": post_id, "account": acc, "comments": data.get("comments", []),
            "pagination": data.get("pagination") or {}, "user": user, "sent": True,
        })
    flash(request, "Reply posted")
    return RedirectResponse("/inbox", 303)


@router.post("/inbox/{post_id}/like")
async def like(post_id: str, request: Request, account: str = Form(...), comment_id: str = Form(...),
               liked: bool = Form(False), db: AsyncSession = Depends(get_db), user: User = Depends(editor),
               brand: Brand = Depends(require_brand)):
    _owned(await _zernio_accounts(db, brand), account)
    try:
        await ZernioAdapter().like_comment(post_id, comment_id, account, liked)
    except PlatformError as e:
        return HTMLResponse(f'<span class="text-xs text-brick">{e}</span>')
    return HTMLResponse(
        f'<button class="btn" data-variant="ghost" data-size="xs" hx-post="/inbox/{post_id}/like" '
        f'hx-vals=\'{{"account":"{account}","comment_id":"{comment_id}","liked":{"false" if liked else "true"}}}\' '
        f'hx-swap="outerHTML">{"♥ Liked" if not liked else "♡ Like"}</button>'
    )
