"""Spark as an MCP server (Streamable HTTP at /mcp).

Clients authenticate with a personal token from Settings → Connectors → MCP access
(`Authorization: Bearer spk_…`). Every tool runs as that user with their role: viewers
read, editors draft and schedule, owners also approve. Posts created here behave exactly
like posts from the composer: same validation, queue slots, approvals and publishing.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from starlette.routing import Route

from spark.config import get_settings
from spark.db import SessionLocal
from spark.models import Brand, Idea, Post, PostStatus, PostTarget, SocialAccount, User
from spark.services import scheduler

log = logging.getLogger(__name__)

INSTRUCTIONS = """Spark is a social media scheduler for a marketing team with one or more brands.
Start with list_brands to see the brands and your role, then list_channels for a brand's accounts.
create_post drafts, queues (next free posting slot), schedules or publishes a post to one or more
channels. Times you pass without a timezone are read in the brand's timezone. Posts by editors may
wait for an owner's approval when the brand requires it. Prefer drafts or the queue unless the user
explicitly asks to publish now."""

server = MCPServer(name="Spark", title="Spark social scheduler", instructions=INSTRUCTIONS,
                   website_url="https://github.com/magnetoid/spark", version="1.0")

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
PUBLISH = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)

BrandArg = Annotated[str | None, Field(description="Brand id, slug or name. Optional when there is only one brand.")]


# ---- auth + helpers ------------------------------------------------------------------------
def _bearer(headers) -> str | None:
    value = (headers or {}).get("authorization") or ""
    return value[7:].strip() if value.lower().startswith("bearer ") else None


class _Session:
    """`async with _Session(ctx) as (db, user)` — a DB session and the token's user."""

    def __init__(self, ctx: Context):
        self.ctx = ctx

    async def __aenter__(self) -> tuple[AsyncSession, User]:
        from spark.web.connectors import user_for_token

        self.db = SessionLocal()
        db = await self.db.__aenter__()
        user = await user_for_token(db, _bearer(self.ctx.headers))
        if user is None:
            await self.db.__aexit__(None, None, None)
            raise ToolError("Invalid or revoked token. Create one under Settings → Connectors → MCP access.")
        return db, user

    async def __aexit__(self, *exc):
        await self.db.__aexit__(*exc)


def _need(user: User, level: Literal["edit", "approve"]) -> None:
    if level == "edit" and not user.can_edit():
        raise ToolError("Your role is viewer: you can read but not change posts.")
    if level == "approve" and not user.can_approve():
        raise ToolError("Only owners can approve posts.")


async def _brand(db: AsyncSession, ref: str | None) -> Brand:
    brands = (await db.execute(select(Brand).order_by(Brand.id))).scalars().all()
    if not brands:
        raise ToolError("No brands yet. Create one in Spark first.")
    if not ref:
        if len(brands) == 1:
            return brands[0]
        raise ToolError("There are several brands; pass brand= one of: " + ", ".join(b.slug for b in brands))
    r = str(ref).strip().lower()
    for b in brands:
        if r in (str(b.id), b.slug.lower(), b.name.lower()):
            return b
    raise ToolError(f"No brand {ref!r}. Brands: " + ", ".join(b.slug for b in brands))


def _tz(brand: Brand) -> ZoneInfo:
    return ZoneInfo(brand.timezone or "UTC")


def _iso(dt: datetime | None, brand: Brand) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_tz(brand)).isoformat(timespec="minutes")


def _parse_when(raw: str, brand: Brand) -> datetime:
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ToolError(f"Could not read {raw!r} as a date and time; use ISO 8601 like 2026-11-03T09:30")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz(brand))
    dt = dt.astimezone(UTC)
    if dt < datetime.now(UTC):
        raise ToolError("That time is in the past. Use action='now' to publish immediately.")
    return dt


def _url(path: str) -> str:
    return get_settings().base_url.rstrip("/") + path


def _account(a: SocialAccount) -> dict:
    return {"id": a.id, "platform": a.platform, "handle": a.handle, "name": a.display_name,
            "via": a.provider, "active": a.is_active, "problem": a.last_error}


def _post(p: Post, brand: Brand) -> dict:
    return {
        "id": p.id, "status": p.status.value, "content": p.content, "link": p.link,
        "scheduled_at": _iso(p.scheduled_at, brand), "timezone": brand.timezone,
        "channels": [{"account_id": t.account_id, "handle": t.account.handle, "platform": t.account.platform,
                      "status": t.status.value, "published_url": t.remote_url, "error": t.error,
                      "text": t.content_override or None} for t in p.targets],
        "edit_url": _url(f"/posts/{p.id}/edit"),
    }


async def _accounts(db: AsyncSession, brand: Brand) -> list[SocialAccount]:
    return (await db.execute(select(SocialAccount).where(SocialAccount.brand_id == brand.id)
                             .order_by(SocialAccount.platform, SocialAccount.handle))).scalars().all()


async def _pick_channels(db: AsyncSession, brand: Brand, refs: list[str] | None) -> list[SocialAccount]:
    accounts = await _accounts(db, brand)
    active = [a for a in accounts if a.is_active]
    if not refs:
        if not active:
            raise ToolError("This brand has no active channels. Connect one under Social accounts.")
        return active
    picked: list[SocialAccount] = []
    for ref in refs:
        r = str(ref).strip().lower().lstrip("@")
        hits = [a for a in accounts if r in (str(a.id), a.handle.lower().lstrip("@"), a.platform.lower())]
        if not hits:
            raise ToolError(f"No channel {ref!r}. Channels: " + ", ".join(f"{a.id}={a.handle} ({a.platform})" for a in accounts))
        for a in hits:
            if not a.is_active:
                raise ToolError(f"{a.handle} ({a.platform}) is paused: {a.last_error or 'reconnect it first'}")
            if a not in picked:
                picked.append(a)
    return picked


async def _get_post(db: AsyncSession, post_id: int) -> tuple[Post, Brand]:
    p = await db.get(Post, post_id)
    if not p or p.is_autosave:
        raise ToolError(f"No post #{post_id}")
    return p, await db.get(Brand, p.brand_id)


async def _after_schedule(post: Post) -> None:
    from spark.services.publisher import as_utc

    if post.status == PostStatus.scheduled and post.scheduled_at and as_utc(post.scheduled_at) <= datetime.now(UTC):
        from spark.web.posts import enqueue

        for t in post.targets:
            if t.status == PostStatus.scheduled:
                await enqueue("publish_now", t.id)


async def _place(db: AsyncSession, post: Post, brand: Brand, user: User, action: str, scheduled_at: str | None) -> str:
    """Apply a scheduling action the way the composer does. Returns a sentence for the model."""
    tz = _tz(brand)
    if action == "draft":
        scheduler.unschedule(post)
        return "Saved as a draft."
    from spark.services.publisher import validate_post

    problems = await validate_post(db, post)
    if problems:
        raise ToolError("Not scheduled: " + "; ".join(problems))
    if action == "now":
        scheduler.schedule(post, datetime.now(UTC), user, brand)
        return "Publishing now." if post.status == PostStatus.scheduled else "Sent for an owner's approval."
    if action == "queue":
        when = await scheduler.next_free_slot(db, brand)
        scheduler.schedule(post, when, user, brand)
        msg = f"Queued for {when.astimezone(tz):%a %b %d, %H:%M} ({brand.timezone})."
    elif action == "next":
        await scheduler.prioritize(db, brand, post, user)
        msg = f"Moved to the front of the queue: {post.scheduled_at.astimezone(tz):%a %b %d, %H:%M} ({brand.timezone})."
    elif action == "schedule":
        if not scheduled_at:
            raise ToolError("Pass scheduled_at with action='schedule'")
        when = _parse_when(scheduled_at, brand)
        scheduler.schedule(post, when, user, brand)
        msg = f"Scheduled for {when.astimezone(tz):%a %b %d, %H:%M} ({brand.timezone})."
    else:
        raise ToolError("action must be draft, queue, next, schedule or now")
    if post.status == PostStatus.pending_approval:
        msg += " It waits for an owner's approval."
    return msg


# ---- tools ---------------------------------------------------------------------------------
@server.tool(annotations=READ)
async def list_brands(ctx: Context) -> dict:
    """List the brands in this Spark workspace, with channel counts, and who you are."""
    async with _Session(ctx) as (db, user):
        brands = (await db.execute(select(Brand).order_by(Brand.name))).scalars().all()
        counts = dict((await db.execute(select(SocialAccount.brand_id, func.count(SocialAccount.id))
                                        .group_by(SocialAccount.brand_id))).all())
        return {"you": {"name": user.name, "email": user.email, "role": user.role.value},
                "brands": [{"id": b.id, "slug": b.slug, "name": b.name, "timezone": b.timezone,
                            "channels": counts.get(b.id, 0), "requires_approval": b.require_approval}
                           for b in brands]}


@server.tool(annotations=READ)
async def list_channels(ctx: Context, brand: BrandArg = None) -> dict:
    """List a brand's social channels (accounts): id, platform, handle and whether they can post."""
    async with _Session(ctx) as (db, _user):
        b = await _brand(db, brand)
        return {"brand": b.slug, "channels": [_account(a) for a in await _accounts(db, b)]}


@server.tool(annotations=READ)
async def list_posts(
    ctx: Context,
    brand: BrandArg = None,
    status: Annotated[Literal["draft", "pending_approval", "scheduled", "publishing", "published", "failed"] | None,
                      Field(description="Only posts with this status")] = None,
    search: Annotated[str | None, Field(description="Text the post contains")] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict:
    """List a brand's posts, newest first; scheduled posts are ordered by their time."""
    async with _Session(ctx) as (db, _user):
        b = await _brand(db, brand)
        q = select(Post).where(Post.brand_id == b.id, Post.is_autosave.is_(False))
        if status:
            q = q.where(Post.status == PostStatus(status))
        if search:
            q = q.where(Post.content.ilike(f"%{search}%"))
        if status in ("scheduled", "pending_approval"):
            q = q.order_by(Post.scheduled_at.asc())
        else:
            q = q.order_by(Post.updated_at.desc())
        posts = (await db.execute(q.limit(limit))).scalars().all()
        return {"brand": b.slug, "posts": [_post(p, b) for p in posts]}


@server.tool(annotations=READ)
async def get_post(ctx: Context, post_id: int) -> dict:
    """Get one post with its per-channel status, published links and errors."""
    async with _Session(ctx) as (db, _user):
        p, b = await _get_post(db, post_id)
        return _post(p, b)


@server.tool(annotations=PUBLISH)
async def create_post(
    ctx: Context,
    content: Annotated[str, Field(description="The post text", min_length=1)],
    action: Annotated[Literal["draft", "queue", "next", "schedule", "now"],
                      Field(description="draft = save only; queue = next free posting slot; next = front of the queue; "
                                        "schedule = at scheduled_at; now = publish immediately")] = "draft",
    channels: Annotated[list[str] | None, Field(description="Channel ids, handles or platform names. Default: every active channel of the brand.")] = None,
    scheduled_at: Annotated[str | None, Field(description="ISO 8601 time for action='schedule', e.g. 2026-11-03T09:30 (brand timezone if no offset)")] = None,
    link: Annotated[str | None, Field(description="Optional URL to attach")] = None,
    first_comment: Annotated[str | None, Field(description="Optional first comment posted right after publishing")] = None,
    brand: BrandArg = None,
) -> dict:
    """Create a post for one or more channels and draft, queue, schedule or publish it."""
    async with _Session(ctx) as (db, user):
        _need(user, "edit")
        b = await _brand(db, brand)
        accounts = await _pick_channels(db, b, channels)
        text = content.strip()
        if b.auto_shorten_links:
            from spark.services.links import shorten_in_text

            text = await shorten_in_text(db, b, text, source="spark")
        post = Post(brand_id=b.id, author_id=user.id, source="mcp", content=text, link=(link or "").strip() or None)
        post.targets = [PostTarget(account_id=a.id, first_comment=(first_comment or "").strip() or None) for a in accounts]
        db.add(post)
        await db.flush()
        await db.refresh(post, ["targets"])
        try:
            msg = await _place(db, post, b, user, action, scheduled_at)
        except ToolError as e:
            scheduler.unschedule(post)
            await db.commit()
            raise ToolError(f"{e} Saved as draft #{post.id} instead.")
        await db.commit()
        await _after_schedule(post)
        await db.refresh(post, ["targets"])
        return {"message": msg, "post": _post(post, b)}


@server.tool(annotations=PUBLISH)
async def reschedule_post(
    ctx: Context,
    post_id: int,
    action: Annotated[Literal["queue", "next", "schedule", "now"], Field(description="Where the post goes")],
    scheduled_at: Annotated[str | None, Field(description="ISO 8601 time for action='schedule'")] = None,
) -> dict:
    """Move a draft or scheduled post: back into the queue, to the front, to a time, or publish now."""
    async with _Session(ctx) as (db, user):
        _need(user, "edit")
        p, b = await _get_post(db, post_id)
        if p.status in (PostStatus.publishing, PostStatus.published):
            raise ToolError(f"Post #{p.id} is {p.status.value} and can't be rescheduled")
        msg = await _place(db, p, b, user, action, scheduled_at)
        await db.commit()
        await _after_schedule(p)
        return {"message": msg, "post": _post(p, b)}


@server.tool(annotations=WRITE)
async def move_to_drafts(ctx: Context, post_id: int) -> dict:
    """Take a scheduled or pending post out of the queue and keep it as a draft."""
    async with _Session(ctx) as (db, user):
        _need(user, "edit")
        p, b = await _get_post(db, post_id)
        if p.status in (PostStatus.publishing, PostStatus.published):
            raise ToolError(f"Post #{p.id} is {p.status.value}")
        scheduler.unschedule(p)
        await db.commit()
        return {"message": "Moved to drafts.", "post": _post(p, b)}


@server.tool(annotations=PUBLISH)
async def approve_post(ctx: Context, post_id: int) -> dict:
    """Approve a post that waits for approval (owners only). It then publishes at its scheduled time."""
    async with _Session(ctx) as (db, user):
        _need(user, "approve")
        p, b = await _get_post(db, post_id)
        if p.status != PostStatus.pending_approval:
            raise ToolError(f"Post #{p.id} is {p.status.value}, not waiting for approval")
        scheduler.approve(p)
        await db.commit()
        await _after_schedule(p)
        return {"message": "Approved.", "post": _post(p, b)}


@server.tool(annotations=PUBLISH)
async def retry_post(ctx: Context, post_id: int) -> dict:
    """Retry the channels of a post that failed to publish."""
    async with _Session(ctx) as (db, user):
        _need(user, "edit")
        p, b = await _get_post(db, post_id)
        now = datetime.now(UTC)
        n = 0
        for t in p.targets:
            if t.status == PostStatus.failed:
                t.status, t.scheduled_at, t.attempts, t.next_attempt_at = PostStatus.scheduled, now, 0, None
                n += 1
        if not n:
            raise ToolError(f"Post #{p.id} has no failed channels")
        p.refresh_status()
        await db.commit()
        await _after_schedule(p)
        return {"message": f"Retrying {n} channel(s).", "post": _post(p, b)}


@server.tool(annotations=READ)
async def list_ideas(
    ctx: Context, brand: BrandArg = None,
    status: Annotated[Literal["idea", "drafting", "ready", "done"] | None, Field(description="Board column")] = None,
) -> dict:
    """List the brand's content ideas (the Ideas board)."""
    async with _Session(ctx) as (db, _user):
        b = await _brand(db, brand)
        q = select(Idea).where(Idea.brand_id == b.id)
        if status:
            q = q.where(Idea.status == status)
        ideas = (await db.execute(q.order_by(Idea.status, Idea.position, Idea.id.desc()).limit(200))).scalars().all()
        return {"brand": b.slug, "ideas": [{"id": i.id, "title": i.title, "body": i.body, "tags": i.tags,
                                            "status": i.status, "source_url": i.source_url, "post_id": i.post_id}
                                           for i in ideas]}


@server.tool(annotations=WRITE)
async def add_idea(
    ctx: Context,
    title: Annotated[str, Field(min_length=1, max_length=200)],
    body: Annotated[str | None, Field(description="Notes, angles, draft text")] = None,
    tags: list[str] | None = None,
    source_url: str | None = None,
    brand: BrandArg = None,
) -> dict:
    """Add an idea to the brand's Ideas board (first column)."""
    async with _Session(ctx) as (db, user):
        _need(user, "edit")
        b = await _brand(db, brand)
        top = await db.scalar(select(func.min(Idea.position)).where(Idea.brand_id == b.id, Idea.status == "idea"))
        idea = Idea(brand_id=b.id, author_id=user.id, title=title.strip(), body=(body or "").strip() or None,
                    tags=[t.strip().lstrip("#") for t in (tags or []) if t.strip()][:20],
                    source_url=source_url, status="idea", position=(top or 0) - 1)
        db.add(idea)
        await db.commit()
        return {"message": "Added to Ideas.", "idea_id": idea.id, "board_url": _url("/ideas")}


@server.tool(annotations=READ)
async def get_analytics(
    ctx: Context, brand: BrandArg = None,
    days: Annotated[int, Field(ge=1, le=365, description="Look-back window")] = 30,
) -> dict:
    """Totals for the last N days (impressions, engagements, clicks, followers), change vs the period before, and top posts."""
    from spark.services import analytics

    async with _Session(ctx) as (db, _user):
        b = await _brand(db, brand)
        data = await analytics.overview(db, b.id, days)
        prev = await analytics.compare(db, b.id, days)
        return {
            "brand": b.slug, "days": days,
            "published": data["published"], "scheduled": data["scheduled"], "failed": data["failed"],
            "impressions": data["totals"]["impressions"], "engagements": data["engagements"],
            "engagement_rate_pct": round(data["engagement_rate"], 2), "link_clicks": data["link_clicks"],
            "followers": data["followers"], "by_platform": data["by_platform"],
            "change_pct": {"impressions": prev["impressions"], "engagements": prev["engagements"]},
            "top_posts": [{"post_id": t["target"].post_id, "channel": t["account"].handle,
                           "platform": t["account"].platform, "engagements": t["engagements"],
                           "text": (t["target"].post.content if t["target"].post else "")[:280],
                           "url": t["target"].remote_url} for t in data["top"][:5]],
        }


@server.tool(annotations=READ)
async def best_posting_times(ctx: Context, brand: BrandArg = None) -> dict:
    """The weekday/hour slots (brand timezone) where past posts got the best engagement rate."""
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    async with _Session(ctx) as (db, _user):
        b = await _brand(db, brand)
        ranked = await scheduler.best_times(db, b.id)
        return {"brand": b.slug, "timezone": b.timezone,
                "slots": [{"day": days[r["weekday"]], "hour": f"{r['hour']:02d}:00", "posts": r["posts"],
                           "score": round(r["score"], 4)} for r in ranked],
                "note": None if ranked else "Not enough published posts with metrics yet."}


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
async def write_posts(
    ctx: Context,
    brief: Annotated[str, Field(description="What the post is about, the goal, any facts to include")],
    platforms: Annotated[list[str] | None, Field(description="Platform keys like x, linkedin, instagram. Default: the brand's channels.")] = None,
    variants: Annotated[int, Field(ge=1, le=3)] = 1,
    brand: BrandArg = None,
) -> dict:
    """Draft post text per platform in the brand's voice with Spark's AI. Nothing is saved; pass a result to create_post."""
    from spark.services.ai import AIUnavailable, ContentAI

    async with _Session(ctx) as (db, user):
        _need(user, "edit")
        b = await _brand(db, brand)
        plats = platforms or sorted({a.platform for a in await _accounts(db, b) if a.is_active}) or ["x"]
        try:
            drafts = await ContentAI().generate(b, brief, plats, variants=variants)
        except AIUnavailable as e:
            raise ToolError(str(e))
        return {"brand": b.slug, "drafts": [d.model_dump() for d in drafts]}


TOOLS_FOR_UI = [  # name, one-line summary for Settings → Connectors → MCP access
    ("list_brands", "brands and your role"), ("list_channels", "a brand's accounts"),
    ("list_posts", "drafts, queue, sent, failed"), ("get_post", "one post with links and errors"),
    ("create_post", "draft, queue, schedule or publish"), ("reschedule_post", "move a post in the queue"),
    ("move_to_drafts", "take a post out of the queue"), ("approve_post", "owners approve"),
    ("retry_post", "retry failed channels"), ("list_ideas", "the Ideas board"), ("add_idea", "capture an idea"),
    ("get_analytics", "numbers and top posts"), ("best_posting_times", "when your audience engages"),
    ("write_posts", "AI drafts in your brand voice"),
]


# ---- HTTP mounting -------------------------------------------------------------------------
def _build_session_manager() -> None:
    # Stateless JSON responses: every request stands alone, so it scales across web workers
    # and needs no sticky sessions. DNS-rebinding checks are off because every request must
    # carry a Spark bearer token, which a rebinding page cannot obtain.
    server.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


_build_session_manager()


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": message}}, 401,
                        headers={"WWW-Authenticate": 'Bearer realm="spark", error="invalid_token"'})


async def _endpoint(scope, receive, send) -> None:
    """Reject requests without a valid token before they reach the MCP session manager."""
    from starlette.requests import Request

    from spark.web.connectors import user_for_token

    request = Request(scope)
    raw = _bearer(request.headers)
    if not raw:
        return await _unauthorized("Missing bearer token. Create one under Settings → Connectors → MCP access.")(scope, receive, send)
    async with SessionLocal() as db:
        if await user_for_token(db, raw) is None:
            return await _unauthorized("Invalid or revoked token")(scope, receive, send)
    await server.session_manager.handle_request(scope, receive, send)


class _ASGIEndpoint:
    """Starlette treats a plain function as a request handler; a class instance is raw ASGI."""

    async def __call__(self, scope, receive, send):
        await _endpoint(scope, receive, send)


route = Route("/mcp", endpoint=_ASGIEndpoint(), methods=["GET", "POST", "DELETE"])


def session_manager_run():
    """Context manager the app lifespan enters; tests call reset() to get a fresh one."""
    return server.session_manager.run()


def reset() -> None:
    _build_session_manager()

