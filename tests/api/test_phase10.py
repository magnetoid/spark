"""Phase 10: reports for a period (CSV, a print page for PDF, an AI summary) and follower growth."""

from datetime import UTC, date, datetime, timedelta

import httpx
import respx
from sqlalchemy import select

from spark.config import get_settings
from spark.models import Metric, Post, PostStatus, PostTarget, SocialAccount
from tests.api.conftest import API


async def _published(
    db, brand, acc, content: str, when: datetime, impressions: int, likes: int
) -> Post:
    p = Post(brand_id=brand.id, content=content, status=PostStatus.published, scheduled_at=when)
    p.targets = [
        PostTarget(
            account_id=acc.id,
            status=PostStatus.published,
            scheduled_at=when,
            published_at=when,
            remote_url=f"https://x/{content[:3]}",
        )
    ]
    db.add(p)
    await db.flush()
    db.add(
        Metric(
            target_id=p.targets[0].id,
            captured_at=when + timedelta(days=1),
            impressions=impressions,
            likes=likes,
            comments=1,
            shares=0,
            clicks=2,
        )
    )
    await db.commit()
    return p


class FakeAI:
    async def summarize_report(self, brand, data):
        assert data["totals"]["published"] == 2
        return {
            "headline": "A strong October for Acme",
            "worked": ["Short how-to posts drew most engagement"],
            "next": ["Post two how-tos a week"],
        }


# ---- a report for a period --------------------------------------------------------------------
async def test_report_covers_the_period_and_exports_csv(api, db, brand):
    from spark.models import FollowerSnapshot
    from spark.services import reports

    bid = brand.id
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == bid))
    acc.followers = 1200
    await _published(
        db, brand, acc, "How to brief a designer", datetime(2026, 10, 5, 9, tzinfo=UTC), 1000, 80
    )
    await _published(db, brand, acc, "Studio tour", datetime(2026, 10, 20, 9, tzinfo=UTC), 400, 10)
    await _published(
        db, brand, acc, "Older post", datetime(2026, 9, 10, 9, tzinfo=UTC), 900, 50
    )  # previous period
    db.add(
        FollowerSnapshot(account_id=acc.id, day=date(2026, 10, 1), followers=1000, source="spark")
    )
    db.add(
        FollowerSnapshot(account_id=acc.id, day=date(2026, 10, 31), followers=1150, source="spark")
    )
    await db.commit()
    assert (
        await reports.snapshot_followers(db) == 1
    )  # today's snapshot from the account's follower count
    assert await reports.snapshot_followers(db) == 0  # once a day

    r = await api.post(
        f"{API}/brands/{bid}/reports", json={"start": "2026-10-01", "end": "2026-10-31"}
    )
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["title"].startswith("Acme") and rep["start"] == "2026-10-01"
    d = rep["data"]
    assert (
        d["totals"]["published"] == 2
        and d["totals"]["impressions"] == 1400
        and d["totals"]["engagements"] == 96
    )
    assert d["channels"][0]["handle"] == "acme" and d["channels"][0]["posts"] == 2
    assert (
        d["top_posts"][0]["content"].startswith("How to") and d["top_posts"][0]["engagements"] == 83
    )
    assert (
        d["followers"]["start"] == 1000
        and d["followers"]["end"] == 1150
        and d["followers"]["delta"] == 150
    )
    assert (
        d["compare"]["published"]["previous"] == 1
        and d["compare"]["engagements"]["pct"] is not None
    )
    assert "inbox" in d and d["series"][0]["day"] == "2026-10-01"
    assert [x["id"] for x in (await api.get(f"{API}/brands/{bid}/reports")).json()] == [rep["id"]]
    r = await api.get(f"{API}/brands/{bid}/reports/{rep['id']}/csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert (
        lines[0].startswith("section,")
        and any(l.startswith("channel,acme,") for l in lines)
        and any("How to brief a designer" in l for l in lines)
    )
    assert (await api.delete(f"{API}/brands/{bid}/reports/{rep['id']}")).status_code == 204
    assert (await api.get(f"{API}/brands/{bid}/reports")).json() == []


async def test_report_summary_is_written_by_ai(api, db, brand, monkeypatch):
    from spark.services import ai as ai_svc

    bid = brand.id
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == bid))
    await _published(db, brand, acc, "One", datetime(2026, 10, 5, 9, tzinfo=UTC), 100, 5)
    await _published(db, brand, acc, "Two", datetime(2026, 10, 6, 9, tzinfo=UTC), 100, 5)
    rep = (
        await api.post(
            f"{API}/brands/{bid}/reports",
            json={"start": "2026-10-01", "end": "2026-10-31", "title": "October"},
        )
    ).json()
    assert rep["title"] == "October" and rep["summary"] is None
    r = await api.post(f"{API}/brands/{bid}/reports/{rep['id']}/summary")
    assert r.status_code == 400 and r.json()["code"] == "ai_unavailable"
    monkeypatch.setattr(ai_svc, "ContentAI", lambda **kw: FakeAI())
    r = await api.post(f"{API}/brands/{bid}/reports/{rep['id']}/summary")
    assert r.status_code == 200 and r.json()["summary"]["headline"].startswith("A strong October")
    assert (await api.get(f"{API}/brands/{bid}/reports/{rep['id']}")).json()["summary"]["next"] == [
        "Post two how-tos a week"
    ]


@respx.mock
async def test_follower_snapshots_use_zernio_when_it_answers(api, db, brand, monkeypatch):
    from spark.models import FollowerSnapshot
    from spark.services import reports

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    z = SocialAccount(
        brand_id=brand.id,
        platform="linkedin",
        provider="zernio",
        external_id="z-li",
        handle="acme-li",
        followers=50,
    )
    z.access_token = "tok"
    db.add(z)
    (
        await db.scalar(
            select(SocialAccount).where(
                SocialAccount.brand_id == brand.id, SocialAccount.handle == "acme"
            )
        )
    ).followers = 10
    await db.commit()
    respx.get("https://zernio.com/api/v1/accounts/follower-stats").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"accountId": "z-li", "date": date.today().isoformat(), "followers": 5600}]
            },
        )
    )
    assert await reports.snapshot_followers(db) == 2
    rows = {s.account_id: s for s in (await db.execute(select(FollowerSnapshot))).scalars()}
    assert rows[z.id].followers == 5600 and rows[z.id].source == "zernio"
    other = next(s for aid, s in rows.items() if aid != z.id)
    assert other.source == "spark"


@respx.mock
async def test_follower_stats_tolerates_odd_shapes(monkeypatch):
    """Zernio answered /accounts/follower-stats with strings in `data` on production; nothing may crash."""
    from spark.platforms.zernio import ZernioAdapter

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    z = ZernioAdapter()
    for payload in (
        {"data": ["z-li", "z-ig"]},
        {"data": "nope"},
        {"stats": None},
        [],
        {"data": {"z-li": {"followers": 7, "date": "2026-11-09"}}},
        {
            "data": [
                {"accountId": "z-li", "followers": 9, "date": "2026-11-10"},
                {"accountId": "z-li", "followersCount": 8, "date": "2026-11-01"},
                "junk",
            ]
        },
    ):
        respx.get("https://zernio.com/api/v1/accounts/follower-stats").mock(
            return_value=httpx.Response(200, json=payload)
        )
        out = await z.follower_stats({"z-li", "z-ig"})
        assert isinstance(out, dict)
    assert out == {"z-li": 9}
    respx.get("https://zernio.com/api/v1/accounts/follower-stats").mock(
        return_value=httpx.Response(
            200, json={"data": {"z-li": {"followers": 7, "date": "2026-11-09"}}}
        )
    )
    assert await z.follower_stats({"z-li"}) == {"z-li": 7}
