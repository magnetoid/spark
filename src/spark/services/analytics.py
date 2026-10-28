"""Metric ingestion from platforms and dashboard aggregations."""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.models import (
    LinkClick,
    Metric,
    Post,
    PostStatus,
    PostTarget,
    ShortLink,
    SocialAccount,
)
from spark.platforms import PlatformError, adapter_for
from spark.services.publisher import as_utc

log = logging.getLogger(__name__)


async def collect_metrics(db: AsyncSession, max_age_days: int = 30) -> int:
    since = datetime.now(UTC) - timedelta(days=max_age_days)
    rows = (
        await db.execute(
            select(PostTarget).where(
                PostTarget.status == PostStatus.published,
                PostTarget.published_at >= since,
                PostTarget.remote_id.is_not(None),
            )
        )
    ).scalars().all()
    by_account: dict[int, list[PostTarget]] = defaultdict(list)
    for t in rows:
        by_account[t.account_id].append(t)
    now, saved = datetime.now(UTC), 0
    for account_id, targets in by_account.items():
        account = await db.get(SocialAccount, account_id)
        if not account or not account.is_active:
            continue
        adapter = adapter_for(account)
        try:
            snaps = await adapter.fetch_metrics(account, [t.remote_id for t in targets])
            # Zernio resolves native URLs after publish; backfill the ones we lack
            if account.provider == "zernio":
                for t in targets:
                    if not t.remote_url and hasattr(adapter, "resolve_url"):
                        t.remote_url = await adapter.resolve_url(t.remote_id)
        except PlatformError as e:
            log.warning("Metrics for account %s failed: %s", account_id, e)
            continue
        by_remote = {t.remote_id: t for t in targets}
        for s in snaps:
            if t := by_remote.get(s.remote_id):
                db.add(
                    Metric(
                        target_id=t.id,
                        captured_at=now,
                        impressions=s.impressions,
                        likes=s.likes,
                        comments=s.comments,
                        shares=s.shares,
                        clicks=s.clicks,
                    )
                )
                saved += 1
    await db.commit()
    return saved


async def _latest_metrics(db: AsyncSession, brand_id: int, since: datetime, until: datetime | None = None):
    """Latest snapshot per target for a brand's targets published since `since`."""
    sub = (
        select(Metric.target_id, func.max(Metric.captured_at).label("mx"))
        .group_by(Metric.target_id)
        .subquery()
    )
    stmt = (
        select(Metric, PostTarget, SocialAccount)
        .join(sub, (sub.c.target_id == Metric.target_id) & (sub.c.mx == Metric.captured_at))
        .join(PostTarget, PostTarget.id == Metric.target_id)
        .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
        .where(SocialAccount.brand_id == brand_id, PostTarget.published_at >= since)
        .options(selectinload(PostTarget.post))  # templates read target.text -> post.content
    )
    if until is not None:
        stmt = stmt.where(PostTarget.published_at < until)
    return (await db.execute(stmt)).all()


def _pct(cur: float, prev: float) -> float | None:
    if not prev:
        return None if not cur else 100.0
    return round((cur - prev) / prev * 100, 1)


async def compare(db: AsyncSession, brand_id: int, days: int = 30) -> dict:
    """Totals for the last `days` vs the `days` before, for the dashboard trend badges."""
    now = datetime.now(UTC)
    since, prev_since = now - timedelta(days=days), now - timedelta(days=2 * days)

    def totals(rows) -> dict:
        t = dict(impressions=0, engagements=0, posts=0)
        for m, _target, _acc in rows:
            t["impressions"] += m.impressions
            t["engagements"] += m.engagements
            t["posts"] += 1
        return t

    cur = totals(await _latest_metrics(db, brand_id, since))
    prev = totals(await _latest_metrics(db, brand_id, prev_since, since))
    published_prev = await db.scalar(
        select(func.count(PostTarget.id))
        .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
        .where(SocialAccount.brand_id == brand_id, PostTarget.status == PostStatus.published,
               PostTarget.published_at >= prev_since, PostTarget.published_at < since)
    ) or 0
    return {
        "impressions": _pct(cur["impressions"], prev["impressions"]),
        "engagements": _pct(cur["engagements"], prev["engagements"]),
        "published_prev": published_prev,
        "rate": (cur["engagements"] / cur["impressions"] * 100) if cur["impressions"] else 0,
        "rate_prev": (prev["engagements"] / prev["impressions"] * 100) if prev["impressions"] else 0,
    }


async def overview(db: AsyncSession, brand_id: int, days: int = 30) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await _latest_metrics(db, brand_id, since)
    totals = dict(impressions=0, likes=0, comments=0, shares=0, clicks=0)
    by_platform: dict[str, dict] = defaultdict(lambda: dict(impressions=0, engagements=0, posts=0))
    by_day: dict[str, dict] = defaultdict(lambda: dict(impressions=0, engagements=0))
    top = []
    for m, t, a in rows:
        for k in totals:
            totals[k] += getattr(m, k)
        p = by_platform[a.platform]
        p["impressions"] += m.impressions
        p["engagements"] += m.engagements
        p["posts"] += 1
        day = as_utc(t.published_at).date().isoformat()
        by_day[day]["impressions"] += m.impressions
        by_day[day]["engagements"] += m.engagements
        top.append((m.engagements, t, a, m))
    top.sort(key=lambda r: r[0], reverse=True)

    published = await db.scalar(
        select(func.count(PostTarget.id))
        .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
        .where(
            SocialAccount.brand_id == brand_id,
            PostTarget.status == PostStatus.published,
            PostTarget.published_at >= since,
        )
    )
    scheduled = await db.scalar(
        select(func.count(Post.id)).where(
            Post.brand_id == brand_id, Post.status == PostStatus.scheduled
        )
    )
    failed = await db.scalar(
        select(func.count(Post.id)).where(Post.brand_id == brand_id, Post.status == PostStatus.failed)
    )
    followers = await db.scalar(
        select(func.coalesce(func.sum(SocialAccount.followers), 0)).where(
            SocialAccount.brand_id == brand_id, SocialAccount.is_active.is_(True)
        )
    )
    link_clicks = await db.scalar(
        select(func.count(LinkClick.id))
        .join(ShortLink, ShortLink.id == LinkClick.link_id)
        .where(ShortLink.brand_id == brand_id, LinkClick.clicked_at >= since)
    )
    engagements = totals["likes"] + totals["comments"] + totals["shares"] + totals["clicks"]
    days_axis = [(since + timedelta(days=i + 1)).date().isoformat() for i in range(days)]
    return {
        "totals": totals,
        "engagements": engagements,
        "engagement_rate": (engagements / totals["impressions"] * 100) if totals["impressions"] else 0,
        "published": published or 0,
        "scheduled": scheduled or 0,
        "failed": failed or 0,
        "followers": followers or 0,
        "link_clicks": link_clicks or 0,
        "by_platform": dict(by_platform),
        "series": {
            "days": days_axis,
            "impressions": [by_day[d]["impressions"] for d in days_axis],
            "engagements": [by_day[d]["engagements"] for d in days_axis],
        },
        "top": [
            {"target": t, "account": a, "metric": m, "engagements": e} for e, t, a, m in top[:10]
        ],
    }


async def link_clicks_series(db: AsyncSession, brand_id: int, days: int = 30) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await db.execute(
            select(LinkClick.clicked_at)
            .join(ShortLink, ShortLink.id == LinkClick.link_id)
            .where(ShortLink.brand_id == brand_id, LinkClick.clicked_at >= since)
        )
    ).all()
    counts: dict[str, int] = defaultdict(int)
    for (ts,) in rows:
        counts[as_utc(ts).date().isoformat()] += 1
    axis = [(since + timedelta(days=i + 1)).date().isoformat() for i in range(days)]
    return {"days": axis, "clicks": [counts[d] for d in axis]}
