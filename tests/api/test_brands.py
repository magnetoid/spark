from sqlalchemy import select

from spark.models import BrandMember, QueueSlot, Role, User
from tests.api.conftest import API


async def test_list_create_and_update_brands(api, db):
    r = await api.get(f"{API}/brands")
    assert r.status_code == 200 and [b["slug"] for b in r.json()] == ["acme"]
    r = await api.post(f"{API}/brands", json={"name": "Beta Co", "timezone": "Europe/Belgrade", "color": "#2F6FED"})
    assert r.status_code == 201, r.text
    beta = r.json()
    assert beta["slug"] == "beta-co" and beta["timezone"] == "Europe/Belgrade" and beta["role"] == "owner"
    assert await db.scalar(select(QueueSlot).where(QueueSlot.brand_id == beta["id"])) is not None  # default slots
    r = await api.patch(f"{API}/brands/{beta['id']}", json={"name": "Beta", "color": "#D13B3B", "require_approval": True})
    assert r.status_code == 200 and r.json()["name"] == "Beta" and r.json()["require_approval"] is True
    r = await api.get(f"{API}/brands/{beta['id']}")
    assert r.json()["color"] == "#D13B3B"
    assert (await api.patch(f"{API}/brands/{beta['id']}", json={"color": "red"})).status_code == 422
    assert (await api.get(f"{API}/brands/999")).status_code == 404


async def test_viewers_cannot_change_brands(api, db, brand):
    user = await db.scalar(select(User))
    user.role = Role.viewer
    db.add(BrandMember(brand_id=brand.id, user_id=user.id, role="viewer"))  # non-owners see only the brands they belong to
    await db.commit()
    brand_id = (await api.get(f"{API}/brands")).json()[0]["id"]
    assert (await api.get(f"{API}/brands/{brand_id}/accounts")).status_code == 200
    r = await api.patch(f"{API}/brands/{brand_id}", json={"name": "Nope"})
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    assert (await api.post(f"{API}/brands", json={"name": "Nope"})).status_code == 403
