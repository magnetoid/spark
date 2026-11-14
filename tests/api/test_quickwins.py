"""Quick wins after the 2026 integrations research: a current image model, chat notifications,
signed outbound webhooks, post disclosures and two-factor login."""

import base64
import io
import json

import httpx
import respx
from PIL import Image

from spark.config import Settings, get_settings
from spark.services import images
from tests.api.conftest import API


def _png(w=64, h=64, color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


# ---- image model -------------------------------------------------------------------------------
def test_the_default_image_model_is_one_openai_still_serves():
    default = Settings.model_fields["image_model"].default
    assert default not in images.RETIRED_MODELS
    assert default == images.DEFAULT_MODEL


@respx.mock
async def test_a_saved_retired_image_model_falls_back_to_the_current_default(
    api, brand, monkeypatch
):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-img")
    monkeypatch.setattr(get_settings(), "image_model", "gpt-image-1")
    gen = respx.post("https://api.openai.com/v1/images/generations").mock(
        return_value=httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(_png()).decode()}]}
        )
    )
    r = await api.post(
        f"{API}/brands/{brand.id}/media/generate", json={"prompt": "a desk", "size": "square"}
    )
    assert r.status_code == 201, r.text
    assert json.loads(gen.calls.last.request.content)["model"] == images.DEFAULT_MODEL


@respx.mock
async def test_an_unknown_image_model_says_where_to_change_it(api, brand, monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-img")
    monkeypatch.setattr(get_settings(), "image_model", "gpt-image-9-gone")
    respx.post("https://api.openai.com/v1/images/generations").mock(
        return_value=httpx.Response(
            404,
            json={
                "error": {
                    "code": "model_not_found",
                    "message": "The model `gpt-image-9-gone` does not exist",
                }
            },
        )
    )
    r = await api.post(
        f"{API}/brands/{brand.id}/media/generate", json={"prompt": "a desk", "size": "square"}
    )
    assert r.status_code >= 400
    msg = r.json()["detail"]
    assert "gpt-image-9-gone" in msg and "Settings → Connectors → Image generation" in msg


# ---- chat notifications ---------------------------------------------------------------------------
from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

SLACK = "https://hooks.slack.com/services/T0/B0/abc"
DISCORD = "https://discord.com/api/webhooks/1/abc"
TEAMS = "https://prod-1.westeurope.logic.azure.com/workflows/abc/triggers/manual/paths/invoke"
TELEGRAM = "https://api.telegram.org/bot123:ABC/sendMessage"


@pytest.fixture
def public_dns(monkeypatch):
    """Host names resolve to a public address without touching the network."""
    from spark.services import fetch

    monkeypatch.setattr(
        fetch.socket, "getaddrinfo", lambda host, *_a, **_k: [(2, 1, 6, "", ("93.184.216.34", 0))]
    )


def _chat(**values):
    from spark.services import connectors

    connectors.apply(values)


async def _failed_post(db, brand, content="Broken post", error="Platform said no"):
    from spark.models import Post, PostStatus, PostTarget, SocialAccount

    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    post = Post(brand_id=brand.id, content=content, status=PostStatus.failed)
    db.add(post)
    await db.flush()
    db.add(
        PostTarget(
            post_id=post.id, account_id=acc.id, status=PostStatus.failed, error=error, attempts=3
        )
    )
    await db.commit()
    return post


@respx.mock
async def test_chat_sends_each_destination_the_shape_it_expects(public_dns):
    from spark.services import chat

    _chat(
        chat_slack_webhook=SLACK,
        chat_discord_webhook=DISCORD,
        chat_teams_webhook=TEAMS,
        chat_telegram_token="123:ABC",
        chat_telegram_chat_id="-100200",
    )
    routes = {
        name: respx.post(url).mock(return_value=httpx.Response(200, json={"ok": True}))
        for name, url in (
            ("slack", SLACK),
            ("discord", DISCORD),
            ("teams", TEAMS),
            ("telegram", TELEGRAM),
        )
    }

    results = await chat.send(
        "[Acme] A post failed", url="http://testserver/publishing?view=failed", label="Review"
    )

    assert results == {"Slack": None, "Discord": None, "Teams": None, "Telegram": None}
    body = {name: json.loads(r.calls.last.request.content) for name, r in routes.items()}
    assert body["slack"] == {
        "text": "[Acme] A post failed\n<http://testserver/publishing?view=failed|Review>"
    }
    assert body["discord"] == {
        "content": "[Acme] A post failed\n[Review](http://testserver/publishing?view=failed)",
        "allowed_mentions": {"parse": []},
    }
    card = body["teams"]["attachments"][0]
    assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert card["content"]["body"][0]["text"] == "[Acme] A post failed"
    assert card["content"]["actions"] == [
        {
            "type": "Action.OpenUrl",
            "title": "Review",
            "url": "http://testserver/publishing?view=failed",
        }
    ]
    assert body["telegram"] == {
        "chat_id": "-100200",
        "disable_web_page_preview": True,
        "text": "[Acme] A post failed\nReview: http://testserver/publishing?view=failed",
    }


@respx.mock
async def test_chat_never_posts_to_an_address_inside_the_network():
    from spark.services import chat

    _chat(chat_slack_webhook="http://127.0.0.1:6379/hook")
    inside = respx.post("http://127.0.0.1:6379/hook").mock(return_value=httpx.Response(200))

    results = await chat.send("Mila wrote <!channel> & left")

    assert not inside.called
    assert "public" in results["Slack"]


@respx.mock
async def test_chat_reports_a_destination_that_answers_with_an_error_and_does_not_follow_redirects(
    public_dns,
):
    from spark.services import chat

    _chat(chat_slack_webhook=SLACK, chat_discord_webhook=DISCORD)
    respx.post(SLACK).mock(return_value=httpx.Response(404, text="no_team"))
    respx.post(DISCORD).mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/"})
    )
    elsewhere = respx.route(host="169.254.169.254").mock(return_value=httpx.Response(200))

    results = await chat.send("hello")

    assert "404" in results["Slack"] and "302" in results["Discord"]
    assert not elsewhere.called


@respx.mock
async def test_the_chat_connector_test_button_says_where_the_message_went(api, public_dns):
    r = await api.post(f"{API}/settings/connectors/chat/test")
    assert r.status_code == 400 and "destination" in r.json()["detail"]

    r = await api.put(
        f"{API}/settings/connectors/chat",
        json={"values": {"chat_slack_webhook": SLACK}, "clear": []},
    )
    assert r.status_code == 200, r.text
    switches = {f["name"]: f["value"] for f in r.json()["fields"] if f["kind"] == "bool"}
    assert switches == {
        "chat_on_approval": True,
        "chat_on_failed": True,
        "chat_on_review": True,
        "chat_on_published": False,
    }
    slack = respx.post(SLACK).mock(return_value=httpx.Response(200, text="ok"))

    r = await api.post(f"{API}/settings/connectors/chat/test")

    assert r.status_code == 200, r.text
    assert "Slack" in r.json()["message"]
    assert "Spark is connected" in json.loads(slack.calls.last.request.content)["text"]
    card = next(
        c for c in (await api.get(f"{API}/settings/connectors")).json() if c["key"] == "chat"
    )
    assert card["configured"] and card["status"] == "Slack"


@respx.mock
async def test_a_failed_post_reaches_chat_once(db, brand, public_dns):
    from spark.services import notify, outbox
    from spark.services.email import ConsoleSender

    _chat(chat_slack_webhook=SLACK)
    slack = respx.post(SLACK).mock(return_value=httpx.Response(200, text="ok"))
    await _failed_post(db, brand)

    await notify.notify_failed(db, ConsoleSender())
    await outbox.process(db)
    await notify.notify_failed(db, ConsoleSender())
    await outbox.process(db)

    assert slack.call_count == 1
    text = json.loads(slack.calls.last.request.content)["text"]
    assert text.startswith("[Acme] ") and "failed to publish" in text
    assert "Broken post" in text and "Platform said no" in text
    assert "http://testserver/publishing?view=failed" in text


@respx.mock
async def test_a_post_waiting_for_approval_reaches_chat_unless_switched_off(db, brand, public_dns):
    from spark.models import Post, PostStatus
    from spark.services import notify, outbox
    from spark.services.email import ConsoleSender

    _chat(chat_slack_webhook=SLACK)
    slack = respx.post(SLACK).mock(return_value=httpx.Response(200, text="ok"))
    db.add(
        Post(brand_id=brand.id, content="Please look at this", status=PostStatus.pending_approval)
    )
    await db.commit()
    await notify.notify_approvals(db, ConsoleSender())
    await outbox.process(db)
    assert slack.call_count == 1
    text = json.loads(slack.calls.last.request.content)["text"]
    assert "waiting for approval" in text and "Please look at this" in text

    _chat(chat_slack_webhook=SLACK, chat_on_approval=False)
    db.add(Post(brand_id=brand.id, content="Second one", status=PostStatus.pending_approval))
    await db.commit()
    await notify.notify_approvals(db, ConsoleSender())
    await outbox.process(db)
    assert slack.call_count == 1


@respx.mock
async def test_a_published_post_is_an_event_and_is_quiet_in_chat_by_default(db, brand, public_dns):
    from spark.models import OutboundEvent, Post, PostStatus, PostTarget, SocialAccount
    from spark.services import outbox, publisher

    _chat(chat_slack_webhook=SLACK)
    slack = respx.post(SLACK).mock(return_value=httpx.Response(200, text="ok"))
    acc = await db.scalar(select(SocialAccount))

    async def publish(content):
        post = Post(brand_id=brand.id, content=content, status=PostStatus.scheduled)
        post.targets = [
            PostTarget(
                account_id=acc.id, status=PostStatus.publishing, scheduled_at=datetime.now(UTC)
            )
        ]
        db.add(post)
        await db.commit()
        await publisher.publish_target(db, post.targets[0].id)
        return post

    post = await publish("It is live")
    events = (await db.execute(select(OutboundEvent))).scalars().all()
    assert [(e.event, e.brand_id) for e in events] == [("post.published", brand.id)]
    assert (
        events[0].data["post"]["id"] == post.id
        and events[0].data["post"]["content"] == "It is live"
    )
    assert events[0].data["targets"][0]["url"]
    await outbox.process(db)
    assert not slack.called

    _chat(chat_slack_webhook=SLACK, chat_on_published=True)
    await publish("Second one is live")
    await outbox.process(db)
    assert slack.call_count == 1
    assert "published" in json.loads(slack.calls.last.request.content)["text"]


@respx.mock
async def test_a_new_review_reaches_chat_and_an_old_one_imported_later_does_not(
    db, brand, public_dns
):
    from spark.models import OutboundEvent, SocialAccount
    from spark.services import inbox, outbox

    _chat(chat_slack_webhook=SLACK)
    slack = respx.post(SLACK).mock(return_value=httpx.Response(200, text="ok"))
    acc = await db.scalar(select(SocialAccount))
    now = datetime.now(UTC)

    await inbox.upsert(
        db,
        acc,
        "review",
        "r-old",
        text="Fine, a year ago",
        rating=4,
        author_name="Ana",
        received_at=now - timedelta(days=3),
    )
    await inbox.upsert(
        db,
        acc,
        "review",
        "r-new",
        text="Cold coffee",
        rating=2,
        author_name="Mila",
        received_at=now,
    )
    await inbox.upsert(
        db,
        acc,
        "review",
        "r-new",
        text="Cold coffee",
        rating=2,
        author_name="Mila",
        received_at=now,
    )
    await inbox.upsert(
        db, acc, "comment", "c-new", text="Nice!", author_name="Joca", received_at=now
    )
    await inbox.upsert(
        db, acc, "message", "m-out", text="Thanks", direction="outgoing", received_at=now
    )
    await db.commit()

    events = (await db.execute(select(OutboundEvent).order_by(OutboundEvent.id))).scalars().all()
    assert [e.event for e in events] == ["inbox.review", "inbox.comment"]
    await outbox.process(db)
    assert slack.call_count == 1  # comments are for webhooks; chat gets the review
    text = json.loads(slack.calls.last.request.content)["text"]
    assert "Mila" in text and "2/5" in text and "Cold coffee" in text


@respx.mock
async def test_chat_text_from_strangers_cannot_ping_the_whole_channel(public_dns):
    from spark.services import chat

    _chat(chat_slack_webhook=SLACK)
    slack = respx.post(SLACK).mock(return_value=httpx.Response(200, text="ok"))

    await chat.send("Mila wrote <!channel> & left")

    assert (
        json.loads(slack.calls.last.request.content)["text"]
        == "Mila wrote &lt;!channel&gt; &amp; left"
    )


# ---- outbound webhooks ----------------------------------------------------------------------------
import hashlib  # noqa: E402
import hmac  # noqa: E402

HOOK = "https://hooks.example.com/spark"


async def _hook(api, **body) -> dict:
    r = await api.post(f"{API}/webhooks", json={"url": HOOK, **body})
    assert r.status_code == 201, r.text
    return r.json()


async def _emit_and_deliver(db, brand_id, event="post.published", data=None) -> int:
    from spark.services import hooks, outbox

    outbox.emit(db, brand_id, event, data or {"post": {"id": 7, "content": "Hello"}})
    await db.commit()
    await outbox.process(db)
    return await hooks.deliver_due(db)


async def _retry_now(db):
    """Make every waiting delivery due, as if its back-off had passed."""
    from spark.models import WebhookDelivery

    for d in (await db.execute(select(WebhookDelivery))).scalars():
        d.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()


async def test_owners_add_a_webhook_and_see_its_secret_once(api, db, brand, public_dns):
    from tests.api.conftest import _client
    from tests.api.test_final_review import _member

    made = await _hook(api, events=["post.published"], description="Zapier")
    assert made["secret"].startswith("whsec_") and len(made["secret"]) > 30
    assert made["events"] == ["post.published"] and made["enabled"] is True
    assert made["brand_id"] is None

    listed = (await api.get(f"{API}/webhooks")).json()
    assert [w["url"] for w in listed["items"]] == [HOOK]
    assert "secret" not in listed["items"][0]
    assert {"post.published", "post.failed", "inbox.review"} <= {
        e["name"] for e in listed["events"]
    }

    await _member(db, "ed@example.com", brand.id, "editor")
    async with await _client() as ed:
        s = (await ed.get(f"{API}/session")).json()
        ed.headers["X-CSRF-Token"] = s["csrf_token"]
        r = await ed.post(
            f"{API}/auth/login", json={"email": "ed@example.com", "password": "password123"}
        )
        ed.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        assert (await ed.get(f"{API}/webhooks")).status_code == 403
        assert (await ed.post(f"{API}/webhooks", json={"url": HOOK})).status_code == 403


async def test_a_webhook_needs_a_public_address_and_events_spark_knows(api, public_dns):
    for bad in ("http://127.0.0.1:6379/x", "ftp://hooks.example.com/x", "not a url"):
        r = await api.post(f"{API}/webhooks", json={"url": bad})
        assert r.status_code == 422 and r.json()["code"] == "invalid_url", (bad, r.text)
    r = await api.post(f"{API}/webhooks", json={"url": HOOK, "events": ["post.exploded"]})
    assert r.status_code == 422 and r.json()["code"] == "unknown_event"
    r = await api.post(f"{API}/webhooks", json={"url": HOOK, "brand_id": 999})
    assert r.status_code == 404


@respx.mock
async def test_an_event_is_delivered_signed_to_the_endpoints_that_asked_for_it(
    api, db, brand, public_dns
):
    everything = await _hook(api)
    reviews = await api.post(
        f"{API}/webhooks",
        json={"url": "https://other.example.com/in", "events": ["inbox.review"]},
    )
    assert reviews.status_code == 201
    hook = respx.post(HOOK).mock(return_value=httpx.Response(200, text="ok"))
    other = respx.post("https://other.example.com/in").mock(return_value=httpx.Response(200))

    assert await _emit_and_deliver(db, brand.id) == 1

    assert hook.call_count == 1 and not other.called
    req = hook.calls.last.request
    body = json.loads(req.content)
    assert body["event"] == "post.published" and body["id"].startswith("evt_")
    assert body["brand"] == {"id": brand.id, "name": "Acme"}
    assert body["data"] == {"post": {"id": 7, "content": "Hello"}}
    assert body["created_at"].endswith("Z")
    assert req.headers["X-Spark-Event"] == "post.published"
    assert req.headers["X-Spark-Delivery"] and req.headers["User-Agent"].startswith("Spark")
    stamp, sig = (part.split("=", 1)[1] for part in req.headers["X-Spark-Signature"].split(","))
    assert (
        req.headers["X-Spark-Signature"].startswith("t=")
        and ",v1=" in req.headers["X-Spark-Signature"]
    )
    expected = hmac.new(
        everything["secret"].encode(), stamp.encode() + b"." + req.content, hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(sig, expected)
    assert abs(int(stamp) - datetime.now(UTC).timestamp()) < 60

    log = (await api.get(f"{API}/webhooks/{everything['id']}/deliveries")).json()["items"]
    assert [(d["event"], d["status"], d["response_status"], d["attempts"]) for d in log] == [
        ("post.published", "delivered", 200, 1)
    ]
    assert await _emit_and_deliver(db, brand.id, "inbox.review", {"item": {"id": 1}}) == 2


@respx.mock
async def test_a_webhook_for_one_brand_hears_only_that_brand(api, db, brand, public_dns):
    from spark.models import Brand

    other = Brand(name="Other", slug="other", timezone="UTC")
    db.add(other)
    await db.commit()
    await _hook(api, brand_id=other.id)
    hook = respx.post(HOOK).mock(return_value=httpx.Response(204))

    assert await _emit_and_deliver(db, brand.id) == 0
    assert not hook.called
    assert await _emit_and_deliver(db, other.id) == 1
    assert json.loads(hook.calls.last.request.content)["brand"]["name"] == "Other"


@respx.mock
async def test_a_delivery_that_fails_is_tried_again_later_and_given_up_after_six_tries(
    api, db, brand, public_dns
):
    from spark.models import WebhookDelivery

    made = await _hook(api)
    hook = respx.post(HOOK).mock(return_value=httpx.Response(500, text="boom"))

    await _emit_and_deliver(db, brand.id)
    d = await db.scalar(select(WebhookDelivery))
    await db.refresh(d)
    assert (d.status, d.attempts, d.response_status) == ("pending", 1, 500)
    wait = d.next_attempt_at.replace(tzinfo=UTC) - datetime.now(UTC)
    assert timedelta(seconds=30) < wait < timedelta(seconds=90)

    from spark.services import hooks

    assert await hooks.deliver_due(db) == 0  # not due yet
    assert hook.call_count == 1

    for _ in range(10):
        await _retry_now(db)
        await hooks.deliver_due(db)
    await db.refresh(d)
    assert (d.status, d.attempts) == ("failed", 6)
    assert hook.call_count == 6
    row = (await api.get(f"{API}/webhooks")).json()["items"][0]
    assert row["id"] == made["id"] and row["last_status"] == 500 and row["failures"] == 6


@respx.mock
async def test_a_delivery_that_succeeds_on_a_later_try_is_delivered_once(
    api, db, brand, public_dns
):
    from spark.models import WebhookDelivery
    from spark.services import hooks

    await _hook(api)
    hook = respx.post(HOOK).mock(
        side_effect=[httpx.Response(503), httpx.Response(200), httpx.Response(200)]
    )
    await _emit_and_deliver(db, brand.id)
    await _retry_now(db)
    assert await hooks.deliver_due(db) == 1
    await _retry_now(db)
    assert await hooks.deliver_due(db) == 0

    d = await db.scalar(select(WebhookDelivery))
    await db.refresh(d)
    assert (d.status, d.attempts, hook.call_count) == ("delivered", 2, 2)
    assert (await api.get(f"{API}/webhooks")).json()["items"][0]["failures"] == 0


@respx.mock
async def test_an_endpoint_that_keeps_failing_is_switched_off_until_an_owner_turns_it_on(
    api, db, brand, public_dns
):
    from spark.models import WebhookEndpoint
    from spark.services import hooks

    made = await _hook(api)
    hook = respx.post(HOOK).mock(return_value=httpx.Response(410))
    ep = await db.get(WebhookEndpoint, made["id"])
    ep.failures = hooks.DISABLE_AFTER - 1
    await db.commit()

    await _emit_and_deliver(db, brand.id)

    row = (await api.get(f"{API}/webhooks")).json()["items"][0]
    assert row["enabled"] is False and "failed" in row["disabled_reason"]
    assert await _emit_and_deliver(db, brand.id) == 0
    assert hook.call_count == 1

    r = await api.patch(f"{API}/webhooks/{made['id']}", json={"enabled": True})
    assert r.status_code == 200
    assert (r.json()["enabled"], r.json()["failures"], r.json()["disabled_reason"]) == (
        True,
        0,
        None,
    )


@respx.mock
async def test_a_delivery_never_follows_a_redirect_or_reaches_inside_the_network(db, brand):
    from spark.models import WebhookDelivery, WebhookEndpoint
    from spark.security import encrypt

    db.add(
        WebhookEndpoint(url="http://169.254.169.254/latest", secret=encrypt("whsec_x"), events=[])
    )
    db.add(WebhookEndpoint(url="https://93.184.216.34/hook", secret=encrypt("whsec_y"), events=[]))
    await db.commit()
    inside = respx.post("http://169.254.169.254/latest").mock(return_value=httpx.Response(200))
    moved = respx.post("https://93.184.216.34/hook").mock(
        return_value=httpx.Response(302, headers={"Location": "http://169.254.169.254/latest"})
    )

    await _emit_and_deliver(db, brand.id)

    assert not inside.called and moved.call_count == 1
    rows = {d.endpoint_id: d for d in (await db.execute(select(WebhookDelivery))).scalars()}
    assert len(rows) == 2 and all(d.status == "pending" for d in rows.values())
    errors = sorted(d.error for d in rows.values())
    assert "302" in errors[0] and "public" in errors[1]


@respx.mock
async def test_the_test_button_sends_a_signed_test_event_right_away(api, public_dns):
    made = await _hook(api, events=["inbox.review"])
    hook = respx.post(HOOK).mock(return_value=httpx.Response(200, text="ok"))

    r = await api.post(f"{API}/webhooks/{made['id']}/test")

    assert r.status_code == 200, r.text
    assert (r.json()["event"], r.json()["status"], r.json()["response_status"]) == (
        "webhook.test",
        "delivered",
        200,
    )
    req = hook.calls.last.request
    assert req.headers["X-Spark-Event"] == "webhook.test"
    assert json.loads(req.content)["data"]["message"]

    hook.mock(return_value=httpx.Response(500))
    r = await api.post(f"{API}/webhooks/{made['id']}/test")
    assert r.status_code == 200 and r.json()["status"] == "failed" and r.json()["attempts"] == 1
    assert hook.call_count == 2  # a test is sent once, never retried


async def test_a_webhook_can_be_edited_and_removed_with_its_history(api, db, brand, public_dns):
    from spark.models import WebhookDelivery, WebhookEndpoint

    made = await _hook(api)
    r = await api.patch(
        f"{API}/webhooks/{made['id']}",
        json={"events": ["post.failed"], "brand_id": brand.id, "description": "Ops"},
    )
    assert r.status_code == 200 and "secret" not in r.json()
    assert (r.json()["events"], r.json()["brand_id"], r.json()["description"]) == (
        ["post.failed"],
        brand.id,
        "Ops",
    )
    r = await api.patch(f"{API}/webhooks/{made['id']}", json={"url": "http://10.0.0.5/x"})
    assert r.status_code == 422

    db.add(
        WebhookDelivery(endpoint_id=made["id"], event_id="evt_1", event="post.failed", payload={})
    )
    await db.commit()
    assert (await api.delete(f"{API}/webhooks/{made['id']}")).status_code == 204
    assert (await api.get(f"{API}/webhooks")).json()["items"] == []
    db.expire_all()
    assert await db.scalar(select(WebhookEndpoint)) is None
    assert await db.scalar(select(WebhookDelivery)) is None
    assert (await api.get(f"{API}/webhooks/{made['id']}/deliveries")).status_code == 404


# ---- post disclosures and formats --------------------------------------------------------------
from sqlalchemy.orm import selectinload  # noqa: E402

from spark.models import Media, Post, PostTarget, SocialAccount  # noqa: E402
from spark.platforms import PublishPayload, get_adapter  # noqa: E402
from spark.platforms.dry_run import DryRunAdapter  # noqa: E402
from spark.platforms.zernio import ZernioAdapter  # noqa: E402


def _z(platform: str):
    return get_adapter(platform, provider="zernio")


def _media(name="a.png", ctype="image/png", source="upload") -> Media:
    return Media(
        id=1, brand_id=1, filename=name, path=name, content_type=ctype, size=1, source=source
    )


async def _zernio_body(monkeypatch, platform: str, payload: PublishPayload, extra=None) -> dict:
    """What Spark asks Zernio to publish for one channel."""
    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")

    async def fake_upload(self, payload, m):
        return {"url": f"https://cdn.test/{m.filename}", "type": "video" if m.is_video else "image"}

    monkeypatch.setattr(ZernioAdapter, "_upload", fake_upload)
    route = respx.post("https://zernio.com/api/v1/posts").mock(
        return_value=httpx.Response(
            201, json={"post": {"_id": "p1", "platforms": [{"status": "published"}]}}
        )
    )
    acc = SocialAccount(
        id=1,
        brand_id=1,
        platform=platform,
        provider="zernio",
        external_id="a",
        handle="h",
        extra=extra or {},
    )
    async with httpx.AsyncClient() as http:
        await ZernioAdapter.for_platform(platform, http).publish(acc, payload)
    return json.loads(route.calls.last.request.content)


def _psd(body: dict) -> dict:
    return body["platforms"][0].get("platformSpecificData", {})


def test_each_network_says_which_extras_it_carries():
    assert set(_z("instagram").option_keys) == {"ai_generated", "paid_partnership", "collaborators"}
    assert set(_z("x").option_keys) == {"ai_generated", "paid_partnership", "poll"}
    assert set(_z("tiktok").option_keys) == {"ai_generated", "paid_partnership"}
    assert _z("youtube").option_keys == ("ai_generated",)
    assert _z("linkedin").option_keys == ("poll",)
    assert _z("facebook").option_keys == () and _z("threads").option_keys == ()
    assert "story" in _z("instagram").post_types and "story" in _z("facebook").post_types
    # The stand-in used with SPARK_FORCE_DRY_RUN offers what the real network would
    assert DryRunAdapter(impersonate=_z("linkedin")).option_keys == ("poll",)


def test_dry_run_mode_offers_what_the_channels_real_connector_would(monkeypatch):
    monkeypatch.setattr(get_settings(), "force_dry_run", True)
    linkedin = get_adapter("linkedin", provider="zernio")
    assert isinstance(linkedin, DryRunAdapter)
    assert linkedin.option_keys == ("poll",) and linkedin.post_types == ("post", "document")
    assert "story" in get_adapter("facebook", provider="zernio").post_types
    assert set(get_adapter("x", provider="zernio").option_keys) == {
        "ai_generated",
        "paid_partnership",
        "poll",
    }
    # the test channel itself still takes everything
    assert "collaborators" in get_adapter("dry_run").option_keys
    assert "story" in get_adapter("dry_run").post_types


async def test_channels_tell_the_composer_which_extras_to_offer(api, db, brand):
    db.add(
        SocialAccount(
            brand_id=brand.id, platform="youtube", provider="zernio", external_id="yt1", handle="yt"
        )
    )
    await db.commit()
    accounts = (await api.get(f"{API}/brands/{brand.id}/accounts")).json()
    by_platform = {a["platform"]: a["capabilities"] for a in accounts}
    assert by_platform["youtube"]["options"] == ["ai_generated"]
    assert set(by_platform["dry_run"]["options"]) == {
        "ai_generated",
        "paid_partnership",
        "collaborators",
        "poll",
    }


@respx.mock
async def test_instagram_gets_the_ai_label_the_partnership_label_and_collaborators(monkeypatch):
    body = await _zernio_body(
        monkeypatch,
        "instagram",
        PublishPayload(
            text="Launch",
            media=[_media()],
            options={
                "ai_generated": True,
                "paid_partnership": True,
                "collaborators": ["friend", "other"],
            },
        ),
    )
    assert _psd(body) == {
        "isAiGenerated": True,
        "isPaidPartnership": True,
        "collaborators": ["friend", "other"],
    }
    plain = await _zernio_body(
        monkeypatch, "instagram", PublishPayload(text="Launch", media=[_media()])
    )
    assert "platformSpecificData" not in plain["platforms"][0]


@respx.mock
async def test_a_story_is_sent_as_a_story_without_what_stories_refuse(monkeypatch):
    body = await _zernio_body(
        monkeypatch,
        "instagram",
        PublishPayload(
            text="",
            media=[_media()],
            post_type="story",
            first_comment="First!",
            options={"ai_generated": True, "paid_partnership": True, "collaborators": ["friend"]},
        ),
    )
    assert _psd(body) == {"contentType": "story", "isAiGenerated": True}
    fb = await _zernio_body(
        monkeypatch,
        "facebook",
        PublishPayload(text="", media=[_media()], post_type="story", first_comment="First!"),
    )
    assert _psd(fb) == {"contentType": "story"}


@respx.mock
async def test_a_facebook_reel_is_sent_as_a_reel(monkeypatch):
    clip = _media("clip.mp4", "video/mp4")
    body = await _zernio_body(
        monkeypatch,
        "facebook",
        PublishPayload(text="Watch", media=[clip], post_type="reel", first_comment="More inside"),
    )
    assert _psd(body) == {"contentType": "reel", "firstComment": "More inside"}
    # Instagram reads a single video as a Reel on its own; a selector there would be wrong
    ig = await _zernio_body(
        monkeypatch, "instagram", PublishPayload(text="Watch", media=[clip], post_type="reel")
    )
    assert "contentType" not in _psd(ig)


@respx.mock
async def test_x_gets_its_labels_and_a_poll(monkeypatch):
    body = await _zernio_body(
        monkeypatch,
        "x",
        PublishPayload(
            text="Which one?",
            media=[],
            options={
                "ai_generated": True,
                "paid_partnership": True,
                "poll": {"options": ["Tea", "Coffee"], "days": 3},
            },
        ),
    )
    assert _psd(body) == {
        "madeWithAi": True,
        "paidPartnership": True,
        "poll": {"options": ["Tea", "Coffee"], "duration_minutes": 3 * 1440},
    }
    long = await _zernio_body(
        monkeypatch,
        "x",
        PublishPayload(text="?", media=[], options={"poll": {"options": ["A", "B"], "days": 14}}),
    )
    assert _psd(long)["poll"]["duration_minutes"] == 7 * 1440  # X polls run a week at most


@respx.mock
async def test_youtube_is_told_when_a_video_is_synthetic(monkeypatch):
    clip = _media("clip.mp4", "video/mp4")
    body = await _zernio_body(
        monkeypatch,
        "youtube",
        PublishPayload(text="Title\nMore", media=[clip], options={"ai_generated": True}),
    )
    assert _psd(body)["containsSyntheticMedia"] is True and _psd(body)["title"] == "Title"
    plain = await _zernio_body(monkeypatch, "youtube", PublishPayload(text="Title", media=[clip]))
    assert "containsSyntheticMedia" not in _psd(plain)


@respx.mock
async def test_tiktok_always_gets_the_settings_it_requires(monkeypatch):
    clip = _media("clip.mp4", "video/mp4")
    body = await _zernio_body(monkeypatch, "tiktok", PublishPayload(text="Dance", media=[clip]))
    assert body["tiktokSettings"] == {
        "privacy_level": "PUBLIC_TO_EVERYONE",
        "allow_comment": True,
        "allow_duet": True,
        "allow_stitch": True,
        "content_preview_confirmed": True,
        "express_consent_given": True,
    }
    labelled = await _zernio_body(
        monkeypatch,
        "tiktok",
        PublishPayload(
            text="Dance", media=[clip], options={"ai_generated": True, "paid_partnership": True}
        ),
    )
    assert labelled["tiktokSettings"]["video_made_with_ai"] is True
    assert labelled["tiktokSettings"]["commercialContentType"] == "brand_content"
    photos = await _zernio_body(
        monkeypatch,
        "tiktok",
        PublishPayload(
            text="Look", media=[_media(), _media("b.png")], options={"ai_generated": True}
        ),
    )
    assert photos["tiktokSettings"]["media_type"] == "photo"
    # Duet, stitch and the AI label belong to videos; TikTok refuses the label on photo posts
    assert not {"allow_duet", "allow_stitch", "video_made_with_ai"} & set(photos["tiktokSettings"])


@respx.mock
async def test_linkedin_gets_a_poll_with_a_question(monkeypatch):
    body = await _zernio_body(
        monkeypatch,
        "linkedin",
        PublishPayload(
            text="Planning 2027\nTell us below",
            media=[],
            options={"poll": {"question": "Where next?", "options": ["Rome", "Oslo"], "days": 14}},
        ),
    )
    assert _psd(body)["poll"] == {
        "question": "Where next?",
        "options": ["Rome", "Oslo"],
        "duration": "FOURTEEN_DAYS",
    }
    untitled = await _zernio_body(
        monkeypatch,
        "linkedin",
        PublishPayload(
            text="Planning 2027\nTell us below",
            media=[],
            options={"poll": {"options": ["Rome", "Oslo"], "days": 2}, "ai_generated": True},
        ),
    )
    # No question typed: the first line of the post asks it. LinkedIn has no AI label to set.
    assert _psd(untitled) == {
        "poll": {"question": "Planning 2027", "options": ["Rome", "Oslo"], "duration": "THREE_DAYS"}
    }


def test_extras_a_network_would_refuse_are_caught_before_publishing():
    ig, x, li = _z("instagram"), _z("x"), _z("linkedin")

    def problems(adapter, **kw) -> str:
        kw.setdefault("media", [_media()] if adapter is ig else [])
        return " | ".join(adapter.validate(PublishPayload(text="Hi", **kw))).lower()

    assert problems(ig, options={"collaborators": ["a"], "ai_generated": True}) == ""
    assert "story" in problems(ig, post_type="story", options={"paid_partnership": True})
    assert "story" in problems(ig, post_type="story", options={"collaborators": ["a"]})
    assert "first comment" in problems(ig, post_type="story", first_comment="Hi")
    assert "3 collaborators" in problems(ig, options={"collaborators": ["a", "b", "c", "d"]})

    assert problems(x, options={"poll": {"options": ["A", "B"], "days": 1}}) == ""
    assert "2 to 4" in problems(x, options={"poll": {"options": ["A"], "days": 1}})
    assert "2 to 4" in problems(x, options={"poll": {"options": list("ABCDE"), "days": 1}})
    assert "25" in problems(x, options={"poll": {"options": ["A" * 26, "B"], "days": 1}})
    poll = {"poll": {"options": ["A", "B"], "days": 1}}
    assert "poll" in problems(x, media=[_media()], options=poll)
    assert "thread" in problems(x, thread=["more"], options=poll)

    assert problems(li, options={"poll": {"options": ["A" * 30, "B"], "days": 7}}) == ""
    assert "30" in problems(li, options={"poll": {"options": ["A" * 31, "B"], "days": 7}})
    assert "140" in problems(
        li, options={"poll": {"question": "Q" * 141, "options": ["A", "B"], "days": 7}}
    )
    # A network that carries no poll is not asked about one
    assert problems(_z("facebook"), options={"poll": {"options": ["A"], "days": 1}}) == ""


async def _only_account(db, brand) -> SocialAccount:
    return await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))


async def _upload_png(api, bid: int, name: str) -> dict:
    r = await api.post(f"{API}/brands/{bid}/media", files=[("files", (name, _png(), "image/png"))])
    assert r.status_code == 201, r.text
    return r.json()["items"][0]


async def test_extras_are_saved_tidied_and_kept_to_what_the_channel_carries(api, db, brand):
    bid = brand.id
    acc = await _only_account(db, brand)
    li = SocialAccount(
        brand_id=bid, platform="linkedin", provider="zernio", external_id="li1", handle="li"
    )
    db.add(li)
    await db.commit()
    r = await api.post(
        f"{API}/brands/{bid}/posts",
        json={
            "content": "Which city?",
            "targets": [
                {
                    "account_id": acc.id,
                    "options": {
                        "paid_partnership": True,
                        "collaborators": [" @friend ", "", "other"],
                    },
                },
                {
                    "account_id": li.id,
                    "options": {
                        "ai_generated": True,
                        "paid_partnership": True,
                        "collaborators": ["friend"],
                        "poll": {
                            "question": " Where? ",
                            "options": [" Rome ", "", "Oslo"],
                            "days": 7,
                        },
                    },
                },
            ],
            "action": "draft",
        },
    )
    assert r.status_code == 201, r.text
    by_account = {t["account_id"]: t["options"] for t in r.json()["post"]["targets"]}
    assert by_account[acc.id] == {
        "ai_generated": None,
        "paid_partnership": True,
        "collaborators": ["friend", "other"],
        "poll": None,
    }
    assert by_account[li.id] == {
        "ai_generated": None,
        "paid_partnership": False,
        "collaborators": [],
        "poll": {"question": "Where?", "options": ["Rome", "Oslo"], "days": 7},
    }


async def test_a_poll_that_cannot_run_blocks_placing_and_shows_while_typing(api, db, brand):
    bid = brand.id
    acc = await _only_account(db, brand)
    half = {"poll": {"options": ["Only one"], "days": 3}}
    r = await api.post(
        f"{API}/brands/{bid}/posts",
        json={
            "content": "Vote",
            "targets": [{"account_id": acc.id, "options": half}],
            "action": "queue",
        },
    )
    assert r.status_code == 422 and "2 to 4" in r.json()["detail"]
    r = await api.post(
        f"{API}/brands/{bid}/posts/validate",
        json={"targets": {str(acc.id): "Vote"}, "options": {str(acc.id): half}},
    )
    assert any("2 to 4" in p for p in r.json()["problems"][str(acc.id)])


async def test_publishing_carries_the_format_and_extras_and_labels_generated_media(
    api, db, brand, monkeypatch
):
    bid = brand.id
    acc = await _only_account(db, brand)
    one, two = await _upload_png(api, bid, "one.png"), await _upload_png(api, bid, "two.png")
    (await db.get(Media, two["id"])).source = "generated"
    await db.commit()
    sent: list[PublishPayload] = []
    real = DryRunAdapter.publish

    async def spy(self, account, payload):
        sent.append(payload)
        return await real(self, account, payload)

    monkeypatch.setattr(DryRunAdapter, "publish", spy)

    async def publish(options: dict, media_ids: list[int]) -> PublishPayload:
        from spark.services import publisher

        r = await api.post(
            f"{API}/brands/{bid}/posts",
            json={
                "content": "Swipe",
                "media_ids": media_ids,
                "targets": [{"account_id": acc.id, "post_type": "carousel", "options": options}],
                "action": "queue",
            },
        )
        assert r.status_code == 201, r.text
        await publisher.publish_target(db, r.json()["post"]["targets"][0]["id"])
        return sent[-1]

    p = await publish({"collaborators": ["friend"]}, [one["id"], two["id"]])
    assert p.post_type == "carousel"
    assert p.options["collaborators"] == ["friend"]
    assert p.options["ai_generated"] is True  # one image was made by the image model
    p = await publish({"ai_generated": False}, [one["id"], two["id"]])
    assert p.options["ai_generated"] is False  # the author said otherwise
    one_more = await _upload_png(api, bid, "three.png")
    p = await publish({}, [one["id"], one_more["id"]])
    assert not p.options.get("ai_generated")


async def test_a_copy_and_an_unfinished_draft_keep_the_format_and_extras(api, db, brand):
    bid = brand.id
    acc = await _only_account(db, brand)
    target = {
        "account_id": acc.id,
        "post_type": "story",
        "options": {"ai_generated": True, "poll": {"options": ["A", "B"], "days": 1}},
    }
    r = await api.post(
        f"{API}/brands/{bid}/posts",
        json={"content": "Original", "targets": [target], "action": "draft"},
    )
    assert r.status_code == 201, r.text
    r = await api.post(f"{API}/brands/{bid}/posts/{r.json()['post']['id']}/duplicate")
    assert r.status_code == 201, r.text
    copy = r.json()["post"]["targets"][0]
    assert copy["post_type"] == "story"
    assert copy["options"]["ai_generated"] is True
    assert copy["options"]["poll"] == {"question": "", "options": ["A", "B"], "days": 1}

    r = await api.put(
        f"{API}/brands/{bid}/posts/autosave", json={"content": "Typing…", "targets": [target]}
    )
    assert r.status_code == 200, r.text
    saved = await db.scalar(select(PostTarget).where(PostTarget.post_id == r.json()["post_id"]))
    assert saved.post_type == "story" and saved.options["poll"]["options"] == ["A", "B"]


async def test_a_recycled_evergreen_post_keeps_the_format_and_extras(api, db, brand):
    from datetime import UTC, datetime, timedelta

    from spark.models import PostStatus
    from spark.services import evergreen

    acc = await _only_account(db, brand)
    old = datetime.now(UTC) - timedelta(days=90)
    src = Post(
        brand_id=brand.id,
        content="Always true",
        status=PostStatus.published,
        evergreen=True,
        recycle_every_days=30,
        scheduled_at=old,
    )
    src.targets = [
        PostTarget(
            account_id=acc.id,
            status=PostStatus.published,
            published_at=old,
            scheduled_at=old,
            post_type="story",
            options={"paid_partnership": True},
        )
    ]
    db.add(src)
    await db.commit()
    assert await evergreen.recycle(db) == 1
    await db.commit()
    copy = await db.scalar(
        select(Post).where(Post.recycled_from_id == src.id).options(selectinload(Post.targets))
    )
    assert copy.targets[0].post_type == "story"
    assert copy.targets[0].options == {"paid_partnership": True}
