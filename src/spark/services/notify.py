"""Team notifications by email: failed posts, posts awaiting approval, weekly digest.

Recipients are Spark users; each opts in or out on the Preferences page
(`User.prefs`: notify_failed, notify_approvals, digest_weekly — all default on).
Sending happens from the worker so the web request path never waits on SMTP.
"""

from __future__ import annotations

import html
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.config import get_settings
from spark.models import Brand, Post, PostStatus, PostTarget, SocialAccount, User
from spark.services import analytics
from spark.services.email import EmailSender, get_sender

log = logging.getLogger(__name__)


def wants(user: User, key: str, default: bool = True) -> bool:
    return bool((user.prefs or {}).get(key, default))


def _base() -> str:
    return get_settings().base_url.rstrip("/")


def layout(title: str, intro: str, body: str, cta_url: str | None = None, cta_label: str = "Open Spark") -> str:
    cta = (f'<p style="margin:24px 0"><a href="{cta_url}" style="background:#171717;color:#fff;padding:10px 16px;'
           f'border-radius:8px;text-decoration:none;font-weight:600">{html.escape(cta_label)}</a></p>' if cta_url else "")
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto;'
        'padding:24px;color:#111;line-height:1.55">'
        f'<h1 style="font-size:20px;margin:0 0 8px">{html.escape(title)}</h1>'
        f'<p style="color:#555;margin:0 0 16px">{intro}</p>{body}{cta}'
        '<hr style="border:none;border-top:1px solid #eee;margin:32px 0 12px">'
        f'<p style="font-size:12px;color:#888">Sent by Spark. Change what you receive under '
        f'<a href="{_base()}/me" style="color:#888">Preferences</a>.</p></div>'
    )


def _rows(items: list[tuple[str, str]]) -> str:
    return "".join(
        f'<div style="padding:10px 0;border-bottom:1px solid #eee"><div>{html.escape(head)}</div>'
        f'<div style="font-size:13px;color:#666">{html.escape(sub)}</div></div>' for head, sub in items)


async def _users(db: AsyncSession) -> list[User]:
    return (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()


async def notify_failed(db: AsyncSession, sender: EmailSender | None = None) -> int:
    """Email editors and owners about targets that failed for good since the last run."""
    sender = sender or get_sender()
    rows = (await db.execute(
        select(PostTarget).where(PostTarget.status == PostStatus.failed, PostTarget.notified_at.is_(None))
        .options(selectinload(PostTarget.post), selectinload(PostTarget.account)))).scalars().all()
    if not rows:
        return 0
    by_brand: dict[int, list[PostTarget]] = {}
    for t in rows:
        by_brand.setdefault(t.account.brand_id, []).append(t)
    users = [u for u in await _users(db) if u.can_edit() and wants(u, "notify_failed")]
    sent = 0
    for brand_id, targets in by_brand.items():
        brand = await db.get(Brand, brand_id)
        items = [((t.post.content or "(no text)")[:90], f"{t.account.handle} · {t.account.platform} — {t.error or 'unknown error'}"[:200])
                 for t in targets]
        n = len(targets)
        subject = f"[{brand.name}] {n} post{'s' if n != 1 else ''} failed to publish"
        body = layout(subject, "Spark could not publish these after retrying. Fix the cause and press Retry.",
                      _rows(items), f"{_base()}/posts?status=failed", "Review failed posts")
        for u in users:
            try:
                await sender.send(u.email, subject, body)
                sent += 1
            except Exception:
                log.exception("Failed-post notification to %s failed", u.email)
        now = datetime.now(UTC)
        for t in targets:
            t.notified_at = now
    await db.commit()
    return sent


async def notify_approvals(db: AsyncSession, sender: EmailSender | None = None) -> int:
    """Email owners once per post that waits for their approval."""
    sender = sender or get_sender()
    posts = (await db.execute(
        select(Post).where(Post.status == PostStatus.pending_approval, Post.approval_notified_at.is_(None),
                           Post.is_autosave.is_(False)))).scalars().all()
    if not posts:
        return 0
    owners = [u for u in await _users(db) if u.can_approve() and wants(u, "notify_approvals")]
    sent = 0
    by_brand: dict[int, list[Post]] = {}
    for p in posts:
        by_brand.setdefault(p.brand_id, []).append(p)
    for brand_id, group in by_brand.items():
        brand = await db.get(Brand, brand_id)
        tz = ZoneInfo(brand.timezone)
        items = []
        for p in group:
            author = await db.get(User, p.author_id) if p.author_id else None
            when = p.scheduled_at.astimezone(tz).strftime("%a %b %d, %H:%M") if p.scheduled_at else "unscheduled"
            channels = ", ".join(t.account.handle for t in p.targets)
            items.append(((p.content or "(no text)")[:90], f"by {author.name if author else 'someone'} · {when} · {channels}"))
        n = len(group)
        subject = f"[{brand.name}] {n} post{'s' if n != 1 else ''} waiting for your approval"
        body = layout(subject, "Nothing goes out until an owner approves it.", _rows(items),
                      f"{_base()}/queue?tab=approvals", "Open approvals")
        for u in owners:
            try:
                await sender.send(u.email, subject, body)
                sent += 1
            except Exception:
                log.exception("Approval notification to %s failed", u.email)
        now = datetime.now(UTC)
        for p in group:
            p.approval_notified_at = now
    await db.commit()
    return sent


def _n(v: float) -> str:
    return f"{v:,.0f}"


async def weekly_digest(db: AsyncSession, sender: EmailSender | None = None, days: int = 7) -> int:
    """One email per user per brand: last week's numbers and what is coming up."""
    sender = sender or get_sender()
    users = [u for u in await _users(db) if wants(u, "digest_weekly")]
    if not users:
        return 0
    brands = (await db.execute(select(Brand).order_by(Brand.name))).scalars().all()
    sent = 0
    for brand in brands:
        has_accounts = await db.scalar(select(SocialAccount.id).where(SocialAccount.brand_id == brand.id).limit(1))
        if not has_accounts:
            continue
        data = await analytics.overview(db, brand.id, days)
        prev = await analytics.compare(db, brand.id, days)
        horizon = datetime.now(UTC) + timedelta(days=days)
        upcoming_n = await db.scalar(select(func.count(Post.id)).where(
            Post.brand_id == brand.id, Post.status == PostStatus.scheduled, Post.scheduled_at <= horizon)) or 0

        def delta(pct: float | None) -> str:
            return f" ({'+' if pct > 0 else ''}{pct:.0f}% vs the week before)" if isinstance(pct, (int, float)) else ""

        pub_pct = analytics._pct(data["published"], prev["published_prev"]) if prev.get("published_prev") else None
        stats = [
            ("Published", f"{data['published']} post{'s' if data['published'] != 1 else ''}{delta(pub_pct)}"),
            ("Impressions", _n(data["totals"]["impressions"]) + delta(prev["impressions"])),
            ("Engagements", f"{_n(data['engagements'])} · {data['engagement_rate']:.1f}% rate{delta(prev['engagements'])}"),
            ("Link clicks", _n(data["link_clicks"])),
            ("Coming up", f"{upcoming_n} scheduled for the next {days} days"
                          + (f" · {data['failed']} failed — needs attention" if data["failed"] else "")),
        ]
        top = [((t["target"].post.content or "(no text)")[:80] if t["target"].post else "(post)",
                f"{t['account'].handle} · {_n(t['engagements'])} engagements") for t in data["top"][:3]]
        body = (
            '<table style="width:100%;border-collapse:collapse;font-size:14px">'
            + "".join(f'<tr><td style="padding:6px 0;color:#666;width:40%">{html.escape(k)}</td>'
                      f'<td style="padding:6px 0;font-weight:600">{html.escape(v)}</td></tr>' for k, v in stats)
            + "</table>"
            + (f'<h2 style="font-size:15px;margin:20px 0 4px">Top posts</h2>{_rows(top)}' if top else "")
        )
        subject = f"[{brand.name}] Your week on social"
        intro = f"{brand.name}, {(datetime.now(UTC) - timedelta(days=days)):%b %d} – {datetime.now(UTC):%b %d}."
        email_html = layout(subject, intro, body, f"{_base()}/analytics", "Open analytics")
        for u in users:
            try:
                await sender.send(u.email, subject, email_html)
                sent += 1
            except Exception:
                log.exception("Digest to %s failed", u.email)
    return sent
