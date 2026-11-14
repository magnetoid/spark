"""Metric ingestion from platforms and dashboard aggregations."""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.config import get_settings
from spark.models import (
    AppState,
    Brand,
    ContentPillar,
    LinkClick,
    Metric,
    Post,
    PostStatus,
    PostTarget,
    ShortLink,
    SocialAccount,
)
from spark.platforms import NotAvailable, PlatformError, RateLimited, adapter_for
from spark.platforms.zernio import REPORTS as zernio_reports
from spark.services.publisher import as_utc

log = logging.getLogger(__name__)


# How often a published post is read, by age: young posts change fast, old ones barely
YOUNG = timedelta(hours=48)
WEEK = timedelta(days=7)
DAILY_GAP = timedelta(hours=20)  # "once a day", with room for cron jitter
THIRD_DAY_GAP = timedelta(hours=68)
STATE_KEY = "metrics"


def metrics_due(published_at: datetime, last_read: datetime | None, now: datetime) -> bool:
    """Under 48 hours: every run. 2 to 7 days: once a day. 7 to 30 days: every third day."""
    if last_read is None:
        return True
    age, gap = now - as_utc(published_at), now - as_utc(last_read)
    if age < YOUNG:
        return True
    if age < WEEK:
        return gap >= DAILY_GAP
    return gap >= THIRD_DAY_GAP


async def _get_state(db: AsyncSession) -> AppState:
    row = await db.get(AppState, STATE_KEY)
    if row is None:
        row = AppState(key=STATE_KEY, value={}, updated_at=datetime.now(UTC))
        db.add(row)
    return row


def _set_state(row: AppState, **changes) -> None:
    row.value = {k: v for k, v in {**(row.value or {}), **changes}.items() if v is not None}
    row.updated_at = datetime.now(UTC)


async def metrics_status(db: AsyncSession, now: datetime | None = None) -> dict:
    """ok, paused (a provider asked to wait) or unavailable (the plan has no analytics)."""
    now = now or datetime.now(UTC)
    row = await db.get(AppState, STATE_KEY)
    v = (row.value if row else None) or {}
    until = datetime.fromisoformat(v["paused_until"]) if v.get("paused_until") else None
    if until and until > now:
        return {"state": "paused", "message": v.get("pause_reason"), "until": until}
    if v.get("unavailable"):
        return {"state": "unavailable", "message": v["unavailable"], "until": None}
    return {"state": "ok", "message": None, "until": None}


async def collect_metrics(
    db: AsyncSession,
    max_age_days: int = 30,
    brand_id: int | None = None,
    *,
    account_id: int | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> int:
    """Read the numbers of published posts that are due (see `metrics_due`; `force` reads all),
    keeping one row per post per day. Stops at the call budget, on a 429 (and waits as long as
    asked) and on a 402 (the plan has no analytics). Returns the number of posts read."""
    now = now or datetime.now(UTC)
    state = await _get_state(db)
    status = await metrics_status(db, now)
    if status["state"] == "paused":
        log.info("Metrics paused until %s", status["until"])
        return 0
    scope = []
    if brand_id:
        scope.append(
            PostTarget.account_id.in_(
                select(SocialAccount.id).where(SocialAccount.brand_id == brand_id)
            )
        )
    if account_id:
        scope.append(PostTarget.account_id == account_id)
    rows = (
        (
            await db.execute(
                select(PostTarget).where(
                    *scope,
                    PostTarget.status == PostStatus.published,
                    PostTarget.published_at >= now - timedelta(days=max_age_days),
                    PostTarget.remote_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0
    ids = [t.id for t in rows]
    last_read = dict(
        (
            await db.execute(
                select(Metric.target_id, func.max(Metric.captured_at))
                .where(Metric.target_id.in_(ids))
                .group_by(Metric.target_id)
            )
        ).all()
    )
    by_account: dict[int, list[PostTarget]] = defaultdict(list)
    for t in rows:
        if force or metrics_due(t.published_at, last_read.get(t.id), now):
            by_account[t.account_id].append(t)

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    budget, used, saved = get_settings().metrics_max_calls_per_run, 0, 0
    for acc_id, targets in by_account.items():
        if used >= budget:
            log.info("Metrics call budget (%s) reached; the rest waits for the next run", budget)
            break
        account = await db.get(SocialAccount, acc_id)
        if not account or not account.is_active:
            continue
        adapter = adapter_for(account)
        try:
            snaps = await adapter.fetch_metrics(account, [t.remote_id for t in targets])
            # Zernio resolves native URLs after publish; the analytics list carries them
            urls = {s.remote_id: s.url for s in snaps if s.url}
            for t in targets:
                if not t.remote_url and urls.get(t.remote_id):
                    t.remote_url = urls[t.remote_id]
            if account.provider == "zernio":
                if state.value.get("unavailable"):
                    _set_state(state, unavailable="")
        except RateLimited as e:
            until = now + timedelta(seconds=max(e.retry_after, 1))
            _set_state(state, paused_until=until.isoformat(), pause_reason=str(e))
            log.warning("Metrics paused until %s: %s", until, e)
            break
        except NotAvailable as e:
            _set_state(state, unavailable=str(e))
            log.warning("Metrics not available: %s", e)
            break
        except PlatformError as e:
            log.warning("Metrics for account %s failed: %s", acc_id, e)
            continue
        finally:
            used += getattr(adapter, "calls", None) or len(targets)
        today = {
            m.target_id: m
            for m in (
                await db.execute(
                    select(Metric)
                    .where(
                        Metric.target_id.in_([t.id for t in targets]),
                        Metric.captured_at >= day_start,
                    )
                    .order_by(Metric.captured_at)
                )
            ).scalars()
        }
        by_remote = {t.remote_id: t for t in targets}
        for snap in snaps:
            t = by_remote.get(snap.remote_id)
            if t is None:
                continue
            m = today.get(t.id)
            if m is None:
                m = Metric(target_id=t.id)
                db.add(m)
            m.captured_at = now
            for f in ("impressions", "likes", "comments", "shares", "clicks"):
                setattr(m, f, getattr(snap, f))
            m.reach, m.views, m.saves = snap.reach, snap.views, snap.saves
            saved += 1
    await db.commit()
    return saved


async def _latest_metrics(
    db: AsyncSession, brand_id: int, since: datetime, until: datetime | None = None
):
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
        t = dict(impressions=0, engagements=0, posts=0, seen=0)
        for m, _target, _acc in rows:
            t["impressions"] += m.impressions
            t["engagements"] += m.engagements
            t["seen"] += m.seen
            t["posts"] += 1
        return t

    cur = totals(await _latest_metrics(db, brand_id, since))
    prev = totals(await _latest_metrics(db, brand_id, prev_since, since))
    published_prev = (
        await db.scalar(
            select(func.count(PostTarget.id))
            .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
            .where(
                SocialAccount.brand_id == brand_id,
                PostTarget.status == PostStatus.published,
                PostTarget.published_at >= prev_since,
                PostTarget.published_at < since,
            )
        )
        or 0
    )
    return {
        "impressions": _pct(cur["impressions"], prev["impressions"]),
        "engagements": _pct(cur["engagements"], prev["engagements"]),
        "published_prev": published_prev,
        "rate": rate(cur["engagements"], cur["seen"]),
        "rate_prev": rate(prev["engagements"], prev["seen"]),
    }


def rate(engagements: int, seen: int) -> float:
    """Engagement rate in percent: engagements over impressions, else views, else reach,
    decided per post (`Metric.seen`) and added up, the same way for every network."""
    return round(engagements / seen * 100, 2) if seen else 0.0


def _group(rows, key) -> list[dict]:
    """Posts, engagements and rate per group, biggest sample first; `key` -> label or None."""
    acc: dict[str, dict] = defaultdict(lambda: dict(posts=0, engagements=0, seen=0))
    for m, t, a in rows:
        k = key(m, t, a)
        if k is None:
            continue
        g = acc[k]
        g["posts"] += 1
        g["engagements"] += m.engagements
        g["seen"] += m.seen
    out = [
        {"key": k, **v, "engagement_rate_pct": rate(v["engagements"], v["seen"])}
        for k, v in acc.items()
    ]
    return sorted(out, key=lambda r: (-r["posts"], r["key"]))


async def history(db: AsyncSession, brand_id: int, days: int = 30) -> list[dict]:
    """What each day added: per post, the day's last reading minus the reading before it,
    summed over the brand's posts. Needs one reading a day per post (`collect_metrics`)."""
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    rows = (
        await db.execute(
            select(Metric)
            .join(PostTarget, PostTarget.id == Metric.target_id)
            .join(SocialAccount, SocialAccount.id == PostTarget.account_id)
            .where(
                SocialAccount.brand_id == brand_id,
                Metric.captured_at >= since - timedelta(days=1),
            )
            .order_by(Metric.target_id, Metric.captured_at)
        )
    ).scalars()
    last_of_day: dict[int, dict[str, Metric]] = defaultdict(dict)
    for m in rows:
        last_of_day[m.target_id][as_utc(m.captured_at).date().isoformat()] = m
    axis = [(since + timedelta(days=i + 1)).date().isoformat() for i in range(days)]
    gains = {d: dict(impressions=0, views=0, engagements=0) for d in axis}
    for per_day in last_of_day.values():
        prev = None
        for day in sorted(per_day):
            m = per_day[day]
            if day in gains:
                g = gains[day]
                g["impressions"] += m.impressions - (prev.impressions if prev else 0)
                g["views"] += (m.views or 0) - ((prev.views or 0) if prev else 0)
                g["engagements"] += m.engagements - (prev.engagements if prev else 0)
            prev = m
    return [{"day": d, **gains[d]} for d in axis]


async def overview(db: AsyncSession, brand_id: int, days: int = 30) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await _latest_metrics(db, brand_id, since)
    brand = await db.get(Brand, brand_id)
    zone = ZoneInfo(brand.timezone if brand and brand.timezone else "UTC")
    pillars = dict(
        (
            await db.execute(
                select(ContentPillar.id, ContentPillar.name).where(
                    ContentPillar.brand_id == brand_id
                )
            )
        ).all()
    )
    totals = dict(impressions=0, likes=0, comments=0, shares=0, clicks=0)
    wide: dict[str, int | None] = dict(reach=None, views=None, saves=None)
    seen = 0
    saves_in_shares = False
    by_platform: dict[str, dict] = defaultdict(
        lambda: dict(impressions=0, views=0, engagements=0, posts=0)
    )
    by_day: dict[str, dict] = defaultdict(lambda: dict(impressions=0, engagements=0))
    top = []
    for m, t, a in rows:
        for k in totals:
            totals[k] += getattr(m, k)
        for k in wide:
            v = getattr(m, k)
            if v is not None:
                wide[k] = (wide[k] or 0) + v
        seen += m.seen
        if (
            m.saves is None
            and a.provider == "zernio"
            and "saves" in zernio_reports.get(a.platform, set())
        ):
            saves_in_shares = True
        p = by_platform[a.platform]
        p["impressions"] += m.impressions
        p["views"] += m.views or 0
        p["engagements"] += m.engagements
        p["posts"] += 1
        day = as_utc(t.published_at).date().isoformat()
        by_day[day]["impressions"] += m.impressions
        by_day[day]["engagements"] += m.engagements
        top.append((m.engagements, t, a, m))
    top.sort(key=lambda r: r[0], reverse=True)

    def slot(m, t, a):
        local = as_utc(t.published_at).astimezone(zone)
        return f"{a.id}|{a.platform}|{local.weekday()}|{local.hour}"

    by_slot = []
    for g in _group(rows, slot):
        acc_id, platform, weekday, hour = g.pop("key").split("|")
        by_slot.append(
            {
                "account_id": int(acc_id),
                "platform": platform,
                "weekday": int(weekday),
                "hour": int(hour),
                **g,
            }
        )

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
        select(func.count(Post.id)).where(
            Post.brand_id == brand_id, Post.status == PostStatus.failed
        )
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
    engagements = sum(m.engagements for m, _t, _a in rows)
    days_axis = [(since + timedelta(days=i + 1)).date().isoformat() for i in range(days)]
    return {
        "totals": totals,
        **wide,
        "engagements": engagements,
        "engagement_rate": rate(engagements, seen),
        "saves_in_shares": saves_in_shares,
        "published": published or 0,
        "scheduled": scheduled or 0,
        "failed": failed or 0,
        "followers": followers or 0,
        "link_clicks": link_clicks or 0,
        "by_platform": dict(by_platform),
        "by_type": _group(rows, lambda m, t, a: t.post_type or "post"),
        "by_pillar": _group(
            rows,
            lambda m, t, a: pillars.get(t.post.pillar_id, "No pillar") if t.post else None,
        ),
        "by_slot": by_slot,
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
