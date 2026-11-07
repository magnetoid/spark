"""Phase 6 in the browser: a review link is made from Publishing › Approvals, a client opens it without
signing in, approves one post and asks for changes on another; the team sees the note as a comment."""

import re
from pathlib import Path

import pytest

from tests.e2e.test_spa_smoke import _sign_in

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"
pytestmark = pytest.mark.skipif(not DIST.exists(), reason="frontend/dist is not built")


async def test_review_link_flow(page, server_url, seeded_brand):
    bid = seeded_brand
    await _sign_in(page, server_url)

    # Publishing › Approvals: create a review link, read the URL out of the dialog
    await page.goto(server_url + "/publishing?view=approvals")
    await page.get_by_role("button", name="New review link").click()
    url = await page.get_by_role("textbox", name="Review link").input_value()
    assert re.search(r"/review/[A-Za-z0-9_-]{20,}$", url)
    await page.get_by_role("button", name="Done").click()
    await page.get_by_text(re.compile(r"until ")).wait_for()  # the link is listed

    # the review page itself needs no account: fresh context, no cookies
    import httpx

    with httpx.Client(base_url=server_url, timeout=30) as c:
        s = c.get("/api/v1/session").json()
        c.headers["X-CSRF-Token"] = s["csrf_token"]
        r = c.post("/api/v1/auth/login", json={"email": "e2e@example.com", "password": "sparkdev-e2e-1"})
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        acc = c.get(f"/api/v1/brands/{bid}/accounts").json()[0]["id"]
        # a post that waits for approval: editors' posts land there when the brand requires approval
        c.patch(f"/api/v1/brands/{bid}", json={"require_approval": True})
        r = c.post(f"/api/v1/brands/{bid}/members", json={"email": "ed-e2e@example.com", "role": "editor", "name": "Ed", "password": "sparkdev-e2e-2"})
        assert r.status_code in (201, 409), r.text
    with httpx.Client(base_url=server_url, timeout=30) as ed:
        s = ed.get("/api/v1/session").json()
        ed.headers["X-CSRF-Token"] = s["csrf_token"]
        r = ed.post("/api/v1/auth/login", json={"email": "ed-e2e@example.com", "password": "sparkdev-e2e-2"})
        ed.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        for t in ("Client, please approve this one", "Client, this one needs your eye"):
            r = ed.post(f"/api/v1/brands/{bid}/posts", json={"content": t, "targets": [{"account_id": acc}], "action": "next"})
            assert r.status_code == 201 and r.json()["post"]["status"] == "pending_approval", r.text

    ctx = await page.context.browser.new_context(viewport={"width": 900, "height": 1000})
    client = await ctx.new_page()
    client.set_default_timeout(20_000)
    await client.goto(url)
    await client.get_by_role("heading", name="E2E Brand").wait_for()
    await client.get_by_text(re.compile(r"2 posts wait for your approval")).wait_for()
    await client.fill("#reviewer", "Dana (client)")
    cards = client.get_by_role("listitem").filter(has_text="Client, please approve this one")
    await cards.get_by_role("button", name="Approve").click()
    await client.get_by_text("Approved").first.wait_for()
    cards2 = client.get_by_role("listitem").filter(has_text="Client, this one needs your eye")
    await cards2.get_by_role("button", name="Request changes").click()
    await cards2.get_by_placeholder("What should change?").fill("Shorter, and mention the webinar")
    await cards2.get_by_role("button", name="Send").click()
    await client.get_by_text("asked for changes").wait_for()
    await ctx.close()

    # back in the team's app: the second post is a draft with the client's note as a comment, the first is scheduled
    await page.goto(server_url + "/publishing?view=drafts")
    await page.get_by_role("button", name=re.compile("Client, this one needs your eye")).click()
    await page.get_by_text("Shorter, and mention the webinar").wait_for()
    await page.get_by_text("requested changes").wait_for()
    await page.keyboard.press("Escape")
    await page.goto(server_url + "/")
    await page.get_by_text(re.compile(r"Dana \(client\) requested changes")).wait_for()
    await page.get_by_text(re.compile(r"Dana \(client\) approved")).wait_for()
