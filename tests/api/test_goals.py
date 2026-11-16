"""Phase 4: posting goals and streaks. A weekly target per channel, the weeks in a row it was met,
and one alert per week when a channel is short of it late in the week."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import ActivityLog, Post, PostStatus, PostTarget, SocialAccount
from spark.services import dashboard, goals
from spark.services.email import ConsoleSender
from tests.api.conftest import API

MON = datetime(2026, 11, 16, 9, tzinfo=UTC)  # a Monday; the week runs to Sunday Nov 22
THU = MON + timedelta(days=3, hours=1)  # Thursday 10:00


async def _acc(db, brand, goal=None, since=None) -> SocialAccount:
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    acc.posting_goal, acc.posting_goal_since = goal, since
    await db.commit()
    return acc


async def _target(db, acc, status: PostStatus, when: datetime) -> None:
    p = Post(brand_id=acc.brand_id, content="Hello", status=status, scheduled_at=when)
    t = PostTarget(account_id=acc.id, status=status, scheduled_at=when)
    if status == PostStatus.published:
        t.published_at = when
    p.targets = [t]
    db.add(p)
    await db.commit()


def _row(rows, acc):
    return next(r for r in rows if r["account_id"] == acc.id)


async def test_this_week_counts_published_and_planned(db, brand):
    acc = await _acc(db, brand, goal=3, since=MON - timedelta(days=30))
    await _target(db, acc, PostStatus.published, MON + timedelta(hours=1))
    await _target(db, acc, PostStatus.scheduled, MON + timedelta(days=4))
    await _target(db, acc, PostStatus.pending_approval, MON + timedelta(days=5))
    await _target(db, acc, PostStatus.scheduled, MON + timedelta(days=8))  # next week
    await _target(db, acc, PostStatus.published, MON - timedelta(days=1))  # last week
    out = await goals.channel_goals(db, brand, THU)
    r = _row(out["channels"], acc)
    assert (r["goal"], r["published"], r["planned"], r["needed"]) == (3, 1, 2, 0)
    assert out["week_start"] == MON.date() and out["days_left"] == 4


async def test_streak_counts_met_weeks_since_the_goal(db, brand):
    since = MON - timedelta(weeks=3)  # Monday Oct 26
    acc = await _acc(db, brand, goal=2, since=since)
    for w in (4, 3, 2, 1):  # the week before the goal was set is met but does not count
        for d in (0, 2):
            await _target(
                db, acc, PostStatus.published, MON - timedelta(weeks=w) + timedelta(days=d)
            )
    r = _row((await goals.channel_goals(db, brand, THU))["channels"], acc)
    assert r["streak"] == 3  # this week is not over, so it does not break the streak
    assert [w["met"] for w in r["weeks"]][-5:] == [None, True, True, True, None]
    await _target(db, acc, PostStatus.published, MON + timedelta(hours=2))
    await _target(db, acc, PostStatus.published, MON + timedelta(hours=3))
    r = _row((await goals.channel_goals(db, brand, THU))["channels"], acc)
    assert r["streak"] == 4 and r["weeks"][-1]["met"] is True


async def test_a_missed_week_breaks_the_streak(db, brand):
    acc = await _acc(db, brand, goal=1, since=MON - timedelta(weeks=5))
    for w in (5, 4, 1):
        await _target(db, acc, PostStatus.published, MON - timedelta(weeks=w))
    r = _row((await goals.channel_goals(db, brand, THU))["channels"], acc)
    assert r["streak"] == 1 and r["best_streak"] == 2


async def test_weeks_follow_the_brand_timezone(db, brand):
    brand.timezone = "America/New_York"
    acc = await _acc(db, brand, goal=1, since=MON - timedelta(weeks=2))
    # Monday 03:00 UTC is still Sunday evening in New York: last week, not this one
    await _target(db, acc, PostStatus.published, datetime(2026, 11, 16, 3, tzinfo=UTC))
    r = _row((await goals.channel_goals(db, brand, THU))["channels"], acc)
    assert r["published"] == 0 and r["weeks"][-2]["published"] == 1


async def test_set_goals_through_the_api(api, db, brand):
    acc = await _acc(db, brand)
    url = f"{API}/brands/{brand.id}/goals"
    r = await api.put(url, json={"goals": [{"account_id": acc.id, "posts_per_week": 3}]})
    assert r.status_code == 200, r.text
    assert _row(r.json()["channels"], acc)["goal"] == 3
    await db.refresh(acc)
    since = acc.posting_goal_since
    assert since is not None
    await api.put(url, json={"goals": [{"account_id": acc.id, "posts_per_week": 3}]})
    await db.refresh(acc)
    assert acc.posting_goal_since == since  # the same goal keeps its streak
    r = await api.put(url, json={"goals": [{"account_id": acc.id, "posts_per_week": None}]})
    await db.refresh(acc)
    assert acc.posting_goal is None and _row(r.json()["channels"], acc)["goal"] is None
    bad = await api.put(url, json={"goals": [{"account_id": acc.id, "posts_per_week": 0}]})
    assert bad.status_code == 422
    other = await api.put(url, json={"goals": [{"account_id": 99999, "posts_per_week": 2}]})
    assert other.status_code == 404
    logs = (await db.execute(select(ActivityLog).where(ActivityLog.verb == "set goals"))).scalars()
    assert len(list(logs)) == 2  # the unchanged save and the refused ones log nothing
    got = await api.get(url)
    assert got.status_code == 200 and "channels" in got.json()


async def test_one_alert_a_week_from_thursday(db, brand):
    ConsoleSender.sent.clear()
    await _acc(db, brand, goal=3, since=MON - timedelta(weeks=1))
    sender = ConsoleSender()
    assert await goals.alert_gaps(db, sender, MON) == 0  # early in the week: no alert
    assert await goals.alert_gaps(db, sender, THU - timedelta(hours=5)) == 0  # not at 05:00
    assert await goals.alert_gaps(db, sender, THU) == 1
    mail = ConsoleSender.sent[-1]
    assert mail["to"] == "owner@example.com" and "weekly goal" in mail["subject"]
    assert await goals.alert_gaps(db, sender, THU + timedelta(hours=5)) == 0
    assert await goals.alert_gaps(db, sender, THU + timedelta(weeks=1)) == 1


async def test_no_alert_when_the_week_is_planned(db, brand):
    acc = await _acc(db, brand, goal=1, since=MON - timedelta(weeks=1))
    await _target(db, acc, PostStatus.scheduled, MON + timedelta(days=5))
    assert await goals.alert_gaps(db, ConsoleSender(), THU) == 0


async def test_today_lists_channels_short_of_their_goal(db, brand):
    await _acc(db, brand, goal=2, since=MON - timedelta(weeks=1))
    assert (await dashboard.today(db, brand, now=MON))["needs_you"]["goals"] == 0
    assert (await dashboard.today(db, brand, now=THU))["needs_you"]["goals"] == 1
