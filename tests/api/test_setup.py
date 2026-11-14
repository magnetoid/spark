"""Phase 1B: a first run that is safe on a public server and a checklist that says what is left."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spark.config import Settings, get_settings
from spark.models import Post, PostStatus, PostTarget, QueueSlot, Role, SocialAccount, User
from spark.security import hash_password
from tests.api.conftest import API, _client

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def no_worker(monkeypatch):
    from spark.services import heartbeat

    async def never():
        return None

    monkeypatch.setattr(heartbeat, "seen_seconds", never)


def _steps(r):
    assert r.status_code == 200, r.text
    return {s["key"]: s for s in r.json()["steps"]}


async def test_checklist_steps(api, db, brand, monkeypatch, no_worker):
    from spark.services import heartbeat, webhooks

    steps = _steps(await api.get(f"{API}/setup/checklist"))
    assert list(steps) == [
        "zernio",
        "webhook",
        "channel",
        "slots",
        "first_post",
        "email",
        "public_url",
        "secret_key",
        "worker",
        "two_factor",
    ]
    done = {k for k, s in steps.items() if s["done"]}
    # the test server has a real secret and a non-local address; nothing else is set up yet
    assert done == {"public_url", "secret_key"}
    assert all(s["title"] and s["action_url"] for s in steps.values())
    assert steps["zernio"]["optional"] is True  # Bluesky, Mastodon and Telegram need no Zernio

    async def registered():
        return {"id": "wh1", "url": webhooks.webhook_url()}

    async def seen():
        return 30

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    monkeypatch.setattr(get_settings(), "email_backend", "smtp")
    monkeypatch.setattr(webhooks, "webhook_status", registered)
    monkeypatch.setattr(heartbeat, "seen_seconds", seen)
    acc = SocialAccount(brand_id=brand.id, platform="bluesky", external_id="did:1", handle="a.b")
    acc.access_token = "t"
    db.add_all([acc, QueueSlot(brand_id=brand.id, weekday=0, time="09:00")])
    await db.flush()
    post = Post(brand_id=brand.id, content="hi", status=PostStatus.scheduled)
    post.targets = [
        PostTarget(
            account_id=acc.id,
            status=PostStatus.scheduled,
            scheduled_at=datetime.now(UTC) + timedelta(days=1),
        )
    ]
    db.add(post)
    await db.commit()
    r = await api.get(f"{API}/setup/checklist")
    steps = _steps(r)
    assert {k for k, s in steps.items() if not s["done"]} == {"two_factor"}
    assert r.json()["done"] == 9 and r.json()["total"] == 10


async def test_checklist_warns_about_a_default_secret_and_localhost(api, monkeypatch, no_worker):
    monkeypatch.setattr(get_settings(), "secret_key", Settings.model_fields["secret_key"].default)
    monkeypatch.setattr(get_settings(), "base_url", "http://localhost:8000")
    steps = _steps(await api.get(f"{API}/setup/checklist"))
    assert not steps["secret_key"]["done"] and not steps["public_url"]["done"]


async def test_checklist_is_for_owners(api, anon, db, brand):
    db.add(
        User(
            email="ed@example.com",
            name="Ed",
            role=Role.editor,
            password_hash=hash_password("password456"),
        )
    )
    await db.commit()
    assert (await anon.get(f"{API}/setup/checklist")).status_code == 401
    r = await anon.post(
        f"{API}/auth/login", json={"email": "ed@example.com", "password": "password456"}
    )
    anon.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    assert (await anon.get(f"{API}/setup/checklist")).status_code == 403


# ---- the first owner -------------------------------------------------------------------------
async def test_setup_requires_token_when_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "setup_token", "first-run-token")
    owner = {"name": "Ana", "email": "ana@example.com", "password": "password123"}
    async with await _client() as c:
        s = (await c.get(f"{API}/session")).json()
        assert s["needs_setup"] is True and s["needs_setup_token"] is True
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        r = await c.post(f"{API}/auth/setup", json=owner)
        assert r.status_code == 403 and r.json()["code"] == "setup_token"
        r = await c.post(f"{API}/auth/setup", json={**owner, "setup_token": "guess"})
        assert r.status_code == 403
        r = await c.post(f"{API}/auth/setup", json={**owner, "setup_token": "first-run-token"})
        assert r.status_code == 200 and r.json()["user"]["email"] == "ana@example.com"
        assert (await c.get(f"{API}/session")).json()["needs_setup_token"] is False


async def test_setup_without_a_token_configured_stays_open():
    async with await _client() as c:
        s = (await c.get(f"{API}/session")).json()
        assert s["needs_setup_token"] is False
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        r = await c.post(
            f"{API}/auth/setup",
            json={"name": "Ana", "email": "ana@example.com", "password": "password123"},
        )
        assert r.status_code == 200


# ---- documentation ---------------------------------------------------------------------------
def test_settings_documented():
    """Every setting has a line in docs/configuration.md and in .env.example."""
    names = {f"SPARK_{name.upper()}" for name in Settings.model_fields}
    for doc in ("docs/configuration.md", ".env.example"):
        text = (ROOT / doc).read_text()
        found = set(re.findall(r"SPARK_[A-Z0-9_]+", text))
        assert not names - found, f"{doc} misses {sorted(names - found)}"
        assert not found - names, f"{doc} names settings that do not exist: {sorted(found - names)}"


def test_readme_names_no_private_server():
    text = (ROOT / "README.md").read_text()
    assert "imbamarketing" not in text and "tetra" not in text
    assert "License" in text
