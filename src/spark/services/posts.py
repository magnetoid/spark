"""Saving, placing and acting on posts. One implementation shared by the web composer, the
JSON API and the MCP tools, so every path validates, shortens links and schedules alike."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import (
    Brand,
    Campaign,
    ContentPillar,
    Media,
    Post,
    PostStatus,
    PostTarget,
    SocialAccount,
    User,
)
from spark.platforms import PublishPayload, adapter_for
from spark.services import access, guardrails, jobs, scheduler
from spark.services.links import shorten_in_text
from spark.services.publisher import as_utc, validate_post

ACTIONS = ("draft", "queue", "next", "schedule", "now")


class PlaceError(Exception):
    """The post cannot be placed as asked; `problems` are sentences for the user."""

    def __init__(self, problems: list[str]):
        super().__init__(" · ".join(problems))
        self.problems = problems


@dataclass
class TargetInput:
    account_id: int
    override: str | None = None
    first_comment: str | None = None
    thread: list[str] = field(default_factory=list)
    post_type: str = "post"
    options: dict = field(default_factory=dict)


def clean_options(adapter, raw: dict | None) -> dict:
    """The extras worth keeping for one channel: tidy, and only what its network carries."""
    raw, keys, out = raw or {}, adapter.option_keys, {}
    if "ai_generated" in keys and raw.get("ai_generated") is not None:
        out["ai_generated"] = bool(raw["ai_generated"])  # an explicit "no" is kept too
    if "paid_partnership" in keys and raw.get("paid_partnership"):
        out["paid_partnership"] = True
    if "collaborators" in keys:
        people = [str(p).strip().lstrip("@").strip() for p in raw.get("collaborators") or []]
        people = list(dict.fromkeys(p[:60] for p in people if p))[:10]
        if people:
            out["collaborators"] = people
    poll = raw.get("poll")
    if "poll" in keys and isinstance(poll, dict):
        choices = [str(c).strip() for c in poll.get("options") or [] if str(c).strip()][:10]
        try:
            days = min(max(int(poll.get("days") or 3), 1), 14)
        except (TypeError, ValueError):
            days = 3
        out["poll"] = {
            "question": str(poll.get("question") or "").strip()[:300],
            "options": choices,
            "days": days,
        }
    return out


async def active_accounts(db: AsyncSession, brand: Brand) -> list[SocialAccount]:
    return (
        (
            await db.execute(
                select(SocialAccount)
                .where(SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True))
                .order_by(SocialAccount.platform)
            )
        )
        .scalars()
        .all()
    )


def channel_capabilities(account: SocialAccount) -> dict:
    """What the composer may offer for this channel, straight from its adapter."""
    ad = adapter_for(account)
    return {
        "max": ad.limits.max_chars,
        "label": ad.label,
        "platform": account.platform,
        "handle": account.handle,
        "requires_media": ad.limits.requires_media,
        "provider": account.provider,
        "avatar": account.avatar_url,
        "display_name": account.display_name or account.handle,
        "first_comment": ad.supports_first_comment,
        "threadable": ad.supports_thread,
        "post_types": list(ad.post_types),
        "options": list(ad.option_keys),
    }


async def save_post(
    db: AsyncSession,
    brand: Brand,
    user: User,
    post: Post | None,
    *,
    content: str,
    link: str | None,
    media_ids: list[int],
    campaign_id: int | None,
    notes: str | None,
    source: str,
    targets: list[TargetInput],
    pillar_id: int | None = None,
    evergreen: bool | None = None,
    recycle_every_days: int | None = None,
) -> Post:
    """Create or update a post and its targets. Does not schedule; see `place_post`."""
    if post is None:
        post = Post(brand_id=brand.id, author_id=user.id, source=source or "manual")
        post.targets = []
        db.add(post)
    post.is_autosave = False
    campaign = await db.get(Campaign, campaign_id) if campaign_id else None
    if campaign is not None and campaign.brand_id != brand.id:
        campaign, campaign_id = None, None
    utm = campaign.utm_campaign if campaign else None
    if media_ids:
        own = set(
            (
                await db.execute(
                    select(Media.id).where(Media.id.in_(media_ids), Media.brand_id == brand.id)
                )
            ).scalars()
        )
        media_ids = [i for i in media_ids if i in own]

    async def short(text: str | None) -> str | None:
        if not text or not brand.auto_shorten_links:
            return text
        return await shorten_in_text(
            db, brand, text, source="spark", campaign=utm, campaign_id=campaign_id
        )

    content = (await short(content.strip())) or ""
    link = (await short((link or "").strip())) or None
    post.content, post.link, post.media_ids, post.campaign_id = (
        content,
        link,
        list(media_ids),
        campaign_id,
    )
    post.notes = notes or None
    pillar = await db.get(ContentPillar, pillar_id) if pillar_id else None
    post.pillar_id = pillar.id if pillar and pillar.brand_id == brand.id else None
    if evergreen is not None:
        post.evergreen = evergreen
        post.recycle_every_days = (recycle_every_days or 30) if evergreen else None

    valid_accounts = {a.id: a for a in await active_accounts(db, brand)}
    valid = set(valid_accounts)
    existing = {t.account_id: t for t in post.targets}
    keep: list[PostTarget] = []
    for ti in targets:
        if ti.account_id not in valid or any(t.account_id == ti.account_id for t in keep):
            continue
        t = existing.get(ti.account_id) or PostTarget(account_id=ti.account_id)
        override = (ti.override or "").strip()
        t.content_override = await short(override) if override and override != content else None
        t.first_comment = await short((ti.first_comment or "").strip() or None)
        items = [str(x).strip() for x in (ti.thread or []) if str(x).strip()][:25]
        t.thread = [await short(x) for x in items]
        adapter = adapter_for(valid_accounts[t.account_id])
        t.post_type = ti.post_type if ti.post_type in adapter.post_types else "post"
        t.options = clean_options(adapter, ti.options)
        if t.status == PostStatus.failed:
            t.status = PostStatus.draft
        keep.append(t)
    post.targets = keep
    await db.flush()
    await db.refresh(post, ["targets"])
    return post


def _fmt(when: datetime, brand: Brand) -> str:
    return f"{as_utc(when).astimezone(ZoneInfo(brand.timezone)):%a %b %d, %H:%M}"


async def place_post(
    db: AsyncSession, brand: Brand, user: User, post: Post, action: str, when: datetime | None
) -> str:
    """Apply a composer action. Returns the message to show; raises PlaceError and leaves the
    post as a draft when it cannot be placed."""
    if action not in ACTIONS:
        raise PlaceError([f"Unknown action {action!r}"])
    if action == "draft":
        scheduler.unschedule(post)
        return "Draft saved"
    problems = (
        ["Pick at least one account to publish to"]
        if not post.targets
        else await validate_post(db, post)
    )
    for t in post.targets:
        for p in guardrails.check(brand, t.content_override or post.content)[0]:
            if p not in problems:
                problems.append(p)
    if action == "schedule" and not when:
        problems.append("Pick a date and time")
    if problems:
        scheduler.unschedule(post)
        raise PlaceError(problems)
    approver = access.can_approve(await access.role_for(db, user, brand.id))
    if action == "now":
        scheduler.schedule(post, datetime.now(UTC), user, brand, approver)
        return "Publishing now…" if post.status == PostStatus.scheduled else "Sent for approval"
    if action == "queue":
        slot = await scheduler.next_free_slot(
            db, brand, account_ids=[t.account_id for t in post.targets]
        )
        status = scheduler.schedule(post, slot, user, brand, approver)
        msg = f"Queued for {_fmt(slot, brand)}"
    elif action == "next":
        status = await scheduler.prioritize(db, brand, post, user, approver)
        msg = f"Sharing next, at {_fmt(post.scheduled_at, brand)}"
    else:
        status = scheduler.schedule(post, when, user, brand, approver)
        msg = "Scheduled"
    if status == PostStatus.pending_approval:
        msg += " (awaiting approval)" if action != "schedule" else " — awaiting approval"
    return msg


async def enqueue_due(post: Post) -> None:
    """After commit: publish right away what is scheduled for now or earlier."""
    if post.status != PostStatus.scheduled or not post.scheduled_at:
        return
    if as_utc(post.scheduled_at) > datetime.now(UTC):
        return
    for t in post.targets:
        if t.status == PostStatus.scheduled:
            await jobs.enqueue("publish_now", t.id)


def retry_failed(post: Post) -> int:
    """Put failed targets back in the queue for an immediate attempt. Returns how many."""
    now = datetime.now(UTC)
    n = 0
    for t in post.targets:
        if t.status == PostStatus.failed:
            t.status, t.scheduled_at, t.attempts, t.next_attempt_at = (
                PostStatus.scheduled,
                now,
                0,
                None,
            )
            n += 1
    if n:
        post.scheduled_at = now
        post.refresh_status()
    return n


async def duplicate_post(db: AsyncSession, brand: Brand, user: User, src: Post) -> Post:
    post = Post(
        brand_id=brand.id,
        author_id=user.id,
        content=src.content,
        link=src.link,
        media_ids=list(src.media_ids),
        campaign_id=src.campaign_id,
        source=src.source,
    )
    post.targets = [
        PostTarget(
            account_id=t.account_id,
            content_override=t.content_override,
            first_comment=t.first_comment,
            thread=list(t.thread or []),
            post_type=t.post_type or "post",
            options=dict(t.options or {}),
        )
        for t in src.targets
    ]
    db.add(post)
    await db.commit()
    await db.refresh(post, ["targets"])
    return post


def move_to_day(post: Post, day: date, brand: Brand) -> datetime:
    """Calendar drag: keep the time of day, change the date. Returns the new UTC time."""
    if post.status not in (PostStatus.scheduled, PostStatus.pending_approval, PostStatus.draft):
        raise PlaceError(["Only unpublished posts can be moved"])
    zone = ZoneInfo(brand.timezone)
    current = (
        as_utc(post.scheduled_at).astimezone(zone)
        if post.scheduled_at
        else datetime.now(zone).replace(hour=9, minute=0, second=0, microsecond=0)
    )
    when = current.replace(year=day.year, month=day.month, day=day.day).astimezone(UTC)
    if when < datetime.now(UTC):
        raise PlaceError(["Can't move a post into the past"])
    post.scheduled_at = when
    for t in post.targets:
        if t.status != PostStatus.published:
            t.scheduled_at = when
    return when


# ---- autosave ---------------------------------------------------------------------------
async def autosave(
    db: AsyncSession,
    brand: Brand,
    user: User,
    post_id: int | None,
    *,
    content: str,
    link: str | None,
    media_ids: list[int],
    source: str,
    targets: list[TargetInput],
) -> Post | None:
    """Keep an unfinished post as a hidden draft. Returns the post, or None when there is nothing to keep."""
    post = None
    if post_id:
        post = await db.get(Post, post_id)
        if not post or post.brand_id != brand.id or post.status != PostStatus.draft:
            return post if post and post.brand_id == brand.id else None
    if post is None:
        if not content.strip() and not media_ids:
            return None
        post = Post(
            brand_id=brand.id, author_id=user.id, source=source or "manual", is_autosave=True
        )
        post.targets = []
        db.add(post)
    post.content, post.link = content.strip(), (link or "").strip() or None
    post.media_ids = [int(m) for m in media_ids]
    valid = {a.id: a for a in await active_accounts(db, brand)}
    existing = {t.account_id: t for t in post.targets}
    keep = []
    for ti in targets:
        if ti.account_id not in valid:
            continue
        t = existing.get(ti.account_id) or PostTarget(account_id=ti.account_id)
        t.content_override = (ti.override or "").strip() or None
        t.first_comment = (ti.first_comment or "").strip() or None
        t.thread = [str(x) for x in (ti.thread or [])][:25]
        adapter = adapter_for(valid[ti.account_id])
        t.post_type = ti.post_type if ti.post_type in adapter.post_types else "post"
        t.options = clean_options(adapter, ti.options)
        keep.append(t)
    post.targets = keep
    await db.commit()
    return post


async def latest_autosave(
    db: AsyncSession, brand: Brand, user: User, max_age: timedelta = timedelta(hours=24)
) -> Post | None:
    """The user's most recent unfinished post, if it is still worth resuming."""
    since = datetime.now(UTC) - max_age
    return await db.scalar(
        select(Post)
        .where(
            Post.brand_id == brand.id,
            Post.author_id == user.id,
            Post.is_autosave.is_(True),
            Post.status == PostStatus.draft,
            Post.updated_at >= since,
        )
        .order_by(Post.updated_at.desc())
        .limit(1)
    )


async def validate_targets(
    db: AsyncSession,
    brand: Brand,
    targets: dict[str, str],
    media_ids: list[int],
    link: str | None,
    post_types: dict[str, str] | None = None,
    options: dict[str, dict] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """Live validation while typing: per-channel problems (block placing) and warnings (shown only)."""
    media = []
    if media_ids:
        media = (
            (
                await db.execute(
                    select(Media).where(Media.id.in_(media_ids), Media.brand_id == brand.id)
                )
            )
            .scalars()
            .all()
        )
    problems: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}
    for aid, text in targets.items():
        acc = await db.get(SocialAccount, int(aid)) if str(aid).isdigit() else None
        if acc and acc.brand_id == brand.id:
            gp, gw = guardrails.check(brand, text or "")
            kind = (post_types or {}).get(str(aid), "post")
            adapter = adapter_for(acc)
            payload = PublishPayload(
                text=text or "",
                media=list(media),
                link=link,
                post_type=kind,
                options=clean_options(adapter, (options or {}).get(str(aid))),
            )
            problems[str(aid)] = adapter.validate(payload) + gp
            warnings[str(aid)] = gw
    return {"problems": problems, "warnings": warnings}
