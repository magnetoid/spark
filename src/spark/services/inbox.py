"""The smart inbox: what people say to the brand, kept in Spark.

Items arrive by Zernio webhook (`ingest_event`) and by a periodic sync that catches what webhooks
missed. A cheap model labels sentiment and intent; on request Claude proposes three replies in
the brand's voice. Rules prepare a reply that waits for a person. Replies go out through Zernio.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import Brand, InboxItem, InboxRule, SavedReply, SocialAccount, User
from spark.platforms.base import PlatformError
from spark.platforms.zernio import ZernioAdapter, from_zernio
from spark.services import activity, events
from spark.services import ai as ai_svc
from spark.services.publisher import as_utc

log = logging.getLogger("spark.inbox")
INBOX_EVENTS = (
    "comment.received",
    "message.received",
    "review.new",
    "review.updated",
    "review.deleted",
    "review.restored",
)


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


async def _account(db: AsyncSession, zernio_account_id: str | None) -> SocialAccount | None:
    if not zernio_account_id:
        return None
    return await db.scalar(
        select(SocialAccount).where(
            SocialAccount.provider == "zernio", SocialAccount.external_id == zernio_account_id
        )
    )


# ---- writing items ---------------------------------------------------------------------------
async def upsert(
    db: AsyncSession, account: SocialAccount, kind: str, external_id: str, **fields
) -> tuple[InboxItem, bool]:
    """Create the item or refresh its text; new incoming items run through the rules. Caller commits."""
    item = await db.scalar(
        select(InboxItem).where(
            InboxItem.account_id == account.id,
            InboxItem.kind == kind,
            InboxItem.external_id == str(external_id),
        )
    )
    if item is not None:
        for k in ("text", "rating", "attachments", "raw", "permalink"):
            if k in fields and fields[k] is not None and getattr(item, k) != fields[k]:
                setattr(item, k, fields[k])
        if fields.get("replied_at") and not item.replied_at:
            item.replied_at, item.status = fields["replied_at"], "resolved"
        return item, False
    direction = fields.pop("direction", "incoming")
    item = InboxItem(
        brand_id=account.brand_id,
        account_id=account.id,
        kind=kind,
        external_id=str(external_id)[:255],
        direction=direction,
        status="resolved" if direction == "outgoing" else "open",
        **fields,
    )
    if item.replied_at:
        item.status = "resolved"
    db.add(item)
    await db.flush()
    if direction == "incoming" and item.status == "open":
        await apply_rules(db, item)
    return item, True


def _author(
    name: str | None, handle: str | None = None, picture: str | None = None, ext: str | None = None
) -> dict:
    return {
        "author_name": (name or handle or "Someone")[:200],
        "author_handle": (handle or None),
        "author_picture": picture or None,
        "author_external_id": str(ext) if ext else None,
    }


async def ingest_event(db: AsyncSession, payload: dict) -> str:
    """One Zernio inbox webhook. Returns a short word for logs and tests."""
    event = payload.get("event", "")
    acc = await _account(db, (payload.get("account") or {}).get("accountId"))
    if acc is None:
        return "unknown-account"
    if event == "comment.received":
        c = payload.get("comment") or {}
        post = payload.get("post") or {}
        author = c.get("author") or {}
        _item, created = await upsert(
            db,
            acc,
            "comment",
            c.get("id") or "",
            thread_id=c.get("postId") or post.get("id"),
            parent_external_id=c.get("parentCommentId"),
            direction="outgoing" if author.get("isOwnAccount") else "incoming",
            text=c.get("text") or "",
            permalink=post.get("permalink"),
            post={
                "id": post.get("id"),
                "content": post.get("content"),
                "image": post.get("imageUrl"),
                "permalink": post.get("permalink"),
            },
            attachments=[c["attachment"]] if c.get("attachment") else [],
            raw=payload,
            received_at=_dt(c.get("createdAt")) or datetime.now(UTC),
            **_author(
                author.get("name"), author.get("username"), author.get("picture"), author.get("id")
            ),
        )
    elif event == "message.received":
        m = payload.get("message") or {}
        s = m.get("sender") or {}
        _item, created = await upsert(
            db,
            acc,
            "message",
            m.get("id") or m.get("platformMessageId") or "",
            thread_id=m.get("conversationId") or (payload.get("conversation") or {}).get("id"),
            direction=m.get("direction") or "incoming",
            text=m.get("text") or "",
            attachments=m.get("attachments") or [],
            raw=payload,
            received_at=_dt(m.get("sentAt")) or datetime.now(UTC),
            **_author(s.get("name"), s.get("username"), s.get("picture"), s.get("id")),
        )
    elif event.startswith("review."):
        r = payload.get("review") or {}
        rid = str(r.get("id") or "")
        reviewer = r.get("reviewer") or {}
        thread = (
            rid.rsplit("/reviews/", 1)[0]
            if "/reviews/" in rid
            else (r.get("locationId") or r.get("locationName") or acc.external_id)
        )
        reply = r.get("reply") or None
        item, created = await upsert(
            db,
            acc,
            "review",
            rid,
            thread_id=str(thread)[:255],
            text=r.get("text") or "",
            rating=int(r["rating"]) if r.get("rating") is not None else None,
            permalink=r.get("reviewUrl"),
            post={"location": r.get("locationName")},
            raw=payload,
            received_at=_dt(r.get("created")) or datetime.now(UTC),
            replied_at=_dt(reply.get("created")) if isinstance(reply, dict) else None,
            **_author(reviewer.get("name"), None, reviewer.get("profileImage"), reviewer.get("id")),
        )
        if event == "review.deleted":
            item.status = "archived"
    else:
        return "ignored"
    await db.commit()
    await events.publish("inbox", acc.brand_id)
    return "created" if created else "updated"


# ---- sync: what webhooks missed ------------------------------------------------------------------
async def sync_brand(
    db: AsyncSession, brand: Brand, adapter: ZernioAdapter | None = None, days: int = 7
) -> dict:
    adapter = adapter or ZernioAdapter()
    accounts = (
        (
            await db.execute(
                select(SocialAccount).where(
                    SocialAccount.brand_id == brand.id,
                    SocialAccount.provider == "zernio",
                    SocialAccount.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    by_ext = {a.external_id: a for a in accounts}
    out = {"new": 0, "updated": 0, "errors": []}
    if not by_ext or not adapter.is_configured():
        return out
    since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()

    async def put(acc: SocialAccount, kind: str, ext: str, **fields) -> None:
        _item, created = await upsert(db, acc, kind, ext, **fields)
        out["new" if created else "updated"] += 1

    try:  # comments: the posts with comments, then each post's comments (replies included)
        for row in await adapter.commented_posts(set(by_ext), since=since, limit=30):
            acc = by_ext.get(row.get("accountId"))
            if not acc:
                continue
            data = await adapter.post_comments(str(row.get("id")), acc.external_id)
            stack = list(data.get("comments") or [])
            while stack:
                c = stack.pop(0)
                frm = c.get("from") or {}
                await put(
                    acc,
                    "comment",
                    str(c.get("id")),
                    thread_id=str(row.get("id")),
                    parent_external_id=c.get("parentId"),
                    direction="outgoing" if frm.get("isOwner") else "incoming",
                    text=c.get("message") or c.get("text") or "",
                    permalink=c.get("url") or row.get("permalink"),
                    received_at=_dt(c.get("createdTime")) or datetime.now(UTC),
                    post={
                        "id": row.get("id"),
                        "content": row.get("content"),
                        "image": row.get("picture"),
                        "permalink": row.get("permalink"),
                    },
                    raw=c,
                    **_author(
                        frm.get("name"), frm.get("username"), frm.get("picture"), frm.get("id")
                    ),
                )
                for rep in c.get("replies") or []:
                    rep.setdefault("parentId", c.get("id"))
                    stack.append(rep)
    except PlatformError as e:
        out["errors"].append(f"comments: {e}")
    try:
        for conv in await adapter.conversations(set(by_ext)):
            acc = by_ext.get(conv.get("accountId"))
            if not acc:
                continue
            for m in await adapter.conversation_messages(str(conv.get("id")), acc.external_id):
                incoming = (m.get("direction") or "incoming") == "incoming"
                await put(
                    acc,
                    "message",
                    str(m.get("id")),
                    thread_id=str(conv.get("id")),
                    direction="incoming" if incoming else "outgoing",
                    text=m.get("message") or m.get("text") or "",
                    attachments=m.get("attachments") or [],
                    raw=m,
                    received_at=_dt(m.get("createdAt")) or datetime.now(UTC),
                    **_author(
                        m.get("senderName") if incoming else acc.handle,
                        conv.get("participantName") if incoming else None,
                        conv.get("participantPicture") if incoming else None,
                        m.get("senderId"),
                    ),
                )
    except PlatformError as e:
        out["errors"].append(f"messages: {e}")
    try:
        for r in await adapter.reviews(set(by_ext)):
            acc = by_ext.get(r.get("accountId"))
            if not acc:
                continue
            rid = str(r.get("id"))
            reviewer = r.get("reviewer") or {}
            reply = r.get("reply") if isinstance(r.get("reply"), dict) else None
            await put(
                acc,
                "review",
                rid,
                thread_id=(
                    rid.rsplit("/reviews/", 1)[0]
                    if "/reviews/" in rid
                    else str(r.get("locationId") or acc.external_id)
                )[:255],
                text=r.get("text") or "",
                rating=int(r["rating"]) if r.get("rating") is not None else None,
                permalink=r.get("reviewUrl"),
                post={"location": r.get("locationName")},
                raw=r,
                received_at=_dt(r.get("created")) or datetime.now(UTC),
                replied_at=(_dt(reply.get("created")) or datetime.now(UTC))
                if (reply or r.get("hasReply"))
                else None,
                **_author(
                    reviewer.get("name"), None, reviewer.get("profileImage"), reviewer.get("id")
                ),
            )
    except PlatformError as e:
        out["errors"].append(f"reviews: {e}")
    try:
        for m in await adapter.mentions(set(by_ext)):
            acc = by_ext.get(m.get("accountId"))
            if not acc:
                continue
            await put(
                acc,
                "mention",
                str(m.get("id")),
                thread_id=str(m.get("postId") or m.get("mediaId") or ""),
                text=m.get("content") or "",
                permalink=m.get("permalink"),
                raw=m,
                received_at=_dt(m.get("publishedAt") or m.get("createdAt")) or datetime.now(UTC),
                post={"type": m.get("type")},
                **_author(
                    m.get("authorName"),
                    m.get("authorUsername"),
                    m.get("authorPicture"),
                    m.get("authorUrn"),
                ),
            )
    except PlatformError as e:
        out["errors"].append(f"mentions: {e}")
    await db.commit()
    if out["new"]:
        await events.publish("inbox", brand.id)
    return out


async def sync_all(db: AsyncSession) -> dict:
    total = {"new": 0, "updated": 0, "errors": []}
    for brand in (await db.execute(select(Brand))).scalars().all():
        try:
            r = await sync_brand(db, brand)
        except Exception as e:  # one brand's trouble never stops the others
            log.exception("Inbox sync failed for %s", brand.slug)
            r = {"new": 0, "updated": 0, "errors": [str(e)]}
            await db.rollback()
        for k in ("new", "updated"):
            total[k] += r[k]
        total["errors"] += [f"{brand.slug}: {e}" for e in r["errors"]]
    return total


# ---- AI: labels and suggestions ------------------------------------------------------------------------
def _ai(fast: bool = False) -> ai_svc.ContentAI:
    s = get_settings()
    return ai_svc.ContentAI(model=s.ai_model_fast if fast else None)


async def classify_pending(db: AsyncSession, limit: int = 50) -> int:
    """Label open, unlabelled incoming items with sentiment and intent, brand by brand."""
    rows = (
        (
            await db.execute(
                select(InboxItem)
                .where(
                    InboxItem.direction == "incoming",
                    InboxItem.classified_at.is_(None),
                    InboxItem.status == "open",
                )
                .order_by(InboxItem.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0
    done = 0
    now = datetime.now(UTC)
    blank = [it for it in rows if not (it.text or "").strip()]
    for it in blank:  # a star-only review or an attachment-only message: nothing for a model to read
        it.sentiment = "positive" if (it.rating or 0) >= 4 else "negative" if it.rating and it.rating <= 2 else "neutral"
        it.intent, it.classified_at = "other", now
        done += 1
    rows = [it for it in rows if it not in blank]
    if blank:
        await db.commit()
    if not rows:
        return done
    try:
        ai = _ai(fast=True)
    except ai_svc.AIUnavailable:
        return done
    by_brand: dict[int, list[InboxItem]] = {}
    for it in rows:
        by_brand.setdefault(it.brand_id, []).append(it)
    for brand_id, items in by_brand.items():
        brand = await db.get(Brand, brand_id)
        payload = [
            {"id": it.id, "kind": it.kind, "text": it.text[:1000], "rating": it.rating}
            for it in items
        ]
        try:
            labels = await ai.classify_inbox(brand, payload)
        except ai_svc.AIUnavailable as e:
            log.warning("Inbox classification failed for %s: %s; items marked neutral", brand.slug, e)
            labels = []
        labelled = {int(lab.get("id", 0)) for lab in labels}
        for it in items:  # one attempt: what the model did not label is neutral/other, not retried every five minutes
            if it.id not in labelled:
                it.sentiment, it.intent, it.classified_at = "neutral", "other", datetime.now(UTC)
        by_id = {it.id: it for it in items}
        now = datetime.now(UTC)
        for lab in labels:
            it = by_id.get(int(lab.get("id", 0)))
            if not it:
                continue
            it.sentiment = (
                lab.get("sentiment")
                if lab.get("sentiment") in ("positive", "neutral", "negative")
                else "neutral"
            )
            it.intent = (
                lab.get("intent")
                if lab.get("intent") in ("question", "complaint", "praise", "lead", "spam", "other")
                else "other"
            )
            it.classified_at = now
            if it.status == "open" and not it.draft_reply:
                await apply_rules(db, it)
            done += 1
        await db.commit()
        await events.publish("inbox", brand_id)
    return done


async def thread_of(db: AsyncSession, item: InboxItem) -> list[InboxItem]:
    if not item.thread_id:
        return [item]
    return (
        (
            await db.execute(
                select(InboxItem)
                .where(
                    InboxItem.account_id == item.account_id,
                    InboxItem.kind == item.kind,
                    InboxItem.thread_id == item.thread_id,
                )
                .order_by(InboxItem.received_at, InboxItem.id)
            )
        )
        .scalars()
        .all()
    )


async def suggest(db: AsyncSession, brand: Brand, item: InboxItem) -> list[str]:
    ai = _ai()
    thread = [
        {"direction": t.direction, "author": t.author_name, "text": t.text}
        for t in (await thread_of(db, item))[-8:]
    ]
    replies = await ai.suggest_replies(
        brand,
        {
            "kind": item.kind,
            "author": item.author_name,
            "text": item.text,
            "rating": item.rating,
            "post": (item.post or {}).get("content"),
            "intent": item.intent,
            "sentiment": item.sentiment,
        },
        thread,
    )
    item.suggestions = [r.strip() for r in replies if r and r.strip()][:3]
    item.suggested_at = datetime.now(UTC)
    await db.commit()
    return item.suggestions


# ---- rules ----------------------------------------------------------------------------------------------------
def _matches(rule: InboxRule, item: InboxItem, platform: str) -> bool:
    if rule.kinds and item.kind not in rule.kinds:
        return False
    if rule.platforms and platform not in rule.platforms:
        return False
    if rule.keywords:
        low = (item.text or "").lower()
        if not any(k.lower() in low for k in rule.keywords if k):
            return False
    if rule.intents and item.intent not in rule.intents:
        return False
    if rule.sentiments and item.sentiment not in rule.sentiments:
        return False
    return bool(rule.keywords or rule.intents or rule.sentiments or rule.kinds or rule.platforms)


async def apply_rules(db: AsyncSession, item: InboxItem) -> InboxRule | None:
    if item.direction != "incoming" or item.draft_reply:
        return None
    rules = (
        (
            await db.execute(
                select(InboxRule)
                .where(InboxRule.brand_id == item.brand_id, InboxRule.enabled.is_(True))
                .order_by(InboxRule.id)
            )
        )
        .scalars()
        .all()
    )
    if not rules:
        return None
    acc = await db.get(SocialAccount, item.account_id)
    for rule in rules:
        if (rule.intents or rule.sentiments) and not item.classified_at:
            continue  # again after classification
        if not _matches(rule, item, acc.platform if acc else ""):
            continue
        text = rule.reply_text or ""
        if rule.saved_reply_id:
            sr = await db.get(SavedReply, rule.saved_reply_id)
            text = sr.body if sr else text
        if not text and not rule.assign_to_id:
            continue
        if text:
            item.draft_reply = text.replace(
                "{name}", item.author_name.split(" ")[0] if item.author_name else "there"
            )
            item.draft_rule_id = rule.id
        if rule.assign_to_id and not item.assignee_id:
            item.assignee_id = rule.assign_to_id
        rule.hits = (rule.hits or 0) + 1
        return rule
    return None


# ---- replying -----------------------------------------------------------------------------------------------------
class CannotReply(Exception):
    pass


async def reply(
    db: AsyncSession,
    brand: Brand,
    item: InboxItem,
    text: str,
    user: User,
    adapter: ZernioAdapter | None = None,
) -> InboxItem:
    text = text.strip()
    if not text:
        raise CannotReply("Write something first")
    acc = await db.get(SocialAccount, item.account_id)
    if acc is None or acc.provider != "zernio":
        raise CannotReply("Replies go out through Zernio; this channel is not connected there")
    adapter = adapter or ZernioAdapter()
    try:
        if item.kind == "comment":
            res = await adapter.reply(
                item.thread_id or "", acc.external_id, text, comment_id=item.external_id
            )
            new_ext = (res.get("data") or {}).get("commentId") or f"spark-{item.id}"
        elif item.kind == "message":
            res = await adapter.send_message(item.thread_id or "", acc.external_id, text)
            new_ext = (res.get("data") or {}).get("messageId") or f"spark-{item.id}"
        elif item.kind == "review":
            await adapter.reply_review(item.external_id, acc.external_id, text)
            new_ext = None
        else:
            raise CannotReply(
                "Mentions can be answered on the network; Spark cannot reply there yet"
            )
    except PlatformError as e:
        raise CannotReply(f"Reply failed: {e}") from e
    now = datetime.now(UTC)
    item.replied_at, item.reply_text, item.replied_by_id, item.status = (
        now,
        text,
        user.id,
        "resolved",
    )
    item.draft_reply, item.draft_rule_id = None, None
    if new_ext:
        await upsert(
            db,
            acc,
            item.kind,
            new_ext,
            thread_id=item.thread_id,
            parent_external_id=item.external_id if item.kind == "comment" else None,
            direction="outgoing",
            text=text,
            received_at=now,
            post=item.post,
            raw={},
            **_author(acc.display_name or acc.handle, acc.handle, acc.avatar_url),
        )
    activity.record(
        db,
        brand.id,
        user,
        "replied to",
        "inbox_item",
        item.id,
        f"{item.author_name}: {item.text[:80]}",
        {"kind": item.kind},
    )
    await db.commit()
    await events.publish("inbox", brand.id)
    return item


# ---- counts ----------------------------------------------------------------------------------------------------------
async def counts(db: AsyncSession, brand_id: int) -> dict:
    base = select(func.count(InboxItem.id)).where(
        InboxItem.brand_id == brand_id, InboxItem.direction == "incoming"
    )
    open_q = base.where(InboxItem.status == "open")
    out = {
        "open": await db.scalar(open_q) or 0,
        "drafts": await db.scalar(open_q.where(InboxItem.draft_reply.is_not(None))) or 0,
        "negative": await db.scalar(open_q.where(InboxItem.sentiment == "negative")) or 0,
        "resolved": await db.scalar(base.where(InboxItem.status == "resolved")) or 0,
    }
    rows = (
        await db.execute(
            select(InboxItem.kind, func.count(InboxItem.id))
            .where(
                InboxItem.brand_id == brand_id,
                InboxItem.direction == "incoming",
                InboxItem.status == "open",
            )
            .group_by(InboxItem.kind)
        )
    ).all()
    out["by_kind"] = {k: n for k, n in rows}
    return out


async def open_count(db: AsyncSession, brand_id: int) -> int:
    return (
        await db.scalar(
            select(func.count(InboxItem.id)).where(
                InboxItem.brand_id == brand_id,
                InboxItem.direction == "incoming",
                InboxItem.status == "open",
            )
        )
        or 0
    )


def platform_of(acc: SocialAccount) -> str:
    return from_zernio(acc.platform) if acc.provider == "zernio" else acc.platform


_unused = as_utc  # kept for callers that import it from here
