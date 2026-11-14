"""Phase 1A of the improvement plan: small bugs that cost trust, and publishing that never
posts twice. Each test names the behaviour a user sees."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from spark.config import get_settings
from spark.models import Media, Post, PostStatus, PostTarget, SocialAccount
from tests.api.conftest import API
from tests.api.test_phase9 import Z, _comment_event, _signed, zacc  # noqa: F401


async def _comment_item(api, anon, brand):
    raw, headers = _signed(_comment_event())
    assert (await anon.post("/webhooks/zernio", content=raw, headers=headers)).status_code == 200
    return (await api.get(f"{API}/brands/{brand.id}/inbox")).json()["items"][0]


# ---- inbox ---------------------------------------------------------------------------------
@respx.mock
async def test_like_posts_and_unlike_deletes(api, anon, brand, zacc):  # noqa: F811
    it = await _comment_item(api, anon, brand)
    like = respx.post(f"{Z}/inbox/comments/p1/c1/like").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    unlike = respx.delete(f"{Z}/inbox/comments/p1/c1/like").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    url = f"{API}/brands/{brand.id}/inbox/items/{it['id']}/like"
    assert (await api.post(url, json={"liked": True})).json() == {"liked": True}
    assert like.call_count == 1 and unlike.call_count == 0
    assert (await api.post(url, json={"liked": False})).json() == {"liked": False}
    assert unlike.call_count == 1


async def test_discard_clears_rule_draft(api, anon, db, brand, zacc):  # noqa: F811
    r = await api.post(
        f"{API}/brands/{brand.id}/inbox/rules",
        json={"name": "Price", "keywords": ["how much"], "reply_text": "It is 120 EUR."},
    )
    assert r.status_code == 201, r.text
    it = await _comment_item(api, anon, brand)
    assert it["draft_reply"] == "It is 120 EUR."
    r = await api.delete(f"{API}/brands/{brand.id}/inbox/items/{it['id']}/draft")
    assert r.status_code == 204
    again = (await api.get(f"{API}/brands/{brand.id}/inbox/items/{it['id']}")).json()["item"]
    assert again["draft_reply"] is None and again["status"] == "open"
    counts = (await api.get(f"{API}/brands/{brand.id}/inbox")).json()["counts"]
    assert counts["drafts"] == 0


def _message_event(eid="ev-m1", conv="conv1"):
    return {
        "id": eid,
        "event": "message.received",
        "timestamp": "2026-11-07T10:01:00Z",
        "message": {
            "id": f"m-{eid}",
            "conversationId": conv,
            "platform": "instagram",
            "direction": "incoming",
            "text": "Do you ship to Austria?",
            "sender": {"id": "u2", "name": "Max"},
            "sentAt": "2026-11-07T10:00:30Z",
        },
        "account": {"accountId": "z-ig", "platform": "instagram"},
    }


@respx.mock
async def test_reply_marks_read(api, anon, brand, zacc):  # noqa: F811
    for eid, conv in (("ev-a", "conv-a"), ("ev-b", "conv-b")):
        raw, headers = _signed(_message_event(eid, conv))
        await anon.post("/webhooks/zernio", content=raw, headers=headers)
    items = {
        i["thread_id"]: i for i in (await api.get(f"{API}/brands/{brand.id}/inbox")).json()["items"]
    }
    respx.post(f"{Z}/inbox/conversations/conv-a/messages").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"messageId": "r"}})
    )
    read_a = respx.post(f"{Z}/inbox/conversations/conv-a/read").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    read_b = respx.post(f"{Z}/inbox/conversations/conv-b/read").mock(
        return_value=httpx.Response(500, json={"error": "down"})
    )
    r = await api.post(
        f"{API}/brands/{brand.id}/inbox/items/{items['conv-a']['id']}/reply", json={"text": "Yes"}
    )
    assert r.status_code == 200 and read_a.called
    assert json.loads(read_a.calls.last.request.content) == {"accountId": "z-ig"}
    # resolving without a reply marks it read too; a failure there never blocks the change
    r = await api.post(
        f"{API}/brands/{brand.id}/inbox/items/{items['conv-b']['id']}/status",
        json={"status": "resolved"},
    )
    assert r.status_code == 200 and r.json()["status"] == "resolved" and read_b.called


# ---- Today -----------------------------------------------------------------------------------
async def test_today_does_not_count_plan_drafts_twice(api, db, brand):
    from spark.models import AgentRun

    run = AgentRun(brand_id=brand.id, kind="weekly_plan", status="done")
    db.add(run)
    await db.flush()
    db.add_all(
        [
            Post(brand_id=brand.id, content="mine", status=PostStatus.draft),
            Post(brand_id=brand.id, content="plan", status=PostStatus.draft, agent_run_id=run.id),
            Post(brand_id=brand.id, content="typing", status=PostStatus.draft, is_autosave=True),
        ]
    )
    await db.commit()
    needs = (await api.get(f"{API}/brands/{brand.id}/today")).json()["needs_you"]
    assert needs["drafts"] == 1 and needs["plan_ready"] == 1


# ---- links -------------------------------------------------------------------------------------
async def test_link_field_is_shortened(api, db, brand):
    brand.auto_shorten_links = True
    await db.commit()
    acc = await db.scalar(select(SocialAccount))
    r = await api.post(
        f"{API}/brands/{brand.id}/posts",
        json={
            "content": "New workshop",
            "link": "https://example.com/workshop",
            "targets": [{"account_id": acc.id}],
            "action": "draft",
        },
    )
    assert r.status_code in (200, 201), r.text
    link = r.json()["post"]["link"] if "post" in r.json() else r.json()["link"]
    assert link.startswith(f"{get_settings().base_url}/l/"), link


# ---- media -------------------------------------------------------------------------------------
@respx.mock
async def test_pdf_uploads_as_document(db, brand, monkeypatch):
    from spark.platforms import PublishPayload
    from spark.platforms.zernio import ZernioAdapter

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    (get_settings().media_dir / "deck.pdf").write_bytes(b"%PDF-1.4 test")
    m = Media(
        brand_id=brand.id,
        filename="deck.pdf",
        path="deck.pdf",
        content_type="application/pdf",
        size=13,
    )
    respx.post(f"{Z}/media/presign").mock(
        return_value=httpx.Response(
            200, json={"uploadUrl": "https://up.example/deck", "publicUrl": "https://cdn/deck.pdf"}
        )
    )
    respx.put("https://up.example/deck").mock(return_value=httpx.Response(200))
    adapter = ZernioAdapter.for_platform("linkedin", httpx.AsyncClient())
    item = await adapter._upload(PublishPayload(text="x", media=[m]), m)
    assert item["type"] == "document"


# ---- publishing never posts twice -------------------------------------------------------------
@pytest.fixture
async def zpost(db, brand, monkeypatch):
    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    acc = SocialAccount(
        brand_id=brand.id, platform="linkedin", provider="zernio", external_id="z-li", handle="acme"
    )
    acc.access_token = "zernio"
    db.add(acc)
    await db.flush()
    post = Post(brand_id=brand.id, content="Launch day", status=PostStatus.scheduled)
    post.targets = [
        PostTarget(account_id=acc.id, status=PostStatus.publishing, scheduled_at=datetime.now(UTC))
    ]
    db.add(post)
    await db.commit()
    return post.targets[0].id


def _ok(post_id="zp1"):
    return httpx.Response(
        201,
        json={
            "post": {"_id": post_id, "status": "published", "platforms": [{"status": "published"}]}
        },
    )


def _failed():
    return httpx.Response(
        207,
        json={
            "post": {
                "_id": "zp-f",
                "status": "failed",
                "platforms": [
                    {"status": "failed", "errorMessage": "busy", "errorCategory": "platform_error"}
                ],
            }
        },
    )


async def _attempt(db, tid):
    from spark.services import publisher

    t = await db.get(PostTarget, tid)
    t.status, t.next_attempt_at = PostStatus.publishing, None
    await db.commit()
    db.expire_all()
    return await publisher.publish_target(db, tid)


@respx.mock
async def test_idempotency_key_stable_across_recover_stuck(db, zpost):
    from spark.services import publisher

    route = respx.post(f"{Z}/posts").mock(side_effect=[httpx.ConnectTimeout("slow"), _ok()])
    t = await _attempt(db, zpost)
    assert t.status == PostStatus.scheduled  # a timeout is retried
    # the worker dies mid-publish and the target is recovered later
    t.status = PostStatus.publishing
    t.updated_at = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()
    assert await publisher.recover_stuck(db) == 1
    t = await _attempt(db, zpost)
    assert t.status == PostStatus.published
    keys = [c.request.headers["Idempotency-Key"] for c in route.calls]
    assert len(keys) == 2 and keys[0] == keys[1] and keys[0].startswith(f"spark-t{zpost}-")


@respx.mock
async def test_new_key_after_zernio_says_failed(db, zpost):
    from spark.services import posts

    route = respx.post(f"{Z}/posts").mock(side_effect=[_failed(), _failed(), _ok()])
    t = await _attempt(db, zpost)
    assert t.status == PostStatus.scheduled
    t = await _attempt(db, zpost)
    post = await db.get(Post, t.post_id)
    await db.refresh(post, ["targets"])
    posts.retry_failed(post) if t.status == PostStatus.failed else None
    await db.commit()
    t = await _attempt(db, zpost)
    assert t.status == PostStatus.published
    keys = [c.request.headers["Idempotency-Key"] for c in route.calls]
    assert len(set(keys)) == 3  # Zernio would replay the failed post for a reused key


@respx.mock
async def test_auth_expired_marks_channel_for_reconnect(db, zpost):
    respx.post(f"{Z}/posts").mock(
        return_value=httpx.Response(
            207,
            json={
                "post": {
                    "_id": "zp-a",
                    "status": "failed",
                    "platforms": [
                        {
                            "status": "failed",
                            "errorMessage": "token",
                            "errorCategory": "auth_expired",
                        }
                    ],
                }
            },
        )
    )
    t = await _attempt(db, zpost)
    assert t.status == PostStatus.failed
    acc = await db.get(SocialAccount, t.account_id)
    await db.refresh(acc)
    assert acc.extra.get("needs_reconnection") is True


# ---- publishing health ----------------------------------------------------------------------------
async def test_publishing_health_counts(api, db, brand):
    acc = await db.scalar(select(SocialAccount))
    now = datetime.now(UTC)

    def target(status, **kw):
        return PostTarget(account_id=acc.id, status=status, **kw)

    post = Post(brand_id=brand.id, content="mixed", status=PostStatus.failed)
    post.targets = [
        target(PostStatus.published, published_at=now - timedelta(days=1)),
        target(PostStatus.published, published_at=now - timedelta(days=2)),
        target(PostStatus.published, published_at=now - timedelta(days=20)),
        target(PostStatus.failed, error="Attempt 3 failed, retrying in 30m: 500: down"),
        target(PostStatus.failed, error="Instagram: requires an image or video"),
        target(PostStatus.scheduled, scheduled_at=now + timedelta(hours=3)),
        target(PostStatus.publishing, scheduled_at=now - timedelta(hours=2)),
    ]
    db.add(post)
    await db.commit()
    stuck = post.targets[-1]
    stuck.updated_at = now - timedelta(hours=2)
    await db.commit()

    r = await api.get(f"{API}/brands/{brand.id}/publishing/health")
    assert r.status_code == 200, r.text
    h = r.json()
    assert h["week"] == {"published": 2, "failed": 2, "success_rate_pct": 50.0}
    assert h["month"] == {"published": 3, "failed": 2, "success_rate_pct": 60.0}
    assert {x["reason"]: x["count"] for x in h["failures_by_reason"]} == {
        "500: down": 1,
        "Instagram: requires an image or video": 1,
    }
    assert h["failures_by_channel"][0]["failed"] == 2
    ch = next(c for c in h["channels"] if c["account"]["id"] == acc.id)
    assert ch["next_scheduled_at"] and ch["account"]["health"] == "ok"
    assert h["stuck"] == 1
    assert (await api.get(f"{API}/brands/{brand.id + 99}/publishing/health")).status_code == 404


async def test_healthz_reports_db_and_worker(anon, monkeypatch):
    from spark.services import heartbeat

    async def seen():
        return 42

    async def never():
        return None

    async def redis_ok():
        return True

    monkeypatch.setattr(
        heartbeat, "seen_seconds", never
    )  # a worker on this machine must not leak in
    r = await anon.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["db"] is True and "version" in body
    assert body["worker_seen_s"] is None  # no worker in tests
    monkeypatch.setattr(heartbeat, "seen_seconds", seen)
    monkeypatch.setattr(heartbeat, "redis_ok", redis_ok)
    body = (await anon.get("/healthz")).json()
    assert body["worker_seen_s"] == 42 and body["redis"] is True


# ---- channel settings that publishing reads -------------------------------------------------------
async def _zchannel(db, brand, platform, ext):
    acc = SocialAccount(
        brand_id=brand.id, platform=platform, provider="zernio", external_id=ext, handle=ext
    )
    acc.access_token = "zernio"
    db.add(acc)
    await db.commit()
    return acc


async def test_account_settings_patch_whitelist(api, db, brand):
    tt = await _zchannel(db, brand, "tiktok", "z-tt")
    rd = await _zchannel(db, brand, "reddit", "z-rd")
    url = f"{API}/brands/{brand.id}/accounts"
    r = await api.patch(f"{url}/{tt.id}", json={"settings": {"privacy_level": "SELF_ONLY"}})
    assert r.status_code == 200, r.text
    assert r.json()["settings"] == {"privacy_level": "SELF_ONLY"}
    await db.refresh(tt)
    assert tt.extra["privacy_level"] == "SELF_ONLY"
    # values outside the list, and keys another network uses, are refused
    r = await api.patch(f"{url}/{tt.id}", json={"settings": {"privacy_level": "EVERYONE!"}})
    assert r.status_code == 422 and r.json()["code"] == "invalid_setting"
    r = await api.patch(f"{url}/{tt.id}", json={"settings": {"board_id": "1"}})
    assert r.status_code == 422
    r = await api.patch(f"{url}/{rd.id}", json={"settings": {"subreddit": "r/SmallBusiness"}})
    assert r.json()["settings"] == {"subreddit": "SmallBusiness"}
    r = await api.patch(f"{url}/{rd.id}", json={"settings": {"subreddit": None}})
    assert r.json()["settings"] == {}
    assert (await api.patch(f"{url}/99999", json={"settings": {}})).status_code == 404


@respx.mock
async def test_pinterest_board_choices_come_from_zernio(api, db, brand, monkeypatch):
    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    pin = await _zchannel(db, brand, "pinterest", "z-pin")
    respx.get(f"{Z}/accounts/z-pin/pinterest-boards").mock(
        return_value=httpx.Response(
            200, json={"boards": [{"id": "b1", "name": "Kitchen"}, {"id": "b2", "name": "Garden"}]}
        )
    )
    r = await api.get(f"{API}/brands/{brand.id}/accounts/{pin.id}/settings")
    assert r.status_code == 200, r.text
    field = r.json()["fields"][0]
    assert field["key"] == "board_id"
    assert [o["value"] for o in field["options"]] == ["b1", "b2"]
    r = await api.patch(
        f"{API}/brands/{brand.id}/accounts/{pin.id}", json={"settings": {"board_id": "b2"}}
    )
    assert r.json()["settings"] == {"board_id": "b2"}


async def test_connect_without_a_brand_says_create_one(api, db, brand):
    from urllib.parse import parse_qs, urlsplit

    def notice(r):
        return parse_qs(urlsplit(r.headers["location"]).query)["notice"][0]

    r = await api.get("/accounts/connect/x", params={"brand": "999"})
    assert r.status_code == 303 and notice(r) == "You are not a member of that brand"
    await db.delete(brand)
    await db.commit()
    r = await api.get("/accounts/zernio/connect/instagram")
    assert r.status_code == 303 and notice(r) == "Create a brand first"
