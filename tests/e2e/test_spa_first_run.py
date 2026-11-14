"""A brand-new install in the browser: the owner account needs the setup token, the first brand
leads to Channels, and Today lists what is left to set up."""

import re
from pathlib import Path

import pytest

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"
pytestmark = pytest.mark.skipif(not DIST.exists(), reason="frontend/dist is not built")


async def test_first_run(fresh_server_url, page):  # the browser closes before the server stops
    url = fresh_server_url
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    await page.goto(url + "/")
    await page.wait_for_url(re.compile(r"/setup$"))
    await page.fill("#name", "First Owner")
    await page.fill("#email", "first@example.com")
    await page.fill("#password", "sparkdev-first-1")
    await page.fill("#setup_token", "not-the-token")
    await page.get_by_role("button", name="Create account").click()
    await page.get_by_text("That setup token is not right").wait_for()

    await page.fill("#setup_token", "e2e-setup-token")
    await page.get_by_role("button", name="Create account").click()
    await page.wait_for_url(re.compile(r"/brands/new$"))
    await page.get_by_label("Name").fill("First Brand")
    await page.get_by_role("button", name="Create brand").click()

    await page.wait_for_url(re.compile(r"/channels\?brand=first-brand"))
    await page.get_by_role("heading", name="Channels").wait_for()
    assert not errors, errors

    await page.get_by_role("link", name="Today").first.click()
    await page.get_by_role("region", name="Finish setting up Spark").wait_for()
