"""Fixtures for the JSON API at /api/v1. The top-level conftest provides db, brand and the env."""

import pytest
from httpx import ASGITransport, AsyncClient

from spark.main import app

API = "/api/v1"


async def _client() -> AsyncClient:
    from spark import main as m

    m._buckets.clear()
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", follow_redirects=False
    )


@pytest.fixture
async def anon(brand):
    """Not signed in, but carrying a CSRF token like the SPA does after /session."""
    async with await _client() as c:
        s = (await c.get(f"{API}/session")).json()
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        yield c


@pytest.fixture
async def api(brand):
    """Signed in as the owner from the `brand` fixture, CSRF header set."""
    async with await _client() as c:
        s = (await c.get(f"{API}/session")).json()
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        r = await c.post(
            f"{API}/auth/login", json={"email": "owner@example.com", "password": "password123"}
        )
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        yield c
