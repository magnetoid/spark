"""Connect links in the built app: an owner makes one on Channels and a client opens it without an
account. Zernio is pointed at an address that answers nothing, so no outside service is called."""

import httpx

from tests.e2e.conftest import _start_server, _stop
from tests.e2e.test_spa_smoke import _sign_in, pytestmark  # noqa: F401  (skip without a build)


async def test_owner_makes_a_connect_link_and_client_opens_it(page):
    url, proc = _start_server(
        SPARK_ZERNIO_API_KEY="sk-e2e", SPARK_ZERNIO_BASE_URL="http://127.0.0.1:9/api/v1"
    )
    try:
        with httpx.Client(base_url=url, timeout=30) as c:
            s = c.get("/api/v1/session").json()
            c.headers["X-CSRF-Token"] = s["csrf_token"]
            r = c.post(
                "/api/v1/auth/setup",
                json={
                    "name": "E2E Owner",
                    "email": "e2e@example.com",
                    "password": "sparkdev-e2e-1",
                },
            )
            c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
            c.post("/api/v1/brands", json={"name": "Nova Bakery"})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await _sign_in(page, url)
        await page.goto(url + "/channels")
        await page.get_by_role("button", name="New connect link").click()
        await page.locator("#ccl-linkedin").check()
        await page.get_by_role("button", name="Make link").click()
        link = await page.get_by_role("textbox", name="Connect link").input_value()
        assert "/c/" in link

        client = await page.context.browser.new_context()  # no session: the client
        cp = await client.new_page()
        await cp.goto(link)
        await cp.get_by_role("heading", name="Nova Bakery").wait_for()
        nets = cp.get_by_role("link", name="LinkedIn")
        await nets.wait_for()
        assert await cp.get_by_role("link", name="Instagram").count() == 0
        await nets.click()  # Zernio cannot be reached: back on the page with a plain note
        await cp.get_by_role("alert").filter(has_text="team that manages it").wait_for()
        await client.close()
        assert not errors, errors
    finally:
        _stop(proc)
