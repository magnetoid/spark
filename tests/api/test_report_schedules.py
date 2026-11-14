"""Phase 3A: richer reports (reach, saves, link clicks, followers per channel, reply time), a
public link to a report that a client opens without an account, and reports sent on a
schedule."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from spark.models import (
    BrandMember,
    FollowerSnapshot,
    InboxItem,
    LinkClick,
    Metric,
    Post,
    PostStatus,
    PostTarget,
    Report,
    ReportSchedule,
    Role,
    ShareLink,
    ShortLink,
    SocialAccount,
    User,
)
from spark.services import ai as ai_svc
from spark.services import report_schedules
from spark.services.email import ConsoleSender
from tests.api.conftest import API


async def _acc(db, brand) -> SocialAccount:
    return await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))


async def _published(db, acc, when: datetime, **metric) -> PostTarget:
    p = Post(brand_id=acc.brand_id, content="Boots are back", status=PostStatus.published)
    t = PostTarget(account_id=acc.id, status=PostStatus.published, published_at=when)
    p.targets = [t]
    db.add(p)
    await db.flush()
    db.add(Metric(target_id=t.id, captured_at=when + timedelta(days=1), **metric))
    await db.commit()
    return t


# ---- richer report data -------------------------------------------------------------------------
async def test_report_has_reach_saves_views_and_link_clicks(api, db, brand):
    acc = await _acc(db, brand)
    when = datetime(2026, 10, 5, 9, tzinfo=UTC)
    t = await _published(
        db, acc, when, impressions=0, views=500, reach=300, saves=10, likes=40, clicks=0
    )
    link = ShortLink(brand_id=brand.id, code="boots", destination="https://x.example")
    db.add(link)
    await db.flush()
    for _ in range(3):
        db.add(LinkClick(link_id=link.id, target_id=t.id, clicked_at=when + timedelta(hours=2)))
    db.add(LinkClick(link_id=link.id, clicked_at=when + timedelta(hours=3)))  # not from a post
    await db.commit()
    r = await api.post(
        f"{API}/brands/{brand.id}/reports", json={"start": "2026-10-01", "end": "2026-10-31"}
    )
    d = r.json()["data"]
    assert d["totals"]["views"] == 500 and d["totals"]["reach"] == 300
    assert d["totals"]["saves"] == 10
    assert d["totals"]["seen"] == 500
    assert d["totals"]["engagement_rate_pct"] == 10.0  # (40 + 10) / 500 views
    assert d["totals"]["link_clicks"] == 4
    assert d["top_posts"][0]["link_clicks"] == 3


async def test_report_followers_per_channel(api, db, brand):
    acc = await _acc(db, brand)
    db.add(FollowerSnapshot(account_id=acc.id, day=date(2026, 10, 1), followers=1000))
    db.add(FollowerSnapshot(account_id=acc.id, day=date(2026, 10, 31), followers=1120))
    await db.commit()
    r = await api.post(
        f"{API}/brands/{brand.id}/reports", json={"start": "2026-10-01", "end": "2026-10-31"}
    )
    ch = r.json()["data"]["followers"]["by_channel"]
    assert ch == [
        {
            "account_id": acc.id,
            "platform": acc.platform,
            "handle": acc.handle,
            "start": 1000,
            "end": 1120,
            "delta": 120,
        }
    ]


async def test_report_median_reply_time(api, db, brand):
    acc = await _acc(db, brand)
    base = datetime(2026, 10, 10, 12, tzinfo=UTC)
    for i, minutes in enumerate((10, 30, 50, None)):
        db.add(
            InboxItem(
                brand_id=brand.id,
                account_id=acc.id,
                kind="comment",
                external_id=f"c{i}",
                received_at=base,
                replied_at=base + timedelta(minutes=minutes) if minutes else None,
            )
        )
    await db.commit()
    r = await api.post(
        f"{API}/brands/{brand.id}/reports", json={"start": "2026-10-01", "end": "2026-10-31"}
    )
    inbox = r.json()["data"]["inbox"]
    assert inbox["replied"] == 3 and inbox["median_reply_minutes"] == 30


# ---- public link ----------------------------------------------------------------------------------
async def _report(api, brand) -> dict:
    r = await api.post(
        f"{API}/brands/{brand.id}/reports", json={"start": "2026-10-01", "end": "2026-10-31"}
    )
    return r.json()


async def test_report_link_opens_without_login_until_revoked(api, anon, db, brand):
    rep = await _report(api, brand)
    r = await api.post(f"{API}/brands/{brand.id}/reports/{rep['id']}/share", json={"days": 30})
    assert r.status_code == 201, r.text
    share = r.json()
    assert "/r/" in share["url"] and share["kind"] == "report"
    token = share["token"]
    r = await anon.get(f"{API}/public/reports/{token}")
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["title"] == rep["title"] and page["brand"]["name"] == "Acme"
    assert page["data"]["totals"] == rep["data"]["totals"]
    assert "report" in [
        l["kind"] for l in (await api.get(f"{API}/brands/{brand.id}/share-links")).json()
    ]
    assert (
        await api.delete(f"{API}/brands/{brand.id}/share-links/{share['id']}")
    ).status_code == 204
    assert (await anon.get(f"{API}/public/reports/{token}")).status_code == 404


async def test_report_and_review_tokens_do_not_mix(api, anon, db, brand):
    rep = await _report(api, brand)
    report_token = (
        await api.post(f"{API}/brands/{brand.id}/reports/{rep['id']}/share", json={})
    ).json()["token"]
    review_token = (await api.post(f"{API}/brands/{brand.id}/share-links", json={})).json()["token"]
    assert (await anon.get(f"{API}/public/review/{report_token}")).status_code == 404
    assert (await anon.get(f"{API}/public/reports/{review_token}")).status_code == 404


async def test_expired_report_link(api, anon, db, brand):
    rep = await _report(api, brand)
    share = (
        await api.post(f"{API}/brands/{brand.id}/reports/{rep['id']}/share", json={"days": 1})
    ).json()
    link = await db.get(ShareLink, share["id"])
    link.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    assert (await anon.get(f"{API}/public/reports/{share['token']}")).status_code == 404


async def test_deleting_a_report_ends_its_link(api, anon, db, brand):
    rep = await _report(api, brand)
    token = (await api.post(f"{API}/brands/{brand.id}/reports/{rep['id']}/share", json={})).json()[
        "token"
    ]
    await api.delete(f"{API}/brands/{brand.id}/reports/{rep['id']}")
    assert (await anon.get(f"{API}/public/reports/{token}")).status_code == 404


# ---- schedules ------------------------------------------------------------------------------------
async def test_schedule_crud_and_validation(api, db, brand):
    base = f"{API}/brands/{brand.id}/report-schedules"
    r = await api.post(base, json={"cadence": "weekly", "recipients": ["client@example.com"]})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["hour"] == 8 and s["is_active"] and s["next_period"]["days"] == 7
    assert [x["id"] for x in (await api.get(base)).json()] == [s["id"]]
    r = await api.patch(
        f"{base}/{s['id']}", json={"cadence": "monthly", "is_active": False, "hour": 9}
    )
    assert r.status_code == 200 and r.json()["cadence"] == "monthly" and not r.json()["is_active"]
    assert (
        await api.post(base, json={"cadence": "weekly", "recipients": ["nope"]})
    ).status_code == 422
    assert (
        await api.post(base, json={"cadence": "daily", "recipients": ["a@example.com"]})
    ).status_code == 422
    assert (await api.post(base, json={"cadence": "weekly", "recipients": []})).status_code == 422
    assert (await api.delete(f"{base}/{s['id']}")).status_code == 204
    assert (await api.get(base)).json() == []


async def test_viewers_cannot_schedule_reports(api, db, brand):
    user = await db.scalar(select(User))
    user.role = Role.viewer
    db.add(BrandMember(brand_id=brand.id, user_id=user.id, role="viewer"))
    await db.commit()
    r = await api.post(
        f"{API}/brands/{brand.id}/report-schedules",
        json={"cadence": "weekly", "recipients": ["client@example.com"]},
    )
    assert r.status_code == 403


async def _schedule(db, brand, **kw) -> ReportSchedule:
    s = ReportSchedule(
        brand_id=brand.id,
        cadence=kw.pop("cadence", "weekly"),
        recipients=kw.pop("recipients", ["client@example.com"]),
        **kw,
    )
    db.add(s)
    await db.commit()
    return s


MONDAY = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


async def test_weekly_report_made_shared_and_sent_once(db, brand):
    s = await _schedule(db, brand)
    ConsoleSender.sent.clear()
    assert await report_schedules.send_due(db, ConsoleSender(), now=MONDAY) == 1
    rep = await db.scalar(select(Report).where(Report.brand_id == brand.id))
    assert (rep.start, rep.end) == (date(2026, 11, 9), date(2026, 11, 15))
    link = await db.scalar(select(ShareLink).where(ShareLink.kind == "report"))
    assert link.scope == {"report_id": rep.id}
    mail = ConsoleSender.sent[-1]
    assert mail["to"] == "client@example.com" and "Acme" in mail["subject"]
    assert "/r/" in mail["html"]
    await db.refresh(s)
    assert s.last_period_end == date(2026, 11, 15)
    assert (
        await report_schedules.send_due(db, ConsoleSender(), now=MONDAY + timedelta(hours=3)) == 0
    )
    assert await db.scalar(select(func.count(Report.id))) == 1


async def test_not_sent_before_the_hour_or_when_paused(db, brand):
    await _schedule(db, brand, hour=10)
    assert await report_schedules.send_due(db, ConsoleSender(), now=MONDAY) == 0
    await _schedule(db, brand, is_active=False)
    assert await report_schedules.send_due(db, ConsoleSender(), now=MONDAY) == 0


async def test_monthly_covers_the_last_month(db, brand):
    await _schedule(db, brand, cadence="monthly")
    assert (
        await report_schedules.send_due(
            db, ConsoleSender(), now=datetime(2026, 12, 1, 9, tzinfo=UTC)
        )
        == 1
    )
    rep = await db.scalar(select(Report))
    assert (rep.start, rep.end) == (date(2026, 11, 1), date(2026, 11, 30))


async def test_schedule_follows_the_brand_timezone(db, brand):
    brand.timezone = "America/New_York"
    await db.commit()
    await _schedule(db, brand, hour=8)
    # 05:00 UTC on Monday is midnight in New York: not yet 08:00 there
    assert (
        await report_schedules.send_due(
            db, ConsoleSender(), now=datetime(2026, 11, 16, 5, tzinfo=UTC)
        )
        == 0
    )
    assert (
        await report_schedules.send_due(
            db, ConsoleSender(), now=datetime(2026, 11, 16, 13, 30, tzinfo=UTC)
        )
        == 1
    )


async def test_report_sent_without_summary_when_ai_is_off(db, brand, monkeypatch):
    class NoAI:
        async def summarize_report(self, brand, data):
            raise ai_svc.AIUnavailable("No AI key")

    monkeypatch.setattr(ai_svc, "ContentAI", lambda **kw: NoAI())
    await _schedule(db, brand, with_summary=True)
    ConsoleSender.sent.clear()
    assert await report_schedules.send_due(db, ConsoleSender(), now=MONDAY) == 1
    rep = await db.scalar(select(Report))
    assert rep.summary is None and ConsoleSender.sent


async def test_worker_sends_scheduled_reports():
    from spark import worker

    names = {c.coroutine.__name__ for c in worker.WorkerSettings.cron_jobs}
    assert "send_scheduled_reports" in names


async def test_new_schedule_starts_with_the_next_period(api, db, brand):
    """A schedule made on a Saturday sends the week that ends tomorrow, on Monday, not last
    week's report right away."""
    r = await api.post(
        f"{API}/brands/{brand.id}/report-schedules",
        json={"cadence": "weekly", "recipients": ["client@example.com"]},
    )
    nxt = r.json()["next_period"]
    start, end = date.fromisoformat(nxt["start"]), date.fromisoformat(nxt["end"])
    send_at = datetime.fromisoformat(nxt["send_at"])
    assert start.weekday() == 0 and (end - start).days == 6
    assert send_at > datetime.now(UTC) and send_at.date() == end + timedelta(days=1)
    s = await db.get(ReportSchedule, r.json()["id"])
    assert await report_schedules.send_due(db, ConsoleSender(), now=datetime.now(UTC)) == 0
    r = await api.patch(
        f"{API}/brands/{brand.id}/report-schedules/{s.id}", json={"cadence": "monthly"}
    )
    nxt = r.json()["next_period"]
    assert date.fromisoformat(nxt["start"]).day == 1
    assert date.fromisoformat(nxt["send_at"][:10]) == date.fromisoformat(nxt["end"]) + timedelta(
        days=1
    )


async def test_new_schedule_on_monday_before_the_hour_sends_today(db, brand):
    s = ReportSchedule(brand_id=brand.id, cadence="weekly", hour=10, recipients=["a@example.com"])
    report_schedules.start_from_next(s, brand, now=MONDAY)  # 09:00, before 10:00
    assert s.last_period_end is None
    report_schedules.start_from_next(s, brand, now=MONDAY + timedelta(hours=2))
    assert s.last_period_end == date(2026, 11, 15)
