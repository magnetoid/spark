import io

from spark.config import get_settings
from tests.api.conftest import API

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


async def _bid(api):
    return (await api.get(f"{API}/brands")).json()[0]["id"]


async def test_media_upload_list_alt_text_and_delete(api, db, brand):
    bid = await _bid(api)
    r = await api.post(f"{API}/brands/{bid}/media", files=[("files", ("dot.png", io.BytesIO(PNG), "image/png")),
                                                            ("files", ("bad.txt", io.BytesIO(b"nope"), "text/plain"))])
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["items"]) == 1 and body["items"][0]["name"] == "dot.png" and body["items"][0]["url"].startswith("/media/")
    assert body["rejected"] == [{"name": "bad.txt", "reason": "unsupported type text/plain"}]
    mid = body["items"][0]["id"]
    assert (get_settings().media_dir / body["items"][0]["url"].removeprefix("/media/")).exists()

    r = await api.get(f"{API}/brands/{bid}/media")
    assert r.status_code == 200 and [m["id"] for m in r.json()["items"]] == [mid]
    r = await api.patch(f"{API}/brands/{bid}/media/{mid}", json={"alt_text": "A single dot"})
    assert r.status_code == 200 and r.json()["alt_text"] == "A single dot"
    assert (await api.delete(f"{API}/brands/{bid}/media/{mid}")).status_code == 204
    assert (await api.get(f"{API}/brands/{bid}/media")).json()["items"] == []
    assert not (get_settings().media_dir / body["items"][0]["url"].removeprefix("/media/")).exists()


async def test_hashtag_groups_and_templates(api, db, brand):
    bid = await _bid(api)
    r = await api.post(f"{API}/brands/{bid}/hashtag-groups", json={"name": "Launch", "tags": ["#Launch", "SaaS", "launch"]})
    assert r.status_code == 201 and r.json()["tags"] == ["Launch", "SaaS"]
    gid = r.json()["id"]
    r = await api.patch(f"{API}/brands/{bid}/hashtag-groups/{gid}", json={"tags": ["one"]})
    assert r.json()["tags"] == ["one"]
    assert [g["id"] for g in (await api.get(f"{API}/brands/{bid}/hashtag-groups")).json()] == [gid]
    assert (await api.delete(f"{API}/brands/{bid}/hashtag-groups/{gid}")).status_code == 204

    r = await api.post(f"{API}/brands/{bid}/templates", json={"name": "Tip", "body": "Tip: {{tip}}", "category": "tip"})
    assert r.status_code == 201 and r.json()["category"] == "tip"
    tid = r.json()["id"]
    r = await api.patch(f"{API}/brands/{bid}/templates/{tid}", json={"body": "New body"})
    assert r.json()["body"] == "New body"
    assert len((await api.get(f"{API}/brands/{bid}/templates")).json()) == 1
    assert (await api.delete(f"{API}/brands/{bid}/templates/{tid}")).status_code == 204


async def test_campaigns_list(api, db, brand):
    from spark.models import Campaign

    db.add(Campaign(brand_id=brand.id, name="Spring", color="#2F6FED"))
    await db.commit()
    bid = await _bid(api)
    r = await api.get(f"{API}/brands/{bid}/campaigns")
    assert r.status_code == 200 and r.json()[0]["name"] == "Spring" and r.json()[0]["color"] == "#2F6FED"


async def test_ai_endpoints_need_a_key_and_use_the_service(api, db, brand, monkeypatch):
    bid = await _bid(api)
    r = await api.post(f"{API}/brands/{bid}/ai/rewrite", json={"text": "hi", "instruction": "longer"})
    assert r.status_code == 400 and r.json()["code"] == "ai_unavailable"

    from spark.api.routes import ai as ai_routes

    class FakeAI:
        async def rewrite(self, brand, text, instruction, platform=None):
            return f"{text} ({instruction})"

        async def hashtags(self, brand, text, count=8):
            return ["spark", "launch"]

        async def generate(self, brand, brief, platforms, **kw):
            from spark.services.ai import PostDraft

            return [PostDraft(platform=p, text=f"{brief} for {p}") for p in platforms]

    monkeypatch.setattr(ai_routes, "_ai", lambda: FakeAI())
    r = await api.post(f"{API}/brands/{bid}/ai/rewrite", json={"text": "hi", "instruction": "longer"})
    assert r.json() == {"text": "hi (longer)"}
    assert (await api.post(f"{API}/brands/{bid}/ai/hashtags", json={"text": "hi"})).json() == {"hashtags": ["spark", "launch"]}
    r = await api.post(f"{API}/brands/{bid}/ai/generate", json={"brief": "Ship it", "platforms": ["x", "linkedin"]})
    assert [d["platform"] for d in r.json()["drafts"]] == ["x", "linkedin"]
