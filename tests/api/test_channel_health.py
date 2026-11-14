"""Channel health: Spark notices a channel that needs reconnecting or whose access is about to
run out, tells the team once per change (email, chat, webhooks), and says when it is fixed."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from spark.config import get_settings
from spark.models import OutboundEvent, SocialAccount
from tests.api.conftest import API
from tests.api.test_phase9 import Z, _signed
from tests.api.test_quickwins import SLACK, _chat, public_dns  # noqa: F401


@pytest.fixture
async def zch(db, brand, monkeypatch):
    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    brand.zernio_profile_id = "prof1"
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


def _accounts(**over):
    a = {
        "_id": "z-ig",
        "platform": "instagram",
        "username": "acme.ig",
        "profileId": "prof1",
        "needsReconnection": False,
    }
    a.update(over)
    return httpx.Response(200, json={"accounts": [a], "pagination": {}})


async def _events(db, name=None):
    q = select(OutboundEvent).order_by(OutboundEvent.id)
    rows = (await db.execute(q)).scalars().all()
    return [e.event for e in rows if name is None or e.event == name]


async def _health(api, brand, acc_id):
    rows = (await api.get(f"{API}/brands/{brand.id}/accounts")).json()
    return next(r for r in rows if r["id"] == acc_id)


@respx.mock
async def test_sync_marks_needs_reconnection_and_alerts_once(api, db, brand, zch):
    from spark.services import channel_health

    respx.get(f"{Z}/accounts").mock(return_value=_accounts(needsReconnection=True))
    await channel_health.sync_channels(db)
    await channel_health.sync_channels(db)
    await db.refresh(zch)
    assert zch.extra["needs_reconnection"] is True and zch.checked_at is not None
    assert await _events(db) == ["channel.reconnect_needed"]
    row = await _health(api, brand, zch.id)
    assert row["health"] == "reconnect"


@respx.mock
async def test_recovery_clears_alert(api, db, brand, zch):
    from spark.services import channel_health

    route = respx.get(f"{Z}/accounts").mock(return_value=_accounts(needsReconnection=True))
    await channel_health.sync_channels(db)
    route.mock(return_value=_accounts())
    await channel_health.sync_channels(db)
    await channel_health.sync_channels(db)
    await db.refresh(zch)
    assert zch.alerted_for is None and not zch.extra.get("needs_reconnection")
    assert await _events(db) == ["channel.reconnect_needed", "channel.recovered"]
    assert (await _health(api, brand, zch.id))["health"] == "ok"


async def test_connected_webhook_clears_flag(anon, db, brand, zch):
    zch.extra = {"needs_reconnection": True}
    zch.alerted_for = "reconnect"
    zch.last_error = "Reconnect needed: token"
    await db.commit()
    raw, headers = _signed(
        {
            "id": "ev-ac1",
            "event": "account.connected",
            "timestamp": "2026-11-07T10:00:00Z",
            "account": {
                "accountId": "z-ig",
                "profileId": "prof1",
                "platform": "instagram",
                "username": "acme.ig",
            },
        }
    )
    assert (await anon.post("/webhooks/zernio", content=raw, headers=headers)).status_code == 200
    await db.refresh(zch)
    assert not zch.extra.get("needs_reconnection") and zch.last_error is None
    assert zch.alerted_for is None
    assert await _events(db) == ["channel.recovered"]


async def test_disconnected_webhook_alerts(anon, db, brand, zch):
    raw, headers = _signed(
        {
            "id": "ev-ad1",
            "event": "account.disconnected",
            "timestamp": "2026-11-07T10:00:00Z",
            "account": {"accountId": "z-ig", "disconnectionType": "revoked"},
        }
    )
    assert (await anon.post("/webhooks/zernio", content=raw, headers=headers)).status_code == 200
    assert await _events(db) == ["channel.reconnect_needed"]


@respx.mock
async def test_expiry_alerts_at_7_3_1(api, db, brand, zch):
    from spark.services import channel_health

    now = datetime.now(UTC)
    route = respx.get(f"{Z}/accounts")
    for days in (20, 6.5, 6.4, 2.5, 0.5):
        route.mock(return_value=_accounts(tokenExpiresAt=(now + timedelta(days=days)).isoformat()))
        await channel_health.sync_channels(db)
    await db.refresh(zch)
    assert zch.alerted_for == "expiring:1"
    expiring = [
        e.data["channel"]["days_left"]
        for e in (await db.execute(select(OutboundEvent))).scalars()
        if e.event == "channel.expiring"
    ]
    assert expiring == [6, 2, 0]
    row = await _health(api, brand, zch.id)
    assert row["health"] == "expiring" and row["expires_at"]


async def test_direct_channel_with_refresh_token_never_warns(db, brand):
    from spark.services import channel_health

    acc = SocialAccount(brand_id=brand.id, platform="linkedin", external_id="li", handle="acme")
    acc.access_token, acc.refresh_token, acc.is_active = "a", "r", True
    acc.token_expires_at = datetime.now(UTC) + timedelta(days=1)
    assert channel_health.health(acc) == "ok"
    acc.refresh_token = None
    assert channel_health.health(acc) == "expiring"
    acc.is_active = False
    assert channel_health.health(acc) == "paused"


@respx.mock
async def test_channel_alert_reaches_email_and_chat_once(db, brand, zch, public_dns):  # noqa: F811
    from spark.services import channel_health, outbox
    from spark.services.email import ConsoleSender

    _chat(chat_slack_webhook=SLACK)
    slack = respx.post(SLACK).mock(return_value=httpx.Response(200, text="ok"))
    respx.get(f"{Z}/accounts").mock(return_value=_accounts(needsReconnection=True))
    ConsoleSender.sent.clear()
    await channel_health.sync_channels(db)
    await outbox.process(db)
    await outbox.process(db)
    assert slack.call_count == 1
    text = json.loads(slack.calls.last.request.content)["text"]
    assert text.startswith("[Acme] ") and "acme.ig" in text and "reconnect" in text.lower()
    mails = [m for m in ConsoleSender.sent if "reconnect" in m["subject"].lower()]
    assert [m["to"] for m in mails] == ["owner@example.com"]


async def test_today_lists_channels_that_need_you(api, db, brand, zch):
    zch.extra = {"needs_reconnection": True}
    await db.commit()
    needs = (await api.get(f"{API}/brands/{brand.id}/today")).json()["needs_you"]
    assert needs["channels"] == 1
