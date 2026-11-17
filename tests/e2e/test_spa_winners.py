"""Winners in the built app: a standout post on Analytics, copied as a draft to the channel it missed."""

import tempfile
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.e2e.conftest import _start_server, _stop
from tests.e2e.test_spa_smoke import _sign_in, pytestmark  # noqa: F401  (skip without a build)


async def _seed(db_url: str, brand_id: int) -> None:
    from spark.models import Metric, Post, PostStatus, PostTarget, SocialAccount

    engine = create_async_engine(db_url)
    async with AsyncSession(engine) as db:
        acc = await db.scalar(
            select(SocialAccount).where(
                SocialAccount.brand_id == brand_id, SocialAccount.handle == "nova-main"
            )
        )
        now = datetime.now(UTC)
        for i in range(13):
            hit = i == 0
            at = now - timedelta(days=2 + i * 5)
            p = Post(
                brand_id=brand_id,
                content="Sourdough at dawn, behind the counter" if hit else f"Daily bread {i}",
                status=PostStatus.published,
            )
            t = PostTarget(account_id=acc.id, status=PostStatus.published, published_at=at)
            p.targets = [t]
            db.add(p)
            await db.flush()
            db.add(
                Metric(
                    target_id=t.id,
                    captured_at=at + timedelta(hours=20),
                    impressions=1000,
                    likes=70 if hit else 10,
                )
            )
        await db.commit()
    await engine.dispose()


async def test_copy_a_winner_to_the_channel_it_missed(page):
    db_url = f"sqlite+aiosqlite:///{tempfile.mkdtemp(prefix='spark-win-')}/win.db"
    url, proc = _start_server(SPARK_DATABASE_URL=db_url)
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
            bid = c.post("/api/v1/brands", json={"name": "Nova Bakery"}).json()["id"]
            for h in ("nova-main", "nova-two"):
                r = c.post(f"/api/v1/brands/{bid}/accounts/connect/dry_run", json={"handle": h})
                assert r.status_code == 201, r.text
        await _seed(db_url, bid)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await _sign_in(page, url)
        await page.goto(url + "/analytics")
        card = page.locator("section", has=page.get_by_role("heading", name="Winners"))
        await card.get_by_text("Sourdough at dawn").wait_for()
        await card.get_by_text("7.0× the channel's usual").wait_for()
        await card.get_by_role("button", name="Post to @nova-two").click()
        dialog = page.get_by_role("dialog", name="Post to other channels")
        await dialog.get_by_role("button", name="Make draft").click()
        await page.get_by_role("dialog").get_by_text("Sourdough at dawn").first.wait_for()
        await page.keyboard.press("Escape")
        await card.get_by_role("button", name="Copy (draft)").wait_for()
        assert not await card.get_by_role("button", name="Post to @nova-two").count()
        assert not errors, errors
    finally:
        _stop(proc)
