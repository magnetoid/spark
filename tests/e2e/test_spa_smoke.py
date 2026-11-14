"""The React app's main loop: sign in, see Today, queue a post from an empty slot, find it in the
queue and on the calendar, capture an idea and turn it into a post.

Runs against the server the e2e conftest starts (SQLite, dry-run publishing) with the built
frontend in frontend/dist. Skipped when there is no build."""

import re
from pathlib import Path

import pytest

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"
pytestmark = pytest.mark.skipif(not DIST.exists(), reason="frontend/dist is not built")


async def _sign_in(page, server_url: str):
    await page.goto(server_url + "/login")
    await page.fill("#email", "e2e@example.com")
    await page.fill("#password", "sparkdev-e2e-1")
    await page.click("button[type=submit]")
    await page.wait_for_url(re.compile(r"/(\?.*)?$"))


async def test_spa_publishing_loop(page, server_url, seeded_brand):
    await _sign_in(page, server_url)
    await page.get_by_role("heading", name=re.compile("^Today")).wait_for()
    await page.get_by_text("Going out today").wait_for()

    # Publishing → queue of the dry-run channel → first empty slot opens the composer with the time set
    await page.get_by_role("link", name="Publishing").click()
    await page.get_by_role("tab", name="Queue").wait_for()
    await page.get_by_role("button", name=re.compile("Empty slot")).first.click()
    textarea = page.get_by_placeholder(re.compile("What do you want to say"))
    await textarea.wait_for()
    await textarea.fill("Hello from the React composer")
    assert await page.get_by_role("radio", name="Pick a time").is_checked()
    await page.get_by_role("button", name="Schedule").click()
    await page.get_by_text(re.compile("^Scheduled")).first.wait_for()  # toast
    await page.get_by_role(
        "button", name=re.compile("Hello from the React composer")
    ).first.wait_for()

    # the calendar shows it too
    await page.get_by_role("tab", name="Calendar").click()
    await page.get_by_title("Hello from the React composer").first.wait_for()

    # ideas: add one, turn it into a post, the composer opens prefilled
    await page.get_by_role("link", name="Ideas").click()
    await page.get_by_role("button", name=re.compile("New idea|Add the first idea")).first.click()
    await page.fill("#i-title", "Teaser for Friday")
    await page.fill("#i-body", "Three things we learned this week")
    await page.get_by_role("button", name="Add idea").click()
    await page.get_by_text("Teaser for Friday").wait_for()
    await page.get_by_role("button", name="Idea actions", exact=True).first.click()
    await page.get_by_role("menuitem", name="Turn into a post").click()
    await page.get_by_placeholder(re.compile("What do you want to say")).wait_for()
    assert (
        "Three things we learned this week"
        in await page.get_by_placeholder(re.compile("What do you want to say")).input_value()
    )
    await page.keyboard.press("Escape")

    # library: templates tab renders its empty state
    await page.get_by_role("link", name="Library").click()
    await page.get_by_role("tab", name="Templates").click()
    await page.get_by_text("No templates yet").wait_for()


async def test_setup_checklist_on_first_run(page, server_url, seeded_brand):
    """A fresh install shows the owner what is left; hiding the list keeps it hidden."""
    await _sign_in(page, server_url)
    card = page.get_by_role("region", name="Finish setting up Spark")
    await card.wait_for()
    await card.get_by_text("Send real email").wait_for()  # the console backend is not real email
    assert await card.get_by_role("button", name="Set up email").count() == 1
    # a test channel is not a real one, so connecting a channel is still asked for
    assert await card.get_by_role("button", name="Connect a channel").count() == 1
    await page.get_by_role("button", name="Hide the setup list").click()
    await card.wait_for(state="detached")
    await page.reload()
    await page.get_by_role("heading", name=re.compile("^Today")).wait_for()
    assert await card.count() == 0
