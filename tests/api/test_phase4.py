"""Phase 4 API: every remaining page's data and actions."""

import io
from datetime import UTC, datetime, timedelta

import httpx
import respx
from sqlalchemy import select

from spark.models import (
    Campaign,
    Contact,
    Metric,
    Post,
    PostStatus,
    PostTarget,
    QueueSlot,
    Role,
    SocialAccount,
    User,
)
from tests.api.conftest import API


async def _bid(api):
    return (await api.get(f"{API}/brands")).json()[0]["id"]


# ---- analytics --------------------------------------------------------------------------
async def test_analytics_overview_and_refresh(api, db, brand):
    acc = await db.scalar(select(SocialAccount))
    p = Post(brand_id=brand.id, content="Top post", status=PostStatus.published, scheduled_at=datetime.now(UTC) - timedelta(days=1))
    t = PostTarget(account_id=acc.id, status=PostStatus.published, published_at=datetime.now(UTC) - timedelta(days=1), remote_id="r1", remote_url="https://example.com/r1")
    p.targets = [t]
    db.add(p)
    await db.flush()
    db.add(Metric(target_id=t.id, captured_at=datetime.now(UTC), impressions=1000, likes=50, comments=5, shares=5, clicks=10))
    await db.commit()
    bid = await _bid(api)
    r = await api.get(f"{API}/brands/{bid}/analytics", params={"days": 7})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["days"] == 7 and a["impressions"] == 1000 and a["engagements"] == 70 and a["published"] == 1
    assert len(a["series"]) == 7 and a["by_platform"]["dry_run"]["impressions"] == 1000
    assert a["top"][0]["post_id"] == p.id and a["top"][0]["url"] == "https://example.com/r1"
    assert "link_clicks_series" in a and isinstance(a["best_times"], list)
    r = await api.post(f"{API}/brands/{bid}/analytics/refresh")
    assert r.status_code == 200 and "collected" in r.json()


# ---- campaigns --------------------------------------------------------------------------
async def test_campaigns_crud_with_counts(api, db, brand):
    bid = await _bid(api)
    r = await api.post(f"{API}/brands/{bid}/campaigns", json={"name": "Spring", "goal": "Sell", "color": "#2F6FED",
                                                                "starts_on": "2026-12-01", "ends_on": "2026-12-20", "utm_campaign": "spring"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["starts_on"].startswith("2026-12-01") and r.json()["counts"]["total"] == 0
    r = await api.patch(f"{API}/brands/{bid}/campaigns/{cid}", json={"name": "Spring sale", "color": "#1F8F5F"})
    assert r.status_code == 200 and r.json()["name"] == "Spring sale"
    rows = (await api.get(f"{API}/brands/{bid}/campaigns")).json()
    assert rows[0]["id"] == cid and rows[0]["counts"] == {"total": 0, "draft": 0, "pending_approval": 0, "scheduled": 0, "publishing": 0, "published": 0, "failed": 0}
    assert (await api.delete(f"{API}/brands/{bid}/campaigns/{cid}")).status_code == 204
    assert await db.get(Campaign, cid) is None


async def test_campaign_ai_plan_creates_drafts(api, db, brand, monkeypatch):
    from spark.services import campaigns as svc

    class FakeAI:
        async def plan_campaign(self, brand, goal, starts, ends, platforms, per_week):
            from spark.services.ai import CampaignPlan, PlannedPost

            return CampaignPlan(summary="One post", posts=[PlannedPost(date=str(starts), theme="Kickoff", text="Day one", platforms=platforms)])

    monkeypatch.setattr(svc, "ContentAI", lambda: FakeAI())
    bid = await _bid(api)
    acc = await db.scalar(select(SocialAccount))
    start = (datetime.now(UTC) + timedelta(days=3)).date()
    r = await api.post(f"{API}/brands/{bid}/campaigns", json={"name": "Planned", "goal": "Awareness", "starts_on": start.isoformat(),
                                                                "ends_on": (start + timedelta(days=14)).isoformat(),
                                                                "ai_plan": {"account_ids": [acc.id], "per_week": 2}})
    assert r.status_code == 201, r.text
    assert r.json()["counts"]["draft"] == 1 and r.json()["planned"] == 1
    post = await db.scalar(select(Post).where(Post.campaign_id == r.json()["id"]))
    assert post.content == "Day one" and post.source == "ai" and post.targets[0].account_id == acc.id


# ---- links, feeds -----------------------------------------------------------------------
async def test_links_crud(api, db, brand):
    bid = await _bid(api)
    r = await api.post(f"{API}/brands/{bid}/links", json={"destination": "example.com/page", "title": "Page", "utm_source": "x", "utm_medium": "social"})
    assert r.status_code == 201, r.text
    link = r.json()
    assert link["destination"].startswith("https://example.com/page?") and "utm_source=x" in link["destination"]
    assert link["short_url"].endswith(f"/l/{link['code']}") and link["clicks"] == 0
    assert [l["id"] for l in (await api.get(f"{API}/brands/{bid}/links")).json()["items"]] == [link["id"]]
    assert (await api.delete(f"{API}/brands/{bid}/links/{link['id']}")).status_code == 204


async def test_feeds_crud(api, db, brand):
    bid = await _bid(api)
    acc = await db.scalar(select(SocialAccount))
    r = await api.post(f"{API}/brands/{bid}/feeds", json={"url": "https://example.com/rss.xml", "name": "Blog", "use_ai": True, "auto_queue": False, "account_ids": [acc.id]})
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    r = await api.patch(f"{API}/brands/{bid}/feeds/{fid}", json={"is_active": False, "auto_queue": True})
    assert r.json()["is_active"] is False and r.json()["auto_queue"] is True
    assert len((await api.get(f"{API}/brands/{bid}/feeds")).json()) == 1
    assert (await api.delete(f"{API}/brands/{bid}/feeds/{fid}")).status_code == 204


# ---- contacts, lists, email --------------------------------------------------------------
async def test_contacts_lists_import_export(api, db, brand):
    bid = await _bid(api)
    r = await api.post(f"{API}/brands/{bid}/lists", json={"name": "Newsletter", "description": "Weekly"})
    assert r.status_code == 201
    lid = r.json()["id"]
    r = await api.post(f"{API}/brands/{bid}/contacts", json={"email": "Ana@Example.com", "first_name": "Ana", "list_ids": [lid]})
    assert r.status_code == 201 and r.json()["email"] == "ana@example.com" and r.json()["lists"] == [lid]
    assert (await api.post(f"{API}/brands/{bid}/contacts", json={"email": "nope"})).status_code == 422
    csv_data = b"email,name\nbob@example.com,Bob Builder\nbad,x\nana@example.com,Ana Again\n"
    r = await api.post(f"{API}/brands/{bid}/contacts/import", files={"file": ("c.csv", io.BytesIO(csv_data), "text/csv")}, data={"list_ids": str(lid)})
    assert r.status_code == 200 and r.json()["imported"] == 2
    page = (await api.get(f"{API}/brands/{bid}/contacts", params={"q": "bob"})).json()
    assert page["total"] == 2 and page["subscribed"] == 2 and [c["email"] for c in page["items"]] == ["bob@example.com"]
    assert len((await api.get(f"{API}/brands/{bid}/contacts", params={"list_id": lid})).json()["items"]) == 2
    r = await api.get(f"{API}/brands/{bid}/contacts/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "bob@example.com" in r.text
    cid = page["items"][0]["id"]
    assert (await api.delete(f"{API}/brands/{bid}/contacts/{cid}")).status_code == 204
    assert (await api.delete(f"{API}/brands/{bid}/lists/{lid}")).status_code == 204
    assert await db.scalar(select(Contact).where(Contact.email == "ana@example.com")) is not None


async def test_email_campaigns_flow(api, db, brand, monkeypatch):
    bid = await _bid(api)
    lid = (await api.post(f"{API}/brands/{bid}/lists", json={"name": "L"})).json()["id"]
    await api.post(f"{API}/brands/{bid}/contacts", json={"email": "a@example.com", "list_ids": [lid]})
    r = await api.post(f"{API}/brands/{bid}/email", json={"name": "Launch mail", "list_id": lid})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["status"] == "draft" and r.json()["recipients"] == 1
    r = await api.patch(f"{API}/brands/{bid}/email/{cid}", json={"subject": "Hello", "body_html": "<p>Hi {{first_name}}</p>", "action": "schedule"})
    assert r.status_code == 422 and r.json()["code"] == "validation"  # no time given
    when = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    r = await api.patch(f"{API}/brands/{bid}/email/{cid}", json={"subject": "Hello", "body_html": "<p>Hi {{first_name}}</p>", "action": "schedule", "scheduled_at": when})
    assert r.status_code == 200 and r.json()["status"] == "scheduled"
    r = await api.patch(f"{API}/brands/{bid}/email/{cid}", json={"action": "unschedule"})
    assert r.json()["status"] == "draft"
    from spark.services import jobs

    calls = []

    async def fake(job, *a):
        calls.append((job, a))
        return True

    monkeypatch.setattr(jobs, "enqueue", fake)
    r = await api.patch(f"{API}/brands/{bid}/email/{cid}", json={"action": "send"})
    assert r.status_code == 200 and r.json()["status"] == "scheduled" and calls == [("send_email_campaign", (cid,))]
    r = await api.post(f"{API}/brands/{bid}/email/{cid}/test")
    assert r.status_code == 200 and "owner@example.com" in r.json()["message"]
    rows = (await api.get(f"{API}/brands/{bid}/email")).json()
    assert rows[0]["id"] == cid and rows[0]["stats"] == {"sent": 0, "opened": 0, "clicked": 0, "failed": 0}
    assert (await api.get(f"{API}/brands/{bid}/email/{cid}")).json()["body_html"].startswith("<p>Hi")
    assert (await api.delete(f"{API}/brands/{bid}/email/{cid}")).status_code == 204


# ---- bio ---------------------------------------------------------------------------------
async def test_bio_page_roundtrip(api, db, brand):
    bid = await _bid(api)
    r = await api.get(f"{API}/brands/{bid}/bio")
    assert r.status_code == 200 and r.json()["title"] == "Acme" and r.json()["public_url"].endswith("/b/acme")
    r = await api.put(f"{API}/brands/{bid}/bio", json={"title": "Acme links", "bio": "Hi", "theme": "dark", "capture_email": False, "is_published": True,
                                                         "links": [{"label": "Site", "url": "https://example.com"}, {"label": "", "url": "x"}]})
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["theme"] == "dark" and len(page["links"]) == 1 and page["links"][0]["code"] and page["links"][0]["clicks"] == 0
    code = page["links"][0]["code"]
    r = await api.put(f"{API}/brands/{bid}/bio", json={**page, "links": [{"label": "Site renamed", "url": "https://example.com", "code": code}]})
    assert r.json()["links"][0]["code"] == code  # same destination keeps its code and click history


# ---- channels -----------------------------------------------------------------------------
async def test_channels_platforms_connect_toggle_delete(api, db, brand):
    bid = await _bid(api)
    r = await api.get(f"{API}/brands/{bid}/platforms")
    assert r.status_code == 200
    direct = {p["name"]: p for p in r.json()["direct"]}
    assert direct["dry_run"]["connect_mode"] == "credentials" and direct["dry_run"]["credential_fields"][0]["name"] == "handle"
    assert "x" in r.json()["zernio"] and r.json()["zernio_ready"] is False
    r = await api.post(f"{API}/brands/{bid}/accounts/connect/dry_run", json={"handle": "second"})
    assert r.status_code == 201, r.text
    new_id = r.json()["accounts"][0]["id"]
    assert r.json()["accounts"][0]["handle"] == "second"
    r = await api.post(f"{API}/brands/{bid}/accounts/{new_id}/toggle")
    assert r.json()["is_active"] is False
    assert (await api.delete(f"{API}/brands/{bid}/accounts/{new_id}")).status_code == 204
    assert (await api.post(f"{API}/brands/{bid}/accounts/connect/nope", json={})).status_code == 404


@respx.mock
async def test_zernio_import_via_api(api, db, brand, monkeypatch):
    from spark.config import get_settings

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    respx.get("https://zernio.com/api/v1/accounts").mock(return_value=httpx.Response(200, json={"accounts": [
        {"_id": "z1", "platform": "linkedin", "username": "imba", "displayName": "Imba", "profileId": "p1"}]}))
    bid = await _bid(api)
    r = await api.post(f"{API}/brands/{bid}/accounts/zernio/import")
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1 and r.json()["accounts"][0]["platform"] == "linkedin"


# ---- settings: slots, team, brand delete -------------------------------------------------
async def test_slots_team_and_brand_delete(api, db, brand):
    bid = await _bid(api)
    r = await api.post(f"{API}/brands/{bid}/slots", json={"weekdays": [0, 2], "time": "09:30"})
    assert r.status_code == 201 and sorted(s["weekday"] for s in r.json()) == [0, 2]
    assert (await api.post(f"{API}/brands/{bid}/slots", json={"weekdays": [0], "time": "9:3"})).status_code == 422
    slots = (await api.get(f"{API}/brands/{bid}/slots")).json()
    assert (await api.delete(f"{API}/brands/{bid}/slots/{slots[0]['id']}")).status_code == 204
    assert await db.scalar(select(QueueSlot).where(QueueSlot.id == slots[0]["id"])) is None

    r = await api.post(f"{API}/team", json={"name": "Ed", "email": "ed@example.com", "password": "longenough1", "role": "editor"})
    assert r.status_code == 201 and r.json()["role"] == "editor"
    uid = r.json()["id"]
    assert (await api.post(f"{API}/team", json={"name": "Ed", "email": "ed@example.com", "password": "longenough1", "role": "editor"})).status_code == 409
    r = await api.patch(f"{API}/team/{uid}", json={"role": "viewer", "is_active": False})
    assert r.json()["role"] == "viewer" and r.json()["is_active"] is False
    me = (await api.get(f"{API}/me")).json()
    assert (await api.patch(f"{API}/team/{me['id']}", json={"role": "viewer"})).status_code == 409  # not yourself
    assert len((await api.get(f"{API}/team")).json()) == 2

    other = (await api.post(f"{API}/brands", json={"name": "Temp"})).json()
    assert (await api.delete(f"{API}/brands/{other['id']}")).status_code == 204
    assert (await api.get(f"{API}/brands/{other['id']}")).status_code == 404


# ---- connectors + tokens ------------------------------------------------------------------
async def test_connectors_api(api, db, brand):
    r = await api.get(f"{API}/settings/connectors")
    assert r.status_code == 200 and r.json()[0]["key"] == "zernio" and r.json()[0]["configured"] is False
    r = await api.get(f"{API}/settings/connectors/zernio")
    assert r.status_code == 200
    fields = {f["name"]: f for f in r.json()["fields"]}
    assert fields["zernio_api_key"]["kind"] == "secret" and fields["zernio_api_key"]["has_value"] is False
    r = await api.put(f"{API}/settings/connectors/zernio", json={"values": {"zernio_api_key": "sk_live_abc_1234567"}})
    assert r.status_code == 200, r.text
    fields = {f["name"]: f for f in r.json()["fields"]}
    assert fields["zernio_api_key"]["has_value"] and fields["zernio_api_key"]["source"] == "saved" and "sk_live" not in str(r.json())
    r = await api.put(f"{API}/settings/connectors/zernio", json={"clear": ["zernio_api_key"]})
    assert {f["name"]: f for f in r.json()["fields"]}["zernio_api_key"]["has_value"] is False
    assert (await api.get(f"{API}/settings/connectors/nope")).status_code == 404
    user = await db.scalar(select(User))
    user.role = Role.editor
    await db.commit()
    assert (await api.put(f"{API}/settings/connectors/zernio", json={"values": {}})).status_code == 403


async def test_api_tokens(api, db, brand):
    r = await api.post(f"{API}/me/tokens", json={"name": "Claude Code"})
    assert r.status_code == 201 and r.json()["token"].startswith("spk_") and r.json()["name"] == "Claude Code"
    tid = r.json()["id"]
    rows = (await api.get(f"{API}/me/tokens")).json()
    assert rows[0]["id"] == tid and "token" not in rows[0]
    assert (await api.delete(f"{API}/me/tokens/{tid}")).status_code == 204
    assert (await api.get(f"{API}/me/tokens")).json() == []


# ---- inbox (live from Zernio) --------------------------------------------------------------
@respx.mock
async def test_inbox_list_and_reply(api, db, brand, monkeypatch):
    from spark.config import get_settings

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    acc = SocialAccount(brand_id=brand.id, platform="linkedin", provider="zernio", external_id="z-acc", handle="imba")
    db.add(acc)
    await db.commit()
    respx.get("https://zernio.com/api/v1/inbox/comments").mock(return_value=httpx.Response(200, json={
        "data": [{"id": "p1", "accountId": "z-acc", "platform": "linkedin", "content": "Hello", "commentCount": 2, "likeCount": 4,
                  "createdTime": "2026-11-01T10:00:00Z"}], "pagination": {"hasMore": False}}))
    respx.get("https://zernio.com/api/v1/inbox/comments/p1").mock(return_value=httpx.Response(200, json={
        "comments": [{"id": "c1", "text": "Nice", "author": {"name": "Ana"}, "createdAt": "2026-11-01T10:00:00Z"}], "pagination": {}}))
    reply = respx.post("https://zernio.com/api/v1/inbox/comments/p1").mock(return_value=httpx.Response(200, json={"ok": True}))
    bid = await _bid(api)
    r = await api.get(f"{API}/brands/{bid}/inbox")
    assert r.status_code == 200, r.text
    assert r.json()["ready"] is True and r.json()["items"][0]["post_id"] == "p1" and r.json()["items"][0]["account"]["handle"] == "imba"
    r = await api.get(f"{API}/brands/{bid}/inbox/p1/comments", params={"account": "z-acc"})
    assert r.status_code == 200 and r.json()["comments"][0]["text"] == "Nice"
    r = await api.post(f"{API}/brands/{bid}/inbox/p1/reply", json={"account": "z-acc", "message": "Thanks!", "comment_id": "c1"})
    assert r.status_code == 200 and reply.called
    assert (await api.post(f"{API}/brands/{bid}/inbox/p1/reply", json={"account": "nope", "message": "x"})).status_code == 404


# ---- palette ---------------------------------------------------------------------------------
async def test_palette_lists_actions_channels_and_posts(api, db, brand):
    bid = await _bid(api)
    r = await api.get(f"{API}/brands/{bid}/palette")
    assert r.status_code == 200
    groups = {i["group"] for i in r.json()}
    assert {"Actions", "Channels"} <= groups and any(i["label"] == "Post to acme" for i in r.json())
