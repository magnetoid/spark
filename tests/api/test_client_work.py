"""Phase 3B-2: links that let a client connect their own channels without a Spark account, and a
CSV import that also carries media, a first comment and the post type."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from sqlalchemy import select

from spark.config import get_settings
from spark.models import ActivityLog, Media, Post, ShareLink, SocialAccount
from spark.services.email import ConsoleSender
from tests.api.conftest import API

Z = "https://zernio.com/api/v1"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
    b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def zkey(monkeypatch):
    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")


async def _link(api, brand, **body) -> dict:
    r = await api.post(f"{API}/brands/{brand.id}/connect-links", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _token(link: dict) -> str:
    return link["url"].rsplit("/c/", 1)[1]


# ---- connect links: making and listing them ------------------------------------------------
async def test_owner_makes_a_connect_link_shown_once(api, brand, zkey):
    link = await _link(api, brand, platforms=["linkedin", "instagram"], days=5)
    assert "/c/" in link["url"] and link["platforms"] == ["linkedin", "instagram"]
    exp = datetime.fromisoformat(link["expires_at"])
    assert timedelta(days=4) < exp - datetime.now(UTC) < timedelta(days=6)
    rows = (await api.get(f"{API}/brands/{brand.id}/connect-links")).json()
    assert [r["id"] for r in rows] == [link["id"]] and "url" not in rows[0]
    # connect links are not review links
    shares = (await api.get(f"{API}/brands/{brand.id}/share-links")).json()
    assert all(s["id"] != link["id"] for s in shares)


async def test_connect_link_needs_zernio_and_known_platforms(api, brand, monkeypatch):
    monkeypatch.setattr(get_settings(), "zernio_api_key", "")
    r = await api.post(f"{API}/brands/{brand.id}/connect-links", json={})
    assert r.status_code == 422 and r.json()["code"] == "zernio_not_configured"
    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    r = await api.post(f"{API}/brands/{brand.id}/connect-links", json={"platforms": ["myspace"]})
    assert r.status_code == 422


# ---- the public page -------------------------------------------------------------------------
async def test_public_page_shows_brand_platforms_and_channels(api, anon, db, brand, zkey):
    acc = SocialAccount(
        brand_id=brand.id, platform="linkedin", provider="zernio", external_id="z-li", handle="acme"
    )
    acc.access_token = "zernio"
    acc.extra = {"needs_reconnection": True}
    db.add(acc)
    await db.commit()
    link = await _link(api, brand, platforms=["linkedin"])
    r = await anon.get(f"{API}/public/connect/{_token(link)}")
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["brand"]["name"] == brand.name
    assert [p["platform"] for p in page["platforms"]] == ["linkedin"]
    assert page["channels"] == [
        {"platform": "linkedin", "handle": "acme", "health": "reconnect"}
    ]  # only channels through Zernio, which a link can connect


async def test_revoked_expired_and_review_links_do_not_open(api, anon, db, brand, zkey):
    link = await _link(api, brand)
    r = await api.delete(f"{API}/brands/{brand.id}/connect-links/{link['id']}")
    assert r.status_code == 204
    assert (await anon.get(f"{API}/public/connect/{_token(link)}")).status_code == 404
    old = await _link(api, brand)
    row = await db.get(ShareLink, old["id"])
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    assert (await anon.get(f"{API}/public/connect/{_token(old)}")).status_code == 404
    review = (await api.post(f"{API}/brands/{brand.id}/share-links", json={})).json()
    assert (await anon.get(f"{API}/public/connect/{review['token']}")).status_code == 404


# ---- connecting through the link ------------------------------------------------------------
@respx.mock
async def test_client_connects_a_channel_through_the_link(api, anon, db, brand, zkey):
    ConsoleSender.sent.clear()
    brand.zernio_profile_id = "prof-acme"
    await db.commit()
    link = await _link(api, brand)
    token = _token(link)
    connect = respx.get(f"{Z}/connect/linkedin").mock(
        return_value=httpx.Response(200, json={"authUrl": "https://linkedin.example/auth?x=1"})
    )
    r = await anon.get(f"/c/{token}/go/linkedin")
    assert r.status_code == 303 and r.headers["location"] == "https://linkedin.example/auth?x=1"
    sent = connect.calls.last.request.url.params
    assert sent["profileId"] == "prof-acme"
    redirect = urlparse(sent["redirect_url"])
    assert redirect.path == "/accounts/zernio/client-callback"
    assert token not in sent["redirect_url"]  # the link itself never travels through Zernio
    state = parse_qs(redirect.query)["state"][0]

    accounts = respx.get(f"{Z}/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "accounts": [
                    {
                        "_id": "z-li",
                        "platform": "linkedin",
                        "username": "acme-co",
                        "displayName": "Acme Co",
                        "profileId": "prof-acme",
                    }
                ]
            },
        )
    )
    r = await anon.get(
        "/accounts/zernio/client-callback",
        params={
            "state": state,
            "connected": "linkedin",
            "profileId": "prof-acme",
            "accountId": "z-li",
            "username": "acme-co",
        },
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"].startswith(f"/c/{token}?connected=")
    assert accounts.calls.last.request.url.params["profileId"] == "prof-acme"  # this brand only
    acc = await db.scalar(
        select(SocialAccount).where(
            SocialAccount.brand_id == brand.id, SocialAccount.external_id == "z-li"
        )
    )
    assert acc is not None and acc.provider == "zernio" and acc.handle == "acme-co"
    log = (
        await db.execute(select(ActivityLog).where(ActivityLog.verb == "connected"))
    ).scalar_one()
    assert "client link" in log.summary and log.actor_id is None
    mail = ConsoleSender.sent[-1]
    assert mail["to"] == "owner@example.com" and "acme-co" in mail["subject"]
    # the state is used once
    r = await anon.get(
        "/accounts/zernio/client-callback", params={"state": state, "accountId": "z-li"}
    )
    assert r.status_code == 400


async def test_link_only_connects_its_platforms(api, anon, brand, zkey):
    link = await _link(api, brand, platforms=["instagram"])
    r = await anon.get(f"/c/{_token(link)}/go/linkedin")
    assert r.status_code == 303 and "error=" in r.headers["location"]


async def test_dead_link_cannot_start_a_connect(anon):
    r = await anon.get("/c/not-a-real-token/go/linkedin")
    assert r.status_code == 404


@respx.mock
async def test_plan_limit_gives_a_clear_message(api, anon, db, brand, zkey):
    brand.zernio_profile_id = "prof-acme"
    await db.commit()
    link = await _link(api, brand)
    respx.get(f"{Z}/connect/linkedin").mock(
        return_value=httpx.Response(
            402,
            json={
                "code": "PAYMENT_REQUIRED",
                "error": "Add a payment method to connect more than 2 accounts.",
                "reason": "free_tier_exceeded",
            },
        )
    )
    r = await anon.get(f"/c/{_token(link)}/go/linkedin")
    loc = r.headers["location"]
    assert r.status_code == 303 and "error=" in loc
    msg = parse_qs(urlparse(loc).query)["error"][0]
    assert "more than 2" not in msg and "team" in msg  # the client sees a plain note
    log = (
        await db.execute(select(ActivityLog).where(ActivityLog.verb == "could not connect"))
    ).scalar_one()
    assert "more than 2 accounts" in log.summary  # the team sees Zernio's reason


@respx.mock
async def test_cancelled_connect_returns_to_the_page(api, anon, db, brand, zkey):
    brand.zernio_profile_id = "prof-acme"
    await db.commit()
    link = await _link(api, brand)
    connect = respx.get(f"{Z}/connect/linkedin").mock(
        return_value=httpx.Response(200, json={"authUrl": "https://linkedin.example/auth"})
    )
    await anon.get(f"/c/{_token(link)}/go/linkedin")
    state = parse_qs(urlparse(connect.calls.last.request.url.params["redirect_url"]).query)[
        "state"
    ][0]
    r = await anon.get(
        "/accounts/zernio/client-callback",
        params={"state": state, "error": "oauth_denied", "platform": "linkedin"},
    )
    loc = r.headers["location"]
    assert loc.startswith(f"/c/{_token(link)}?error=") and "cancel" in loc.lower()


# ---- CSV import: media, first comment, post type --------------------------------------------
@pytest.fixture
async def ig(db, brand, zkey):
    acc = SocialAccount(
        brand_id=brand.id,
        platform="instagram",
        provider="zernio",
        external_id="z-ig",
        handle="acme.ig",
    )
    acc.access_token = "zernio"
    db.add(acc)
    await db.commit()
    return acc


async def _import(api, brand, csv: str) -> dict:
    r = await api.post(f"{API}/brands/{brand.id}/posts/import", json={"csv": csv})
    assert r.status_code == 200, r.text
    return r.json()


async def _posts(db, brand) -> list[Post]:
    rows = await db.execute(select(Post).where(Post.brand_id == brand.id).order_by(Post.id))
    return list(rows.scalars())


async def test_import_sets_first_comment_and_post_type(api, db, brand, ig):
    out = await _import(
        api,
        brand,
        "content,channels,first_comment,post_type\n"
        "Boots are back,acme.ig,Shop at the link in bio,reel\n",
    )
    assert out == {"created": 1, "errors": []}
    (post,) = await _posts(db, brand)
    await db.refresh(post, ["targets"])
    (t,) = post.targets
    assert t.first_comment == "Shop at the link in bio" and t.post_type == "reel"


async def test_import_notes_a_post_type_a_channel_lacks(api, db, brand, ig):
    li = SocialAccount(
        brand_id=brand.id,
        platform="linkedin",
        provider="zernio",
        external_id="z-li",
        handle="acme-li",
    )
    li.access_token = "zernio"
    db.add(li)
    await db.commit()
    out = await _import(api, brand, "content,channels,post_type\nHello,acme-li;acme.ig,story\n")
    assert out["created"] == 1
    assert [e["row"] for e in out["errors"]] == [1] and "acme-li" in out["errors"][0]["error"]
    (post,) = await _posts(db, brand)
    await db.refresh(post, ["targets"])
    types = {t.account_id: t.post_type for t in post.targets}
    assert types == {ig.id: "story", li.id: "post"}


@respx.mock
async def test_import_media_from_library_names_and_urls(api, db, brand, ig, monkeypatch):
    from spark.services import fetch

    monkeypatch.setattr(fetch, "is_public_url", lambda url: url.startswith("https://cdn."))
    lib = Media(
        brand_id=brand.id, filename="boots.jpg", path="1/boots.jpg", content_type="image/jpeg"
    )
    db.add(lib)
    await db.commit()
    respx.get("https://cdn.example.com/a.png").mock(
        return_value=httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    )
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d 10:00")
    out = await _import(
        api,
        brand,
        "content,channels,media,when\n"
        f"Two pictures,acme.ig,Boots.JPG; https://cdn.example.com/a.png,{tomorrow}\n",
    )
    assert out == {"created": 1, "errors": []}
    (post,) = await _posts(db, brand)
    assert len(post.media_ids) == 2 and post.media_ids[0] == lib.id
    fetched = await db.get(Media, post.media_ids[1])
    assert fetched.content_type == "image/png" and fetched.source == "import"
    assert post.status.value == "scheduled"


async def test_import_keeps_a_draft_when_media_cannot_be_used(api, db, brand, ig):
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d 10:00")
    out = await _import(
        api,
        brand,
        "content,channels,media,when\n"
        f"Private,acme.ig,http://127.0.0.1/secret.png,{tomorrow}\n"
        f"Missing,acme.ig,nothere.jpg,{tomorrow}\n",
    )
    assert out["created"] == 2 and [e["row"] for e in out["errors"]] == [1, 2]
    assert "127.0.0.1" in out["errors"][0]["error"] and "nothere.jpg" in out["errors"][1]["error"]
    posts = await _posts(db, brand)
    assert [p.status.value for p in posts] == ["draft", "draft"] and posts[0].media_ids == []


@respx.mock
async def test_zernio_unreachable_returns_a_clear_message(api, anon, db, brand, zkey):
    brand.zernio_profile_id = "prof-acme"
    await db.commit()
    link = await _link(api, brand)
    respx.get(f"{Z}/connect/linkedin").mock(side_effect=httpx.ConnectError("down"))
    r = await anon.get(f"/c/{_token(link)}/go/linkedin")
    assert r.status_code == 303 and "error=" in r.headers["location"]
