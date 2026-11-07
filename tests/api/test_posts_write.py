from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import BrandMember, Post, PostStatus, QueueSlot, Role, SocialAccount, User
from tests.api.conftest import API


async def _ctx(api, db, brand):
    db.add(QueueSlot(brand_id=brand.id, weekday=datetime.now(UTC).weekday(), time="23:59"))
    for d in range(7):
        db.add(QueueSlot(brand_id=brand.id, weekday=d, time="09:00"))
    await db.commit()
    bid = (await api.get(f"{API}/brands")).json()[0]["id"]
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    return bid, acc


def _body(acc, **kw):
    return {"content": "Hello from the API", "targets": [{"account_id": acc.id}], "action": "draft", **kw}


async def test_create_edit_place_and_delete_a_post(api, db, brand):
    bid, acc = await _ctx(api, db, brand)
    r = await api.post(f"{API}/brands/{bid}/posts", json=_body(acc, link="https://example.com", notes="internal"))
    assert r.status_code == 201, r.text
    post = r.json()["post"]
    assert post["status"] == "draft" and post["link"] == "https://example.com" and r.json()["message"] == "Draft saved"
    assert post["targets"][0]["account_id"] == acc.id and post["notes"] == "internal"

    r = await api.patch(f"{API}/brands/{bid}/posts/{post['id']}", json=_body(
        acc, content="Edited", action="queue", targets=[{"account_id": acc.id, "first_comment": "fc", "thread": ["two"]}]))
    assert r.status_code == 200, r.text
    assert r.json()["post"]["status"] == "scheduled" and r.json()["message"].startswith("Queued for")
    assert r.json()["post"]["targets"][0]["first_comment"] == "fc" and r.json()["post"]["targets"][0]["thread"] == ["two"]

    when = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    r = await api.post(f"{API}/brands/{bid}/posts/{post['id']}/place", json={"action": "schedule", "scheduled_at": when.isoformat()})
    assert r.status_code == 200 and r.json()["post"]["scheduled_at"].startswith(when.strftime("%Y-%m-%dT%H:%M"))

    r = await api.post(f"{API}/brands/{bid}/posts/{post['id']}/place", json={"action": "schedule"})
    assert r.status_code == 422 and r.json()["code"] == "cannot_place" and "date and time" in r.json()["problems"][0]

    r = await api.post(f"{API}/brands/{bid}/posts/{post['id']}/unschedule")
    assert r.status_code == 200 and r.json()["post"]["status"] == "draft"
    r = await api.post(f"{API}/brands/{bid}/posts/{post['id']}/duplicate")
    assert r.status_code == 201 and r.json()["post"]["id"] != post["id"] and r.json()["post"]["content"] == "Edited"
    assert (await api.delete(f"{API}/brands/{bid}/posts/{post['id']}")).status_code == 204
    assert (await api.get(f"{API}/brands/{bid}/posts/{post['id']}")).status_code == 404


async def test_create_with_no_channels_stays_a_draft_and_explains(api, db, brand):
    bid, _acc = await _ctx(api, db, brand)
    r = await api.post(f"{API}/brands/{bid}/posts", json={"content": "x", "targets": [], "action": "queue"})
    assert r.status_code == 422 and r.json()["code"] == "cannot_place"
    assert "at least one" in r.json()["problems"][0] and r.json()["post"]["status"] == "draft"


async def test_approve_retry_move_and_roles(api, db, brand):
    bid, acc = await _ctx(api, db, brand)
    user = await db.scalar(select(User))
    brand.require_approval = True
    user.role = Role.editor
    member = BrandMember(brand_id=bid, user_id=user.id, role="editor")  # non-owners act through their membership
    db.add(member)
    await db.commit()
    r = await api.post(f"{API}/brands/{bid}/posts", json=_body(acc, action="now"))
    pid = r.json()["post"]["id"]
    assert r.json()["post"]["status"] == "pending_approval"
    assert (await api.post(f"{API}/brands/{bid}/posts/{pid}/approve")).status_code == 403
    user.role = Role.owner
    await db.commit()
    r = await api.post(f"{API}/brands/{bid}/posts/{pid}/approve")
    assert r.status_code == 200 and r.json()["post"]["status"] == "scheduled"

    post = await db.get(Post, pid)
    post.targets[0].status = PostStatus.failed
    post.targets[0].error = "boom"
    post.refresh_status()
    await db.commit()
    r = await api.post(f"{API}/brands/{bid}/posts/{pid}/retry")
    assert r.status_code == 200 and r.json()["post"]["status"] == "scheduled" and r.json()["retried"] == 1

    day = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    r = await api.post(f"{API}/brands/{bid}/posts/{pid}/move", json={"day": day})
    assert r.status_code == 200 and r.json()["post"]["scheduled_at"].startswith(day)
    slot = (datetime.now(UTC) + timedelta(days=4)).replace(hour=9, minute=0, second=0, microsecond=0)
    r = await api.post(f"{API}/brands/{bid}/posts/{pid}/move", json={"when": slot.isoformat()})
    assert r.status_code == 200 and r.json()["post"]["scheduled_at"].startswith(slot.strftime("%Y-%m-%dT%H:%M"))
    r = await api.post(f"{API}/brands/{bid}/posts/{pid}/move", json={"day": "2020-01-01"})
    assert r.status_code == 422 and "past" in r.json()["detail"]

    user.role = Role.viewer
    member.role = "viewer"
    await db.commit()
    assert (await api.post(f"{API}/brands/{bid}/posts", json=_body(acc))).status_code == 403


async def test_autosave_and_resume(api, db, brand):
    bid, acc = await _ctx(api, db, brand)
    assert (await api.get(f"{API}/brands/{bid}/posts/autosave")).json() is None
    r = await api.put(f"{API}/brands/{bid}/posts/autosave", json={"content": "typing…", "targets": [{"account_id": acc.id}]})
    assert r.status_code == 200 and r.json()["post_id"]
    pid = r.json()["post_id"]
    r = await api.put(f"{API}/brands/{bid}/posts/autosave", json={"post_id": pid, "content": "typing more", "targets": []})
    assert r.json()["post_id"] == pid
    resume = (await api.get(f"{API}/brands/{bid}/posts/autosave")).json()
    assert resume and resume["id"] == pid and resume["content"] == "typing more"
    # hidden from lists until saved for real
    assert pid not in [p["id"] for p in (await api.get(f"{API}/brands/{bid}/posts")).json()["items"]]
    r = await api.patch(f"{API}/brands/{bid}/posts/{pid}", json=_body(acc, content="typing more"))
    assert r.status_code == 200 and (await api.get(f"{API}/brands/{bid}/posts/autosave")).json() is None
    assert (await api.put(f"{API}/brands/{bid}/posts/autosave", json={"content": "   ", "targets": []})).json()["post_id"] is None


async def test_validate_targets(api, db, brand):
    bid, acc = await _ctx(api, db, brand)
    r = await api.post(f"{API}/brands/{bid}/posts/validate", json={"targets": {str(acc.id): "x" * 6000}, "media_ids": [], "link": None})
    assert r.status_code == 200 and "characters" in r.json()["problems"][str(acc.id)][0]
    r = await api.post(f"{API}/brands/{bid}/posts/validate", json={"targets": {str(acc.id): "fine"}, "media_ids": []})
    assert r.json()["problems"][str(acc.id)] == [] and r.json()["warnings"][str(acc.id)] == []
