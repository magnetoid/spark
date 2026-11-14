"""Clicks on tracked links, added up per link and per campaign. No IP addresses are kept: a
click is its time, the post target it came from, the referrer and the browser's name."""

import csv
import io
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import (
    Brand,
    Campaign,
    LinkClick,
    Metric,
    Post,
    PostStatus,
    PostTarget,
    ShortLink,
    SocialAccount,
)
from spark.services.analytics import rate
from spark.services.links import short_url
from spark.services.publisher import as_utc
from spark.services.reports import _cell as cell

NOT_FROM_POST = "Not from a post"
DIRECT = "Direct or unknown"


def referrer_host(referrer: str | None) -> str:
    host = urlsplit(referrer or "").hostname or ""
    return host.removeprefix("www.") or DIRECT


def _counts(counter: Counter) -> list[dict]:
    return [{"key": k, "clicks": n} for k, n in counter.most_common()]


def _days(counter: Counter, start: date, end: date) -> list[dict]:
    out, d = [], start
    while d <= end:
        out.append({"day": d, "clicks": counter.get(d, 0)})
        d += timedelta(days=1)
    return out


async def _clicks(db: AsyncSession, link_ids: list[int], since: datetime | None = None):
    """(clicked_at, referrer, target_id, platform, post_id, post content) per click."""
    if not link_ids:
        return []
    stmt = (
        select(
            LinkClick.clicked_at,
            LinkClick.referrer,
            LinkClick.target_id,
            SocialAccount.platform,
            PostTarget.post_id,
            Post.content,
        )
        .outerjoin(PostTarget, PostTarget.id == LinkClick.target_id)
        .outerjoin(SocialAccount, SocialAccount.id == PostTarget.account_id)
        .outerjoin(Post, Post.id == PostTarget.post_id)
        .where(LinkClick.link_id.in_(link_ids))
    )
    if since is not None:
        stmt = stmt.where(LinkClick.clicked_at >= since)
    return (await db.execute(stmt)).all()


def _excerpt(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= 80 else text[:79] + "…"


def _breakdown(rows, tz: ZoneInfo) -> dict:
    by_day: Counter = Counter()
    by_platform: Counter = Counter()
    by_referrer: Counter = Counter()
    by_post: Counter = Counter()
    excerpts: dict[int, str] = {}
    for clicked_at, referrer, target_id, platform, post_id, content in rows:
        by_day[as_utc(clicked_at).astimezone(tz).date()] += 1
        by_platform[platform if target_id and platform else NOT_FROM_POST] += 1
        by_referrer[referrer_host(referrer)] += 1
        if post_id:
            by_post[post_id] += 1
            excerpts[post_id] = _excerpt(content)
    return {
        "by_day": by_day,
        "by_platform": _counts(by_platform),
        "by_referrer": _counts(by_referrer),
        "by_post": [
            {"post_id": pid, "excerpt": excerpts[pid], "clicks": n}
            for pid, n in by_post.most_common(20)
        ],
    }


async def link_stats(db: AsyncSession, brand: Brand, link: ShortLink, days: int = 30) -> dict:
    tz = ZoneInfo(brand.timezone or "UTC")
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    rows = await _clicks(db, [link.id], since)
    b = _breakdown(rows, tz)
    today = now.astimezone(tz).date()
    return {
        "days": days,
        "total": len(rows),
        **b,
        "by_day": _days(b["by_day"], today - timedelta(days=days - 1), today),
    }


async def campaign_links(db: AsyncSession, campaign: Campaign) -> list[ShortLink]:
    post_ids = select(Post.id).where(Post.campaign_id == campaign.id)
    return list(
        (
            await db.execute(
                select(ShortLink)
                .where(
                    ShortLink.brand_id == campaign.brand_id,
                    or_(ShortLink.campaign_id == campaign.id, ShortLink.post_id.in_(post_ids)),
                )
                .order_by(ShortLink.clicks.desc(), ShortLink.id.desc())
            )
        )
        .scalars()
        .all()
    )


async def _campaign_targets(db: AsyncSession, campaign: Campaign):
    """(target, account, post, latest metric or None) for the campaign's published targets."""
    latest = (
        select(Metric.target_id, func.max(Metric.captured_at).label("mx"))
        .group_by(Metric.target_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(PostTarget, SocialAccount, Post, Metric)
            .join(Post, Post.id == PostTarget.post_id)
            .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
            .outerjoin(latest, latest.c.target_id == PostTarget.id)
            .outerjoin(
                Metric,
                (Metric.target_id == PostTarget.id) & (Metric.captured_at == latest.c.mx),
            )
            .where(
                Post.campaign_id == campaign.id,
                Post.brand_id == campaign.brand_id,
                PostTarget.status == PostStatus.published,
            )
            .order_by(PostTarget.published_at.desc())
        )
    ).all()
    return rows


async def campaign_summary(db: AsyncSession, brand: Brand, campaign: Campaign) -> dict:
    tz = ZoneInfo(brand.timezone or "UTC")
    posts = (
        await db.execute(
            select(Post.status, func.count(Post.id))
            .where(Post.campaign_id == campaign.id, Post.is_autosave.is_(False))
            .group_by(Post.status)
        )
    ).all()
    by_status = {s: n for s, n in posts}
    targets = await _campaign_targets(db, campaign)
    seen = sum(m.seen for *_, m in targets if m is not None)
    engagements = sum(m.engagements for *_, m in targets if m is not None)
    links = await campaign_links(db, campaign)
    rows = await _clicks(db, [l.id for l in links])
    b = _breakdown(rows, tz)
    days = sorted(b["by_day"])
    return {
        "posts": sum(by_status.values()),
        "published": by_status.get(PostStatus.published, 0),
        "seen": seen,
        "engagements": engagements,
        "engagement_rate_pct": rate(engagements, seen) if seen else None,
        "link_clicks": sum(l.clicks for l in links),
        "links": links,
        "by_platform": b["by_platform"],
        "by_day": _days(b["by_day"], days[0], days[-1]) if days else [],
    }


async def campaign_csv(db: AsyncSession, campaign: Campaign) -> str:
    """One row per published post and channel, then one per link."""
    targets = await _campaign_targets(db, campaign)
    clicks = dict(
        (
            await db.execute(
                select(LinkClick.target_id, func.count(LinkClick.id))
                .where(LinkClick.target_id.in_([t.id for t, *_ in targets] or [0]))
                .group_by(LinkClick.target_id)
            )
        ).all()
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["kind", "name", "channel", "date", "url", "seen", "engagements", "link_clicks"])
    for t, acc, post, m in targets:
        w.writerow(
            map(
                cell,
                [
                    "post",
                    _excerpt(t.content_override or post.content),
                    f"{acc.platform} {acc.handle or ''}".strip(),
                    as_utc(t.published_at).isoformat() if t.published_at else "",
                    t.remote_url or "",
                    m.seen if m else "",
                    m.engagements if m else "",
                    clicks.get(t.id, 0),
                ],
            )
        )
    for link in await campaign_links(db, campaign):
        w.writerow(
            map(
                cell,
                [
                    "link",
                    link.title or link.code,
                    "",
                    as_utc(link.created_at).isoformat() if link.created_at else "",
                    short_url(link),
                    "",
                    "",
                    link.clicks,
                ],
            )
        )
    return buf.getvalue()
