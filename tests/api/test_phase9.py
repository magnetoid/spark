"""Phase 9, the smart inbox: comments, messages, reviews and mentions kept in Spark, arriving by
webhook and by sync, classified, with suggested replies, saved replies, assignment, status and
rules that prepare a reply for approval."""

import hashlib
import hmac
import json

import httpx
import pytest
import respx

from spark.config import get_settings
from spark.models import SocialAccount
from spark.services.webhooks import webhook_secret
from tests.api.conftest import API

Z = "https://zernio.com/api/v1"


@pytest.fixture
async def zacc(db, brand, monkeypatch):
    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    acc = SocialAccount(
        brand_id=brand.id,
        platform="instagram",
        provider="zernio",
        external_id="z-ig",
        handle="acme.ig",
    )
    acc.access_token = "tok"
    db.add(acc)
    await db.commit()
    return acc


def _signed(body: dict) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    sig = hmac.new(webhook_secret().encode(), raw, hashlib.sha256).hexdigest()
    return raw, {
        "Content-Type": "application/json",
        "X-Zernio-Signature": sig,
        "X-Zernio-Event-Id": body["id"],
        "X-Zernio-Event": body["event"],
    }


def _comment_event(eid="ev-c1", cid="c1", text="How much is the workshop?", username="dana"):
    return {
        "id": eid,
        "event": "comment.received",
        "timestamp": "2026-11-07T10:00:00Z",
        "comment": {
            "id": cid,
            "postId": "p1",
            "platformPostId": "ig_p1",
            "platform": "instagram",
            "text": text,
            "author": {
                "id": "u1",
                "username": username,
                "name": "Dana",
                "picture": "https://img/d.png",
                "isOwnAccount": False,
            },
            "createdAt": "2026-11-07T09:59:00Z",
            "isReply": False,
            "parentCommentId": None,
        },
        "post": {
            "id": "p1",
            "platformPostId": "ig_p1",
            "content": "Autumn workshops",
            "imageUrl": "https://img/p.png",
            "permalink": "https://ig/p/1",
        },
        "account": {
            "id": "a1",
            "accountId": "z-ig",
            "platform": "instagram",
            "username": "acme.ig",
        },
    }


class FakeAI:
    async def classify_inbox(self, brand, items):
        return [
            {
                "id": i["id"],
                "sentiment": "negative"
                if "angry" in i["text"]
                else "positive"
                if "love" in i["text"]
                else "neutral",
                "intent": "complaint"
                if "angry" in i["text"]
                else "question"
                if "?" in i["text"]
                else "praise"
                if "love" in i["text"]
                else "other",
            }
            for i in items
        ]

    async def suggest_replies(self, brand, item, thread):
        return [
            f"Thanks {item['author']}! It is 120 EUR, link in bio.",
            "Great question: 120 EUR, early birds 99.",
            "DM us and we will send the details.",
        ]


# ---- webhooks fill the inbox -------------------------------------------------------------------
async def test_webhooks_create_inbox_items_once(api, anon, db, brand, zacc):
    raw, headers = _signed(_comment_event())
    r = await anon.post("/webhooks/zernio", content=raw, headers=headers)
    assert r.status_code == 200, r.text
    r = await anon.post("/webhooks/zernio", content=raw, headers=headers)  # redelivery
    assert r.status_code == 200
    raw, headers = _signed(
        {
            "id": "ev-m1",
            "event": "message.received",
            "timestamp": "2026-11-07T10:01:00Z",
            "message": {
                "id": "m1",
                "conversationId": "conv1",
                "platform": "instagram",
                "direction": "incoming",
                "text": "Do you ship to Austria?",
                "sender": {"id": "u2", "name": "Max", "username": "max", "picture": None},
                "sentAt": "2026-11-07T10:00:30Z",
                "isRead": False,
            },
            "conversation": {"id": "conv1"},
            "account": {"accountId": "z-ig", "platform": "instagram", "username": "acme.ig"},
        }
    )
    assert (await anon.post("/webhooks/zernio", content=raw, headers=headers)).status_code == 200
    raw, headers = _signed(
        {
            "id": "ev-r1",
            "event": "review.new",
            "timestamp": "2026-11-07T10:02:00Z",
            "review": {
                "id": "accounts/1/locations/2/reviews/3",
                "rating": 2,
                "text": "Waited 40 minutes, angry about it",
                "reviewer": {"name": "Pat", "profileImage": None},
                "created": "2026-11-07T09:00:00Z",
                "locationName": "Acme Vienna",
                "reviewUrl": "https://g/r/3",
            },
            "account": {"accountId": "z-ig", "platform": "googlebusiness", "username": "Acme"},
        }
    )
    assert (await anon.post("/webhooks/zernio", content=raw, headers=headers)).status_code == 200
    r = await api.get(f"{API}/brands/{brand.id}/inbox")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["counts"]["open"] == 3 and {i["kind"] for i in out["items"]} == {
        "comment",
        "message",
        "review",
    }
    c = next(i for i in out["items"] if i["kind"] == "comment")
    assert (
        c["author"]["name"] == "Dana"
        and c["text"].startswith("How much")
        and c["status"] == "open"
        and c["post"]["permalink"] == "https://ig/p/1"
    )
    rv = next(i for i in out["items"] if i["kind"] == "review")
    assert rv["rating"] == 2 and rv["thread_id"].endswith("locations/2")
    assert (await api.get(f"{API}/brands/{brand.id}/inbox", params={"kind": "message"})).json()[
        "items"
    ][0]["thread_id"] == "conv1"
    assert (await api.get(f"{API}/brands/{brand.id}/today")).json()["needs_you"]["replies"] == 3


# ---- sync pulls what webhooks missed -----------------------------------------------------------------
@respx.mock
async def test_sync_upserts_without_duplicates(api, db, brand, zacc):
    respx.get(f"{Z}/inbox/comments").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "p9",
                        "platform": "instagram",
                        "accountId": "z-ig",
                        "content": "Post nine",
                        "permalink": "https://ig/p/9",
                        "createdTime": "2026-11-06T10:00:00Z",
                        "commentCount": 1,
                        "likeCount": 3,
                    }
                ],
                "pagination": {"hasMore": False},
            },
        )
    )
    respx.get(f"{Z}/inbox/comments/p9").mock(
        return_value=httpx.Response(
            200,
            json={
                "comments": [
                    {
                        "id": "c9",
                        "message": "love this",
                        "createdTime": "2026-11-06T11:00:00Z",
                        "from": {
                            "id": "u9",
                            "name": "Lee",
                            "username": "lee",
                            "picture": None,
                            "isOwner": False,
                        },
                        "likeCount": 0,
                        "replyCount": 0,
                        "platform": "instagram",
                        "replies": [],
                    },
                    {
                        "id": "c9r",
                        "message": "thanks!",
                        "createdTime": "2026-11-06T11:05:00Z",
                        "from": {
                            "id": "z",
                            "name": "acme.ig",
                            "username": "acme.ig",
                            "isOwner": True,
                        },
                        "parentId": "c9",
                        "platform": "instagram",
                    },
                ],
                "pagination": {"hasMore": False},
            },
        )
    )
    respx.get(f"{Z}/inbox/conversations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "conv7",
                        "platform": "instagram",
                        "accountId": "z-ig",
                        "participantId": "u7",
                        "participantName": "Kim",
                        "participantPicture": None,
                        "lastMessage": "Is it vegan?",
                        "updatedTime": "2026-11-06T12:00:00Z",
                        "status": "active",
                        "unreadCount": 1,
                    }
                ],
                "pagination": {"hasMore": False},
            },
        )
    )
    respx.get(f"{Z}/inbox/conversations/conv7/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "messages": [
                    {
                        "id": "m7",
                        "conversationId": "conv7",
                        "accountId": "z-ig",
                        "platform": "instagram",
                        "message": "Is it vegan?",
                        "senderId": "u7",
                        "senderName": "Kim",
                        "direction": "incoming",
                        "createdAt": "2026-11-06T12:00:00Z",
                    }
                ],
                "pagination": {"hasMore": False},
            },
        )
    )
    respx.get(f"{Z}/inbox/reviews").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "accounts/1/locations/2/reviews/8",
                        "platform": "googlebusiness",
                        "accountId": "z-ig",
                        "locationId": "2",
                        "locationName": "Acme Vienna",
                        "reviewer": {"id": "r8", "name": "Sam", "profileImage": None},
                        "rating": 5,
                        "text": "Best coffee",
                        "created": "2026-11-05T09:00:00Z",
                        "hasReply": False,
                        "reply": None,
                        "reviewUrl": "https://g/r/8",
                    }
                ],
                "pagination": {"hasMore": False},
                "summary": {"totalReviews": 1, "averageRating": 5},
            },
        )
    )
    respx.get(f"{Z}/inbox/mentions").mock(
        return_value=httpx.Response(200, json={"data": [], "pagination": {"hasMore": False}})
    )
    r = await api.post(f"{API}/brands/{brand.id}/inbox/sync")
    assert r.status_code == 200, r.text
    assert (
        r.json()["new"] == 4
    )  # the owner's own reply is kept as outgoing, not counted as new work
    r = await api.post(f"{API}/brands/{brand.id}/inbox/sync")
    assert r.json()["new"] == 0
    out = (await api.get(f"{API}/brands/{brand.id}/inbox", params={"status": "all"})).json()
    kinds = sorted(i["kind"] for i in out["items"])
    assert kinds == ["comment", "comment", "message", "review"] and out["counts"]["open"] == 3
    reply = next(i for i in out["items"] if i["direction"] == "outgoing")
    assert reply["parent_external_id"] == "c9"


# ---- triage: classify, suggest, assign, resolve, search -------------------------------------------------
async def test_triage_with_ai_and_people(api, anon, db, brand, zacc, monkeypatch):
    from spark.services import ai as ai_svc
    from spark.services import inbox

    monkeypatch.setattr(ai_svc, "ContentAI", lambda **kw: FakeAI())
    for eid, cid, text in (
        ("e1", "c1", "How much is the workshop?"),
        ("e2", "c2", "love the new space"),
        ("e3", "c3", "angry, nobody answered my mail"),
    ):
        raw, headers = _signed(_comment_event(eid, cid, text))
        await anon.post("/webhooks/zernio", content=raw, headers=headers)
    assert await inbox.classify_pending(db) == 3
    out = (await api.get(f"{API}/brands/{brand.id}/inbox")).json()
    by = {i["text"][:4]: i for i in out["items"]}
    assert (
        by["How "]["intent"] == "question"
        and by["love"]["sentiment"] == "positive"
        and by["angr"]["intent"] == "complaint"
    )
    assert out["counts"]["negative"] == 1
    item = by["How "]
    r = await api.post(f"{API}/brands/{brand.id}/inbox/items/{item['id']}/suggest")
    assert (
        r.status_code == 200
        and len(r.json()["suggestions"]) == 3
        and "120" in r.json()["suggestions"][0]
    )
    me = (await api.get(f"{API}/session")).json()["user"]["id"]
    r = await api.post(
        f"{API}/brands/{brand.id}/inbox/items/{item['id']}/assign", json={"user_id": me}
    )
    assert r.json()["assignee"]["id"] == me
    assert [
        i["id"]
        for i in (
            await api.get(f"{API}/brands/{brand.id}/inbox", params={"assignee": "me"})
        ).json()["items"]
    ] == [item["id"]]
    r = await api.post(
        f"{API}/brands/{brand.id}/inbox/items/{item['id']}/status", json={"status": "resolved"}
    )
    assert r.json()["status"] == "resolved"
    assert (await api.get(f"{API}/brands/{brand.id}/inbox")).json()["counts"]["open"] == 2
    assert (
        len(
            (await api.get(f"{API}/brands/{brand.id}/inbox", params={"q": "space"})).json()["items"]
        )
        == 1
    )
    assert (
        (await api.get(f"{API}/brands/{brand.id}/inbox", params={"sentiment": "negative"}))
        .json()["items"][0]["text"]
        .startswith("angry")
    )


# ---- replying -----------------------------------------------------------------------------------------------
@respx.mock
async def test_replies_go_out_by_kind(api, anon, db, brand, zacc):
    bid = brand.id
    raw, headers = _signed(_comment_event())
    await anon.post("/webhooks/zernio", content=raw, headers=headers)
    raw, headers = _signed(
        {
            "id": "ev-m2",
            "event": "message.received",
            "timestamp": "2026-11-07T10:01:00Z",
            "message": {
                "id": "m2",
                "conversationId": "conv2",
                "platform": "instagram",
                "direction": "incoming",
                "text": "Hi",
                "sender": {"id": "u2", "name": "Max"},
                "sentAt": "2026-11-06T10:00:30Z",
            },
            "account": {"accountId": "z-ig", "platform": "instagram"},
        }
    )
    await anon.post("/webhooks/zernio", content=raw, headers=headers)
    raw, headers = _signed(
        {
            "id": "ev-r2",
            "event": "review.new",
            "timestamp": "2026-11-07T10:02:00Z",
            "review": {
                "id": "accounts/1/locations/2/reviews/5",
                "rating": 4,
                "text": "Nice",
                "reviewer": {"name": "Pat"},
                "created": "2026-11-07T09:00:00Z",
            },
            "account": {"accountId": "z-ig", "platform": "googlebusiness"},
        }
    )
    await anon.post("/webhooks/zernio", content=raw, headers=headers)
    items = {i["kind"]: i for i in (await api.get(f"{API}/brands/{bid}/inbox")).json()["items"]}
    c = respx.post(f"{Z}/inbox/comments/p1").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"commentId": "c1-r"}})
    )
    m = respx.post(f"{Z}/inbox/conversations/conv2/messages").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"messageId": "m2-r"}})
    )
    rv = respx.post(f"{Z}/inbox/reviews/accounts%2F1%2Flocations%2F2%2Freviews%2F5/reply").mock(
        return_value=httpx.Response(200, json={"status": "ok", "reply": {"id": "x"}})
    )
    r = await api.post(
        f"{API}/brands/{bid}/inbox/items/{items['comment']['id']}/reply",
        json={"text": "120 EUR, link in bio"},
    )
    assert r.status_code == 200, r.text
    assert json.loads(c.calls.last.request.content) == {
        "accountId": "z-ig",
        "message": "120 EUR, link in bio",
        "commentId": "c1",
    }
    assert r.json()["status"] == "resolved" and r.json()["replied_at"]
    r = await api.post(
        f"{API}/brands/{bid}/inbox/items/{items['message']['id']}/reply", json={"text": "Hello Max"}
    )
    assert (
        r.status_code == 200 and json.loads(m.calls.last.request.content)["message"] == "Hello Max"
    )
    r = await api.post(
        f"{API}/brands/{bid}/inbox/items/{items['review']['id']}/reply",
        json={"text": "Thank you Pat"},
    )
    assert r.status_code == 200 and rv.called
    out = (await api.get(f"{API}/brands/{bid}/inbox", params={"status": "all"})).json()
    assert (
        sum(1 for i in out["items"] if i["direction"] == "outgoing") == 2
    )  # our comment and message replies are kept in the thread
    thread = (await api.get(f"{API}/brands/{bid}/inbox/items/{items['message']['id']}")).json()
    assert [t["direction"] for t in thread["thread"]] == ["incoming", "outgoing"]
    verbs = [a["verb"] for a in (await api.get(f"{API}/brands/{bid}/activity")).json()["items"]]
    assert verbs.count("replied to") == 3


# ---- saved replies and rules ---------------------------------------------------------------------------------
@respx.mock
async def test_saved_replies_and_rules_prepare_a_reply_for_approval(api, anon, db, brand, zacc):
    bid = brand.id
    r = await api.post(
        f"{API}/brands/{bid}/inbox/saved-replies",
        json={
            "title": "Price",
            "body": "The workshop is 120 EUR; early birds 99.",
            "shortcut": "price",
        },
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert [
        s["shortcut"] for s in (await api.get(f"{API}/brands/{bid}/inbox/saved-replies")).json()
    ] == ["price"]
    r = await api.post(
        f"{API}/brands/{bid}/inbox/rules",
        json={
            "name": "Price questions",
            "keywords": ["how much", "price"],
            "kinds": ["comment", "message"],
            "saved_reply_id": sid,
        },
    )
    assert r.status_code == 201, r.text
    raw, headers = _signed(_comment_event("e-rule", "c-rule", "How much is it?"))
    await anon.post("/webhooks/zernio", content=raw, headers=headers)
    raw, headers = _signed(_comment_event("e-norule", "c-norule", "Lovely"))
    await anon.post("/webhooks/zernio", content=raw, headers=headers)
    out = (await api.get(f"{API}/brands/{bid}/inbox", params={"has_draft": "true"})).json()
    assert (
        len(out["items"]) == 1
        and out["items"][0]["draft_reply"].startswith("The workshop is 120")
        and out["items"][0]["draft_rule"]["name"] == "Price questions"
    )
    assert out["counts"]["drafts"] == 1
    sent = respx.post(f"{Z}/inbox/comments/p1").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"commentId": "r"}})
    )
    r = await api.post(
        f"{API}/brands/{bid}/inbox/items/{out['items'][0]['id']}/reply",
        json={"text": out["items"][0]["draft_reply"], "from_draft": True},
    )
    assert r.status_code == 200 and sent.called and r.json()["draft_reply"] is None
    assert (
        await api.patch(
            f"{API}/brands/{bid}/inbox/rules/{(await api.get(f'{API}/brands/{bid}/inbox/rules')).json()[0]['id']}",
            json={"enabled": False},
        )
    ).json()["enabled"] is False
    assert (await api.delete(f"{API}/brands/{bid}/inbox/saved-replies/{sid}")).status_code == 204
