"""Agency tools in the built app: a new brand that starts from another brand's setup, the
all-clients overview, and an approval deadline in brand settings."""

from tests.e2e.test_spa_smoke import _sign_in, pytestmark  # noqa: F401  (skip without a build)


async def test_new_brand_from_setup_overview_and_deadline(page, server_url, seeded_brand):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await _sign_in(page, server_url)

    await page.goto(server_url + "/brands/new")
    await page.fill("#nb-name", "Zeta Client")
    await page.click("#nb-from")
    await page.get_by_role("option", name="E2E Brand").click()
    await page.get_by_label("Content pillars").wait_for()
    await page.get_by_role("button", name="Create brand").click()
    await page.get_by_text("with the setup of E2E Brand").wait_for()

    await page.get_by_role("link", name="All clients").click()
    await page.get_by_role("heading", name="All clients").wait_for()
    brands = page.get_by_role("list", name="Brands")
    await brands.get_by_text("Zeta Client").wait_for()
    await brands.get_by_text("E2E Brand").wait_for()

    await page.goto(server_url + "/settings?brand=zeta-client")
    await page.click("#b-lead")
    await page.get_by_role("option", name="1 day before the post").click()
    await page.click("#b-timeout")
    await page.get_by_role("option", name="Move it back to drafts").click()
    await page.get_by_role("button", name="Save brand settings").click()
    await page.wait_for_timeout(500)
    await page.reload()
    await page.get_by_role("combobox", name="Approval deadline").filter(has_text="1 day").wait_for()
    assert not errors, errors
