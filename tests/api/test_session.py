from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import Role, User
from tests.api.conftest import API


async def test_session_before_login_has_csrf_and_no_user(anon):
    s = (await anon.get(f"{API}/session")).json()
    assert s["user"] is None and s["csrf_token"] and s["needs_setup"] is False and s["brands"] == []


async def test_login_logout_and_csrf(anon, db):
    r = await anon.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": "nope"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
    r = await anon.post(f"{API}/auth/login", json={"email": "Owner@Example.com", "password": "password123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "owner@example.com" and body["user"]["role"] == "owner"
    assert body["brands"][0]["slug"] == "acme" and body["brands"][0]["role"] == "owner"
    # login rotated the session: the old CSRF token is dead, the new one works
    r = await anon.post(f"{API}/auth/logout")
    assert r.status_code == 403 and r.json()["code"] == "csrf"
    anon.headers["X-CSRF-Token"] = body["csrf_token"]
    assert (await anon.post(f"{API}/auth/logout")).status_code == 200
    assert (await anon.get(f"{API}/session")).json()["user"] is None


async def test_protected_routes_answer_json_401(anon):
    r = await anon.get(f"{API}/brands")
    assert r.status_code == 401 and r.json()["code"] == "login_required"
    assert "text/html" not in r.headers["content-type"]


async def test_setup_creates_the_first_owner_only_once(db, brand):
    from tests.api.conftest import _client

    await db.execute(User.__table__.delete())
    await db.commit()
    async with await _client() as c:
        s = (await c.get(f"{API}/session")).json()
        assert s["needs_setup"] is True
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        r = await c.post(f"{API}/auth/setup", json={"name": "First", "email": "first@example.com", "password": "longenough1"})
        assert r.status_code == 200 and r.json()["user"]["role"] == "owner"
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        r = await c.post(f"{API}/auth/setup", json={"name": "Second", "email": "second@example.com", "password": "longenough1"})
        assert r.status_code == 409
    assert (await db.scalar(select(User).where(User.email == "first@example.com"))).role == Role.owner


async def test_bearer_token_skips_the_cookie_and_csrf(api, db, brand):
    from spark.services import tokens
    from tests.api.conftest import _client

    user = await db.scalar(select(User))
    raw, _ = await tokens.create_token(db, user, "script")
    async with await _client() as c:
        assert (await c.get(f"{API}/brands", headers={"Authorization": "Bearer spk_wrong"})).status_code == 401
        r = await c.get(f"{API}/brands", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 200 and r.json()[0]["slug"] == "acme"
        # a write with a bearer token needs no CSRF header
        r = await c.patch(f"{API}/me", json={"name": "Scripted"}, headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 200 and r.json()["name"] == "Scripted"


async def test_me_update_and_prefs(api):
    r = await api.patch(f"{API}/me", json={"name": "New Name", "prefs": {"default_action": "draft", "ignored": 1}})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name" and r.json()["prefs"]["default_action"] == "draft"
    assert "ignored" not in r.json()["prefs"]
    r = await api.patch(f"{API}/me", json={"email": "not-an-email"})
    assert r.status_code == 422


def _soon():
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()
