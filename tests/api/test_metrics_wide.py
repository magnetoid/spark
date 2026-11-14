"""Phase 2A: wider metrics (reach, views, saves), one row per post per day, a call budget and
a cadence for Zernio analytics, honest handling of 429 and 402, and breakdowns."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import func, select

from spark.config import get_settings
from spark.models import ContentPillar, Metric, Post, PostStatus, PostTarget, SocialAccount
from spark.services import analytics
from tests.api.conftest import API
from tests.api.test_phase9 import Z, zacc  # noqa: F401  (fixture)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


async def _account(db, brand, platform: str, ext: str) -> SocialAccount:
    acc = SocialAccount(
        brand_id=brand.id, platform=platform, provider="zernio", external_id=ext, handle=ext
    )
    acc.access_token = "tok"
    db.add(acc)
    await db.commit()
    return acc


async def _published(
    db, acc, rid, *, age=timedelta(days=1), post_type="post", pillar_id=None, now=NOW
) -> PostTarget:
    p = Post(
        brand_id=acc.brand_id,
        content=f"Post {rid}",
        status=PostStatus.published,
        pillar_id=pillar_id,
    )
    t = PostTarget(
        account_id=acc.id,
        status=PostStatus.published,
        published_at=now - age,
        remote_id=rid,
        post_type=post_type,
    )
    p.targets = [t]
    db.add(p)
    await db.commit()
    return t


def _item(late_id: str, account: str = "z-ig", platform: str = "instagram", **numbers) -> dict:
    a = dict(impressions=0, reach=0, likes=0, comments=0, shares=0, saves=0, clicks=0, views=0)
    a.update(numbers)
    return {
        "_id": f"ext-{late_id}",
        "latePostId": late_id,
        "platform": platform,
        "platformPostUrl": f"https://example.com/{late_id}",
        "analytics": a,
        "platformAnalytics": [
            {"platform": platform, "accountId": account, "status": "published", "analytics": a}
        ],
    }


def _page(*items, page=1, pages=1) -> dict:
    return {"posts": list(items), "pagination": {"page": page, "pages": pages, "total": len(items)}}


# ---- reading from Zernio ---------------------------------------------------------------------
@respx.mock
async def test_saves_and_views_kept_separate(db, zacc):  # noqa: F811
    await _published(db, zacc, "zp1")
    respx.get(f"{Z}/analytics").respond(
        200,
        json=_page(
            _item(
                "zp1",
                impressions=1000,
                reach=800,
                likes=40,
                comments=5,
                shares=3,
                saves=12,
                clicks=7,
                views=900,
            )
        ),
    )
    assert await analytics.collect_metrics(db, now=NOW) == 1
    m = await db.scalar(select(Metric))
    assert (m.impressions, m.reach, m.views, m.shares, m.saves) == (1000, 800, 900, 3, 12)
    assert m.engagements == 40 + 5 + 3 + 12 + 7


@respx.mock
async def test_numbers_a_network_does_not_report_stay_empty(db, brand, zacc):  # noqa: F811
    tt = await _account(db, brand, "tiktok", "z-tt")
    await _published(db, tt, "zp2")
    respx.get(f"{Z}/analytics").respond(
        200, json=_page(_item("zp2", "z-tt", "tiktok", likes=9, views=500))
    )
    await analytics.collect_metrics(db, now=NOW)
    m = await db.scalar(select(Metric))
    assert m.views == 500 and m.reach is None and m.saves is None and m.impressions == 0


@respx.mock
async def test_zernio_is_read_per_account_not_per_post(db, zacc):  # noqa: F811
    for rid in ("a1", "a2", "a3"):
        await _published(db, zacc, rid)
    route = respx.get(f"{Z}/analytics").respond(
        200, json=_page(*[_item(r, likes=1) for r in ("a1", "a2", "a3")])
    )
    assert await analytics.collect_metrics(db, now=NOW) == 3
    assert route.call_count == 1
    params = route.calls[0].request.url.params
    assert params["accountId"] == "z-ig" and params["source"] == "late"
    assert "postId" not in params


@respx.mock
async def test_a_post_on_the_second_page_is_found(db, zacc):  # noqa: F811
    await _published(db, zacc, "late")
    route = respx.get(f"{Z}/analytics")
    route.side_effect = [
        httpx.Response(200, json=_page(_item("someone-else"), page=1, pages=2)),
        httpx.Response(200, json=_page(_item("late", likes=4), page=2, pages=2)),
    ]
    assert await analytics.collect_metrics(db, now=NOW) == 1
    assert route.call_count == 2


# ---- history ---------------------------------------------------------------------------------
@respx.mock
async def test_one_metric_row_per_post_per_day(db, zacc):  # noqa: F811
    await _published(db, zacc, "d1")
    route = respx.get(f"{Z}/analytics")
    route.respond(200, json=_page(_item("d1", likes=5)))
    await analytics.collect_metrics(db, now=NOW)
    route.respond(200, json=_page(_item("d1", likes=8)))
    await analytics.collect_metrics(db, now=NOW + timedelta(hours=3))
    rows = (await db.execute(select(Metric))).scalars().all()
    assert len(rows) == 1 and rows[0].likes == 8  # the same day: updated, not added

    route.respond(200, json=_page(_item("d1", likes=11)))
    await analytics.collect_metrics(db, now=NOW + timedelta(days=1))
    assert await db.scalar(select(func.count(Metric.id))) == 2


# ---- cadence and budget ----------------------------------------------------------------------
def test_cadence_reads_young_posts_often_and_old_posts_rarely():
    due = analytics.metrics_due
    assert due(NOW - timedelta(days=1), None, NOW)
    assert due(NOW - timedelta(days=1), NOW - timedelta(hours=1), NOW)  # under 48 hours
    assert not due(NOW - timedelta(days=5), NOW - timedelta(hours=3), NOW)  # 2 to 7 days: daily
    assert due(NOW - timedelta(days=5), NOW - timedelta(hours=21), NOW)
    assert not due(NOW - timedelta(days=10), NOW - timedelta(days=2), NOW)  # 7 to 30: every 3rd
    assert due(NOW - timedelta(days=10), NOW - timedelta(days=3), NOW)


@respx.mock
async def test_nothing_due_means_no_call(db, zacc):  # noqa: F811
    t = await _published(db, zacc, "old", age=timedelta(days=10))
    db.add(Metric(target_id=t.id, captured_at=NOW - timedelta(days=1), likes=1))
    await db.commit()
    route = respx.get(f"{Z}/analytics").respond(200, json=_page())
    assert await analytics.collect_metrics(db, now=NOW) == 0
    assert route.call_count == 0


@respx.mock
async def test_the_call_budget_stops_a_run(db, brand, zacc, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "metrics_max_calls_per_run", 1)
    li = await _account(db, brand, "linkedin", "z-li")
    await _published(db, zacc, "b1")
    await _published(db, li, "b2")
    route = respx.get(f"{Z}/analytics").respond(
        200, json=_page(_item("b1", likes=1), _item("b2", "z-li", "linkedin", likes=1))
    )
    await analytics.collect_metrics(db, now=NOW)
    assert route.call_count == 1


@respx.mock
async def test_429_stops_the_run_and_waits(db, brand, zacc):  # noqa: F811
    li = await _account(db, brand, "linkedin", "z-li")
    await _published(db, zacc, "c1")
    await _published(db, li, "c2")
    route = respx.get(f"{Z}/analytics").respond(
        429, headers={"Retry-After": "120"}, json={"error": "Too many requests"}
    )
    await analytics.collect_metrics(db, now=NOW)
    assert route.call_count == 1  # the second account is not tried
    status = await analytics.metrics_status(db, now=NOW)
    assert status["state"] == "paused"

    await analytics.collect_metrics(db, now=NOW + timedelta(seconds=60))
    assert route.call_count == 1  # still waiting
    await analytics.collect_metrics(db, now=NOW + timedelta(seconds=180))
    assert route.call_count == 2


@respx.mock
async def test_402_says_analytics_is_not_available_until_it_works(api, db, brand, zacc):  # noqa: F811
    await _published(db, zacc, "e1", now=datetime.now(UTC))
    route = respx.get(f"{Z}/analytics").respond(402, json={"error": "Analytics add-on required"})
    await analytics.collect_metrics(db)
    body = (await api.get(f"{API}/brands/{brand.id}/analytics")).json()
    assert body["metrics_status"]["state"] == "unavailable"
    assert "Analytics" in body["metrics_status"]["message"]

    route.respond(200, json=_page(_item("e1", likes=2)))
    await analytics.collect_metrics(db)
    body = (await api.get(f"{API}/brands/{brand.id}/analytics")).json()
    assert body["metrics_status"]["state"] == "ok"


# ---- Zernio tells Spark when fresh numbers exist ---------------------------------------------
async def test_analytics_synced_queues_a_read_of_that_account(db, zacc, monkeypatch):  # noqa: F811
    from spark.services import jobs, webhooks

    seen = []

    async def fake(job, *args):
        seen.append((job, *args))
        return True

    monkeypatch.setattr(jobs, "enqueue", fake)
    out = await webhooks.handle_zernio_event(
        db, {"id": "ev-a1", "event": "analytics.synced", "account": {"accountId": "z-ig"}}
    )
    assert out == "metrics-queued" and seen == [("collect_account_metrics", zacc.id)]
    assert "analytics.synced" in webhooks.ZERNIO_EVENTS


def test_the_worker_runs_account_reads():
    from spark.worker import WorkerSettings

    assert "collect_account_metrics" in {f.__name__ for f in WorkerSettings.functions}


# ---- the analytics page ----------------------------------------------------------------------
async def _metric_post(db, brand, *, post_type="post", pillar=None, hour=9, **numbers):
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    when = datetime.now(UTC).replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(
        days=2
    )
    t = await _published(
        db,
        acc,
        f"m{datetime.now().timestamp()}",
        age=datetime.now(UTC) - when,
        post_type=post_type,
        pillar_id=pillar.id if pillar else None,
        now=datetime.now(UTC),
    )
    db.add(Metric(target_id=t.id, captured_at=datetime.now(UTC), **numbers))
    await db.commit()
    return t


async def test_overview_has_reach_views_and_saves(api, db, brand):
    await _metric_post(db, brand, impressions=1000, reach=700, views=900, likes=50, saves=10)
    body = (await api.get(f"{API}/brands/{brand.id}/analytics")).json()
    assert (body["reach"], body["views"], body["saves"]) == (700, 900, 10)
    assert body["engagements"] == 60
    assert body["engagement_rate_pct"] == 6.0  # engagements / impressions


async def test_rate_falls_back_to_views_when_there_are_no_impressions(api, db, brand):
    await _metric_post(db, brand, impressions=0, views=400, likes=20)
    body = (await api.get(f"{API}/brands/{brand.id}/analytics")).json()
    assert body["engagement_rate_pct"] == 5.0
    assert body["reach"] is None and body["saves"] is None  # nobody reported them


async def test_old_rows_are_marked(api, db, brand):
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    # a Zernio channel on a network that reports saves, read before saves were kept apart
    acc.platform, acc.provider = "instagram", "zernio"
    await db.commit()
    await _metric_post(db, brand, impressions=100, likes=5, shares=3)
    body = (await api.get(f"{API}/brands/{brand.id}/analytics")).json()
    assert body["saves_in_shares"] is True


async def test_breakdowns_carry_their_sample_size(api, db, brand):
    pillar = ContentPillar(brand_id=brand.id, name="Education")
    db.add(pillar)
    await db.commit()
    await _metric_post(
        db, brand, post_type="reel", pillar=pillar, hour=9, impressions=100, likes=10
    )
    await _metric_post(db, brand, post_type="post", hour=9, impressions=100, likes=2)
    await _metric_post(db, brand, post_type="post", hour=17, impressions=100, likes=4)
    body = (await api.get(f"{API}/brands/{brand.id}/analytics")).json()
    by_type = {r["key"]: r for r in body["by_type"]}
    assert by_type["reel"]["posts"] == 1 and by_type["reel"]["engagement_rate_pct"] == 10.0
    assert by_type["post"]["posts"] == 2 and by_type["post"]["engagement_rate_pct"] == 3.0
    by_pillar = {r["key"]: r for r in body["by_pillar"]}
    assert by_pillar["Education"]["posts"] == 1 and by_pillar["No pillar"]["posts"] == 2
    slots = {(r["hour"], r["posts"]) for r in body["by_slot"]}
    assert (9, 2) in slots and (17, 1) in slots


async def test_history_shows_what_each_day_added(api, db, brand):
    t = await _metric_post(db, brand, impressions=100, likes=4)
    today = (await db.execute(select(Metric))).scalars().one()
    today.captured_at = datetime.now(UTC) - timedelta(days=1)
    db.add(Metric(target_id=t.id, captured_at=datetime.now(UTC), impressions=250, likes=10))
    await db.commit()
    body = (await api.get(f"{API}/brands/{brand.id}/analytics")).json()
    hist = {p["day"]: p for p in body["history"]}
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    assert hist[yesterday]["impressions"] == 100
    assert hist[datetime.now(UTC).date().isoformat()]["impressions"] == 150


pytestmark = pytest.mark.usefixtures("brand")
