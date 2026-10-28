"""The main flow in a real browser: setup -> brand -> channel -> modal compose -> queue."""

import re

import pytest

pytestmark = pytest.mark.e2e


async def test_first_run_to_queued_post(page, server_url):
    await page.goto(server_url + "/")
    await page.wait_for_url(re.compile(r"/setup$"))
    await page.fill("input[name=name]", "E2E Owner")
    await page.fill("input[name=email]", "e2e@example.com")
    await page.fill("input[name=password]", "sparkdev-e2e-1")
    await page.click("button:has-text('Create account')")

    await page.wait_for_url(re.compile(r"/brands/new$"))
    await page.fill("input[name=name]", "E2E Brand")
    await page.click("button:has-text('Create brand')")
    await page.wait_for_url(re.compile(r"/accounts$"))

    # onboarding checklist shows on Overview with the channel step open
    await page.goto(server_url + "/")
    await page.wait_for_selector("text=Get Spark posting")
    await page.wait_for_selector("text=Connect a channel")

    # dry-run channel via the credentials form of the Bluesky card
    await page.goto(server_url + "/accounts")
    card = page.locator(".card", has_text="Bluesky (dry run)").first
    await card.get_by_role("button", name="Connect", exact=True).click()
    await card.locator("input[name=handle]").fill("e2e-handle")
    await card.locator("button:has-text('Save and connect')").click()
    await page.wait_for_selector("text=Connected 1")

    # queue page: open the composer from an empty slot, write, add to queue — no navigation
    await page.goto(server_url + "/queue")
    await page.locator("text=Empty slot — add a post").first.click()
    dlg = page.locator("#publish-modal")
    box = dlg.locator("textarea[name=content]")
    await box.wait_for(state="visible")
    await box.fill("Hello from the browser test")
    # opened from a slot, the composer preselects that time -> primary action is "Schedule"
    # the dialog body must be centred (Basecoat's translate survives Tailwind Play's reset)
    rect = await dlg.locator("> *").first.evaluate("el => el.getBoundingClientRect().toJSON()")
    assert abs((rect["x"] + rect["width"] / 2) - 640) < 40, rect
    await dlg.get_by_role("button", name="Schedule", exact=True).click()
    await page.wait_for_selector("#toaster .toast")
    await page.wait_for_selector("#queue-column:has-text('Hello from the browser test')")
    assert "/queue" in page.url

    # keyboard: c opens the composer, Escape closes it
    await page.keyboard.press("Escape")
    await page.keyboard.press("c")
    await box.wait_for(state="visible")
    await page.keyboard.press("Escape")
    await box.wait_for(state="hidden")
    assert not await dlg.evaluate("d => d.open")

    # ideas and inbox render their empty states
    await page.goto(server_url + "/ideas")
    await page.wait_for_selector("text=Nothing yet")
    await page.goto(server_url + "/inbox")
    await page.wait_for_selector("text=Set SPARK_ZERNIO_API_KEY")
