"""Posting goals and streaks.

A channel can have a weekly target (posts a week). Weeks run Monday to Sunday in the brand's
timezone. A week counts toward the streak only from the week the goal was set; the week in
progress adds to the streak once it is met and never breaks it. Late in the week (from
Thursday) a channel whose published and planned posts fall short is "at risk": Today lists it
and the team gets one email per brand per week.

Posting in more weeks, and more often per week, is the habit with the strongest evidence for
follower growth and reach, which is why this exists.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Post, PostStatus, PostTarget, SocialAccount
from spark.services.email import EmailSender, get_sender
from spark.services.publisher import as_utc

log = logging.getLogger(__name__)
HISTORY_WEEKS = 8  # shown per channel
LOOKBACK_WEEKS = 52  # for streaks
ALERT_FROM_DAYS_LEFT = 4  # Thursday: four days left, Sunday included
PLANNED = (PostStatus.scheduled, PostStatus.pending_approval, PostStatus.publishing)


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _local(dt: datetime, tz: str) -> datetime:
    return as_utc(dt).astimezone(ZoneInfo(tz))


def _utc(d: date, tz: str) -> datetime:
    return datetime.combine(d, time(0), ZoneInfo(tz)).astimezone(UTC)


def week_key(now: datetime, tz: str) -> str:
    y, w, _ = _local(now, tz).isocalendar()
    return f"{y}-W{w:02d}"


async def channel_goals(db: AsyncSession, brand: Brand, now: datetime | None = None) -> dict:
    """This week and the streak for every active channel of the brand (goal or not)."""
    now = now or datetime.now(UTC)
    tz = brand.timezone
    today = _local(now, tz).date()
    this_week = _week_start(today)
    week_end = _utc(this_week + timedelta(days=7), tz)
    days_left = 7 - today.weekday()
    oldest = this_week - timedelta(weeks=LOOKBACK_WEEKS)
    accounts = list(
        (
            await db.execute(
                select(SocialAccount)
                .where(SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True))
                .order_by(SocialAccount.platform, SocialAccount.handle)
            )
        ).scalars()
    )
    ids = [a.id for a in accounts]
    published: dict[int, dict[date, int]] = {i: {} for i in ids}
    planned: dict[int, int] = dict.fromkeys(ids, 0)
    if ids:
        rows = await db.execute(
            select(PostTarget.account_id, PostTarget.published_at)
            .join(Post, Post.id == PostTarget.post_id)
            .where(
                PostTarget.account_id.in_(ids),
                PostTarget.status == PostStatus.published,
                PostTarget.published_at >= _utc(oldest, tz),
                Post.is_autosave.is_(False),
            )
        )
        for aid, at in rows:
            wk = _week_start(_local(at, tz).date())
            published[aid][wk] = published[aid].get(wk, 0) + 1
        rows = await db.execute(
            select(PostTarget.account_id)
            .join(Post, Post.id == PostTarget.post_id)
            .where(
                PostTarget.account_id.in_(ids),
                PostTarget.status.in_(PLANNED),
                PostTarget.scheduled_at >= _utc(this_week, tz),
                PostTarget.scheduled_at < week_end,
                Post.is_autosave.is_(False),
            )
        )
        for (aid,) in rows:
            planned[aid] += 1

    channels = []
    for a in accounts:
        goal = a.posting_goal
        since = (
            _week_start(_local(a.posting_goal_since, tz).date()) if a.posting_goal_since else None
        )
        counts = published[a.id]
        done = counts.get(this_week, 0)

        def met(wk: date, goal=goal, since=since, counts=counts) -> bool | None:
            if not goal or since is None or wk < since:
                return None
            ok = counts.get(wk, 0) >= goal
            return ok if (wk < this_week or ok) else None  # this week only counts once met

        streak, wk = 0, this_week - timedelta(weeks=1)
        while wk >= oldest and met(wk):
            streak += 1
            wk -= timedelta(weeks=1)
        if met(this_week):
            streak += 1
        best = run = 0
        wk = oldest
        while wk <= this_week:
            run = run + 1 if met(wk) else 0
            best = max(best, run)
            wk += timedelta(weeks=1)
        needed = max(0, goal - done - planned[a.id]) if goal else 0
        channels.append(
            {
                "account_id": a.id,
                "platform": a.platform,
                "handle": a.handle,
                "goal": goal,
                "published": done,
                "planned": planned[a.id],
                "needed": needed,
                "streak": streak,
                "best_streak": best,
                "at_risk": bool(goal and needed and days_left <= ALERT_FROM_DAYS_LEFT),
                "weeks": [
                    {"start": w, "published": counts.get(w, 0), "met": met(w)}
                    for w in (
                        this_week - timedelta(weeks=n) for n in range(HISTORY_WEEKS - 1, -1, -1)
                    )
                ],
            }
        )
    return {"week_start": this_week, "days_left": days_left, "channels": channels}


async def at_risk_count(db: AsyncSession, brand: Brand, now: datetime | None = None) -> int:
    return sum(1 for c in (await channel_goals(db, brand, now))["channels"] if c["at_risk"])


async def alert_gaps(
    db: AsyncSession, sender: EmailSender | None = None, now: datetime | None = None
) -> int:
    """From Thursday, email a brand's owners and editors once a week about channels short of their
    goal. Returns the emails sent."""
    from spark.services import notify

    now = now or datetime.now(UTC)
    brand_ids = set(
        (
            await db.execute(
                select(SocialAccount.brand_id).where(
                    SocialAccount.posting_goal.is_not(None), SocialAccount.is_active.is_(True)
                )
            )
        ).scalars()
    )
    sent = 0
    for bid in sorted(brand_ids):
        brand = await db.get(Brand, bid)
        key = week_key(now, brand.timezone)
        if brand.goal_alert_week == key:
            continue
        data = await channel_goals(db, brand, now)
        if data["days_left"] > ALERT_FROM_DAYS_LEFT or _local(now, brand.timezone).hour < 9:
            continue  # from Thursday morning, not at midnight
        brand.goal_alert_week = key
        short = [c for c in data["channels"] if c["at_risk"]]
        if not short:
            continue
        sender = sender or get_sender()
        n = len(short)
        days = data["days_left"]
        rows = notify._rows(
            [
                (
                    f"@{c['handle']}: {c['needed']} more {'post' if c['needed'] == 1 else 'posts'}",
                    f"{c['published']} published and {c['planned']} planned of {c['goal']} this week"
                    + (f"; {c['streak']} weeks in a row so far" if c["streak"] else ""),
                )
                for c in short
            ]
        )
        body = notify.layout(
            f"{brand.name}: weekly goals",
            f"{'This channel is' if n == 1 else 'These channels are'} short of the weekly goal, "
            f"with {days} {'day' if days == 1 else 'days'} left including today.",
            rows,
            f"{notify._base()}/?brand={brand.slug}",
            "Plan posts",
        )
        subject = (
            f"[{brand.name}] {n} {'channel' if n == 1 else 'channels'} short of the weekly goal"
        )
        for u, role in await notify._brand_people(db, brand.id):
            if role not in ("owner", "editor") or not notify.wants(u, "notify_goals"):
                continue
            try:
                await sender.send(u.email, subject, body)
                sent += 1
            except Exception as e:  # one bad address must not stop the others
                log.warning("goal alert to %s failed: %s", u.email, e)
    await db.commit()
    return sent
