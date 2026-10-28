import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from spark.models import Brand, Post, PostStatus, PostTarget, SocialAccount, User
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


async def test_hashtag_groups_and_templates(client, db, brand):
    from spark.models import HashtagGroup, PostTemplate

    r = await client.post("/settings/hashtags", data={"name": "Launch", "tags": "#launch, SaaS #launch marketing"})
    assert r.status_code == 303
    g = await db.scalar(select(HashtagGroup))
    assert g.tags == ["launch", "SaaS", "marketing"] and g.text == "#launch #SaaS #marketing"
    r = await client.post("/settings/templates", data={"name": "Tip", "body": "Tip: {{thing}}\n\nWhy it works.", "category": "tip"})
    assert r.status_code == 303
    t = await db.scalar(select(PostTemplate))
    assert t.category == "tip"
    r = await client.get("/compose")
    assert r.status_code == 200 and "Insert hashtags" in r.text and '"hashtagGroups": [{"id"' in r.text
    r = await client.get("/settings")
    assert r.status_code == 200 and "#launch #SaaS #marketing" in r.text


async def test_bio_links_are_tracked(client, db, brand):
    from spark.models import ShortLink

    await client.get("/bio")
    r = await client.post("/bio", data={"title": "Acme", "link_label": "Pricing", "link_url": "https://acme.example.com/pricing",
                                        "is_published": "on", "capture_email": "on"})
    assert r.status_code == 303
    link = await db.scalar(select(ShortLink).where(ShortLink.title == "Pricing"))
    assert link and "utm_source=bio" in link.destination
    r = await client.get("/b/acme")
    assert f'href="/l/{link.code}"' in r.text
    r = await client.get(f"/l/{link.code}")
    assert r.status_code == 302
    await db.refresh(link)
    assert link.clicks == 1
    # Re-saving the same link keeps the same code (and its click history)
    await client.post("/bio", data={"title": "Acme", "link_label": "Pricing", "link_url": "https://acme.example.com/pricing",
                                    "link_code": link.code, "is_published": "on"})
    r = await client.get("/bio")
    assert r.status_code == 200 and link.code in r.text and "1 link clicks" in r.text


async def test_csrf_required(client, db, brand):
    saved = client.headers.pop("X-CSRF-Token")
    r = await client.post("/links", data={"destination": "https://example.com"})
    assert r.status_code == 403
    client.headers["X-CSRF-Token"] = saved
    r = await client.post("/links", data={"destination": "https://example.com"})
    assert r.status_code == 303
    r = await client.get("/api/palette")
    assert r.status_code == 200 and any(i["label"] == "Queue" for i in r.json())


async def test_csrf_form_field_without_header(client, db, brand):
    token = client.headers.pop("X-CSRF-Token")
    r = await client.post("/links", data={"destination": "https://example.com/f", "csrf": token})
    assert r.status_code == 303
    files = {"files": ("pic.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")}
    r = await client.post("/media", data={"csrf": token}, files=files)
    assert r.status_code == 303
    client.headers["X-CSRF-Token"] = token


async def test_compose_modal_and_hx_save(client, db, brand):
    acc = await db.scalar(select(SocialAccount))
    r = await client.get(f"/compose/modal?account={acc.id}&at=2030-01-01T10:00")
    assert r.status_code == 200 and "composer(" in r.text and 'hx-post="/compose"' in r.text
    assert "<html" not in r.text  # a partial, not a page
    r = await client.post("/compose", data={"content": "From the modal", "action": "draft",
                                            "account_ids": [str(acc.id)]}, headers={"HX-Request": "true"})
    assert r.status_code == 204 and r.headers.get("HX-Reswap") == "none"
    trig = json.loads(r.headers["HX-Trigger"])
    assert trig["toast"]["message"] == "Draft saved" and trig["post-saved"]["account_ids"] == [acc.id]


async def test_autosave_hidden_until_saved(client, db, brand):
    acc = await db.scalar(select(SocialAccount))
    r = await client.post("/compose/autosave", json={"content": "half-written", "account_ids": [acc.id]})
    pid = r.json()["post_id"]
    r = await client.get("/posts")
    assert "half-written" not in r.text
    r = await client.get("/compose/modal")
    assert "Resume unfinished post" in r.text
    r = await client.post("/compose/autosave", json={"post_id": pid, "content": "half-written, more"})
    assert r.json()["post_id"] == pid
    r = await client.post("/compose", data={"post_id": str(pid), "content": "finished", "action": "draft",
                                            "account_ids": [str(acc.id)]}, headers={"HX-Request": "true"})
    assert r.status_code == 204
    post = await db.get(Post, pid)
    await db.refresh(post)
    assert post.is_autosave is False and post.content == "finished"
    r = await client.get("/posts")
    assert "finished" in r.text


async def test_compose_from_idea_and_reuse(client, db, brand):
    from spark.models import Idea

    acc = await db.scalar(select(SocialAccount))
    await client.post("/ideas", data={"title": "Idea title", "body": "Idea body text", "source_url": "https://x.io"})
    idea = await db.scalar(select(Idea))
    r = await client.get(f"/compose/modal?idea_id={idea.id}")
    assert "Idea body text" in r.text and 'name="idea_id"' in r.text
    r = await client.post("/compose", data={"content": "Idea body text", "action": "draft", "idea_id": str(idea.id),
                                            "account_ids": [str(acc.id)]}, headers={"HX-Request": "true"})
    assert r.status_code == 204
    await db.refresh(idea)
    assert idea.post_id and idea.status == "ready"
    r = await client.get(f"/compose/modal?from_post={idea.post_id}")
    assert "Idea body text" in r.text and f'"selected": [{acc.id}]' in r.text


def test_every_write_route_requires_a_role():
    """Any POST/PUT/PATCH/DELETE route must depend on editor/owner, or be on the allowlist."""
    from fastapi.routing import APIRoute

    from spark.main import app
    from spark.web import deps

    allow = {"/login", "/setup", "/logout", "/b/{slug}/subscribe", "/e/u/{tok}", "/me/prefs", "/me", "/me/password",
             "/webhooks/zernio", "/ideas/{idea_id}/move"}
    offenders = []
    for r in app.routes:
        if not isinstance(r, APIRoute) or not (r.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if r.path in allow:
            continue
        calls = {d.call for d in r.dependant.dependencies}
        if not (calls & {deps.editor, deps.owner}):
            offenders.append(r.path)
    assert offenders == [], offenders


async def test_rate_limit_and_security_headers(client, db, brand):
    r = await client.get("/queue")
    assert r.headers.get("X-Content-Type-Options") == "nosniff" and "Content-Security-Policy" in r.headers
    from spark import main as m

    m._buckets.clear()
    codes = [(await client.get("/l/nope")).status_code for _ in range(125)]
    assert 429 in codes and codes[0] == 404
    m._buckets.clear()


async def test_prefs_and_onboarding(client, db, brand):
    r = await client.get("/")
    assert "Get Spark posting" in r.text
    r = await client.post("/me/prefs", json={"onboarding_dismissed": True, "ignored": 1})
    assert r.json() == {"onboarding_dismissed": True}
    r = await client.get("/")
    assert "Get Spark posting" not in r.text


# ---- Phase E: notifications, preferences, webhooks ------------------------------------

async def _failed_target(db, brand, content="Broken post", error="Platform said no"):
    from spark.models import Post, PostStatus, PostTarget, SocialAccount

    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    post = Post(brand_id=brand.id, content=content, status=PostStatus.failed)
    db.add(post)
    await db.flush()
    t = PostTarget(post_id=post.id, account_id=acc.id, status=PostStatus.failed, error=error, attempts=3)
    db.add(t)
    await db.commit()
    return post, t


async def test_notify_failed_emails_once(db, brand):
    from spark.services import notify
    from spark.services.email import ConsoleSender

    ConsoleSender.sent.clear()
    _post, t = await _failed_target(db, brand)
    assert await notify.notify_failed(db, ConsoleSender()) == 1
    mail = ConsoleSender.sent[-1]
    assert mail["to"] == "owner@example.com" and "failed to publish" in mail["subject"]
    assert "Broken post" in mail["html"] and "Platform said no" in mail["html"]
    await db.refresh(t)
    assert t.notified_at is not None
    assert await notify.notify_failed(db, ConsoleSender()) == 0  # not again


async def test_notify_failed_respects_prefs(db, brand):
    from spark.services import notify
    from spark.services.email import ConsoleSender

    user = await db.scalar(select(User))
    user.prefs = {"notify_failed": False}
    await db.commit()
    await _failed_target(db, brand)
    assert await notify.notify_failed(db, ConsoleSender()) == 0


async def test_notify_approvals(db, brand):
    from spark.models import Post, PostStatus
    from spark.services import notify
    from spark.services.email import ConsoleSender

    ConsoleSender.sent.clear()
    user = await db.scalar(select(User))
    post = Post(brand_id=brand.id, content="Please approve me", status=PostStatus.pending_approval,
                author_id=user.id, scheduled_at=datetime.now(UTC) + timedelta(hours=2))
    db.add(post)
    await db.commit()
    assert await notify.notify_approvals(db, ConsoleSender()) == 1
    assert "approval" in ConsoleSender.sent[-1]["subject"] and "Please approve me" in ConsoleSender.sent[-1]["html"]
    assert await notify.notify_approvals(db, ConsoleSender()) == 0


async def test_weekly_digest(db, brand):
    from spark.services import notify
    from spark.services.email import ConsoleSender

    ConsoleSender.sent.clear()
    assert await notify.weekly_digest(db, ConsoleSender()) == 1
    mail = ConsoleSender.sent[-1]
    assert "Your week on social" in mail["subject"] and "Coming up" in mail["html"]


async def test_preferences_page_and_save(client, db, brand):
    r = await client.get("/me")
    assert r.status_code == 200 and "Weekly digest" in r.text
    r = await client.post("/me", data={"name": "Owner Two", "email": "owner@example.com", "digest_weekly": "true",
                                       "default_action": "next"})
    assert r.status_code == 303
    user = await db.scalar(select(User))
    await db.refresh(user)
    assert user.name == "Owner Two"
    assert user.prefs["default_action"] == "next" and user.prefs["notify_failed"] is False
    # composer honours the default action; shortcuts flag lands on <html>
    r = await client.get("/compose")
    assert "x-data=\"{mode:'next'}\"" in r.text and 'data-shortcuts="off"' in r.text
    r = await client.post("/me/password", data={"current": "wrong", "new": "longenough123"})
    assert r.status_code == 303
    r = await client.post("/me/password", data={"current": "password123", "new": "longenough123"})
    await db.refresh(user)
    from spark.security import verify_password

    assert verify_password(user.password_hash, "longenough123")


def _signed(body: dict) -> tuple[bytes, dict]:
    import hashlib
    import hmac
    import json

    from spark.services.webhooks import webhook_secret

    raw = json.dumps(body).encode()
    sig = hmac.new(webhook_secret().encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-Zernio-Signature": sig, "Content-Type": "application/json"}


async def test_zernio_webhook_signature_and_dedupe(client, db, brand):
    raw, headers = _signed({"id": "evt-1", "event": "webhook.test", "test": True})
    r = await client.post("/webhooks/zernio", content=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 401  # no signature, no CSRF either: signature is the auth
    r = await client.post("/webhooks/zernio", content=raw, headers={**headers, "X-Zernio-Signature": "deadbeef"})
    assert r.status_code == 401
    r = await client.post("/webhooks/zernio", content=raw, headers=headers)
    assert r.status_code == 200 and r.json()["result"] == "test"
    r = await client.post("/webhooks/zernio", content=raw, headers=headers)
    assert r.json()["result"] == "duplicate"


async def test_zernio_webhook_marks_target_published_and_failed(client, db, brand):
    from spark.models import Post, PostStatus, PostTarget, SocialAccount

    acc = SocialAccount(brand_id=brand.id, platform="linkedin", provider="zernio", external_id="z-acc-1",
                        handle="imba")
    db.add(acc)
    await db.flush()
    post = Post(brand_id=brand.id, content="Out via Zernio", status=PostStatus.publishing)
    db.add(post)
    await db.flush()
    t = PostTarget(post_id=post.id, account_id=acc.id, status=PostStatus.publishing, remote_id="zpost-9")
    db.add(t)
    await db.commit()

    raw, headers = _signed({"id": "evt-pub", "event": "post.platform.published",
                            "post": {"id": "zpost-9"}, "account": {"accountId": "z-acc-1", "platform": "linkedin"},
                            "platform": {"name": "linkedin", "status": "published",
                                         "publishedUrl": "https://linkedin.com/posts/1"}})
    r = await client.post("/webhooks/zernio", content=raw, headers=headers)
    assert r.json()["result"] == "updated"
    await db.refresh(t)
    await db.refresh(post)
    assert t.status == PostStatus.published and t.remote_url == "https://linkedin.com/posts/1"
    assert post.status == PostStatus.published

    # a whole-post failure for another target
    post2 = Post(brand_id=brand.id, content="Second", status=PostStatus.publishing)
    db.add(post2)
    await db.flush()
    t2 = PostTarget(post_id=post2.id, account_id=acc.id, status=PostStatus.publishing, remote_id="zpost-10")
    db.add(t2)
    await db.commit()
    raw, headers = _signed({"id": "evt-fail", "event": "post.failed",
                            "post": {"id": "zpost-10", "platforms": [{"accountId": "z-acc-1", "status": "failed",
                                                                       "error": "Token expired"}]}})
    r = await client.post("/webhooks/zernio", content=raw, headers=headers)
    assert r.json()["result"] == "updated"
    await db.refresh(t2)
    assert t2.status == PostStatus.failed and "Token expired" in t2.error

    # the same failure reported again per platform is not a second change
    raw, headers = _signed({"id": "evt-fail-2", "event": "post.platform.failed",
                            "post": {"id": "zpost-10"}, "account": {"accountId": "z-acc-1"},
                            "platform": {"status": "failed", "error": "Token expired"}})
    assert (await client.post("/webhooks/zernio", content=raw, headers=headers)).json()["result"] == "unchanged"

    # removed on the platform after it went out: still published, not a failure
    raw, headers = _signed({"id": "evt-del", "event": "post.platform.deleted",
                            "post": {"id": "zpost-9"}, "account": {"accountId": "z-acc-1"},
                            "platform": {"status": "deleted"}})
    assert (await client.post("/webhooks/zernio", content=raw, headers=headers)).json()["result"] == "updated"
    await db.refresh(t)
    assert t.status == PostStatus.published and t.remote_url is None and "Deleted" in t.error

    # account disconnected -> paused with a reason; connected again -> back
    raw, headers = _signed({"id": "evt-dc", "event": "account.disconnected",
                            "account": {"accountId": "z-acc-1", "disconnectionType": "unintentional",
                                        "reason": "token revoked"}})
    assert (await client.post("/webhooks/zernio", content=raw, headers=headers)).json()["result"] == "disconnected"
    await db.refresh(acc)
    assert acc.is_active is False and "token revoked" in acc.last_error

    brand.zernio_profile_id = "prof-1"
    await db.commit()
    raw, headers = _signed({"id": "evt-c", "event": "account.connected",
                            "account": {"accountId": "z-acc-1", "profileId": "prof-1", "platform": "linkedin",
                                        "username": "imba-new"}})
    assert (await client.post("/webhooks/zernio", content=raw, headers=headers)).json()["result"] == "connected"
    await db.refresh(acc)
    assert acc.is_active is True and acc.handle == "imba-new" and acc.last_error is None


async def test_notify_failed_again_after_retry(db, brand):
    from spark.services import notify, publisher
    from spark.services.email import ConsoleSender

    _post, t = await _failed_target(db, brand)
    assert await notify.notify_failed(db, ConsoleSender()) == 1
    # Retry, then it fails for good a second time: that is news again
    publisher._fail(t, "Still broken")
    await db.commit()
    assert await notify.notify_failed(db, ConsoleSender()) == 1


async def test_notify_approvals_again_after_resubmit(db, brand):
    from spark.models import Post, PostStatus
    from spark.services import notify, scheduler
    from spark.services.email import ConsoleSender

    user = await db.scalar(select(User))
    brand.require_approval = True
    post = Post(brand_id=brand.id, content="Needs a look", status=PostStatus.pending_approval, author_id=user.id)
    db.add(post)
    await db.commit()
    assert await notify.notify_approvals(db, ConsoleSender()) == 1

    class Editor:  # an editor who cannot approve resubmits after the post went back to drafts
        def can_approve(self):
            return False

    when = datetime.now(UTC) + timedelta(hours=3)
    scheduler.schedule(post, when, Editor(), brand)  # still pending: no reset, no second email
    await db.commit()
    assert await notify.notify_approvals(db, ConsoleSender()) == 0
    post.status = PostStatus.draft
    scheduler.schedule(post, when, Editor(), brand)
    await db.commit()
    assert await notify.notify_approvals(db, ConsoleSender()) == 1
