"""Working together on a brand: members, the activity log, post comments and review links."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    ActivityOut,
    ActivityPage,
    Actor,
    CommentIn,
    CommentOut,
    MemberIn,
    MemberOut,
    MemberUpdate,
    ReviewAction,
    ReviewActionOut,
    ReviewChannel,
    ReviewPage,
    ReviewPost,
    ShareLinkCreated,
    ShareLinkIn,
    ShareLinkOut,
)
from spark.config import get_settings
from spark.db import get_db
from spark.models import (
    Brand,
    BrandMember,
    Media,
    Post,
    PostComment,
    PostStatus,
    PostTarget,
    Role,
    ShareLink,
    User,
)
from spark.security import hash_password
from spark.services import access, activity, events, scheduler
from spark.services import posts as svc
from spark.services.publisher import as_utc

router = APIRouter(prefix="/brands/{brand_id}", tags=["collaboration"])
public = APIRouter(prefix="/public/review", tags=["review"])


# ---- members -------------------------------------------------------------------------------
def _member_out(m: BrandMember) -> MemberOut:
    """A workspace owner is an owner everywhere, whatever their row says, so the row shows as fixed."""
    wo = m.user.role == Role.owner
    return MemberOut(
        id=m.id, user_id=m.user_id, name=m.user.name, email=m.user.email, role="owner" if wo else m.role,
        is_active=m.user.is_active, workspace_owner=wo,
    )


async def _members(db: AsyncSession, brand_id: int) -> list[MemberOut]:
    """Explicit members plus the workspace owners, who see every brand without a membership row."""
    rows = (
        await db.execute(select(BrandMember).where(BrandMember.brand_id == brand_id).options(selectinload(BrandMember.user)))
    ).scalars().all()
    out = [_member_out(m) for m in rows]
    seen = {m.user_id for m in rows}
    owners = (await db.execute(select(User).where(User.role == Role.owner, User.id.not_in(seen)))).scalars().all()
    out += [
        MemberOut(id=None, user_id=u.id, name=u.name, email=u.email, role="owner", is_active=u.is_active, workspace_owner=True)
        for u in owners
    ]
    return sorted(out, key=lambda m: (m.role != "owner", m.name.lower()))


@router.get("/members", response_model=list[MemberOut])
async def list_members(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    members = await _members(db, ctx.brand.id)
    if not ctx.can_manage():  # names for everyone, addresses for owners
        for m in members:
            m.email = ""
    return members


@router.post("/members", response_model=MemberOut, status_code=201)
async def add_member(
    body: MemberIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.owner_brand),
):
    email = body.email.lower()
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        if not (body.name and body.password):
            raise not_found("No user with that email. Add a name and a password to create one.")
        user = User(
            email=email,
            name=body.name.strip(),
            role=Role.viewer,  # brand roles grant everything else
            password_hash=hash_password(body.password),
        )
        db.add(user)
        await db.flush()
    existing = await db.scalar(
        select(BrandMember).where(
            BrandMember.brand_id == ctx.brand.id, BrandMember.user_id == user.id
        )
    )
    if existing is not None:
        raise ApiError(
            409, "already_member", f"{user.name} is already a member of {ctx.brand.name}"
        )
    m = await access.add_member(db, ctx.brand, user, body.role)
    activity.record(
        db,
        ctx.brand.id,
        ctx.user,
        "added",
        "member",
        user.id,
        f"{user.name} as {body.role}",
        {"role": body.role},
    )
    await db.commit()
    await db.refresh(m, ["user"])
    return _member_out(m)


@router.patch("/members/{user_id}", response_model=MemberOut)
async def update_member(
    user_id: int,
    body: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.owner_brand),
):
    m = await db.scalar(
        select(BrandMember)
        .where(BrandMember.brand_id == ctx.brand.id, BrandMember.user_id == user_id)
        .options(selectinload(BrandMember.user))
    )
    if m is None:
        raise not_found("Not a member of this brand")
    m.role = body.role
    activity.record(
        db,
        ctx.brand.id,
        ctx.user,
        "changed role of",
        "member",
        user_id,
        f"{m.user.name} to {body.role}",
        {"role": body.role},
    )
    await db.commit()
    return _member_out(m)


@router.delete("/members/{user_id}", status_code=204)
async def remove_member(
    user_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.owner_brand)
):
    m = await db.scalar(
        select(BrandMember)
        .where(BrandMember.brand_id == ctx.brand.id, BrandMember.user_id == user_id)
        .options(selectinload(BrandMember.user))
    )
    if m is None:
        raise not_found("Not a member of this brand")
    activity.record(db, ctx.brand.id, ctx.user, "removed", "member", user_id, m.user.name)
    await db.delete(m)
    await db.commit()
    return Response(status_code=204)


# ---- activity ---------------------------------------------------------------------------------
@router.get("/activity", response_model=ActivityPage)
async def list_activity(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
):
    rows = await activity.recent(db, ctx.brand.id, min(limit, 200), offset)
    return ActivityPage(
        items=[
            ActivityOut(
                id=a.id,
                actor=Actor(id=a.actor_id, name=a.actor_name),
                verb=a.verb,
                object_type=a.object_type,
                object_id=a.object_id,
                summary=a.summary,
                data=a.data or {},
                created_at=as_utc(a.created_at),
            )
            for a in rows
        ]
    )


# ---- comments ----------------------------------------------------------------------------------
def _comment_out(c: PostComment) -> CommentOut:
    name = c.author.name if c.author else (c.guest_name or "Guest")
    return CommentOut(
        id=c.id,
        author=Actor(id=c.author_id, name=name),
        body=c.body,
        kind=c.kind,
        created_at=as_utc(c.created_at),
    )


async def _brand_post(db: AsyncSession, brand_id: int, post_id: int) -> Post:
    post = await db.scalar(
        select(Post)
        .where(Post.id == post_id, Post.brand_id == brand_id)
        .options(
            selectinload(Post.targets).selectinload(PostTarget.account)
        )
    )
    if post is None:
        raise not_found("No such post")
    return post


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
async def list_comments(
    post_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    await _brand_post(db, ctx.brand.id, post_id)
    rows = (
        (
            await db.execute(
                select(PostComment)
                .where(PostComment.post_id == post_id)
                .order_by(PostComment.created_at, PostComment.id)
            )
        )
        .scalars()
        .all()
    )
    return [_comment_out(c) for c in rows]


@router.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    post_id: int,
    body: CommentIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
):
    text = body.body.strip()
    if not text:
        raise ApiError(422, "empty", "Write something first")
    post = await _brand_post(db, ctx.brand.id, post_id)
    c = PostComment(post_id=post.id, author_id=ctx.user.id, body=text, kind="comment")
    db.add(c)
    activity.record(db, ctx.brand.id, ctx.user, "commented on", "post", post.id, text[:120])
    await db.commit()
    await db.refresh(c, ["author"])
    await events.publish("posts", ctx.brand.id, ids=[post.id])
    return _comment_out(c)


# ---- share links ------------------------------------------------------------------------------
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _link_out(link: ShareLink) -> ShareLinkOut:
    scope = link.scope or {}
    return ShareLinkOut(
        id=link.id,
        kind=link.kind,
        prefix=link.prefix,
        url_hint=f"{get_settings().base_url}/review/{link.prefix}…",
        expires_at=as_utc(link.expires_at),
        created_at=as_utc(link.created_at),
        last_used_at=as_utc(link.last_used_at),
        posts=len(scope["post_ids"]) if scope.get("post_ids") else None,
    )


@router.get("/share-links", response_model=list[ShareLinkOut])
async def list_share_links(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)
):
    rows = (
        (
            await db.execute(
                select(ShareLink)
                .where(ShareLink.brand_id == ctx.brand.id, ShareLink.revoked_at.is_(None))
                .order_by(ShareLink.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_link_out(l) for l in rows]


@router.post("/share-links", response_model=ShareLinkCreated, status_code=201)
async def create_share_link(
    body: ShareLinkIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    token = secrets.token_urlsafe(24)
    link = ShareLink(
        brand_id=ctx.brand.id,
        token_hash=_hash(token),
        prefix=token[:8],
        kind="approval",
        scope={"post_ids": body.post_ids} if body.post_ids else {},
        created_by=ctx.user.id,
        expires_at=datetime.now(UTC) + timedelta(days=body.days),
    )
    db.add(link)
    await db.flush()
    activity.record(
        db,
        ctx.brand.id,
        ctx.user,
        "created",
        "share_link",
        link.id,
        f"review link, {body.days} days",
    )
    await db.commit()
    out = _link_out(link)
    return ShareLinkCreated(
        **out.model_dump(), token=token, url=f"{get_settings().base_url}/review/{token}"
    )


@router.delete("/share-links/{link_id}", status_code=204)
async def revoke_share_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    link = await db.get(ShareLink, link_id)
    if link is None or link.brand_id != ctx.brand.id:
        raise not_found("No such link")
    link.revoked_at = datetime.now(UTC)
    activity.record(db, ctx.brand.id, ctx.user, "revoked", "share_link", link.id, "review link")
    await db.commit()
    return Response(status_code=204)


# ---- the public review page (no login) ---------------------------------------------------------
async def _link(db: AsyncSession, token: str) -> tuple[ShareLink, Brand]:
    link = await db.scalar(select(ShareLink).where(ShareLink.token_hash == _hash(token)))
    now = datetime.now(UTC)
    if (
        link is None
        or link.revoked_at is not None
        or (link.expires_at and as_utc(link.expires_at) < now)
    ):
        raise not_found("This review link is no longer valid")
    link.last_used_at = now
    return link, await db.get(Brand, link.brand_id)


async def _review_posts(db: AsyncSession, link: ShareLink) -> list[Post]:
    q = (
        select(Post)
        .where(Post.brand_id == link.brand_id, Post.is_autosave.is_(False))
        .options(
            selectinload(Post.targets).selectinload(PostTarget.account)
        )
    )
    ids = (link.scope or {}).get("post_ids")
    if ids:
        q = q.where(Post.id.in_(ids))
    else:
        # everything that waits for approval, what is already scheduled ahead (so the client sees the
        # plan), and the posts this link sent back for changes, so the reviewer sees their note landed
        now = datetime.now(UTC)
        asked = select(PostComment.post_id).where(PostComment.share_link_id == link.id)
        q = q.where(
            (Post.status == PostStatus.pending_approval)
            | ((Post.status == PostStatus.scheduled) & (Post.scheduled_at >= now))
            | Post.id.in_(asked)
        )
    rows = (await db.execute(q)).scalars().all()
    order = {PostStatus.pending_approval: 0, PostStatus.scheduled: 1, PostStatus.draft: 2}
    return sorted(
        rows,
        key=lambda p: (
            order.get(p.status, 3),
            as_utc(p.scheduled_at) or datetime.max.replace(tzinfo=UTC),
            p.id,
        ),
    )


async def _review_post(db: AsyncSession, p: Post) -> ReviewPost:
    comments = (
        (
            await db.execute(
                select(PostComment)
                .where(PostComment.post_id == p.id)
                .order_by(PostComment.created_at, PostComment.id)
            )
        )
        .scalars()
        .all()
    )
    media = (await db.execute(select(Media).where(Media.id.in_(p.media_ids), Media.brand_id == p.brand_id))).scalars().all() if p.media_ids else []
    return ReviewPost(
        id=p.id,
        content=p.content,
        link=p.link,
        status=p.status.value,
        scheduled_at=as_utc(p.scheduled_at),
        media=[f"{get_settings().base_url}{m.url}" for m in media],
        channels=[
            ReviewChannel(platform=t.account.platform, handle=t.account.handle, text=t.content_override or p.content,
                          first_comment=t.first_comment or None, thread=list(t.thread or []), post_type=t.post_type or "post")
            for t in p.targets
            if t.account
        ],
        comments=[_comment_out(c) for c in comments],
    )


@public.get("/{token}", response_model=ReviewPage)
async def review_page(token: str, db: AsyncSession = Depends(get_db)):
    link, brand = await _link(db, token)
    posts = await _review_posts(db, link)
    await db.commit()
    return ReviewPage(
        brand={"name": brand.name, "color": brand.color or "", "slug": brand.slug},
        timezone=brand.timezone,
        expires_at=as_utc(link.expires_at),
        posts=[await _review_post(db, p) for p in posts],
    )


async def _reviewable(db: AsyncSession, link: ShareLink, post_id: int) -> Post:
    """Only posts the review page itself shows can be acted on through the link."""
    for p in await _review_posts(db, link):
        if p.id == post_id:
            return p
    raise not_found("No such post")


@public.post("/{token}/posts/{post_id}/request-changes", response_model=ReviewActionOut)
async def review_request_changes(
    token: str, post_id: int, body: ReviewAction, db: AsyncSession = Depends(get_db)
):
    link, brand = await _link(db, token)
    post = await _reviewable(db, link, post_id)
    text = (body.body or "").strip()
    if not text:
        raise ApiError(422, "empty", "Say what should change")
    if post.status in (PostStatus.pending_approval, PostStatus.scheduled):
        scheduler.unschedule(post)
    db.add(
        PostComment(
            post_id=post.id,
            guest_name=body.name.strip(),
            share_link_id=link.id,
            body=text,
            kind="change_request",
        )
    )
    activity.record(
        db,
        brand.id,
        None,
        "requested changes",
        "post",
        post.id,
        text[:120],
        actor_name=body.name.strip(),
    )
    await db.commit()
    await events.publish("posts", brand.id, ids=[post.id])
    return ReviewActionOut(message="Thanks, the team will see your note", status=post.status.value)


@public.post("/{token}/posts/{post_id}/approve", response_model=ReviewActionOut)
async def review_approve(
    token: str, post_id: int, body: ReviewAction, db: AsyncSession = Depends(get_db)
):
    link, brand = await _link(db, token)
    post = await _reviewable(db, link, post_id)
    if post.status != PostStatus.pending_approval:
        raise ApiError(409, "not_pending", "This post is not waiting for approval")
    scheduler.approve(post)
    note = (body.body or "").strip()
    db.add(
        PostComment(
            post_id=post.id,
            guest_name=body.name.strip(),
            share_link_id=link.id,
            body=note or "Approved",
            kind="approval",
        )
    )
    activity.record(
        db,
        brand.id,
        None,
        "approved",
        "post",
        post.id,
        post.content[:120],
        actor_name=body.name.strip(),
    )
    await db.commit()
    await svc.enqueue_due(post)
    await events.publish("posts", brand.id, ids=[post.id])
    return ReviewActionOut(message="Approved", status=post.status.value)
