"""Phase 6: per-brand membership with a client role, activity log, post comments, approval share links."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import Brand, Post, PostStatus, PostTarget, Role, SocialAccount, User
from spark.security import hash_password
from tests.api.conftest import API, _client


@asynccontextmanager
async def _login(email: str, password: str = "password123"):
    async with await _client() as c:
        s = (await c.get(f"{API}/session")).json()
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        r = await c.post(f"{API}/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        yield c


async def _pending_post(db, brand) -> Post:
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    when = datetime.now(UTC) + timedelta(days=1)
    p = Post(brand_id=brand.id, content="Please approve", status=PostStatus.pending_approval, scheduled_at=when)
    p.targets = [PostTarget(account_id=acc.id, status=PostStatus.pending_approval, scheduled_at=when)]
    db.add(p)
    await db.commit()
    return p


# ---- membership -------------------------------------------------------------------------
async def test_members_decide_which_brands_a_user_sees(api, db, brand):
    other = Brand(name="Other", slug="other")
    db.add(other)
    ed = User(email="ed@example.com", name="Ed", role=Role.editor, password_hash=hash_password("password123"))
    db.add(ed)
    await db.commit()
    bid = brand.id
    # the workspace owner sees every brand and can manage members
    r = await api.get(f"{API}/brands/{bid}/members")
    assert r.status_code == 200 and [m["email"] for m in r.json()] == ["owner@example.com"]
    r = await api.post(f"{API}/brands/{bid}/members", json={"email": "ed@example.com", "role": "editor"})
    assert r.status_code == 201 and r.json()["role"] == "editor" and r.json()["user_id"] == ed.id
    async with _login("ed@example.com") as edc:
        brands = (await edc.get(f"{API}/brands")).json()
        assert [b["slug"] for b in brands] == ["acme"] and brands[0]["role"] == "editor"
        assert (await edc.get(f"{API}/brands/{other.id}/posts")).status_code == 404  # not a member: invisible
        assert (await edc.get(f"{API}/brands/{bid}/members")).status_code == 200
        assert (await edc.post(f"{API}/brands/{bid}/members", json={"email": "x@example.com", "role": "viewer"})).status_code == 403
    r = await api.patch(f"{API}/brands/{bid}/members/{ed.id}", json={"role": "client"})
    assert r.json()["role"] == "client"
    async with _login("ed@example.com") as edc:
        assert (await edc.get(f"{API}/brands")).json()[0]["role"] == "client"
        # a client can approve but not write
        post = await _pending_post(db, brand)
        assert (await edc.post(f"{API}/brands/{bid}/posts", json={"content": "x", "targets": []})).status_code == 403
        r = await edc.post(f"{API}/brands/{bid}/posts/{post.id}/approve")
        assert r.status_code == 200 and r.json()["post"]["status"] == "scheduled"
    assert (await api.delete(f"{API}/brands/{bid}/members/{ed.id}")).status_code == 204
    async with _login("ed@example.com") as edc:
        assert (await edc.get(f"{API}/brands")).json() == []
        assert (await edc.get(f"{API}/brands/{bid}/posts")).status_code == 404


async def test_add_member_can_create_the_user(api, db, brand):
    r = await api.post(f"{API}/brands/{brand.id}/members", json={"email": "new@example.com", "role": "viewer", "name": "New One", "password": "longenough1"})
    assert r.status_code == 201, r.text
    assert await db.scalar(select(User).where(User.email == "new@example.com")) is not None
    assert (await api.post(f"{API}/brands/{brand.id}/members", json={"email": "ghost@example.com", "role": "viewer"})).status_code == 404
    assert (await api.post(f"{API}/brands/{brand.id}/members", json={"email": "new@example.com", "role": "editor"})).status_code == 409


async def test_mcp_tools_respect_membership(db, brand):
    from mcp.server.mcpserver.exceptions import ToolError

    from spark.mcp_server import _brand

    ed = User(email="ed@example.com", name="Ed", role=Role.editor, password_hash="x")
    other = Brand(name="Other", slug="other")
    db.add_all([ed, other])
    await db.commit()
    try:
        await _brand(db, "acme", ed)
    except ToolError as e:
        assert "No brand" in str(e) or "brands" in str(e).lower()
    else:
        raise AssertionError("a non-member resolved the brand")
    owner = await db.scalar(select(User).where(User.email == "owner@example.com"))
    assert (await _brand(db, "acme", owner)).id == brand.id


# ---- activity log --------------------------------------------------------------------------
async def test_activity_log_records_post_and_member_events(api, db, brand):
    acc = await db.scalar(select(SocialAccount))
    r = await api.post(f"{API}/brands/{brand.id}/posts", json={"content": "Logged", "targets": [{"account_id": acc.id}], "action": "draft"})
    pid = r.json()["post"]["id"]
    await api.post(f"{API}/brands/{brand.id}/posts/{pid}/place", json={"action": "queue"})
    await api.post(f"{API}/brands/{brand.id}/members", json={"email": "v@example.com", "role": "viewer", "name": "V", "password": "longenough1"})
    r = await api.get(f"{API}/brands/{brand.id}/activity")
    assert r.status_code == 200
    verbs = [(a["verb"], a["object_type"]) for a in r.json()["items"]]
    assert ("created", "post") in verbs and ("placed", "post") in verbs and ("added", "member") in verbs
    first = r.json()["items"][0]
    assert first["actor"]["name"] == "Owner" and first["created_at"]


# ---- comments --------------------------------------------------------------------------------
async def test_post_comments(api, db, brand):
    post = await _pending_post(db, brand)
    r = await api.post(f"{API}/brands/{brand.id}/posts/{post.id}/comments", json={"body": "Can we mention the webinar?"})
    assert r.status_code == 201 and r.json()["author"]["name"] == "Owner" and r.json()["kind"] == "comment"
    assert (await api.post(f"{API}/brands/{brand.id}/posts/{post.id}/comments", json={"body": "   "})).status_code == 422
    rows = (await api.get(f"{API}/brands/{brand.id}/posts/{post.id}/comments")).json()
    assert [c["body"] for c in rows] == ["Can we mention the webinar?"]
    assert (await api.get(f"{API}/brands/{brand.id}/posts/{post.id}")).json()["comment_count"] == 1


# ---- share links -------------------------------------------------------------------------------
async def test_share_link_review_flow(api, db, brand):
    post = await _pending_post(db, brand)
    r = await api.post(f"{API}/brands/{brand.id}/share-links", json={"days": 7})
    assert r.status_code == 201, r.text
    link = r.json()
    assert link["url"].endswith(f"/review/{link['token']}") and link["kind"] == "approval"
    token = link["token"]
    assert [l["id"] for l in (await api.get(f"{API}/brands/{brand.id}/share-links")).json()] == [link["id"]]
    assert "token" not in (await api.get(f"{API}/brands/{brand.id}/share-links")).json()[0]

    # the public review page needs no login
    async with await _client() as anon:
        r = await anon.get(f"{API}/public/review/{token}")
        assert r.status_code == 200, r.text
        page = r.json()
        assert page["brand"]["name"] == "Acme" and [p["id"] for p in page["posts"]] == [post.id]
        assert page["posts"][0]["channels"][0]["platform"] == "dry_run"
        r = await anon.post(f"{API}/public/review/{token}/posts/{post.id}/request-changes", json={"name": "Dana (client)", "body": "Shorter please"})
        assert r.status_code == 200 and r.json()["status"] == "draft"
        r = await anon.get(f"{API}/brands/{brand.id}/posts/{post.id}/comments")
        assert r.status_code == 401  # internal API still needs a user
        post2 = await _pending_post(db, brand)
        r = await anon.post(f"{API}/public/review/{token}/posts/{post2.id}/approve", json={"name": "Dana"})
        assert r.status_code == 200 and r.json()["status"] == "scheduled"
        assert (await anon.get(f"{API}/public/review/nope")).status_code == 404
    comments = (await api.get(f"{API}/brands/{brand.id}/posts/{post.id}/comments")).json()
    assert comments[0]["kind"] == "change_request" and comments[0]["author"]["name"] == "Dana (client)"
    verbs = [a["verb"] for a in (await api.get(f"{API}/brands/{brand.id}/activity")).json()["items"]]
    assert "requested changes" in verbs and "approved" in verbs

    assert (await api.delete(f"{API}/brands/{brand.id}/share-links/{link['id']}")).status_code == 204
    async with await _client() as anon:
        assert (await anon.get(f"{API}/public/review/{token}")).status_code == 404
