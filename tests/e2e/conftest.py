"""Playwright smoke tests run against a real server (SQLite, dry-run publishing)."""

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server_url():
    tmp = tempfile.mkdtemp(prefix="spark-e2e-")
    port = _free_port()
    env = {**os.environ,
           "SPARK_DATABASE_URL": f"sqlite+aiosqlite:///{tmp}/e2e.db", "SPARK_MEDIA_DIR": f"{tmp}/media",
           "SPARK_SECRET_KEY": "e2e-secret", "SPARK_BASE_URL": f"http://127.0.0.1:{port}",
           "SPARK_FORCE_DRY_RUN": "true", "SPARK_ENV": "development", "SPARK_ZERNIO_API_KEY": "",
           "SPARK_ANTHROPIC_API_KEY": ""}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "spark.main:app", "--port", str(port)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(450):  # cold import can take a while on CI
        try:
            urllib.request.urlopen(url + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("server did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
async def page():
    pw = pytest.importorskip("playwright.async_api")
    async with pw.async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        pg = await ctx.new_page()
        pg.set_default_timeout(20_000)
        pg.set_default_navigation_timeout(45_000)
        yield pg
        await browser.close()


@pytest.fixture(scope="session")
def seeded_brand(server_url):
    """An owner (e2e@example.com), a brand and a dry-run channel, created once per server. Works whether
    or not the first-run smoke test already created them."""
    import httpx

    with httpx.Client(base_url=server_url, follow_redirects=False, timeout=30) as c:
        s = c.get("/api/v1/session").json()
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        creds = {"email": "e2e@example.com", "password": "sparkdev-e2e-1"}
        r = c.post("/api/v1/auth/setup", json={"name": "E2E Owner", **creds}) if s["needs_setup"] else c.post("/api/v1/auth/login", json=creds)
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        brands = r.json()["brands"] or [c.post("/api/v1/brands", json={"name": "E2E Brand"}).json()]
        bid = brands[0]["id"]
        if not c.get(f"/api/v1/brands/{bid}/accounts").json():
            # the channel connect API arrives in phase 4; the form route works with the same session + CSRF header
            r = c.post("/accounts/connect/dry_run", data={"handle": "e2e-handle"})
            assert r.status_code in (200, 303), r.text
        return bid
