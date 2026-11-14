"""Analytics, the link tracker and campaign results render and work in the built app: create a
short link with a chosen back-half and UTM tags, follow it, see the click and its QR code, and
open a campaign's results."""

import re

from tests.e2e.test_spa_smoke import _sign_in, pytestmark  # noqa: F401  (skip without a build)


async def test_tracking_pages(page, server_url, seeded_brand):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await _sign_in(page, server_url)

    await page.get_by_role("link", name="Analytics").click()
    await page.get_by_role("heading", name="Analytics").wait_for()

    await page.get_by_role("link", name="Campaigns").click()
    await page.get_by_role("button", name=re.compile("New campaign")).first.click()
    await page.fill("#c-name", "E2E autumn")
    await page.fill("#c-utm", "e2e-autumn")
    await page.get_by_role("button", name="Create", exact=True).click()
    await page.get_by_role("heading", name="E2E autumn").wait_for()

    await page.get_by_role("link", name="Links").click()
    await page.fill("#l-dest", "shop.example.com/boots")
    await page.fill("#l-code", "e2e-boots")
    await page.fill("#l-src", "newsletter")
    await page.get_by_text(
        re.compile(r"Sends people to https://shop\.example\.com/boots\?utm_source=newsletter")
    ).wait_for()
    await page.get_by_role("button", name="Create link").click()
    await page.get_by_role("link", name=re.compile("l.e2e-boots$")).wait_for()

    browser = {"user-agent": "Mozilla/5.0 (Macintosh)"}  # headless browsers count as bots
    r = await page.request.get(server_url + "/l/e2e-boots", max_redirects=0, headers=browser)
    assert r.status == 302 and "utm_source=newsletter" in r.headers["location"]

    await page.reload()
    await page.get_by_role("button", name=re.compile("Clicks and QR code for .*e2e-boots")).click()
    dialog = page.get_by_role("dialog")
    await dialog.get_by_text("Not from a post").wait_for()
    await dialog.get_by_role("img", name=re.compile("QR code for")).wait_for()
    await dialog.get_by_role("button", name="Download QR code").wait_for()
    await page.keyboard.press("Escape")

    await page.get_by_role("link", name="Campaigns").click()
    await page.get_by_role("button", name="Results").first.click()
    await page.get_by_role("dialog").get_by_text("Link clicks").wait_for()
    assert not errors, errors
