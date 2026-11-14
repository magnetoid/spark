"""The outbox: events Spark announces to chat (and, through `hooks`, to webhook endpoints).

`emit` writes a row in the caller's transaction, so an event exists exactly when the change it
describes was committed. The worker calls `process`, which takes each row once (a conditional
update, safe with several workers), tells chat and queues webhook deliveries.

Events: post.approval_needed, post.published, post.failed, inbox.comment, inbox.message,
inbox.review, inbox.mention, channel.reconnect_needed, channel.expiring, channel.recovered.
Channel events are emailed to the brand's owners and editors too. Every payload is plain JSON and is what webhook endpoints receive.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import (
    Brand,
    InboxItem,
    OutboundEvent,
    Post,
    PostStatus,
    PostTarget,
    SocialAccount,
)
from spark.services import chat, hooks

log = logging.getLogger(__name__)
EVENTS = {
    "post.approval_needed": "A post waits for approval",
    "post.published": "A post went out on every channel it was meant for",
    "post.failed": "A post could not be published after retrying",
    "inbox.comment": "A new comment arrived",
    "inbox.message": "A new direct message arrived",
    "inbox.review": "A new review arrived",
    "inbox.mention": "The brand was mentioned",
    "channel.reconnect_needed": "A channel stopped working and needs reconnecting",
    "channel.expiring": "A channel's access runs out soon (7, 3 and 1 days before)",
    "channel.recovered": "A channel works again",
}
FRESH = timedelta(hours=24)  # older inbox items are history being imported, not news
KEEP = timedelta(days=7)
CHAT_SWITCH = {  # event → the switch in the Chat notifications connector; others never go to chat
    "post.approval_needed": "chat_on_approval",
    "post.failed": "chat_on_failed",
    "post.published": "chat_on_published",
    "inbox.review": "chat_on_review",
    "channel.reconnect_needed": "chat_on_channel",
    "channel.expiring": "chat_on_channel",
    "channel.recovered": "chat_on_channel",
}
CHANNEL_EMAIL = ("channel.reconnect_needed", "channel.expiring")


def _base() -> str:
    return get_settings().base_url.rstrip("/")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (
        (dt if dt.tzinfo else dt.replace(tzinfo=UTC))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ---- what an event says -----------------------------------------------------------------------
def post_data(post: Post, targets: list[PostTarget] | None = None) -> dict:
    return {
        "post": {
            "id": post.id,
            "content": (post.content or "")[:280],
            "status": post.status.value,
            "scheduled_at": _iso(post.scheduled_at),
            "url": f"{_base()}/posts/{post.id}/edit",
        },
        "targets": [
            {
                "platform": t.account.platform,
                "handle": t.account.handle,
                "status": t.status.value,
                "url": t.remote_url,
                "error": t.error,
            }
            for t in (post.targets if targets is None else targets)
        ],
    }


def inbox_data(item: InboxItem, account: SocialAccount) -> dict:
    return {
        "item": {
            "id": item.id,
            "kind": item.kind,
            "platform": account.platform,
            "handle": account.handle,
            "author": item.author_name or item.author_handle or "",
            "text": (item.text or "")[:1000],
            "rating": item.rating,
            "received_at": _iso(item.received_at),
            "permalink": item.permalink,
            "url": f"{_base()}/inbox",
        }
    }


# ---- writing events (the caller commits) --------------------------------------------------------
def emit(db: AsyncSession, brand_id: int | None, event: str, data: dict) -> OutboundEvent:
    row = OutboundEvent(brand_id=brand_id, event=event, data=data)
    db.add(row)
    return row


def track_published(db: AsyncSession, post: Post, before: PostStatus) -> None:
    """Call right after `post.refresh_status()`: announces the post once, when its last channel went out."""
    if post.status == PostStatus.published and before != PostStatus.published:
        emit(db, post.brand_id, "post.published", post_data(post))


def track_inbox(db: AsyncSession, item: InboxItem, account: SocialAccount) -> None:
    """A new incoming item is news only when it is recent; a first sync brings months of history."""
    received = item.received_at
    if received is not None:
        received = received if received.tzinfo else received.replace(tzinfo=UTC)
        if datetime.now(UTC) - received > FRESH:
            return
    if f"inbox.{item.kind}" in EVENTS:
        emit(db, item.brand_id, f"inbox.{item.kind}", inbox_data(item, account))


# ---- telling chat -----------------------------------------------------------------------------------
def _quote(text: str, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    return f"“{text[:limit]}{'…' if len(text) > limit else ''}”" if text else "(no text)"


def describe(event: str, data: dict, brand_name: str) -> tuple[str, str, str] | None:
    """The chat message for an event: (text, link, link label). None when chat has nothing to say."""
    head = f"[{brand_name}] " if brand_name else ""
    post, targets, item = data.get("post") or {}, data.get("targets") or [], data.get("item") or {}
    where = ", ".join(f"{t.get('handle')} ({t.get('platform')})" for t in targets)
    if event == "post.failed":
        errors = "; ".join(
            f"{t.get('handle')} ({t.get('platform')}): {t.get('error') or 'unknown error'}"
            for t in targets
        )
        return (
            f"{head}A post failed to publish: {_quote(post.get('content'))}\n{errors}"[:1500],
            f"{_base()}/publishing?view=failed",
            "Review failed posts",
        )
    if event == "post.approval_needed":
        return (
            f"{head}A post is waiting for approval: {_quote(post.get('content'))}"
            + (f"\nFor {where}" if where else ""),
            f"{_base()}/publishing?view=approvals",
            "Open approvals",
        )
    if event == "post.published":
        live = next((t.get("url") for t in targets if t.get("url")), None)
        return (
            f"{head}A post was published: {_quote(post.get('content'))}"
            + (f"\nOn {where}" if where else ""),
            live or post.get("url") or _base(),
            "See the post" if live else "Open in Spark",
        )
    if event.startswith("channel."):
        said = channel_text(event, data.get("channel") or {})
        if said is None:
            return None
        return (f"{head}{said[0]}", said[1], said[2])
    if event == "inbox.review":
        stars = f"{item['rating']}/5 " if item.get("rating") is not None else ""
        return (
            f"{head}New {stars}review from {item.get('author') or 'someone'} on {item.get('handle')} "
            f"({item.get('platform')}): {_quote(item.get('text'), 300)}",
            item.get("url") or f"{_base()}/inbox",
            "Reply in Spark",
        )
    return None


def channel_text(event: str, ch: dict) -> tuple[str, str, str] | None:
    """What a channel event says, for chat and email alike: (text, link, link label)."""
    name = f"{ch.get('handle')} ({ch.get('platform')})"
    link = ch.get("url") or f"{_base()}/channels"
    if event == "channel.reconnect_needed":
        why = f"\n{ch['error']}" if ch.get("error") else ""
        return (
            f"{name} needs reconnecting. Posts to it will fail until it is.{why}"[:1500],
            link,
            "Reconnect",
        )
    if event == "channel.expiring":
        days = ch.get("days_left")
        when = "today" if not days else f"in {days} day{'s' if days != 1 else ''}"
        return (f"{name} loses access {when}. Reconnect it to keep posting.", link, "Reconnect")
    if event == "channel.recovered":
        return (f"{name} works again.", link, "Open channels")
    return None


async def _email_channel(db: AsyncSession, brand: Brand | None, event: str, data: dict) -> None:
    if brand is None or event not in CHANNEL_EMAIL:
        return
    from spark.services import notify

    said = channel_text(event, data.get("channel") or {})
    if said is None:
        return
    people = [
        u
        for u, role in await notify._brand_people(db, brand.id)
        if role in ("owner", "editor") and notify.wants(u, "notify_channels")
    ]
    if not people:
        return
    subject = f"[{brand.name}] {said[0].splitlines()[0]}"[:200]
    import html

    intro = html.escape(said[0]).replace("\n", "<br>")
    body = notify.layout(subject, intro, "", said[1], said[2])
    sender = notify.get_sender()
    for u in people:
        try:
            await sender.send(u.email, subject, body)
        except Exception:
            log.exception("Channel alert email to %s failed", u.email)


async def _tell_chat(event: str, data: dict, brand_name: str) -> None:
    switch = CHAT_SWITCH.get(event)
    if not switch or not getattr(get_settings(), switch) or not chat.destinations():
        return
    said = describe(event, data, brand_name)
    if said:
        await chat.send(said[0], url=said[1], label=said[2])


# ---- the worker's side ------------------------------------------------------------------------------
async def process(db: AsyncSession, limit: int = 200) -> int:
    """Take every waiting event once: tell chat and queue webhook deliveries. Returns how many."""
    rows = (
        (
            await db.execute(
                select(OutboundEvent)
                .where(OutboundEvent.processed_at.is_(None))
                .order_by(OutboundEvent.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    waiting = [(ev.id, ev.brand_id, ev.event, ev.data or {}, ev.created_at) for ev in rows]
    done = 0
    for event_id, brand_id, event, data, created_at in waiting:
        taken = await db.execute(
            update(OutboundEvent)
            .where(OutboundEvent.id == event_id, OutboundEvent.processed_at.is_(None))
            .values(processed_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        if taken.rowcount != 1:  # another worker has it
            await db.rollback()
            continue
        brand = await db.get(Brand, brand_id) if brand_id else None
        brand_name = brand.name if brand else ""
        await hooks.enqueue(db, event_id, event, data, brand, created_at)
        await db.commit()  # taken and queued for webhooks in one step
        done += 1
        try:
            await _tell_chat(event, data, brand_name)
        except Exception:  # chat is best effort; the event stays taken
            log.exception("Chat notification for event %s failed", event_id)
        try:
            await _email_channel(db, brand, event, data)
        except Exception:  # email is best effort too
            log.exception("Channel email for event %s failed", event_id)
    if waiting:
        await db.execute(
            delete(OutboundEvent)
            .where(
                OutboundEvent.processed_at.is_not(None),
                OutboundEvent.created_at < datetime.now(UTC) - KEEP,
            )
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    return done
