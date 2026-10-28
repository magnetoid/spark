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
