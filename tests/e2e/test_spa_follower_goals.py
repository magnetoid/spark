"""Follower goals in the built app: set a target on Analytics and see it with its forecast state."""

import re

from tests.e2e.test_spa_smoke import _sign_in, pytestmark  # noqa: F401  (skip without a build)


async def test_set_a_follower_goal_on_analytics(page, server_url, seeded_brand):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await _sign_in(page, server_url)
    await page.goto(server_url + "/analytics")
    card = page.locator("section", has=page.get_by_role("heading", name="Follower goals"))
    await card.get_by_role("button", name=re.compile("Set a goal|Change goals")).click()
    dialog = page.get_by_role("dialog", name="Follower goals")
    await dialog.get_by_role("spinbutton").first.fill("5000")
    await dialog.get_by_role("button", name="Save goals").click()
    await card.get_by_text(re.compile(r"of 5,000")).wait_for()
    await card.get_by_text(
        re.compile("Forecast after two weeks|On track|Behind|Not growing")
    ).wait_for()
    assert not errors, errors
