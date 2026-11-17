"""Phase 4: the winner detector. Posts in the top tenth of their own channel's engagement rate (90
days, ten posts with numbers at least) get two offers: a new angle written by the AI, or a copy for
the channels that missed it. Both land as drafts; a person always schedules them."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import ActivityLog, Metric, Post, PostStatus, PostTarget, SocialAccount
from spark.services import winners
from tests.api.conftest import API

NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)


async def _acc(db, brand) -> SocialAccount:
    return await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))


async def _other(db, brand, platform="dry_run", handle="acme.two", active=True) -> SocialAccount:
    a = SocialAccount(
        brand_id=brand.id,
        platform=platform,
        external_id=f"x-{handle}",
        handle=handle,
        is_active=active,
    )
    a.access_token = "tok"
    db.add(a)
    await db.commit()
    return a


async def _post(db, acc, days_ago: float, likes: int, *, seen=1000, text="Hello", **kw):
    at = NOW - timedelta(days=days_ago)
    p = Post(brand_id=acc.brand_id, content=text, status=PostStatus.published, link=kw.get("link"))
    t = PostTarget(
        account_id=acc.id,
        status=PostStatus.published,
        published_at=at,
        post_type=kw.get("post_type", "post"),
    )
    p.targets = [t]
    db.add(p)
    await db.flush()
    db.add(
        Metric(target_id=t.id, captured_at=at + timedelta(days=1), impressions=seen, likes=likes)
    )
    await db.commit()
    return p, t


async def _pool(db, acc, n=12, likes=10, start_days=35):
    """`n` ordinary posts (1% rate) spread over the 90 days."""
    for i in range(n):
        await _post(db, acc, start_days + i * 4, likes, text=f"Usual {i}")


async def test_top_tenth_of_the_channels_own_rate_is_a_winner(db, brand):
    acc = await _acc(db, brand)
    await _pool(db, acc)
    _p, t = await _post(db, acc, 3, 60, text="Big hit")  # 6% against 1%
    await _post(db, acc, 5, 12, text="Fine")
    out = await winners.find(db, brand, now=NOW)
    assert [w["text"] for w in out["winners"]] == ["Big hit"]
    w = out["winners"][0]
    assert w["target_id"] == t.id and w["engagement_rate_pct"] == 6.0
    assert w["median_rate_pct"] == 1.0 and w["vs_usual"] == 6.0
    assert w["channel_posts"] == 14
    ch = out["channels"][0]
    assert ch["account_id"] == acc.id and ch["posts"] == 14 and ch["rated"] is True


async def test_old_winners_and_tiny_reach_are_left_out(db, brand):
    acc = await _acc(db, brand)
    await _pool(db, acc)
    await _post(db, acc, 45, 80, text="Last month")  # in the pool, too old to offer
    await _post(db, acc, 2, 5, seen=10, text="Ten people saw it")  # 50% of almost nobody
    out = await winners.find(db, brand, now=NOW)
    assert out["winners"] == []


async def test_a_channel_with_few_posts_is_not_rated(db, brand):
    acc = await _acc(db, brand)
    await _pool(db, acc, n=5)
    await _post(db, acc, 3, 60, text="Big hit")
    out = await winners.find(db, brand, now=NOW)
    assert out["winners"] == []
    assert out["channels"][0]["rated"] is False and out["channels"][0]["posts"] == 6
    assert out["min_posts"] == winners.MIN_POOL


async def test_missed_channels_are_the_active_ones_it_did_not_go_to(db, brand):
    acc = await _acc(db, brand)
    two = await _other(db, brand)
    await _other(db, brand, handle="paused", active=False)
    await _pool(db, acc)
    await _post(db, acc, 3, 60, text="Big hit")
    w = (await winners.find(db, brand, now=NOW))["winners"][0]
    assert [m["account_id"] for m in w["missed"]] == [two.id]


async def test_share_to_missed_channels_makes_a_draft(api, db, brand):
    acc = await _acc(db, brand)
    two = await _other(db, brand)
    await _pool(db, acc)
    src, t = await _post(db, acc, 3, 60, text="Big hit", link="https://acme.test/boots")
    r = await api.post(
        f"{API}/brands/{brand.id}/winners/{t.id}/share", json={"account_ids": [two.id]}
    )
    assert r.status_code == 200, r.text
    draft = await db.get(Post, r.json()["post_id"])
    await db.refresh(draft, ["targets"])
    assert draft.status == PostStatus.draft and draft.recycled_from_id == src.id
    assert draft.content == "Big hit" and draft.link == "https://acme.test/boots"
    assert draft.source == "winner_share"
    assert [x.account_id for x in draft.targets] == [two.id]
    assert all(x.status == PostStatus.draft for x in draft.targets)
    log = await db.scalar(select(ActivityLog).where(ActivityLog.object_id == draft.id))
    assert log is not None and "winning post" in log.summary
    # the channel no longer counts as missed, and the draft shows as a follow-up
    w = (await winners.find(db, brand))["winners"]
    hit = next(x for x in w if x["target_id"] == t.id)
    assert hit["missed"] == []
    assert hit["follow_ups"] == [{"post_id": draft.id, "kind": "share", "status": "draft"}]


async def test_share_refuses_channels_it_already_went_to_or_other_brands(api, db, brand):
    acc = await _acc(db, brand)
    await _pool(db, acc)
    _src, t = await _post(db, acc, 3, 60, text="Big hit")
    r = await api.post(
        f"{API}/brands/{brand.id}/winners/{t.id}/share", json={"account_ids": [acc.id]}
    )
    assert r.status_code == 422 and r.json()["code"] == "unknown_channel"
    r = await api.post(
        f"{API}/brands/{brand.id}/winners/999999/share", json={"account_ids": [acc.id]}
    )
    assert r.status_code == 404


async def test_new_angle_is_written_by_the_ai_and_lands_as_a_draft(api, db, brand, monkeypatch):
    from spark.api.routes import winners as routes

    seen = {}

    class FakeAI:
        async def rewrite(self, b, text, instruction, platform=None):
            seen.update(text=text, instruction=instruction, platform=platform)
            return "Boots, but from the shop floor"

    monkeypatch.setattr(routes, "_ai", lambda: FakeAI())
    acc = await _acc(db, brand)
    await _pool(db, acc)
    src, t = await _post(db, acc, 3, 60, text="Big hit", post_type="post")
    r = await api.post(f"{API}/brands/{brand.id}/winners/{t.id}/new-angle", json={})
    assert r.status_code == 200, r.text
    draft = await db.get(Post, r.json()["post_id"])
    await db.refresh(draft, ["targets"])
    assert draft.content == "Boots, but from the shop floor"
    assert draft.status == PostStatus.draft and draft.source == "winner_angle"
    assert draft.recycled_from_id == src.id
    assert [x.account_id for x in draft.targets] == [acc.id]
    assert seen["text"] == "Big hit" and "angle" in seen["instruction"]
    assert seen["platform"] == acc.platform


async def test_new_angle_without_ai_says_so(api, db, brand, monkeypatch):
    from spark.api.routes import winners as routes
    from spark.services.ai import AIUnavailable

    def no_ai():
        raise AIUnavailable("No AI key")

    monkeypatch.setattr(routes, "_ai", no_ai)
    acc = await _acc(db, brand)
    _src, t = await _post(db, acc, 3, 60, text="Big hit")
    r = await api.post(f"{API}/brands/{brand.id}/winners/{t.id}/new-angle", json={})
    assert r.status_code == 400 and r.json()["code"] == "ai_unavailable"
    assert (await db.scalar(select(Post).where(Post.source == "winner_angle"))) is None


async def test_winners_need_sign_in(anon, brand):
    r = await anon.get(f"{API}/brands/{brand.id}/winners")
    assert r.status_code == 401


async def test_winners_route(api, db, brand):
    acc = await _acc(db, brand)
    await _pool(db, acc, start_days=8)  # recent enough for a real `now`
    await _post(db, acc, 0, 60, text="Big hit")
    r = await api.get(f"{API}/brands/{brand.id}/winners")
    assert r.status_code == 200
    body = r.json()
    assert body["min_posts"] == winners.MIN_POOL and body["top_share_pct"] == 10
    assert [w["text"] for w in body["winners"]] == ["Big hit"]
