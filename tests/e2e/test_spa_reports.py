"""Client reports in the built app: schedule a weekly report, make one, share it, and open the
shared link in a browser that is not signed in."""

import re

from tests.e2e.test_spa_smoke import _sign_in, pytestmark  # noqa: F401  (skip without a build)


async def test_schedule_share_and_open_report(page, server_url, seeded_brand):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await _sign_in(page, server_url)

    await page.get_by_role("link", name="Analytics").click()
    await page.get_by_role("button", name="Schedule a report").click()
    await page.fill("#rs-to", "client@example.com")
    await page.get_by_role("button", name="Schedule", exact=True).click()
    await page.get_by_text(re.compile(r"Weekly, Mondays at 08:00")).wait_for()
    await page.get_by_text("to client@example.com").wait_for()

    await page.get_by_role("button", name="New report").click()
    async with page.context.expect_page() as popup:
        await page.get_by_role("button", name="Make the report").click()
    report = await popup.value
    report.on("pageerror", lambda e: errors.append(str(e)))
    title = await report.get_by_role("heading", level=1).inner_text()  # hidden once a dialog opens
    await report.get_by_role("button", name="Share").click()
    await report.get_by_role("button", name="Create link").click()
    link = report.get_by_role("textbox", name="Report link")
    await link.wait_for()
    url = await link.input_value()
    assert "/r/" in url

    browser = page.context.browser
    stranger = await browser.new_context()
    other = await stranger.new_page()
    other.on("pageerror", lambda e: errors.append(str(e)))
    await other.goto(server_url + url[url.index("/r/") :])
    await other.get_by_role("heading", name=title).wait_for()
    await other.get_by_text("Posts published").wait_for()
    assert await other.get_by_role("button", name="Share").count() == 0
    await other.goto(server_url + "/r/not-a-real-token")
    await other.get_by_text("This report link no longer works").wait_for()
    await stranger.close()
    assert not errors, errors
