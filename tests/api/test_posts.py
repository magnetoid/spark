from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import Post, PostStatus, PostTarget, SocialAccount
from tests.api.conftest import API


async def _brand_id(api) -> int:
    return (await api.get(f"{API}/brands")).json()[0]["id"]


async def _seed(db, brand, n=3):
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    now = datetime.now(UTC).replace(microsecond=0)
    posts = []
    for i in range(n):
        p = Post(brand_id=brand.id, content=f"Post {i}", status=PostStatus.scheduled, scheduled_at=now + timedelta(hours=i + 1))
        p.targets = [PostTarget(account_id=acc.id, status=PostStatus.scheduled, scheduled_at=p.scheduled_at)]
        db.add(p)
        posts.append(p)
    failed = Post(brand_id=brand.id, content="Broken", status=PostStatus.failed)
    failed.targets = [PostTarget(account_id=acc.id, status=PostStatus.failed, error="Platform said no")]
    db.add(failed)
    hidden = Post(brand_id=brand.id, content="autosave", is_autosave=True)
    db.add(hidden)
    await db.commit()
    return posts, failed


async def test_accounts_and_posts_are_brand_scoped(api, db, brand):
    bid = await _brand_id(api)
    await _seed(db, brand)
    r = await api.get(f"{API}/brands/{bid}/accounts")
    assert r.status_code == 200
    acc = r.json()[0]
    assert acc["platform"] == "dry_run" and acc["handle"] == "acme" and acc["capabilities"]["threadable"] is True
    r = await api.get(f"{API}/brands/{bid}/posts")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4 and "autosave" not in [p["content"] for p in body["items"]]
    r = await api.get(f"{API}/brands/{bid}/posts", params={"status": "failed"})
    assert [p["content"] for p in r.json()["items"]] == ["Broken"]
    assert r.json()["items"][0]["targets"][0]["error"] == "Platform said no"
    r = await api.get(f"{API}/brands/{bid}/posts", params={"status": "scheduled", "q": "Post 1"})
    assert [p["content"] for p in r.json()["items"]] == ["Post 1"]
    one = r.json()["items"][0]
    r = await api.get(f"{API}/brands/{bid}/posts/{one['id']}")
    assert r.status_code == 200 and r.json()["scheduled_at"].endswith("+00:00") or "Z" in r.json()["scheduled_at"]
    assert (await api.get(f"{API}/brands/{bid + 1}/posts")).status_code == 404
    assert (await api.get(f"{API}/brands/{bid}/posts/99999")).status_code == 404


async def test_today_overview(api, db, brand):
    bid = await _brand_id(api)
    posts, failed = await _seed(db, brand, n=2)
    r = await api.get(f"{API}/brands/{bid}/today")
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["date"] and t["timezone"] == "UTC"
    assert {i["post_id"] for i in t["timeline"]} >= {p.id for p in posts if p.scheduled_at.date() == datetime.now(UTC).date()}
    assert t["needs_you"]["failed"] == 1 and t["needs_you"]["approvals"] == 0
    assert set(t["week"]) >= {"engagements", "impressions", "published", "change_pct", "series"}
    assert len(t["week"]["series"]) == 7
    assert isinstance(t["free_slots_today"], int)
