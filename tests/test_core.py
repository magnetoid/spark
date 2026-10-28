from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from spark.models import Brand, Post, PostStatus, PostTarget, SocialAccount
from spark.platforms import PublishPayload, get_adapter
from spark.platforms.bluesky import facets
from spark.platforms.zernio import ZernioAdapter, from_zernio, to_zernio
from spark.security import decrypt, encrypt, hash_password, verify_password
from spark.services import publisher, scheduler
from spark.services.links import add_utm


def test_password_and_crypto_roundtrip():
    h = hash_password("hunter22")
    assert verify_password(h, "hunter22") and not verify_password(h, "nope")
    assert decrypt(encrypt("secret")) == "secret"
    assert decrypt("garbage") is None


def test_add_utm_keeps_existing_params():
    url = add_utm("https://x.io/p?a=1&utm_source=keep", source="new", medium="social", campaign=None)
    assert "a=1" in url and "utm_source=keep" in url and "utm_medium=social" in url
    assert "utm_campaign" not in url


def test_bluesky_facets_use_byte_offsets():
    text = "héllo https://bsky.app #Tag"
    f = facets(text)
    kinds = {x["features"][0]["$type"] for x in f}
    assert kinds == {"app.bsky.richtext.facet#link", "app.bsky.richtext.facet#tag"}
    link = next(x for x in f if "link" in x["features"][0]["$type"])
    assert text.encode()[link["index"]["byteStart"]:link["index"]["byteEnd"]] == b"https://bsky.app"


def test_validate_limits():
    x = get_adapter("x")
    problems = x.validate(PublishPayload(text="a" * 281, media=[]))
    assert any("281/280" in p for p in problems)
    ig = get_adapter("instagram")
    assert any("requires" in p for p in ig.validate(PublishPayload(text="hi", media=[])))


def test_zernio_platform_mapping():
    assert to_zernio("x") == "twitter" and from_zernio("twitter") == "x"
    assert get_adapter("x", provider="zernio").limits.max_chars == 280
    assert get_adapter("reddit").label.startswith("Reddit")


@respx.mock
async def test_zernio_publish_flow(monkeypatch):
    from spark.config import get_settings

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    route = respx.post("https://zernio.com/api/v1/posts").mock(
        return_value=httpx.Response(201, json={"post": {"_id": "p1", "platforms": [
            {"platform": "twitter", "status": "published", "platformPostUrl": "https://x.com/a/1"}]}})
    )
    acc = SocialAccount(id=1, brand_id=1, platform="x", provider="zernio", external_id="acc1",
                        handle="acme", extra={})
    adapter = ZernioAdapter.for_platform("x", httpx.AsyncClient())
    res = await adapter.publish(acc, PublishPayload(text="hello", media=[], link=None))
    assert res.remote_id == "p1" and res.url == "https://x.com/a/1"
    body = route.calls.last.request.content
    assert b'"publishNow": true' in body or b'"publishNow":true' in body
    assert b'"twitter"' in body


@respx.mock
async def test_zernio_failure_categories(monkeypatch):
    from spark.config import get_settings
    from spark.platforms import AuthExpired

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    respx.post("https://zernio.com/api/v1/posts").mock(return_value=httpx.Response(207, json={
        "post": {"_id": "p2", "platforms": [{"status": "failed", "errorCategory": "auth_expired",
                                             "errorMessage": "token dead"}]}}))
    acc = SocialAccount(id=1, brand_id=1, platform="linkedin", provider="zernio", external_id="a", handle="h", extra={})
    with pytest.raises(AuthExpired):
        await ZernioAdapter.for_platform("linkedin", httpx.AsyncClient()).publish(
            acc, PublishPayload(text="x", media=[]))


async def test_publisher_state_machine(db, brand):
    acc = await db.scalar(select(SocialAccount))
    post = Post(brand_id=brand.id, content="hello world")
    post.targets = [PostTarget(account_id=acc.id)]
    db.add(post)
    await db.flush()
    owner_user = await db.scalar(select(__import__("spark.models", fromlist=["User"]).User))
    when = datetime.now(UTC) - timedelta(minutes=1)
    assert scheduler.schedule(post, when, owner_user, brand) == PostStatus.scheduled
    await db.commit()

    ids = await publisher.claim_due(db)
    assert ids == [post.targets[0].id]
    t = await publisher.publish_target(db, ids[0])
    assert t.status == PostStatus.published and t.remote_id and t.remote_url
    await db.refresh(post)
    assert post.status == PostStatus.published


async def test_publisher_permanent_failure(db, brand):
    acc = await db.scalar(select(SocialAccount))
    post = Post(brand_id=brand.id, content="this will #fail")
    post.targets = [PostTarget(account_id=acc.id, status=PostStatus.scheduled,
                               scheduled_at=datetime.now(UTC))]
    db.add(post)
    await db.commit()
    ids = await publisher.claim_due(db)
    t = await publisher.publish_target(db, ids[0])
    assert t.status == PostStatus.failed and "forced failure" in t.error


async def test_approval_flow(db, brand):
    from spark.models import Role, User

    brand.require_approval = True
    editor = User(email="e@example.com", name="E", role=Role.editor, password_hash="x")
    acc = await db.scalar(select(SocialAccount))
    post = Post(brand_id=brand.id, content="needs ok")
    post.targets = [PostTarget(account_id=acc.id)]
    db.add_all([editor, post])
    await db.flush()
    assert scheduler.schedule(post, datetime.now(UTC), editor, brand) == PostStatus.pending_approval
    assert await publisher.claim_due(db) == []
    scheduler.approve(post)
    await db.commit()
    assert len(await publisher.claim_due(db)) == 1


async def test_next_free_slot_skips_taken(db, brand):
    first = await scheduler.next_free_slot(db, brand)
    p = Post(brand_id=brand.id, content="x", status=PostStatus.scheduled, scheduled_at=first)
    db.add(p)
    await db.commit()
    second = await scheduler.next_free_slot(db, brand)
    assert second > first


async def test_web_smoke(client, db, brand):
    for path in ("/", "/compose", "/calendar", "/posts", "/accounts", "/analytics", "/links",
                 "/contacts", "/email", "/bio", "/settings", "/campaigns", "/feeds", "/media"):
        r = await client.get(path)
        assert r.status_code == 200, (path, r.status_code, r.text[:300])
    acc = await db.scalar(select(SocialAccount))
    r = await client.post("/compose", data={"content": "Hello from a test", "action": "draft",
                                            "account_ids": [str(acc.id)]})
    assert r.status_code == 303
    post = await db.scalar(select(Post))
    assert post.content == "Hello from a test" and post.status == PostStatus.draft


async def test_public_short_link_and_bio(client, db, brand):
    r = await client.post("/links", data={"destination": "example.com/x", "utm_source": "t"})
    assert r.status_code == 303
    from spark.models import ShortLink

    link = await db.scalar(select(ShortLink))
    r = await client.get(f"/l/{link.code}")
    assert r.status_code == 302 and r.headers["location"].startswith("https://example.com/x?")
    await client.get("/bio")  # creates the page
    r = await client.get("/b/acme")
    assert r.status_code == 200 and "Acme" in r.text
    r = await client.post("/b/acme/subscribe", data={"email": "fan@example.com"})
    assert r.status_code == 200 and "on the list" in r.text
    b = await db.get(Brand, brand.id)
    assert b is not None


async def test_prioritize_bumps_slot_posts(db, brand):
    from spark.models import User

    acc = await db.scalar(select(SocialAccount))
    owner_user = await db.scalar(select(User))
    first_slot = await scheduler.next_free_slot(db, brand)
    a = Post(brand_id=brand.id, content="A")
    a.targets = [PostTarget(account_id=acc.id)]
    db.add(a)
    await db.flush()
    scheduler.schedule(a, first_slot, owner_user, brand)
    await db.commit()

    b = Post(brand_id=brand.id, content="B")
    b.targets = [PostTarget(account_id=acc.id)]
    db.add(b)
    await db.flush()
    await scheduler.prioritize(db, brand, b, owner_user)
    await db.commit()
    await db.refresh(a)
    await db.refresh(b)
    assert publisher.as_utc(b.scheduled_at) == first_slot
    assert publisher.as_utc(a.scheduled_at) > first_slot
    items = await scheduler.channel_queue(db, brand, acc)
    queued = [i["post"].content for i in items if i["post"]]
    assert queued[:2] == ["B", "A"]


async def test_ideas_board_and_to_post(client, db, brand):
    from spark.models import Idea

    r = await client.post("/ideas", data={"title": "Launch thread", "body": "Three lessons from launch week",
                                          "tags": "Launch, #tips, launch"})
    assert r.status_code == 303
    idea = await db.scalar(select(Idea))
    assert idea.tags == ["launch", "tips"] and idea.status == "idea"
    r = await client.post(f"/ideas/{idea.id}/move", data={"status": "drafting"},
                          headers={"Accept": "application/json"})
    assert r.status_code == 200
    r = await client.post(f"/ideas/{idea.id}/to-post")
    assert r.status_code == 303 and r.headers["location"].endswith("/edit")
    await db.refresh(idea)
    post = await db.get(Post, idea.post_id)
    assert post.content == "Three lessons from launch week" and idea.status == "ready"
    r = await client.get("/ideas")
    assert r.status_code == 200 and "Launch thread" in r.text


@respx.mock
async def test_zernio_thread_items(monkeypatch):
    import json as _json

    from spark.config import get_settings

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    route = respx.post("https://zernio.com/api/v1/posts").mock(
        return_value=httpx.Response(201, json={"post": {"_id": "p9", "platforms": [{"status": "published"}]}})
    )
    acc = SocialAccount(id=1, brand_id=1, platform="x", provider="zernio", external_id="acc1",
                        handle="acme", extra={})
    await ZernioAdapter.for_platform("x", httpx.AsyncClient()).publish(
        acc, PublishPayload(text="root (1/3)", media=[], thread=["two (2/3)", "three (3/3)"]))
    body = _json.loads(route.calls.last.request.content)
    items = body["platforms"][0]["platformSpecificData"]["threadItems"]
    assert [i["content"] for i in items] == ["root (1/3)", "two (2/3)", "three (3/3)"]
    assert "mediaItems" not in body


@respx.mock
async def test_zernio_list_accounts_all_profiles(monkeypatch):
    from spark.config import get_settings

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    route = respx.get("https://zernio.com/api/v1/accounts").mock(return_value=httpx.Response(200, json={
        "accounts": [
            {"_id": "a1", "platform": "linkedin", "username": "Imba Marketing", "isActive": True,
             "profileId": {"_id": "p-default", "name": "Default"}},
            {"_id": "a2", "platform": "twitter", "username": "@imba", "isActive": True,
             "profileId": {"_id": "p-default", "name": "Default"}},
            {"_id": "a3", "platform": "whatsapp", "username": "+381", "isActive": True},
        ],
        "pagination": {"nextCursor": None},
    }))
    pairs = await ZernioAdapter(httpx.AsyncClient()).list_accounts(None)
    assert "profileId" not in dict(route.calls.last.request.url.params)
    assert [(p, a.external_id) for p, a in pairs] == [("linkedin", "a1"), ("x", "a2")]
    assert pairs[0][1].extra["zernio_profile_name"] == "Default"
    assert pairs[1][1].handle == "imba"


@respx.mock
async def test_zernio_inbox_filters_to_brand_accounts(monkeypatch):
    from spark.config import get_settings

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    respx.get("https://zernio.com/api/v1/inbox/comments").mock(return_value=httpx.Response(200, json={
        "data": [
            {"id": "p1", "platform": "linkedin", "accountId": "a1", "commentCount": 3, "isAd": False},
            {"id": "p2", "platform": "facebook", "accountId": "other", "commentCount": 1, "isAd": False},
            {"id": "ad", "platform": "facebook", "accountId": "a1", "commentCount": 9, "isAd": True},
        ],
        "pagination": {"hasMore": False, "nextCursor": None},
    }))
    reply = respx.post("https://zernio.com/api/v1/inbox/comments/p1").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {}}))
    z = ZernioAdapter(httpx.AsyncClient())
    rows = await z.commented_posts({"a1"}, since="2026-10-01")
    assert [r["id"] for r in rows] == ["p1"]
    await z.reply("p1", "a1", "Thanks!", comment_id="c7")
    import json as _json

    assert _json.loads(reply.calls.last.request.content) == {"accountId": "a1", "message": "Thanks!", "commentId": "c7"}
    assert "Idempotency-Key" in reply.calls.last.request.headers
