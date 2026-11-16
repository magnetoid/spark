"""Phase 4: the weekly review. Last week's posts against each channel's own median (not industry
averages), a few plain findings, and those findings handed to the next weekly plan."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from spark.models import ContentPillar, Metric, Post, PostStatus, PostTarget, SocialAccount
from spark.services import agent, review
from tests.api.conftest import API

TODAY = date(2026, 11, 18)  # a Wednesday; last week is Mon Nov 9 to Sun Nov 15
LAST_MON = date(2026, 11, 9)


async def _acc(db, brand) -> SocialAccount:
    return await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))


async def _post(
    db,
    acc,
    when: date,
    likes: int,
    *,
    impressions=1000,
    post_type="post",
    pillar=None,
    text="Hello",
):
    at = datetime.combine(when, datetime.min.time(), UTC) + timedelta(hours=10)
    p = Post(brand_id=acc.brand_id, content=text, status=PostStatus.published, pillar_id=pillar)
    t = PostTarget(
        account_id=acc.id, status=PostStatus.published, published_at=at, post_type=post_type
    )
    p.targets = [t]
    db.add(p)
    await db.flush()
    db.add(
        Metric(
            target_id=t.id, captured_at=at + timedelta(days=1), impressions=impressions, likes=likes
        )
    )
    await db.commit()
    return p


async def _baseline(db, acc, values=(10, 10, 10, 20, 20, 20)):
    for i, v in enumerate(values):
        await _post(db, acc, LAST_MON - timedelta(days=3 + i * 5), v)


def _by_text(out):
    return {p["text"]: p for p in out["posts"]}


async def test_posts_against_the_channels_own_median(db, brand):
    acc = await _acc(db, brand)
    await _baseline(db, acc)  # median 15 engagements
    await _post(db, acc, LAST_MON, 45, text="Great one")
    await _post(db, acc, LAST_MON + timedelta(days=2), 15, text="Usual one")
    await _post(db, acc, LAST_MON + timedelta(days=4), 5, text="Quiet one")
    await _post(db, acc, TODAY, 90, text="This week")  # not part of last week
    out = await review.weekly_review(db, brand, today=TODAY)
    assert out["week_start"] == LAST_MON and out["week_end"] == LAST_MON + timedelta(days=6)
    posts = _by_text(out)
    assert set(posts) == {"Great one", "Usual one", "Quiet one"}
    assert posts["Great one"]["verdict"] == "above" and posts["Great one"]["vs_usual"] == 3.0
    assert posts["Usual one"]["verdict"] == "usual" and posts["Quiet one"]["verdict"] == "below"
    base = out["baselines"][0]
    assert base["median_engagements"] == 15 and base["posts"] == 6
    assert out["counts"] == {"posts": 3, "above": 1, "usual": 1, "below": 1, "unrated": 0}
    assert any("Great one" in f and "3.0×" in f for f in out["findings"])


async def test_too_few_earlier_posts_means_no_rating(db, brand):
    acc = await _acc(db, brand)
    await _baseline(db, acc, values=(10, 20))
    await _post(db, acc, LAST_MON, 45, text="Early days")
    out = await review.weekly_review(db, brand, today=TODAY)
    assert _by_text(out)["Early days"]["verdict"] == "unrated"
    assert out["counts"]["unrated"] == 1


async def test_a_format_that_beat_the_usual_is_named(db, brand):
    acc = await _acc(db, brand)
    pillar = ContentPillar(brand_id=brand.id, name="Behind the scenes")
    db.add(pillar)
    await db.commit()
    await _baseline(db, acc)
    await _post(db, acc, LAST_MON, 40, post_type="reel", pillar=pillar.id, text="Reel A")
    await _post(
        db, acc, LAST_MON + timedelta(days=1), 35, post_type="reel", pillar=pillar.id, text="Reel B"
    )
    await _post(db, acc, LAST_MON + timedelta(days=3), 6, text="Plain")
    out = await review.weekly_review(db, brand, today=TODAY)
    text = " ".join(out["findings"])
    assert "Reels did" in text and "Behind the scenes" in text


async def test_an_earlier_week_can_be_asked_for(db, brand):
    acc = await _acc(db, brand)
    await _post(db, acc, LAST_MON - timedelta(days=7), 12, text="Two weeks ago")
    out = await review.weekly_review(db, brand, week=LAST_MON - timedelta(days=5), today=TODAY)
    assert out["week_start"] == LAST_MON - timedelta(days=7)
    assert [p["text"] for p in out["posts"]] == ["Two weeks ago"]


async def test_the_weekly_plan_reads_last_weeks_findings(db, brand, monkeypatch):
    acc = await _acc(db, brand)
    await _baseline(db, acc)
    await _post(db, acc, LAST_MON, 45, text="Great one")
    monkeypatch.setattr(review, "_today", lambda tz: TODAY)
    task = await agent._task(db, brand, "weekly_plan", None)
    assert "own usual" in task and "Great one" in task


async def test_review_through_the_api(api, db, brand):
    r = await api.get(f"{API}/brands/{brand.id}/weekly-review")
    assert r.status_code == 200, r.text
    assert {"week_start", "posts", "findings", "counts", "baselines"} <= set(r.json())
    r = await api.get(f"{API}/brands/{brand.id}/weekly-review", params={"week": "2026-11-02"})
    assert r.status_code == 200 and r.json()["week_start"] == "2026-11-02"
    assert (
        await api.get(f"{API}/brands/{brand.id}/weekly-review", params={"week": "x"})
    ).status_code == 422
