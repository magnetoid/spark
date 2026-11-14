"""Outbound webhooks: every event in the outbox, POSTed as signed JSON to the addresses owners added.

The request
    POST <endpoint url>
    Content-Type: application/json
    X-Spark-Event: post.published
    X-Spark-Delivery: 42                      (the same on every retry of this delivery)
    X-Spark-Signature: t=1731500000,v1=<hex>  (HMAC-SHA256 of "<t>.<body>" with the endpoint's secret)

    {"id": "evt_17", "event": "post.published", "created_at": "2026-11-13T10:00:00Z",
     "brand": {"id": 1, "name": "Acme"}, "data": {...}}

Any 2xx answer within 10 seconds counts as delivered. Anything else is tried again after 1 minute,
5 minutes, 30 minutes, 2 hours and 6 hours, then given up. Redirects are not followed and the
address has to be a public one, checked before every attempt. An endpoint that fails 20 times in a
row is switched off until an owner turns it back on. Receivers should treat `id` as the key for
deduplication: a delivery whose answer got lost is sent again.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, WebhookDelivery, WebhookEndpoint
from spark.security import decrypt, encrypt, token
from spark.services.fetch import is_public_url

log = logging.getLogger(__name__)
TIMEOUT = 10
RETRY_AFTER = (60, 300, 1800, 7200, 21600)  # seconds to wait after the 1st, 2nd, … failed try
MAX_ATTEMPTS = len(RETRY_AFTER) + 1
LEASE = timedelta(minutes=5)  # a try that never reported back (worker died) is repeated after this
DISABLE_AFTER = 20  # failed tries in a row
KEEP = timedelta(days=30)
TEST_EVENT = "webhook.test"
USER_AGENT = "Spark-Webhooks/1.0"


def new_secret() -> str:
    return "whsec_" + token(32)


def sign(secret: str, body: bytes, timestamp: int) -> str:
    """The value of X-Spark-Signature for this body at this time."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


async def url_problem(url: str) -> str | None:
    """Why this address cannot be a webhook, or None when it can."""
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")) or len(url) > 2000:
        return "A webhook address starts with https:// (or http://)"
    if not await asyncio.to_thread(is_public_url, url):
        return "A webhook address has to be reachable on the public internet"
    return None


def _iso(dt: datetime | None) -> str:
    dt = dt or datetime.now(UTC)
    return (
        (dt if dt.tzinfo else dt.replace(tzinfo=UTC))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def envelope(
    event_id: str, event: str, data: dict, brand: Brand | None, created_at: datetime | None = None
) -> dict:
    return {
        "id": event_id,
        "event": event,
        "created_at": _iso(created_at),
        "brand": {"id": brand.id, "name": brand.name} if brand else None,
        "data": data,
    }


async def create(
    db: AsyncSession,
    url: str,
    brand_id: int | None,
    events: list[str],
    description: str,
    user_id: int | None,
) -> tuple[WebhookEndpoint, str]:
    """A new endpoint and its secret; the secret is readable only now."""
    secret = new_secret()
    ep = WebhookEndpoint(
        url=url.strip(),
        brand_id=brand_id,
        events=sorted(set(events)),
        description=description.strip()[:200],
        secret=encrypt(secret),
        created_by=user_id,
    )
    db.add(ep)
    await db.commit()
    return ep, secret


async def enqueue(
    db: AsyncSession,
    event_id: int,
    event: str,
    data: dict,
    brand: Brand | None,
    created_at: datetime | None,
) -> int:
    """Queue one delivery per endpoint that listens for this event. The caller commits."""
    scope = WebhookEndpoint.brand_id.is_(None)
    if brand is not None:
        scope = or_(scope, WebhookEndpoint.brand_id == brand.id)
    endpoints = (
        (await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.enabled.is_(True), scope)))
        .scalars()
        .all()
    )
    payload = envelope(f"evt_{event_id}", event, data, brand, created_at)
    n = 0
    for ep in endpoints:
        if ep.events and event not in ep.events:
            continue
        db.add(
            WebhookDelivery(endpoint_id=ep.id, event_id=payload["id"], event=event, payload=payload)
        )
        n += 1
    return n


async def _send(
    http: httpx.AsyncClient, ep: WebhookEndpoint, d: WebhookDelivery
) -> tuple[int | None, str | None]:
    """One HTTP try. Returns (status the endpoint answered with, why it does not count)."""
    if not await asyncio.to_thread(is_public_url, ep.url):
        return None, "the address is not a public http(s) address"
    secret = decrypt(ep.secret)
    if not secret:
        return None, "the signing secret cannot be read; remove this webhook and add it again"
    body = json.dumps(d.payload, separators=(",", ":"), ensure_ascii=False).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Spark-Event": d.event,
        "X-Spark-Delivery": str(d.id),
        "X-Spark-Signature": sign(secret, body, int(time.time())),
    }
    try:
        async with http.stream("POST", ep.url, content=body, headers=headers) as r:
            if r.is_success:
                return r.status_code, None
            said = b""
            async for chunk in r.aiter_bytes():
                said += chunk
                if len(said) >= 300:
                    break
            detail = " ".join(said[:300].decode("utf-8", "replace").split())
            return r.status_code, f"answered {r.status_code}" + (f": {detail}" if detail else "")
    except httpx.TimeoutException:
        return None, f"no answer in {TIMEOUT} seconds"
    except httpx.HTTPError as e:
        return None, f"could not connect ({type(e).__name__})"


async def _attempt(db: AsyncSession, http: httpx.AsyncClient, delivery_id: int) -> bool:
    """Take the delivery (so no other worker sends it too), send it, write down what happened."""
    now = datetime.now(UTC)
    leased = await db.execute(
        update(WebhookDelivery)
        .where(
            WebhookDelivery.id == delivery_id,
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= now,
        )
        .values(attempts=WebhookDelivery.attempts + 1, next_attempt_at=now + LEASE)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if leased.rowcount != 1:
        return False
    d = await db.get(WebhookDelivery, delivery_id, populate_existing=True)
    ep = await db.get(WebhookEndpoint, d.endpoint_id, populate_existing=True) if d else None
    if d is None or ep is None:
        return False
    is_test = d.event == TEST_EVENT
    if not ep.enabled and not is_test:
        d.status, d.error = "failed", "the webhook was switched off"
        await db.commit()
        return False
    status, error = await _send(http, ep, d)
    now = datetime.now(UTC)
    d.response_status, d.error = status, (error or None) and error[:500]
    ep.last_status, ep.last_error, ep.last_delivery_at = status, d.error, now
    if error is None:
        d.status, d.delivered_at = "delivered", now
        ep.failures = 0
    elif is_test:
        d.status = "failed"  # a test is sent once and never counts against the endpoint
    else:
        if d.attempts >= MAX_ATTEMPTS:
            d.status = "failed"
        else:
            d.next_attempt_at = now + timedelta(seconds=RETRY_AFTER[d.attempts - 1])
        ep.failures += 1
        if ep.failures >= DISABLE_AFTER:
            ep.enabled = False
            ep.disabled_reason = (
                f"Switched off after {ep.failures} failed tries in a row. Last: {error}"[:500]
            )
            log.warning("Webhook %s switched off after %s failed tries", ep.id, ep.failures)
    await db.commit()
    return error is None


async def deliver_due(db: AsyncSession, limit: int = 100) -> int:
    """Send every delivery whose time has come. Returns how many were delivered."""
    due = (
        (
            await db.execute(
                select(WebhookDelivery.id)
                .where(
                    WebhookDelivery.status == "pending",
                    WebhookDelivery.next_attempt_at <= datetime.now(UTC),
                )
                .order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not due:
        return 0
    delivered = 0
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as http:
        for delivery_id in due:
            try:
                delivered += await _attempt(db, http, delivery_id)
            except Exception:
                await db.rollback()
                log.exception("Webhook delivery %s failed unexpectedly", delivery_id)
    return delivered


async def send_test(db: AsyncSession, ep: WebhookEndpoint) -> WebhookDelivery:
    """Send a test event to this endpoint now, whatever it listens for."""
    brand = await db.get(Brand, ep.brand_id) if ep.brand_id else None
    d = WebhookDelivery(
        endpoint_id=ep.id,
        event_id="evt_test",
        event=TEST_EVENT,
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        payload=envelope(
            "evt_test",
            TEST_EVENT,
            {
                "message": "This is a test from Spark. Real events look the same, with their own data."
            },
            brand,
        ),
    )
    db.add(d)
    await db.commit()
    delivery_id = d.id
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as http:
        await _attempt(db, http, delivery_id)
    return await db.get(WebhookDelivery, delivery_id, populate_existing=True)


async def remove(db: AsyncSession, ep: WebhookEndpoint) -> None:
    await db.execute(
        delete(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == ep.id)
        .execution_options(synchronize_session=False)
    )
    await db.delete(ep)
    await db.commit()


async def prune(db: AsyncSession) -> int:
    """Forget finished deliveries older than a month."""
    res = await db.execute(
        delete(WebhookDelivery)
        .where(
            WebhookDelivery.status != "pending",
            WebhookDelivery.created_at < datetime.now(UTC) - KEEP,
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return res.rowcount or 0
