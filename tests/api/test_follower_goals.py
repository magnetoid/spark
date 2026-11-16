"""Phase 4: follower goals with a forecast from the channel's own follower history, and how its
posting rate went with follower growth."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from spark.models import ActivityLog, Post, PostStatus, PostTarget, SocialAccount
from spark.models.reports import FollowerSnapshot
from spark.services import follower_goals
from tests.api.conftest import API

TODAY = date(2026, 11, 16)  # a Monday


async def _acc(db, brand, **kw) -> SocialAccount:
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    for k, v in kw.items():
        setattr(acc, k, v)
    await db.commit()
    return acc


async def _history(db, acc, days: int, start: int, per_day: float) -> None:
    for i in range(days):
        d = TODAY - timedelta(days=days - 1 - i)
        db.add(FollowerSnapshot(account_id=acc.id, day=d, followers=round(start + per_day * i)))
    acc.followers = round(start + per_day * (days - 1))
    await db.commit()


def _row(out, acc):
    return next(c for c in out if c["account_id"] == acc.id)


async def test_on_track_with_steady_growth(db, brand):
    acc = await _acc(db, brand)
    await _history(db, acc, 30, 1000, 10)  # 1290 today, 70 a week
    await _acc(db, brand, follower_goal=1990, follower_goal_by=TODAY + timedelta(days=77))
    r = _row(await follower_goals.brand_goals(db, brand, TODAY), acc)
    assert r["followers"] == 1290 and r["per_week"] == 70
    assert r["status"] == "on_track" and r["eta"] == TODAY + timedelta(days=70)
    assert r["expected_by_date"] == 1290 + 770


async def test_behind_says_what_a_week_needs(db, brand):
    acc = await _acc(db, brand)
    await _history(db, acc, 30, 1000, 10)
    await _acc(db, brand, follower_goal=1990, follower_goal_by=TODAY + timedelta(days=35))
    r = _row(await follower_goals.brand_goals(db, brand, TODAY), acc)
    assert r["status"] == "behind" and r["needed_per_week"] == 140


async def test_too_little_history_is_learning(db, brand):
    acc = await _acc(db, brand)
    await _history(db, acc, 5, 1000, 10)
    await _acc(db, brand, follower_goal=2000)
    r = _row(await follower_goals.brand_goals(db, brand, TODAY), acc)
    assert r["status"] == "learning" and r["per_week"] is None and r["eta"] is None
    assert r["history_days"] == 5


async def test_flat_history_is_stalled_and_reached_is_reached(db, brand):
    acc = await _acc(db, brand)
    await _history(db, acc, 20, 500, 0)
    await _acc(db, brand, follower_goal=600)
    r = _row(await follower_goals.brand_goals(db, brand, TODAY), acc)
    assert r["status"] == "stalled" and r["eta"] is None
    await _acc(db, brand, follower_goal=400)
    r = _row(await follower_goals.brand_goals(db, brand, TODAY), acc)
    assert r["status"] == "reached"


async def test_posting_rate_and_growth_side_by_side(db, brand):
    acc = await _acc(db, brand)
    n = 1000
    monday = TODAY - timedelta(weeks=12)
    db.add(FollowerSnapshot(account_id=acc.id, day=monday - timedelta(days=1), followers=n))
    for w in range(12):
        busy = w % 2 == 0
        week = monday + timedelta(weeks=w)
        for d in range(7):
            if d == 0:
                n += 50 if busy else 10
            db.add(FollowerSnapshot(account_id=acc.id, day=week + timedelta(days=d), followers=n))
        for i in range(4 if busy else 1):
            at = datetime.combine(week + timedelta(days=i), datetime.min.time(), UTC)
            p = Post(brand_id=brand.id, content="x", status=PostStatus.published)
            p.targets = [
                PostTarget(account_id=acc.id, status=PostStatus.published, published_at=at)
            ]
            db.add(p)
    await db.commit()
    r = _row(await follower_goals.brand_goals(db, brand, TODAY), acc)
    d = r["driver"]
    assert d["threshold"] == 3 and d["weeks_more"] == 6 and d["weeks_less"] == 6
    assert d["gain_more"] == 50 and d["gain_less"] == 10


async def test_no_driver_without_enough_weeks(db, brand):
    acc = await _acc(db, brand)
    await _history(db, acc, 20, 1000, 5)
    r = _row(await follower_goals.brand_goals(db, brand, TODAY), acc)
    assert r["driver"] is None and r["goal"] is None and r["status"] is None


async def test_set_follower_goals_through_the_api(api, db, brand):
    acc = await _acc(db, brand, followers=800)
    url = f"{API}/brands/{brand.id}/follower-goals"
    by = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    r = await api.put(url, json={"goals": [{"account_id": acc.id, "target": 1000, "by": by}]})
    assert r.status_code == 200, r.text
    row = _row(r.json()["channels"], acc)
    assert row["goal"] == 1000 and row["by"] == by and row["start"] == 800
    past = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    bad = await api.put(url, json={"goals": [{"account_id": acc.id, "target": 1000, "by": past}]})
    assert bad.status_code == 422
    bad = await api.put(url, json={"goals": [{"account_id": acc.id, "target": 0}]})
    assert bad.status_code == 422
    other = await api.put(url, json={"goals": [{"account_id": 99999, "target": 10}]})
    assert other.status_code == 404
    r = await api.put(url, json={"goals": [{"account_id": acc.id, "target": None}]})
    assert _row(r.json()["channels"], acc)["goal"] is None
    logs = (
        await db.execute(select(ActivityLog).where(ActivityLog.verb == "set follower goals"))
    ).scalars()
    assert len(list(logs)) == 2
    assert (await api.get(url)).status_code == 200
