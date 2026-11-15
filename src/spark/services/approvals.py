"""Approval deadlines.

A brand can ask for approval some hours before a post's time (`approval_lead_hours`). Before the
deadline the people who approve get one reminder; after it the brand's rule applies: the post keeps
waiting ("wait") or goes back to drafts ("drafts") and its author hears why. A deadline never
publishes anything.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Post, PostStatus, User
from spark.services.email import EmailSender, get_sender

log = logging.getLogger(__name__)

TIMEOUT_RULES = ("wait", "drafts")
MIN_NOTICE = timedelta(hours=1)  # a deadline set now is at least this far away
MAX_REMINDER = timedelta(hours=4)  # the reminder goes out this long before the deadline (at most)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def due_for(post: Post, brand: Brand, now: datetime | None = None) -> datetime | None:
    """When approval is due: `lead` hours before the post, but never sooner than an hour from now
    and never after the post's own time."""
    when = _utc(post.scheduled_at)
    if not brand.approval_lead_hours or when is None:
        return None
    now = _utc(now) or datetime.now(UTC)
    due = max(when - timedelta(hours=brand.approval_lead_hours), now + MIN_NOTICE)
    return min(due, when)


def set_due(post: Post, brand: Brand, now: datetime | None = None) -> None:
    """A fresh request for approval: a new due date and a new reminder."""
    post.approval_due_at = due_for(post, brand, now)
    post.approval_reminded_at = None


def overdue(post: Post, now: datetime | None = None) -> bool:
    now = _utc(now) or datetime.now(UTC)
    due = _utc(post.approval_due_at) or _utc(post.scheduled_at)
    return due is not None and due <= now


def _reminder_window(brand: Brand) -> timedelta:
    return min(MAX_REMINDER, timedelta(hours=(brand.approval_lead_hours or 0) / 2))


async def run(
    db: AsyncSession, sender: EmailSender | None = None, now: datetime | None = None
) -> int:
    """One pass over waiting posts: give them a due date, remind once, apply the rule after it.
    Returns the number of emails sent."""
    from spark.services import activity, notify, scheduler

    sender = sender or get_sender()
    now = _utc(now) or datetime.now(UTC)
    waiting = (
        (
            await db.execute(
                select(Post).where(
                    Post.status == PostStatus.pending_approval, Post.is_autosave.is_(False)
                )
            )
        )
        .scalars()
        .all()
    )
    brands: dict[int, Brand] = {}
    remind: dict[int, list[Post]] = {}
    expired: list[Post] = []
    for p in waiting:
        brand = brands.get(p.brand_id) or await db.get(Brand, p.brand_id)
        brands[p.brand_id] = brand
        if not brand.approval_lead_hours:
            continue
        if p.approval_due_at is None:
            p.approval_due_at = due_for(p, brand, now)
            if p.approval_due_at is None:
                continue
        due = _utc(p.approval_due_at)
        if due <= now:
            if brand.approval_timeout == "drafts":
                expired.append(p)
        elif p.approval_reminded_at is None and due - now <= _reminder_window(brand):
            remind.setdefault(p.brand_id, []).append(p)

    sent = 0
    for brand_id, group in remind.items():
        brand = brands[brand_id]
        tz = ZoneInfo(brand.timezone or "UTC")
        first = min(_utc(p.approval_due_at) for p in group)
        n = len(group)
        subject = (
            f"[{brand.name}] Approval due {first.astimezone(tz).strftime('%a %H:%M')}: "
            f"{n} post{'s' if n != 1 else ''}"
        )
        rule = (
            "After the deadline these posts go back to drafts."
            if brand.approval_timeout == "drafts"
            else "After the deadline these posts keep waiting and miss their time."
        )
        items = [
            (
                (p.content or "(no text)")[:90],
                "due "
                + _utc(p.approval_due_at).astimezone(tz).strftime("%a %b %d, %H:%M")
                + " · goes out "
                + _utc(p.scheduled_at).astimezone(tz).strftime("%a %b %d, %H:%M"),
            )
            for p in group
        ]
        body = notify.layout(
            subject,
            rule,
            notify._rows(items),
            f"{notify._base()}/publishing?view=approvals",
            "Open approvals",
        )
        for u, role in await notify._brand_people(db, brand_id):
            if role not in ("owner", "client") or not notify.wants(u, "notify_approvals"):
                continue
            try:
                await sender.send(u.email, subject, body)
                sent += 1
            except Exception:
                log.exception("Approval reminder to %s failed", u.email)
        for p in group:
            p.approval_reminded_at = now

    for p in expired:
        brand = brands[p.brand_id]
        scheduler.unschedule(p)
        p.approval_due_at = None
        activity.record(
            db,
            p.brand_id,
            None,
            "moved to drafts",
            "post",
            p.id,
            "No approval before the deadline: " + (p.content or "")[:80],
        )
        author = await db.get(User, p.author_id) if p.author_id else None
        if author and author.is_active:
            subject = f"[{brand.name}] Not approved in time, moved to drafts"
            body = notify.layout(
                subject,
                "Nobody approved this post before its deadline, so it went back to drafts. "
                "Pick a new time and ask for approval again.",
                notify._rows([((p.content or "(no text)")[:90], "")]),
                f"{notify._base()}/publishing?view=drafts",
                "Open drafts",
            )
            try:
                await sender.send(author.email, subject, body)
                sent += 1
            except Exception:
                log.exception("Approval timeout notice to %s failed", author.email)
    await db.commit()
    return sent
