from sqlalchemy import select

from spark.models import Idea, Post
from tests.api.conftest import API


async def _bid(api):
    return (await api.get(f"{API}/brands")).json()[0]["id"]


async def test_ideas_crud_move_and_to_post(api, db, brand):
    bid = await _bid(api)
    r = await api.post(
        f"{API}/brands/{bid}/ideas",
        json={
            "title": "Launch teaser",
            "body": "Short clip",
            "tags": ["#Launch", "video", "launch"],
            "source_url": "https://example.com",
        },
    )
    assert r.status_code == 201, r.text
    idea = r.json()
    assert idea["status"] == "idea" and idea["tags"] == ["launch", "video"]
    r = await api.post(f"{API}/brands/{bid}/ideas", json={"title": "Second"})
    second = r.json()
    assert second["position"] < idea["position"]  # newest first within the column

    r = await api.patch(
        f"{API}/brands/{bid}/ideas/{idea['id']}",
        json={"title": "Launch teaser v2", "tags": ["launch"]},
    )
    assert (
        r.status_code == 200
        and r.json()["title"] == "Launch teaser v2"
        and r.json()["tags"] == ["launch"]
    )
    r = await api.post(
        f"{API}/brands/{bid}/ideas/{idea['id']}/move", json={"status": "drafting", "position": 3}
    )
    assert r.status_code == 200 and r.json()["status"] == "drafting" and r.json()["position"] == 3
    assert (
        await api.post(f"{API}/brands/{bid}/ideas/{idea['id']}/move", json={"status": "nope"})
    ).status_code == 422

    board = (await api.get(f"{API}/brands/{bid}/ideas")).json()
    assert {i["id"] for i in board["items"]} == {idea["id"], second["id"]} and board["tags"] == [
        "launch"
    ]
    only = (await api.get(f"{API}/brands/{bid}/ideas", params={"tag": "launch"})).json()
    assert [i["id"] for i in only["items"]] == [idea["id"]]

    r = await api.post(f"{API}/brands/{bid}/ideas/{idea['id']}/to-post")
    assert r.status_code == 201, r.text
    post_id = r.json()["post"]["id"]
    assert (
        r.json()["post"]["content"] == "Short clip"
        and r.json()["post"]["link"] == "https://example.com"
    )
    assert (await db.get(Idea, idea["id"])).status == "ready"
    # a second call reuses the same post
    assert (await api.post(f"{API}/brands/{bid}/ideas/{idea['id']}/to-post")).json()["post"][
        "id"
    ] == post_id

    assert (await api.delete(f"{API}/brands/{bid}/ideas/{second['id']}")).status_code == 204
    assert await db.scalar(select(Idea).where(Idea.id == second["id"])) is None
    assert await db.get(Post, post_id) is not None


async def test_idea_ai_expand_uses_a_fake_ai(api, db, brand, monkeypatch):
    from spark.services import ideas as svc

    class FakeAI:
        async def generate(self, brand, brief, platforms, **kw):
            from spark.services.ai import PostDraft

            return [PostDraft(platform=platforms[0], text=f"Expanded: {brief.splitlines()[0]}")]

    monkeypatch.setattr(svc, "ContentAI", lambda: FakeAI())
    bid = await _bid(api)
    idea = (
        await api.post(f"{API}/brands/{bid}/ideas", json={"title": "Why we ship weekly"})
    ).json()
    r = await api.post(f"{API}/brands/{bid}/ideas/{idea['id']}/ai")
    assert r.status_code == 200, r.text
    assert (
        r.json()["body"].startswith("Expanded: Why we ship weekly")
        and r.json()["status"] == "drafting"
    )
