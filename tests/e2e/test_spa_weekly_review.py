"""The weekly review in the built app: last week on Analytics, and the week before it."""

import re

from tests.e2e.test_spa_smoke import _sign_in, pytestmark  # noqa: F401  (skip without a build)


async def test_week_in_review_on_analytics(page, server_url, seeded_brand):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await _sign_in(page, server_url)
    await page.goto(server_url + "/analytics")
    heading = page.get_by_role("heading", name=re.compile("Week in review"))
    await heading.wait_for()
    first = await heading.inner_text()
    await page.get_by_role("button", name="Week before").click()
    old_range = first.split("·")[1].strip()
    await (
        page.get_by_role("heading", name=re.compile("Week in review"))
        .filter(has_not_text=old_range)
        .wait_for()
    )
    assert not errors, errors
