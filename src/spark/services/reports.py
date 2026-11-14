"""Reports: a period's numbers, frozen, with a previous-period comparison, follower growth, the
inbox's load, and an AI summary of what worked and what to do next."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import secrets
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import (
    Brand,
    ContentPillar,
    FollowerSnapshot,
    InboxItem,
    LinkClick,
    Post,
    PostStatus,
    PostTarget,
    Report,
    ShareLink,
    ShortLink,
    SocialAccount,
    User,
)
from spark.platforms.base import PlatformError
from spark.platforms.zernio import ZernioAdapter
from spark.services import activity
from spark.services import ai as ai_svc
from spark.services.analytics import _latest_metrics, _pct, rate
from spark.services.publisher import as_utc

log = logging.getLogger("spark.reports")


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min, tzinfo=UTC), datetime.combine(
        end + timedelta(days=1), time.min, tzinfo=UTC
    )


async def _period(db: AsyncSession, brand: Brand, start: date, end: date) -> dict:
    since, until = _bounds(start, end)
    rows = await _latest_metrics(db, brand.id, since, until)
    totals = dict(impressions=0, likes=0, comments=0, shares=0, clicks=0, engagements=0, seen=0)
    # Empty when no post in the period has the number; the networks report these unevenly
    wide: dict[str, int | None] = dict(reach=None, views=None, saves=None)
    link_clicks = await _link_clicks(db, brand, since, until)
    by_channel: dict[int, dict] = {}
    by_day: dict[str, dict] = defaultdict(lambda: dict(impressions=0, engagements=0, posts=0))
    by_pillar: dict[int | None, int] = defaultdict(int)
    top = []
    for m, t, a in rows:
        for k in ("impressions", "likes", "comments", "shares", "clicks"):
            totals[k] += getattr(m, k)
        for k in wide:
            if getattr(m, k) is not None:
                wide[k] = (wide[k] or 0) + getattr(m, k)
        totals["engagements"] += m.engagements
        totals["seen"] += m.seen
        c = by_channel.setdefault(
            a.id,
            {
                "account_id": a.id,
                "platform": a.platform,
                "handle": a.handle,
                "posts": 0,
                "impressions": 0,
                "seen": 0,
                "engagements": 0,
            },
        )
        c["posts"] += 1
        c["impressions"] += m.impressions
        c["seen"] += m.seen
        c["engagements"] += m.engagements
        day = as_utc(t.published_at).date().isoformat()
        by_day[day]["impressions"] += m.impressions
        by_day[day]["engagements"] += m.engagements
        by_day[day]["posts"] += 1
        by_pillar[t.post.pillar_id] += 1
        top.append(
            {
                "post_id": t.post_id,
                "content": (t.post.content or "")[:200],
                "platform": a.platform,
                "handle": a.handle,
                "published_at": as_utc(t.published_at).isoformat(),
                "url": t.remote_url,
                "impressions": m.impressions,
                "seen": m.seen,
                "engagements": m.engagements,
                "link_clicks": link_clicks["by_target"].get(t.id, 0),
            }
        )
    published = (
        await db.scalar(
            select(func.count(PostTarget.id))
            .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
            .where(
                SocialAccount.brand_id == brand.id,
                PostTarget.status == PostStatus.published,
                PostTarget.published_at >= since,
                PostTarget.published_at < until,
            )
        )
        or 0
    )
    for c in by_channel.values():
        c["engagement_rate_pct"] = rate(c["engagements"], c["seen"])
    totals["published"] = published
    totals.update(wide)
    totals["link_clicks"] = link_clicks["total"]
    totals["engagement_rate_pct"] = rate(totals["engagements"], totals["seen"])
    days = []
    d = start
    while d <= end:
        key = d.isoformat()
        days.append({"day": key, **by_day.get(key, dict(impressions=0, engagements=0, posts=0))})
        d += timedelta(days=1)
    top.sort(key=lambda r: r["engagements"], reverse=True)
    return {
        "totals": totals,
        "channels": sorted(by_channel.values(), key=lambda c: c["engagements"], reverse=True),
        "series": days,
        "top_posts": top[:10],
        "pillars": dict(by_pillar),
    }


async def _link_clicks(db: AsyncSession, brand: Brand, since: datetime, until: datetime) -> dict:
    """Clicks on the brand's short links in the period, all and per published post target."""
    rows = (
        await db.execute(
            select(LinkClick.target_id, func.count(LinkClick.id))
            .join(ShortLink, ShortLink.id == LinkClick.link_id)
            .where(
                ShortLink.brand_id == brand.id,
                LinkClick.clicked_at >= since,
                LinkClick.clicked_at < until,
            )
            .group_by(LinkClick.target_id)
        )
    ).all()
    return {
        "total": sum(n for _, n in rows),
        "by_target": {tid: n for tid, n in rows if tid is not None},
    }


async def _followers(db: AsyncSession, brand: Brand, start: date, end: date) -> dict:
    accounts = (
        (
            await db.execute(
                select(SocialAccount.id).where(
                    SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    if not accounts:
        return {"start": 0, "end": 0, "delta": 0, "series": [], "by_channel": []}
    rows = (
        (
            await db.execute(
                select(FollowerSnapshot)
                .where(
                    FollowerSnapshot.account_id.in_(accounts),
                    FollowerSnapshot.day >= start - timedelta(days=7),
                    FollowerSnapshot.day <= end,
                )
                .order_by(FollowerSnapshot.day)
            )
        )
        .scalars()
        .all()
    )
    # per account: the last known count on or before each day; summed across accounts
    per_day: dict[date, dict[int, int]] = defaultdict(dict)
    for s in rows:
        per_day[s.day][s.account_id] = s.followers
    last: dict[int, int] = {}
    series = []
    d = start - timedelta(days=7)
    first_total = None
    while d <= end:
        last.update(per_day.get(d, {}))
        if d >= start and last:
            total = sum(last.values())
            series.append({"day": d.isoformat(), "followers": total})
            if first_total is None:
                first_total = total
        d += timedelta(days=1)
    end_total = series[-1]["followers"] if series else 0
    # Per channel: the first count known in the period (or just before it) and the last one
    first: dict[int, int] = {}
    latest: dict[int, int] = {}
    for snap in rows:
        if snap.day <= start or snap.account_id not in first:
            first[snap.account_id] = snap.followers
        latest[snap.account_id] = snap.followers
    meta = {
        a.id: a
        for a in (
            await db.execute(select(SocialAccount).where(SocialAccount.id.in_(list(latest))))
        ).scalars()
    }
    by_channel = sorted(
        (
            {
                "account_id": aid,
                "platform": meta[aid].platform,
                "handle": meta[aid].handle,
                "start": first[aid],
                "end": latest[aid],
                "delta": latest[aid] - first[aid],
            }
            for aid in latest
            if aid in meta
        ),
        key=lambda c: c["delta"],
        reverse=True,
    )
    return {
        "start": first_total or 0,
        "end": end_total,
        "delta": end_total - (first_total or 0),
        "series": series,
        "by_channel": by_channel,
    }


async def _inbox(db: AsyncSession, brand: Brand, start: date, end: date) -> dict:
    since, until = _bounds(start, end)
    base = select(func.count(InboxItem.id)).where(
        InboxItem.brand_id == brand.id,
        InboxItem.direction == "incoming",
        InboxItem.received_at >= since,
        InboxItem.received_at < until,
    )
    received = await db.scalar(base) or 0
    replied = await db.scalar(base.where(InboxItem.replied_at.is_not(None))) or 0
    negative = await db.scalar(base.where(InboxItem.sentiment == "negative")) or 0
    kinds = (
        await db.execute(
            select(InboxItem.kind, func.count(InboxItem.id))
            .where(
                InboxItem.brand_id == brand.id,
                InboxItem.direction == "incoming",
                InboxItem.received_at >= since,
                InboxItem.received_at < until,
            )
            .group_by(InboxItem.kind)
        )
    ).all()
    waits = [
        (as_utc(done) - as_utc(got)).total_seconds() / 60
        for got, done in (
            await db.execute(
                select(InboxItem.received_at, InboxItem.replied_at).where(
                    InboxItem.brand_id == brand.id,
                    InboxItem.direction == "incoming",
                    InboxItem.received_at >= since,
                    InboxItem.received_at < until,
                    InboxItem.replied_at.is_not(None),
                )
            )
        ).all()
        if done >= got
    ]
    return {
        "received": received,
        "replied": replied,
        "negative": negative,
        "by_kind": {k: n for k, n in kinds},
        "median_reply_minutes": round(statistics.median(waits)) if waits else None,
    }


async def build(db: AsyncSession, brand: Brand, start: date, end: date) -> dict:
    cur = await _period(db, brand, start, end)
    span = (end - start).days + 1
    prev = await _period(db, brand, start - timedelta(days=span), start - timedelta(days=1))
    compare = {
        k: {
            "current": cur["totals"][k],
            "previous": prev["totals"][k],
            "pct": _pct(cur["totals"][k], prev["totals"][k]) if prev["totals"][k] else None,
        }
        for k in ("published", "impressions", "seen", "engagements", "clicks", "link_clicks")
    }
    pillars = {
        p.id: {"name": p.name, "color": p.color, "target_share": p.target_share}
        for p in (
            await db.execute(select(ContentPillar).where(ContentPillar.brand_id == brand.id))
        ).scalars()
    }
    pillar_rows = []
    total_posts = sum(cur["pillars"].values()) or 0
    for pid, n in cur["pillars"].items():
        meta = pillars.get(pid, {"name": "No pillar", "color": "#9aa0a6", "target_share": 0})
        pillar_rows.append(
            {**meta, "posts": n, "share_pct": round(n / total_posts * 100) if total_posts else 0}
        )
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": span},
        "generated_at": datetime.now(UTC).isoformat(),
        "totals": cur["totals"],
        "channels": cur["channels"],
        "series": cur["series"],
        "top_posts": cur["top_posts"],
        "pillars": sorted(pillar_rows, key=lambda r: r["posts"], reverse=True),
        "compare": compare,
        "followers": await _followers(db, brand, start, end),
        "inbox": await _inbox(db, brand, start, end),
    }


async def create(
    db: AsyncSession,
    brand: Brand,
    user: User | None,
    start: date,
    end: date,
    title: str | None = None,
) -> Report:
    data = await build(db, brand, start, end)
    rep = Report(
        brand_id=brand.id,
        title=(title or f"{brand.name} · {start:%d %b} – {end:%d %b %Y}")[:200],
        start=start,
        end=end,
        data=data,
        created_by=user.id if user else None,
    )
    db.add(rep)
    await db.flush()
    activity.record(db, brand.id, user, "created", "report", rep.id, rep.title)
    await db.commit()
    return rep


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def report_url(token: str) -> str:
    return f"{get_settings().base_url.rstrip('/')}/r/{token}"


async def share(
    db: AsyncSession, brand: Brand, rep: Report, user: User | None, days: int = 30
) -> tuple[ShareLink, str]:
    """A login-free link to one report. Returns the link and its token; only the hash is kept."""
    token = secrets.token_urlsafe(24)
    link = ShareLink(
        brand_id=brand.id,
        token_hash=token_hash(token),
        prefix=token[:8],
        kind="report",
        scope={"report_id": rep.id},
        created_by=user.id if user else None,
        expires_at=datetime.now(UTC) + timedelta(days=days),
    )
    db.add(link)
    await db.flush()
    activity.record(
        db, brand.id, user, "shared", "report", rep.id, f"{rep.title}, link for {days} days"
    )
    return link, token


async def summarize(db: AsyncSession, brand: Brand, rep: Report) -> dict:
    ai = ai_svc.ContentAI()
    summary = await ai.summarize_report(brand, rep.data)
    rep.summary = {**summary, "written_at": datetime.now(UTC).isoformat()}
    await db.commit()
    return rep.summary


def _cell(v) -> str:
    """Spreadsheets run cells that start with = + - @; a leading apostrophe keeps them text."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(rep: Report) -> str:
    d = rep.data or {}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "section",
            "name",
            "platform",
            "posts",
            "impressions",
            "engagements",
            "engagement_rate_pct",
            "extra",
        ]
    )
    t = d.get("totals", {})
    w.writerow(
        [
            "totals",
            _cell(rep.title),
            "",
            t.get("published", 0),
            t.get("impressions", 0),
            t.get("engagements", 0),
            t.get("engagement_rate_pct", 0),
            f"{d.get('period', {}).get('start')} to {d.get('period', {}).get('end')}",
        ]
    )
    for c in d.get("channels", []):
        w.writerow(
            [
                "channel",
                _cell(c["handle"]),
                c["platform"],
                c["posts"],
                c["impressions"],
                c["engagements"],
                c["engagement_rate_pct"],
                "",
            ]
        )
    for p in d.get("top_posts", []):
        w.writerow(
            [
                "post",
                _cell(p["content"].replace("\n", " ")),
                p["platform"],
                1,
                p["impressions"],
                p["engagements"],
                "",
                p.get("url") or p["published_at"],
            ]
        )
    for day in d.get("series", []):
        w.writerow(
            [
                "day",
                day["day"],
                "",
                day.get("posts", 0),
                day["impressions"],
                day["engagements"],
                "",
                "",
            ]
        )
    f = d.get("followers", {})
    w.writerow(
        [
            "followers",
            "start→end",
            "",
            "",
            "",
            "",
            "",
            f"{f.get('start', 0)}→{f.get('end', 0)} ({f.get('delta', 0):+d})",
        ]
    )
    i = d.get("inbox", {})
    w.writerow(
        [
            "inbox",
            "received/replied",
            "",
            "",
            "",
            "",
            "",
            f"{i.get('received', 0)}/{i.get('replied', 0)}, {i.get('negative', 0)} negative",
        ]
    )
    return buf.getvalue()


# ---- follower snapshots ------------------------------------------------------------------------
async def snapshot_followers(db: AsyncSession, today: date | None = None) -> int:
    """One row per active account for today. Zernio's follower stats win when they answer."""
    today = today or datetime.now(UTC).date()
    accounts = (
        (await db.execute(select(SocialAccount).where(SocialAccount.is_active.is_(True))))
        .scalars()
        .all()
    )
    have = {
        aid
        for (aid,) in (
            await db.execute(
                select(FollowerSnapshot.account_id).where(FollowerSnapshot.day == today)
            )
        ).all()
    }
    todo = [a for a in accounts if a.id not in have]
    if not todo:
        return 0
    from_zernio: dict[str, int] = {}
    zernio_ids = {a.external_id for a in todo if a.provider == "zernio"}
    if zernio_ids:
        adapter = ZernioAdapter()
        if adapter.is_configured():
            try:
                from_zernio = await adapter.follower_stats(zernio_ids)
            except PlatformError as e:  # the analytics add-on is optional
                log.info("Zernio follower stats unavailable: %s", e)
    made = 0
    for a in todo:
        if a.provider == "zernio" and a.external_id in from_zernio:
            n, source = from_zernio[a.external_id], "zernio"
            a.followers = n
        elif a.followers is not None:
            n, source = a.followers, "spark"
        else:
            continue
        db.add(
            FollowerSnapshot(
                account_id=a.id,
                day=today,
                followers=int(n),
                source=source,
                captured_at=datetime.now(UTC),
            )
        )
        made += 1
    await db.commit()
    return made


def _unused(*_: object) -> None:
    return None


_unused(Post)
