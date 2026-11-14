"""Phase 8: repurpose a source into drafts, images (generated, described, measured, tagged, cropped),
post formats per channel, the channel grid."""

import base64
import io
import json

import httpx
import respx
from PIL import Image
from sqlalchemy import select

from spark.config import get_settings
from spark.models import SocialAccount
from tests.api.conftest import API


def _png(w: int = 640, h: int = 480, color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


async def _upload(api, bid: int, name: str, data: bytes, ctype: str) -> dict:
    r = await api.post(f"{API}/brands/{bid}/media", files=[("files", (name, data, ctype))])
    assert r.status_code == 201, r.text
    return r.json()["items"][0]


async def _acc(db, brand) -> SocialAccount:
    return await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))


class FakeAI:
    async def describe_image(self, brand, data: bytes, content_type: str) -> str:
        assert data[:2] == b"\xff\xd8" and content_type == "image/jpeg"  # vision gets a shrunk JPEG
        return f"A red rectangle for {brand.name}"

    async def generate(self, brand, brief, platforms, *, source_text=None, link=None, variants=1):
        from spark.services.ai import PostDraft

        assert source_text and "webinar" in source_text
        return [
            PostDraft(platform=p, text=f"{p}: three things from the webinar", hashtags=["#webinar"])
            for p in platforms
        ]


# ---- media: dimensions, tags, search ----------------------------------------------------------
async def test_media_dimensions_tags_and_filters(api, db, brand):
    bid = brand.id
    m = await _upload(api, bid, "hero.png", _png(640, 480), "image/png")
    assert (m["width"], m["height"], m["source"], m["tags"]) == (640, 480, "upload", [])
    r = await api.patch(
        f"{API}/brands/{bid}/media/{m['id']}", json={"tags": ["Hero", "autumn", "hero"]}
    )
    assert r.status_code == 200 and r.json()["tags"] == ["hero", "autumn"]
    await _upload(api, bid, "other.png", _png(100, 100, "blue"), "image/png")
    assert [
        x["id"]
        for x in (await api.get(f"{API}/brands/{bid}/media", params={"tag": "autumn"})).json()[
            "items"
        ]
    ] == [m["id"]]
    assert [
        x["name"]
        for x in (await api.get(f"{API}/brands/{bid}/media", params={"q": "oth"})).json()["items"]
    ] == ["other.png"]
    tags = (await api.get(f"{API}/brands/{bid}/media/tags")).json()
    assert tags == [{"tag": "autumn", "count": 1}, {"tag": "hero", "count": 1}]


# ---- alt text from Claude vision ----------------------------------------------------------------
async def test_alt_text_is_written_by_vision(api, db, brand, monkeypatch):
    from spark.services import ai as ai_svc

    bid = brand.id
    m = await _upload(api, bid, "chair.png", _png(), "image/png")
    r = await api.post(f"{API}/brands/{bid}/media/{m['id']}/alt-text")
    assert r.status_code == 400 and r.json()["code"] == "ai_unavailable"  # no key in tests
    monkeypatch.setattr(ai_svc, "ContentAI", lambda: FakeAI())
    r = await api.post(f"{API}/brands/{bid}/media/{m['id']}/alt-text")
    assert r.status_code == 200 and r.json()["alt_text"] == "A red rectangle for Acme"
    assert (await api.get(f"{API}/brands/{bid}/media")).json()["items"][0][
        "alt_text"
    ] == "A red rectangle for Acme"


# ---- generated images --------------------------------------------------------------------------
@respx.mock
async def test_image_generation_through_the_images_connector(api, db, brand, monkeypatch):
    bid = brand.id
    r = await api.post(
        f"{API}/brands/{bid}/media/generate",
        json={"prompt": "a warm studio desk", "size": "square"},
    )
    assert r.status_code == 409 and r.json()["code"] == "images_not_configured"
    assert (await api.get(f"{API}/session")).json()["features"]["images"] is False
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-img")
    assert (await api.get(f"{API}/session")).json()["features"]["images"] is True
    gen = respx.post("https://api.openai.com/v1/images/generations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(_png(1024, 1024, "green")).decode(),
                        "revised_prompt": "a warm studio desk",
                    }
                ]
            },
        )
    )
    r = await api.post(
        f"{API}/brands/{bid}/media/generate",
        json={"prompt": "a warm studio desk", "size": "square"},
    )
    assert r.status_code == 201, r.text
    m = r.json()
    assert (
        m["source"] == "generated"
        and (m["width"], m["height"]) == (1024, 1024)
        and m["content_type"] == "image/png"
    )
    sent = json.loads(gen.calls.last.request.content)
    assert sent["prompt"].startswith("a warm studio desk") and sent["size"] == "1024x1024"
    assert gen.calls.last.request.headers["authorization"] == "Bearer sk-img"
    respx.get("https://api.openai.com/v1/models/gpt-image-2.6-flare").mock(
        return_value=httpx.Response(200, json={"id": "gpt-image-2.6-flare"})
    )
    r = await api.post(f"{API}/settings/connectors/images/test")
    assert r.status_code == 200 and "gpt-image-2.6-flare" in r.json()["message"]


# ---- cropping -------------------------------------------------------------------------------------
async def test_crop_makes_a_new_media_in_the_network_ratio(api, db, brand):
    bid = brand.id
    m = await _upload(api, bid, "wide.png", _png(1600, 900), "image/png")
    r = await api.post(
        f"{API}/brands/{bid}/media/{m['id']}/crop", json={"ratio": "1:1", "x": 0.5, "y": 0.5}
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert (
        (c["width"], c["height"], c["source"]) == (900, 900, "crop")
        and c["name"].startswith("wide")
        and "1x1" in c["name"]
    )
    r = await api.post(
        f"{API}/brands/{bid}/media/{m['id']}/crop", json={"ratio": "9:16", "x": 0.5, "y": 0.5}
    )
    c = r.json()
    assert abs(c["width"] / c["height"] - 9 / 16) < 0.01


# ---- post formats ------------------------------------------------------------------------------------
async def test_post_formats_are_offered_and_checked(api, db, brand):
    bid = brand.id
    acc = await _acc(db, brand)
    caps = (await api.get(f"{API}/brands/{bid}/accounts")).json()[0]["capabilities"]
    assert "carousel" in caps["post_types"] and "post" in caps["post_types"]
    img = await _upload(api, bid, "one.png", _png(), "image/png")
    body = {
        "content": "Swipe",
        "media_ids": [img["id"]],
        "targets": [{"account_id": acc.id, "post_type": "carousel"}],
        "action": "queue",
    }
    r = await api.post(f"{API}/brands/{bid}/posts", json=body)
    assert r.status_code == 422 and "carousel" in r.json()["detail"].lower()
    img2 = await _upload(api, bid, "two.png", _png(), "image/png")
    body["media_ids"] = [img["id"], img2["id"]]
    r = await api.post(f"{API}/brands/{bid}/posts", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["post"]["targets"][0]["post_type"] == "carousel"
    r = await api.post(
        f"{API}/brands/{bid}/posts",
        json={
            "content": "Reel",
            "media_ids": [img["id"]],
            "targets": [{"account_id": acc.id, "post_type": "reel"}],
            "action": "queue",
        },
    )
    assert r.status_code == 422 and "video" in r.json()["detail"].lower()
    r = await api.post(
        f"{API}/brands/{bid}/posts/validate",
        json={
            "targets": {str(acc.id): "x"},
            "media_ids": [],
            "link": None,
            "post_types": {str(acc.id): "document"},
        },
    )
    assert any("PDF" in p or "document" in p.lower() for p in r.json()["problems"][str(acc.id)])


# ---- repurpose ------------------------------------------------------------------------------------------
def test_transcripts_become_plain_text():
    from spark.services.repurpose import to_text

    srt = "1\n00:00:01,000 --> 00:00:04,000\nWelcome to the webinar.\n\n2\n00:00:04,500 --> 00:00:08,000\nThree things we learned.\n"
    assert to_text("talk.srt", srt) == "Welcome to the webinar. Three things we learned."
    vtt = "WEBVTT\n\n00:01.000 --> 00:04.000\n<v Dana>Hello there\n\n00:04.000 --> 00:06.000\nagain.\n"
    assert to_text("talk.vtt", vtt) == "Hello there again."
    assert to_text("notes.txt", "Just text.\n") == "Just text."


async def test_repurpose_directly_with_claude_when_janus_is_off(api, db, brand, monkeypatch):
    from spark.services import ai as ai_svc
    from spark.services import repurpose

    bid = brand.id
    acc = await _acc(db, brand)
    monkeypatch.setattr(ai_svc, "ContentAI", lambda: FakeAI())

    async def fake_fetch(url, http=None):
        return (
            "Notes from the webinar: three things we learned about briefs, budgets and the first week of a redesign. "
            * 2
        )

    monkeypatch.setattr(repurpose, "fetch_page_text", fake_fetch)
    r = await api.post(
        f"{API}/brands/{bid}/ai/repurpose",
        json={"source_url": "https://example.com/webinar", "account_ids": [acc.id]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1 and r.json()["mode"] == "claude"
    items = (await api.get(f"{API}/brands/{bid}/posts", params={"status": "draft"})).json()["items"]
    assert (
        len(items) == 1
        and items[0]["source"] == "repurpose"
        and items[0]["link"] == "https://example.com/webinar"
        and "webinar" in items[0]["content"]
    )
    r = await api.post(
        f"{API}/brands/{bid}/ai/repurpose", json={"source_text": "x" * 10, "account_ids": [acc.id]}
    )
    assert r.status_code == 422  # too short to be worth it


@respx.mock
async def test_repurpose_goes_through_janus_when_configured(api, db, brand, monkeypatch):
    bid = brand.id
    s = get_settings()
    monkeypatch.setattr(s, "janus_base_url", "http://janus.test:8642")
    monkeypatch.setattr(s, "janus_api_key", "k")
    from spark.services import agent

    monkeypatch.setattr(agent, "INLINE_FOLLOW", False)
    start = respx.post("http://janus.test:8642/v1/runs").mock(
        return_value=httpx.Response(202, json={"run_id": "run_r", "status": "started"})
    )
    text = "Transcript of the webinar. " * 20
    r = await api.post(
        f"{API}/brands/{bid}/ai/repurpose",
        json={"source_text": text, "source_name": "webinar.txt", "account_ids": []},
    )
    assert r.status_code == 200 and r.json()["mode"] == "janus" and r.json()["run_id"]
    sent = json.loads(start.calls.last.request.content)
    assert "Transcript of the webinar" in sent["input"] and "series" in sent["input"].lower()
    run = (await api.get(f"{API}/brands/{bid}/agent/runs/{r.json()['run_id']}")).json()
    assert run["kind"] == "repurpose"


# ---- the channel grid --------------------------------------------------------------------------------------
async def test_channel_grid_lists_posts_with_their_first_image(api, db, brand):
    bid = brand.id
    acc = await _acc(db, brand)
    img = await _upload(api, bid, "grid.png", _png(), "image/png")
    r = await api.post(
        f"{API}/brands/{bid}/posts",
        json={
            "content": "Gridded",
            "media_ids": [img["id"]],
            "targets": [{"account_id": acc.id}],
            "action": "queue",
        },
    )
    assert r.status_code == 201, r.text
    r = await api.get(f"{API}/brands/{bid}/channels/{acc.id}/grid")
    assert r.status_code == 200
    items = r.json()["items"]
    assert (
        len(items) == 1
        and items[0]["image"].endswith(".png")
        and items[0]["status"] == "scheduled"
        and items[0]["post_id"]
    )
