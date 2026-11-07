"""Phase 7, the planning half that needs no agent: content pillars, per-channel posting times,
guardrails checked before a post goes out, evergreen posts that fill empty slots, CSV import."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import Post, PostStatus, PostTarget, SocialAccount
from spark.services.publisher import as_utc
from tests.api.conftest import API


async def _acc(db, brand, handle="acme"):
    return await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id, SocialAccount.handle == handle))


async def _second_account(db, brand) -> SocialAccount:
    acc = SocialAccount(brand_id=brand.id, platform="dry_run", external_id="dry-two", handle="acme-two")
    acc.access_token = "tok"
    db.add(acc)
    await db.commit()
    return acc


# ---- pillars -----------------------------------------------------------------------------------
async def test_pillars_crud_and_posts_carry_one(api, db, brand):
    bid = brand.id
    r = await api.post(f"{API}/brands/{bid}/pillars", json={"name": "Education", "color": "#2F6FED", "target_share": 40})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = await api.post(f"{API}/brands/{bid}/pillars", json={"name": "Behind the scenes", "color": "#1F8F5F", "target_share": 60})
    assert r.status_code == 201
    acc = await _acc(db, brand)
    r = await api.post(f"{API}/brands/{bid}/posts", json={"content": "How to", "targets": [{"account_id": acc.id}], "pillar_id": pid})
    assert r.status_code == 201 and r.json()["post"]["pillar_id"] == pid
    rows = (await api.get(f"{API}/brands/{bid}/pillars")).json()
    assert [p["name"] for p in rows] == ["Education", "Behind the scenes"]
    assert rows[0]["posts_30d"] == 1 and rows[1]["posts_30d"] == 0
    r = await api.patch(f"{API}/brands/{bid}/pillars/{pid}", json={"name": "Teach"})
    assert r.json()["name"] == "Teach"
    assert (await api.delete(f"{API}/brands/{bid}/pillars/{pid}")).status_code == 204
    post_id = (await api.get(f"{API}/brands/{bid}/posts")).json()["items"][0]["id"]
    assert (await api.get(f"{API}/brands/{bid}/posts/{post_id}")).json()["pillar_id"] is None
    # filter posts by pillar
    assert (await api.get(f"{API}/brands/{bid}/posts", params={"pillar_id": 999})).json()["items"] == []


# ---- per-channel posting times ---------------------------------------------------------------------
async def test_slots_per_channel_drive_the_queue(api, db, brand):
    bid = brand.id
    one = await _acc(db, brand)
    two = await _second_account(db, brand)
    # no brand-wide slots: channel one posts Mondays 08:00, channel two Tuesdays 10:00 (brand is UTC)
    r = await api.post(f"{API}/brands/{bid}/slots", json={"weekdays": [0], "time": "08:00", "account_id": one.id})
    assert r.status_code == 201 and r.json()[0]["account_id"] == one.id
    await api.post(f"{API}/brands/{bid}/slots", json={"weekdays": [1], "time": "10:00", "account_id": two.id})
    q = (await api.get(f"{API}/brands/{bid}/queue", params={"account": two.id})).json()
    assert [(s["weekday"], s["time"]) for s in q["slots"]] == [(1, "10:00")]
    r = await api.post(f"{API}/brands/{bid}/posts", json={"content": "For two", "targets": [{"account_id": two.id}], "action": "queue"})
    assert r.status_code == 201, r.text
    when = datetime.fromisoformat(r.json()["post"]["scheduled_at"])
    assert when.weekday() == 1 and (when.hour, when.minute) == (10, 0)
    # a post for both channels falls back to the union of their slots: the earliest upcoming one
    r = await api.post(f"{API}/brands/{bid}/posts", json={"content": "For both", "targets": [{"account_id": one.id}, {"account_id": two.id}], "action": "queue"})
    both = datetime.fromisoformat(r.json()["post"]["scheduled_at"])
    assert both.weekday() in (0, 1)


# ---- guardrails -----------------------------------------------------------------------------------------
async def test_guardrails_block_and_warn(api, db, brand):
    bid = brand.id
    acc = await _acc(db, brand)
    r = await api.patch(f"{API}/brands/{bid}", json={"agent_config": {"never_say": ["cheap"], "avoid_topics": ["politics"], "keywords": ["workshop", "design"]}})
    assert r.status_code == 200 and r.json()["agent_config"]["never_say"] == ["cheap"]
    r = await api.post(f"{API}/brands/{bid}/posts/validate", json={"targets": {str(acc.id): "Our cheap new design workshop"}, "media_ids": [], "link": None})
    assert r.status_code == 200
    out = r.json()
    assert any("cheap" in p for p in out["problems"][str(acc.id)])
    assert out["warnings"][str(acc.id)] == []
    r = await api.post(f"{API}/brands/{bid}/posts/validate", json={"targets": {str(acc.id): "Thoughts on politics today"}, "media_ids": [], "link": None})
    w = r.json()["warnings"][str(acc.id)]
    assert any("politics" in x for x in w) and any("keyword" in x.lower() for x in w)
    # the rule holds when placing: a banned phrase keeps the post a draft
    r = await api.post(f"{API}/brands/{bid}/posts", json={"content": "Cheap seats!", "targets": [{"account_id": acc.id}], "action": "queue"})
    assert r.status_code == 422 and r.json()["code"] == "cannot_place" and "cheap" in r.json()["detail"].lower()


# ---- evergreen -------------------------------------------------------------------------------------------
async def test_evergreen_posts_refill_empty_slots(api, db, brand):
    from spark.services import evergreen

    bid = brand.id
    acc = await _acc(db, brand)
    long_ago = datetime.now(UTC) - timedelta(days=40)
    p = Post(brand_id=bid, content="Our story, always worth retelling", status=PostStatus.published, scheduled_at=long_ago,
             evergreen=True, recycle_every_days=30)
    p.targets = [PostTarget(account_id=acc.id, status=PostStatus.published, scheduled_at=long_ago, published_at=long_ago)]
    fresh = Post(brand_id=bid, content="Too recent", status=PostStatus.published, scheduled_at=datetime.now(UTC) - timedelta(days=2),
                 evergreen=True, recycle_every_days=30)
    fresh.targets = [PostTarget(account_id=acc.id, status=PostStatus.published, scheduled_at=fresh.scheduled_at, published_at=fresh.scheduled_at)]
    db.add_all([p, fresh])
    await db.commit()
    assert await evergreen.recycle(db) == 1
    copies = (await db.execute(select(Post).where(Post.recycled_from_id == p.id))).scalars().all()
    assert len(copies) == 1 and copies[0].status == PostStatus.scheduled and copies[0].source == "evergreen"
    assert as_utc(copies[0].scheduled_at) > datetime.now(UTC)
    assert await evergreen.recycle(db) == 0  # the copy counts as the latest run
    # the flag is editable through the API and visible on the post
    r = await api.patch(f"{API}/brands/{bid}/posts/{p.id}", json={"content": p.content, "targets": [{"account_id": acc.id}], "evergreen": False})
    assert r.status_code == 200 and r.json()["post"]["evergreen"] is False


# ---- CSV import --------------------------------------------------------------------------------------------
async def test_csv_import_makes_drafts_and_scheduled_posts(api, db, brand):
    bid = brand.id
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d 10:00")
    csv = "content,link,when,channels\n" \
          f"\"Hello, world\",https://example.com,{tomorrow},acme\n" \
          "Just a draft,,,acme\n" \
          "Unknown channel,,,nobody\n"
    r = await api.post(f"{API}/brands/{bid}/posts/import", json={"csv": csv})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 2 and [e["row"] for e in out["errors"]] == [3]
    items = (await api.get(f"{API}/brands/{bid}/posts")).json()["items"]
    by = {p["content"]: p for p in items}
    assert by["Hello, world"]["status"] == "scheduled" and by["Hello, world"]["link"] == "https://example.com"
    assert by["Just a draft"]["status"] == "draft" and by["Just a draft"]["source"] == "import"
