"""Fixes from the final whole-branch review: brand isolation, safe uploads, no DB session in the
SSE stream, past-dated imports, agent runs that finish, approval by brand role, inbox labelling
that gives up, CSV cells that stay text."""

import io
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from PIL import Image
from sqlalchemy import select

from spark.config import get_settings
from spark.models import (
    Brand,
    BrandMember,
    ContactList,
    Post,
    PostStatus,
    PostTarget,
    Role,
    SocialAccount,
    User,
)
from spark.security import hash_password
from tests.api.conftest import API, _client


class Outbox:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, subject: str, html: str) -> None:
        self.sent.append((to, subject))


@asynccontextmanager
async def _login(email: str, password: str = "password123"):
    async with await _client() as c:
        s = (await c.get(f"{API}/session")).json()
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        r = await c.post(f"{API}/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        yield c


async def _second_brand(db) -> tuple[Brand, SocialAccount]:
    b = Brand(name="Other", slug="other", timezone="UTC")
    db.add(b)
    await db.flush()
    acc = SocialAccount(brand_id=b.id, platform="dry_run", external_id="dry-other", handle="other")
    acc.access_token = "tok"
    db.add(acc)
    await db.commit()
    return b, acc


async def _member(
    db, email: str, brand_id: int, role: str, global_role: Role = Role.editor
) -> User:
    u = User(
        email=email,
        name=email.split("@")[0].title(),
        role=global_role,
        password_hash=hash_password("password123"),
    )
    db.add(u)
    await db.flush()
    db.add(BrandMember(brand_id=brand_id, user_id=u.id, role=role))
    await db.commit()
    return u


def _png(w=64, h=64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "red").save(buf, "PNG")
    return buf.getvalue()


# 1 ---- notifications stay inside the brand ------------------------------------------------------------
async def test_notifications_go_to_the_brands_own_people(db, brand):
    from spark.services import notify

    other, oacc = await _second_brand(db)
    ed = await _member(db, "ed@example.com", other.id, "editor")  # only on Other
    cl = await _member(
        db, "client@example.com", brand.id, "client", Role.viewer
    )  # approves on Acme
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    now = datetime.now(UTC)
    failed = Post(brand_id=brand.id, content="Broke", status=PostStatus.failed, scheduled_at=now)
    failed.targets = [
        PostTarget(account_id=acc.id, status=PostStatus.failed, scheduled_at=now, error="boom")
    ]
    pending = Post(
        brand_id=brand.id,
        content="Approve me",
        status=PostStatus.pending_approval,
        scheduled_at=now + timedelta(days=1),
    )
    pending.targets = [
        PostTarget(
            account_id=acc.id,
            status=PostStatus.pending_approval,
            scheduled_at=now + timedelta(days=1),
        )
    ]
    db.add_all([failed, pending])
    await db.commit()
    out = Outbox()
    await notify.notify_failed(db, out)
    assert {t for t, _ in out.sent} == {"owner@example.com"}  # Ed edits Other, not Acme
    out = Outbox()
    await notify.notify_approvals(db, out)
    assert {t for t, _ in out.sent} == {"owner@example.com", "client@example.com"}
    out = Outbox()
    await notify.weekly_digest(db, out)
    assert all(s.startswith("[Other]") for t, s in out.sent if t == ed.email) and any(
        t == ed.email for t, _ in out.sent
    )
    assert all(s.startswith("[Acme]") for t, s in out.sent if t == cl.email)


# 2 ---- the SSE stream never holds a database session ------------------------------------------------------
def test_sse_route_depends_on_no_database_session():
    from fastapi.dependencies.utils import get_dependant

    from spark.api.routes import events as ev
    from spark.db import get_db

    class route:  # noqa: N801 - a stand-in with the one attribute the check reads
        dependant = get_dependant(path="/events", call=ev.stream)

    def calls(dep):
        yield dep.call
        for sub in dep.dependencies:
            yield from calls(sub)

    assert get_db not in set(calls(route.dependant))


# 3 ---- Zernio imports stay inside the brand's profile -----------------------------------------------------
@respx.mock
async def test_zernio_import_uses_the_brand_profile_and_refuses_foreign_channels(
    api, db, brand, monkeypatch
):
    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    brand.zernio_profile_id = "prof-acme"
    other, _ = await _second_brand(db)
    taken = SocialAccount(
        brand_id=other.id,
        platform="linkedin",
        provider="zernio",
        external_id="z-shared",
        handle="theirs",
    )
    taken.access_token = "tok"
    db.add(taken)
    await db.commit()
    listing = respx.get("https://zernio.com/api/v1/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "accounts": [
                    {
                        "_id": "z-shared",
                        "platform": "linkedin",
                        "username": "theirs",
                        "displayName": "Theirs",
                    },
                    {
                        "_id": "z-mine",
                        "platform": "instagram",
                        "username": "mine",
                        "displayName": "Mine",
                    },
                ],
                "pagination": {"hasMore": False},
            },
        )
    )
    r = await api.post(f"{API}/brands/{brand.id}/accounts/zernio/import")
    assert r.status_code == 200, r.text
    assert listing.calls.last.request.url.params["profileId"] == "prof-acme"
    assert [a["handle"] for a in r.json()["accounts"]] == ["mine"] and r.json()["skipped"] == [
        "theirs (connected to another brand)"
    ]
    # the OAuth entry point refuses a brand the user is not a member of
    await _member(db, "ed@example.com", brand.id, "editor")
    async with _login("ed@example.com") as ed:
        r = await ed.get(f"/accounts/zernio/connect/instagram?brand={other.id}")
        assert r.status_code == 303 and "kind=error" in r.headers["location"]


# 4 ---- CSV rows dated in the past stay drafts -------------------------------------------------------------------
async def test_csv_import_keeps_past_dates_as_drafts(api, db, brand):
    r = await api.post(
        f"{API}/brands/{brand.id}/posts/import",
        json={"csv": "content,when,channels\nOld news,2020-01-01 10:00,acme\n"},
    )
    assert (
        r.status_code == 200
        and r.json()["created"] == 1
        and "past" in r.json()["errors"][0]["error"]
    )
    items = (await api.get(f"{API}/brands/{brand.id}/posts")).json()["items"]
    assert items[0]["status"] == "draft"


# 5 ---- uploads are sniffed and served without scripts ---------------------------------------------------------------
async def test_uploads_are_sniffed_and_media_is_sandboxed(api, db, brand):
    r = await api.post(
        f"{API}/brands/{brand.id}/media",
        files=[("files", ("x.html", b"<script>alert(1)</script>", "image/png"))],
    )
    assert (
        r.status_code == 201
        and r.json()["items"] == []
        and "not an image" in r.json()["rejected"][0]["reason"]
    )
    r = await api.post(
        f"{API}/brands/{brand.id}/media", files=[("files", ("evil.svg", _png(), "image/png"))]
    )
    m = r.json()["items"][0]
    assert m["url"].endswith(".png") and m["content_type"] == "image/png"
    r = await api.get(m["url"])
    assert (
        r.status_code == 200
        and r.headers["x-content-type-options"] == "nosniff"
        and "sandbox" in r.headers["content-security-policy"]
    )


# 6 ---- media and campaigns from another brand are not attached ----------------------------------------------------------
async def test_other_brands_media_and_campaign_are_dropped(api, db, brand):
    from spark.models import Campaign, Media

    other, _ = await _second_brand(db)
    foreign_media = Media(
        brand_id=other.id,
        filename="theirs.png",
        path="x/theirs.png",
        content_type="image/png",
        size=1,
    )
    foreign_campaign = Campaign(brand_id=other.id, name="Theirs")
    db.add_all([foreign_media, foreign_campaign])
    await db.commit()
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    r = await api.post(
        f"{API}/brands/{brand.id}/posts",
        json={
            "content": "Mine",
            "media_ids": [foreign_media.id],
            "campaign_id": foreign_campaign.id,
            "targets": [{"account_id": acc.id}],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["post"]["media_ids"] == [] and r.json()["post"]["campaign_id"] is None


# 7 ---- email campaigns cannot borrow another brand's list ------------------------------------------------------------------
async def test_email_campaign_refuses_foreign_list(api, db, brand):
    other, _ = await _second_brand(db)
    lst = ContactList(brand_id=other.id, name="Theirs")
    db.add(lst)
    await db.commit()
    r = await api.post(f"{API}/brands/{brand.id}/email", json={"name": "Oops", "list_id": lst.id})
    assert r.status_code == 404


# 8 ---- a new brand member is a workspace viewer ------------------------------------------------------------------------------
async def test_new_member_has_no_workspace_power(api, db, brand):
    r = await api.post(
        f"{API}/brands/{brand.id}/members",
        json={"email": "v@example.com", "role": "viewer", "name": "V", "password": "longenough1"},
    )
    assert r.status_code == 201
    u = await db.scalar(select(User).where(User.email == "v@example.com"))
    assert u.role == Role.viewer
    async with _login("v@example.com", "longenough1") as v:
        assert (await v.post(f"{API}/brands", json={"name": "Sneaky"})).status_code == 403


# 9 ---- workspace-wide data is for owners ----------------------------------------------------------------------------------
async def test_team_and_connectors_are_owner_only(api, db, brand):
    await _member(db, "ed@example.com", brand.id, "editor")
    async with _login("ed@example.com") as ed:
        assert (await ed.get(f"{API}/team")).status_code == 403
        assert (await ed.get(f"{API}/settings/connectors/zernio")).status_code == 403
        members = (await ed.get(f"{API}/brands/{brand.id}/members")).json()
        assert all(m["email"] == "" for m in members)  # emails are for owners
    assert (await api.get(f"{API}/team")).status_code == 200


# 10 ---- MCP list_brands respects membership -----------------------------------------------------------------------------------
async def test_mcp_list_brands_respects_membership(db, brand):
    from spark.mcp_server import _visible_brand_rows

    other, _ = await _second_brand(db)
    ed = await _member(db, "ed@example.com", brand.id, "editor")
    assert [b.slug for b in await _visible_brand_rows(db, ed)] == ["acme"]


# 11 ---- stale agent runs are failed by the sweeper --------------------------------------------------------------------------------
async def test_stale_agent_runs_are_swept(db, brand):
    from spark.models import AgentRun
    from spark.services import agent

    run = AgentRun(brand_id=brand.id, kind="ask", status="running", janus_run_id="run_old")
    db.add(run)
    await db.commit()
    run.updated_at = datetime.now(UTC) - timedelta(minutes=30)
    await db.commit()
    assert await agent.sweep_stale(db) == 1
    await db.refresh(run)
    assert run.status == "failed" and "no news" in (run.error or "").lower()


# 12 ---- posts and voice are applied separately --------------------------------------------------------------------------------------
async def test_apply_posts_and_voice_are_separate_choices(api, db, brand):
    from spark.models import AgentRun

    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    run = AgentRun(
        brand_id=brand.id,
        kind="ask",
        status="completed",
        janus_run_id="run_v",
        proposal={
            "summary": "both",
            "posts": [
                {"content": "A post", "channels": ["acme"], "channel_ids": [acc.id], "when": None}
            ],
            "voice_profile": {
                "tone": "Bold",
                "audience": "Makers",
                "rules": "",
                "examples": "",
                "summary": "Bold makers",
            },
        },
    )
    db.add(run)
    await db.commit()
    r = await api.post(f"{API}/brands/{brand.id}/agent/runs/{run.id}/apply", json={"what": "posts"})
    assert r.status_code == 200 and r.json()["created"] == 1 and r.json()["voice_applied"] is False
    await db.refresh(brand)
    assert not brand.voice_profile
    r = await api.post(f"{API}/brands/{brand.id}/agent/runs/{run.id}/apply", json={"what": "voice"})
    assert r.status_code == 200 and r.json()["voice_applied"] is True and r.json()["created"] == 0
    assert (
        await api.post(f"{API}/brands/{brand.id}/agent/runs/{run.id}/apply", json={"what": "posts"})
    ).status_code == 409


# 13 ---- the review link shows the final text and only the review set ---------------------------------------------------------------
async def test_review_link_shows_channel_text_and_guards_other_posts(api, db, brand):
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    when = datetime.now(UTC) + timedelta(days=1)
    p = Post(
        brand_id=brand.id,
        content="Main text",
        status=PostStatus.pending_approval,
        scheduled_at=when,
    )
    p.targets = [
        PostTarget(
            account_id=acc.id,
            status=PostStatus.pending_approval,
            scheduled_at=when,
            content_override="Channel text",
            first_comment="First!",
        )
    ]
    draft = Post(brand_id=brand.id, content="Secret draft", status=PostStatus.draft)
    db.add_all([p, draft])
    await db.commit()
    token = (await api.post(f"{API}/brands/{brand.id}/share-links", json={"days": 3})).json()[
        "token"
    ]
    async with await _client() as anon:
        page = (await anon.get(f"{API}/public/review/{token}")).json()
        ch = page["posts"][0]["channels"][0]
        assert ch["text"] == "Channel text" and ch["first_comment"] == "First!"
        assert (
            await anon.post(
                f"{API}/public/review/{token}/posts/{draft.id}/request-changes",
                json={"name": "X", "body": "leak?"},
            )
        ).status_code == 404
        r = await anon.post(
            f"{API}/public/review/{token}/posts/{p.id}/approve", json={"name": "Dana"}
        )
        assert (
            r.status_code == 200 and r.json()["status"] == "scheduled" and "content" not in r.json()
        )


# 14 ---- approval follows the brand role ---------------------------------------------------------------------------------------------------
async def test_approval_follows_the_brand_role(api, db, brand):
    brand.require_approval = True
    await db.commit()
    await _member(
        db, "bo@example.com", brand.id, "owner", Role.editor
    )  # brand owner, workspace editor
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    async with _login("bo@example.com") as bo:
        r = await bo.post(
            f"{API}/brands/{brand.id}/posts",
            json={"content": "Owner here", "targets": [{"account_id": acc.id}], "action": "queue"},
        )
        assert r.status_code == 201 and r.json()["post"]["status"] == "scheduled"


# 15 ---- labelling gives up instead of looping, skips empty text and resolved items ------------------------------------------------------
async def test_classification_gives_up_and_skips_empty_and_resolved(db, brand, monkeypatch):
    from spark.models import InboxItem
    from spark.services import ai as ai_svc
    from spark.services import inbox

    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    now = datetime.now(UTC)
    empty = InboxItem(
        brand_id=brand.id,
        account_id=acc.id,
        kind="review",
        external_id="r1",
        text="",
        rating=4,
        received_at=now,
    )
    resolved = InboxItem(
        brand_id=brand.id,
        account_id=acc.id,
        kind="comment",
        external_id="c0",
        text="done",
        status="resolved",
        received_at=now,
    )
    hard = InboxItem(
        brand_id=brand.id,
        account_id=acc.id,
        kind="comment",
        external_id="c1",
        text="label me",
        received_at=now,
    )
    db.add_all([empty, resolved, hard])
    await db.commit()
    calls = []

    class Failing:
        async def classify_inbox(self, brand, items):
            calls.append([i["id"] for i in items])
            raise ai_svc.AIUnavailable("down")

    monkeypatch.setattr(ai_svc, "ContentAI", lambda **kw: Failing())
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    assert await inbox.classify_pending(db) == 1  # the empty one, labelled without the model
    assert calls == [[hard.id]]
    assert (
        await inbox.classify_pending(db) == 0 and len(calls) == 1
    )  # no second attempt on the failed one
    await db.refresh(empty)
    await db.refresh(hard)
    assert (
        empty.sentiment == "positive" and hard.classified_at is not None and hard.intent == "other"
    )


# 16 ---- the page fetch is capped ----------------------------------------------------------------------------------------------------------------
@respx.mock
async def test_fetch_caps_the_body_size(monkeypatch):
    from spark.services import fetch

    monkeypatch.setattr(fetch, "is_public_url", lambda u: True)
    big = b"<p>" + b"x" * (6 * 1024 * 1024) + b"</p>"
    respx.get("https://example.com/big").mock(
        return_value=httpx.Response(200, content=big, headers={"content-type": "text/html"})
    )
    text = await fetch.fetch_page_text("https://example.com/big")
    assert text is not None and len(text) <= fetch.MAX_CHARS


# 17 ---- image handling: garbage gives 422, vision gets a small JPEG -------------------------------------------------------------------------------
async def test_crop_rejects_garbage_and_vision_gets_a_small_jpeg(api, db, brand):
    from spark.models import Media
    from spark.services import images

    broken = Media(
        brand_id=brand.id,
        filename="b.png",
        path=f"{brand.id}/broken.png",
        content_type="image/png",
        size=3,
    )
    db.add(broken)
    await db.commit()
    p = get_settings().media_dir / broken.path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"nope")
    r = await api.post(f"{API}/brands/{brand.id}/media/{broken.id}/crop", json={"ratio": "1:1"})
    assert r.status_code == 422
    small, ctype = await images.for_vision(_png(3000, 2000), "image/png")
    with Image.open(io.BytesIO(small)) as im:
        assert max(im.size) <= 1568 and ctype == "image/jpeg"


# 19 ---- CSV cells never run as formulas ------------------------------------------------------------------------------------------------------------
def test_csv_cells_are_text():
    from spark.services.reports import _cell

    assert (
        _cell('=HYPERLINK("x")').startswith("'")
        and _cell("+1").startswith("'")
        and _cell("hello") == "hello"
    )


# 21 ---- inbox ids stay inside the brand ---------------------------------------------------------------------------------------------------------------
async def test_inbox_assign_and_rules_check_the_brand(api, db, brand):
    from spark.models import InboxItem, SavedReply

    other, _ = await _second_brand(db)
    stranger = await _member(db, "s@example.com", other.id, "editor")
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    item = InboxItem(
        brand_id=brand.id,
        account_id=acc.id,
        kind="comment",
        external_id="c1",
        text="hi",
        received_at=datetime.now(UTC),
    )
    foreign = SavedReply(brand_id=other.id, title="Theirs", body="x")
    db.add_all([item, foreign])
    await db.commit()
    assert (
        await api.post(
            f"{API}/brands/{brand.id}/inbox/items/{item.id}/assign", json={"user_id": stranger.id}
        )
    ).status_code == 404
    assert (
        await api.post(
            f"{API}/brands/{brand.id}/inbox/rules",
            json={"name": "r", "keywords": ["x"], "saved_reply_id": foreign.id},
        )
    ).status_code == 404


# 23 ---- metrics refresh is scoped to the brand ------------------------------------------------------------------------------------------------------------
async def test_metrics_refresh_is_scoped(api, db, brand, monkeypatch):
    from spark.services import analytics

    seen = {}

    async def fake(db, max_age_days=30, brand_id=None, **kw):
        seen["brand_id"] = brand_id
        return 0

    monkeypatch.setattr(analytics, "collect_metrics", fake)
    assert (await api.post(f"{API}/brands/{brand.id}/analytics/refresh")).status_code == 200
    assert seen["brand_id"] == brand.id


# 24 ---- proposals without a known channel are not sent everywhere ----------------------------------------------------------------------------------------------
async def test_proposal_without_channels_is_not_sent_everywhere(db, brand):
    from spark.services import agent

    out = await agent.parse_proposal(
        db,
        brand,
        '```spark-proposal\n{"summary": "x", "posts": [{"content": "Hello", "channels": ["nobody"]}]}\n```',
    )
    assert out["posts"][0]["channel_ids"] == [] and out["posts"][0]["needs_channels"] is True


pytestmark = pytest.mark.usefixtures("brand")
