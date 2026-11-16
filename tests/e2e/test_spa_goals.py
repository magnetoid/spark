"""Posting goals in the built app: set a weekly goal on Today and see this week's progress."""

import re

from tests.e2e.test_spa_smoke import _sign_in, pytestmark  # noqa: F401  (skip without a build)


async def test_set_a_weekly_goal_on_today(page, server_url, seeded_brand):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await _sign_in(page, server_url)
    card = page.locator("section", has=page.get_by_role("heading", name="Posting goals"))
    await card.get_by_role("button", name=re.compile("Set goals|Change goals")).click()
    dialog = page.get_by_role("dialog", name="Weekly posting goals")
    await dialog.get_by_role("spinbutton").first.fill("2")
    await dialog.get_by_role("button", name="Save goals").click()
    await card.get_by_text(re.compile(r"of 2 published")).wait_for()
    await card.get_by_role("progressbar").first.wait_for()
    assert not errors, errors
