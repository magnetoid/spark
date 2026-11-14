from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import Post, PostStatus, PostTarget, QueueSlot, SocialAccount
from tests.api.conftest import API


async def test_channel_queue_merges_posts_and_free_slots(api, db, brand):
    for d in range(7):
        db.add(QueueSlot(brand_id=brand.id, weekday=d, time="10:00"))
        db.add(QueueSlot(brand_id=brand.id, weekday=d, time="16:00"))
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    when = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    p = Post(brand_id=brand.id, content="Queued", status=PostStatus.scheduled, scheduled_at=when)
    p.targets = [PostTarget(account_id=acc.id, status=PostStatus.scheduled, scheduled_at=when)]
    d = Post(brand_id=brand.id, content="A draft", status=PostStatus.draft)
    d.targets = [PostTarget(account_id=acc.id, status=PostStatus.draft)]
    db.add_all([p, d])
    await db.commit()
    bid = (await api.get(f"{API}/brands")).json()[0]["id"]
    r = await api.get(f"{API}/brands/{bid}/queue", params={"account": acc.id, "days": 3})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["account"]["id"] == acc.id
    filled = [i for i in q["items"] if i["post"]]
    empty = [i for i in q["items"] if not i["post"]]
    assert len(filled) == 1 and filled[0]["post"]["content"] == "Queued" and filled[0]["target_id"]
    assert empty and all(i["when"] for i in empty)
    assert q["items"] == sorted(q["items"], key=lambda i: i["when"])
    assert q["counts"] == {"queue": 1, "drafts": 1, "approvals": 0}
    assert {"weekday": 0, "time": "10:00"} in q["slots"]
    assert (await api.get(f"{API}/brands/{bid}/queue", params={"account": 9999})).status_code == 404
    # no account given: the first channel
    assert (await api.get(f"{API}/brands/{bid}/queue")).json()["account"]["id"] == acc.id
