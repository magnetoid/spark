"""Phase 2B: clicks tied to the post and channel they came from, and a link and campaign
tracker (UTM builder, custom back-half, expiry, stats per day, channel, post and referrer)."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from spark.config import get_settings
from spark.models import (
    Campaign,
    LinkClick,
    Metric,
    Post,
    PostStatus,
    PostTarget,
    ShortLink,
    SocialAccount,
)
from spark.services import links as links_svc
from spark.services.publisher import build_payload
from tests.api.conftest import API

BASE = get_settings().base_url.rstrip("/")


async def _bid(api) -> int:
    return (await api.get(f"{API}/brands")).json()[0]["id"]


async def _target(db, brand, text: str, *, platform="instagram", campaign_id=None) -> PostTarget:
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    acc.platform = platform
    p = Post(brand_id=brand.id, content=text, status=PostStatus.published, campaign_id=campaign_id)
    t = PostTarget(
        account_id=acc.id,
        status=PostStatus.published,
        published_at=datetime.now(UTC) - timedelta(days=1),
        remote_id="r1",
    )
    p.targets = [t]
    db.add(p)
    await db.commit()
    return t


async def _link(db, brand, dest="https://shop.example.com/a?utm_source=spark&utm_medium=social"):
    link = await links_svc.create_short_link(db, brand, dest)
    await db.commit()
    return link


# ---- clicks tied to posts ------------------------------------------------------------------
async def test_payload_marks_spark_links_with_target(db, brand):
    link = await _link(db, brand)
    t = await _target(db, brand, f"Sale {BASE}/l/{link.code} and https://other.example.com")
    await db.refresh(t, ["post"])
    payload = await build_payload(db, t)
    assert f"{BASE}/l/{link.code}/{t.id}" in payload.text
    assert "https://other.example.com" in payload.text


async def test_click_attributed_to_target(anon, db, brand):
    link = await _link(db, brand)
    t = await _target(db, brand, "x")
    r = await anon.get(f"/l/{link.code}/{t.id}", headers={"user-agent": "Mozilla/5.0"})
    assert r.status_code == 302
    click = await db.scalar(select(LinkClick).where(LinkClick.link_id == link.id))
    assert click.target_id == t.id


async def test_redirect_sets_platform_utm(anon, db, brand):
    link = await _link(db, brand)
    t = await _target(db, brand, "x", platform="linkedin")
    r = await anon.get(f"/l/{link.code}/{t.id}", headers={"user-agent": "Mozilla/5.0"})
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["utm_source"] == ["linkedin"]
    assert q["utm_content"] == [f"post-{t.post_id}"]
    assert q["utm_medium"] == ["social"]


async def test_target_of_another_brand_is_not_attributed(anon, db, brand):
    link = await _link(db, brand)
    t = await _target(db, brand, "x")
    acc = await db.get(SocialAccount, t.account_id)
    other = ShortLink(brand_id=brand.id + 999, code="otherbrand1", destination="https://x.test")
    acc.brand_id = brand.id  # unchanged; the link of another brand is the stranger here
    db.add(other)
    await db.commit()
    r = await anon.get(f"/l/{other.code}/{t.id}", headers={"user-agent": "Mozilla/5.0"})
    assert r.status_code == 302 and r.headers["location"] == "https://x.test"
    click = await db.scalar(select(LinkClick).where(LinkClick.link_id == other.id))
    assert click.target_id is None
    assert link.id != other.id


async def test_bots_are_redirected_but_not_counted(anon, db, brand):
    link = await _link(db, brand)
    for ua in ("facebookexternalhit/1.1", "Twitterbot/1.0", "LinkedInBot/1.0", "Slackbot 1.0"):
        r = await anon.get(f"/l/{link.code}", headers={"user-agent": ua})
        assert r.status_code == 302
    await db.refresh(link)
    assert link.clicks == 0
    assert await db.scalar(select(LinkClick).where(LinkClick.link_id == link.id)) is None


async def test_expired_link_answers_410(anon, db, brand):
    link = await _link(db, brand)
    link.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()
    r = await anon.get(f"/l/{link.code}", headers={"user-agent": "Mozilla/5.0"})
    assert r.status_code == 410 and "expired" in r.text


async def test_auto_shortened_links_know_their_post(api, db, brand):
    brand.auto_shorten_links = True
    await db.commit()
    bid = await _bid(api)
    acc = await db.scalar(select(SocialAccount))
    r = await api.post(
        f"{API}/brands/{bid}/posts",
        json={
            "content": "Read https://blog.example.com/post",
            "targets": [{"account_id": acc.id}],
            "action": "draft",
        },
    )
    assert r.status_code in (200, 201), r.text
    link = await db.scalar(select(ShortLink).where(ShortLink.brand_id == brand.id))
    assert link.post_id == r.json()["post"]["id"]


# ---- link builder ---------------------------------------------------------------------------
async def test_link_builder_fills_brand_and_campaign_utm(api, db, brand):
    brand.utm_defaults = {"campaign": "always-on"}
    camp = Campaign(brand_id=brand.id, name="Autumn", utm_campaign="autumn-sale")
    db.add(camp)
    await db.commit()
    bid = await _bid(api)
    r = await api.post(
        f"{API}/brands/{bid}/links",
        json={"destination": "https://shop.example.com", "utm_term": "boots"},
    )
    q = parse_qs(urlsplit(r.json()["destination"]).query)
    assert q["utm_campaign"] == ["always-on"] and q["utm_term"] == ["boots"]
    r = await api.post(
        f"{API}/brands/{bid}/links",
        json={"destination": "https://shop.example.com", "campaign_id": camp.id},
    )
    q = parse_qs(urlsplit(r.json()["destination"]).query)
    assert q["utm_campaign"] == ["autumn-sale"] and r.json()["campaign_id"] == camp.id


async def test_link_campaign_must_belong_to_brand(api, db, brand):
    camp = Campaign(brand_id=brand.id + 999, name="Not ours")
    db.add(camp)
    await db.commit()
    r = await api.post(
        f"{API}/brands/{await _bid(api)}/links",
        json={"destination": "https://shop.example.com", "campaign_id": camp.id},
    )
    assert r.status_code == 404


async def test_custom_back_half_and_clash(api, db, brand):
    bid = await _bid(api)
    body = {"destination": "https://shop.example.com", "code": "autumn-sale"}
    r = await api.post(f"{API}/brands/{bid}/links", json=body)
    assert r.status_code == 201 and r.json()["short_url"].endswith("/l/autumn-sale")
    r = await api.post(f"{API}/brands/{bid}/links", json=body)
    assert r.status_code == 409
    r = await api.post(f"{API}/brands/{bid}/links", json={**body, "code": "bad code!"})
    assert r.status_code == 422


async def test_link_expiry_set_and_changed(api, db, brand):
    bid = await _bid(api)
    when = (datetime.now(UTC) + timedelta(days=7)).replace(microsecond=0)
    r = await api.post(
        f"{API}/brands/{bid}/links",
        json={"destination": "https://shop.example.com", "expires_at": when.isoformat()},
    )
    link = r.json()
    assert link["expires_at"] and link["expired"] is False
    r = await api.patch(
        f"{API}/brands/{bid}/links/{link['id']}",
        json={"title": "Boots", "expires_at": None},
    )
    assert r.status_code == 200 and r.json()["expires_at"] is None
    assert r.json()["title"] == "Boots"


# ---- stats ----------------------------------------------------------------------------------
async def test_link_stats_by_day_channel_post_and_referrer(api, anon, db, brand):
    link = await _link(db, brand)
    t = await _target(db, brand, "x", platform="instagram")
    ua = {"user-agent": "Mozilla/5.0"}
    await anon.get(f"/l/{link.code}/{t.id}", headers=ua)
    await anon.get(f"/l/{link.code}/{t.id}", headers=ua)
    await anon.get(
        f"/l/{link.code}", headers={**ua, "referer": "https://news.example.org/today?x=1"}
    )
    r = await api.get(f"{API}/brands/{await _bid(api)}/links/{link.id}/stats")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["total"] == 3
    assert sum(d["clicks"] for d in s["by_day"]) == 3
    assert {"key": "instagram", "clicks": 2} in s["by_platform"]
    assert {"key": "Not from a post", "clicks": 1} in s["by_platform"]
    assert s["by_post"][0]["post_id"] == t.post_id and s["by_post"][0]["clicks"] == 2
    assert {"key": "news.example.org", "clicks": 1} in s["by_referrer"]
    assert {"key": "Direct or unknown", "clicks": 2} in s["by_referrer"]


async def test_stats_of_another_brands_link_is_404(api, db, brand):
    other = ShortLink(brand_id=brand.id + 999, code="strangerx", destination="https://x.test")
    db.add(other)
    await db.commit()
    r = await api.get(f"{API}/brands/{await _bid(api)}/links/{other.id}/stats")
    assert r.status_code == 404


# ---- campaigns ------------------------------------------------------------------------------
async def test_campaign_summary_and_csv(api, anon, db, brand):
    camp = Campaign(brand_id=brand.id, name="Autumn", utm_campaign="autumn-sale")
    db.add(camp)
    await db.commit()
    t = await _target(db, brand, "x", campaign_id=camp.id)
    db.add(
        Metric(
            target_id=t.id,
            captured_at=datetime.now(UTC),
            impressions=1000,
            likes=40,
            comments=5,
            shares=3,
            clicks=2,
        )
    )
    link = await links_svc.create_short_link(
        db, brand, "https://shop.example.com", campaign_id=camp.id
    )
    await db.commit()
    await anon.get(f"/l/{link.code}/{t.id}", headers={"user-agent": "Mozilla/5.0"})
    bid = await _bid(api)
    r = await api.get(f"{API}/brands/{bid}/campaigns/{camp.id}/summary")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["posts"] == 1 and s["published"] == 1
    assert s["seen"] == 1000 and s["engagements"] == 50
    assert s["link_clicks"] == 1 and s["links"][0]["id"] == link.id
    r = await api.get(f"{API}/brands/{bid}/campaigns/{camp.id}/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("kind,")
    assert any(l.startswith("post,") and ",1000," in l for l in lines)
    assert any(l.startswith("link,") for l in lines)
