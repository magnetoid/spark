"""Live updates: small "something changed" hints the browser turns into refetches.

`publish()` is fire-and-forget: it fans out to subscribers in this process and, when Redis is
reachable, to every other process (the worker publishes post results this way). Nothing
depends on delivery; polling remains the safety net.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator

from spark.config import get_settings

log = logging.getLogger(__name__)
CHANNEL = "spark:events"
_local: set[asyncio.Queue] = set()


def _event(kind: str, brand_id: int | None, data: dict) -> dict:
    return {"kind": kind, "brand_id": brand_id, "at": time.time(), **data}


async def publish(kind: str, brand_id: int | None = None, **data) -> None:
    """Tell listeners that `kind` changed for `brand_id` (e.g. "posts", "accounts", "inbox")."""
    event = _event(kind, brand_id, data)
    for q in list(_local):
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(event)
    try:
        import redis.asyncio as redis

        r = redis.from_url(get_settings().redis_url)
        try:
            await asyncio.wait_for(r.publish(CHANNEL, json.dumps(event)), timeout=1.0)
        finally:
            await r.aclose()
    except Exception as e:  # Redis down: local listeners still got it
        log.debug("event not published to redis: %s", e)


async def subscribe() -> AsyncIterator[dict]:
    """Yield events from this process and from Redis until the consumer stops."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _local.add(q)
    pubsub = None
    try:
        try:
            import redis.asyncio as redis

            r = redis.from_url(get_settings().redis_url)
            pubsub = r.pubsub()
            await asyncio.wait_for(pubsub.subscribe(CHANNEL), timeout=1.0)
        except Exception as e:
            pubsub = None
            log.debug("live updates without redis: %s", e)
        while True:
            if pubsub is not None:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
                if msg and msg.get("type") == "message":
                    with contextlib.suppress(ValueError):
                        yield json.loads(msg["data"])
                try:
                    yield q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            else:
                try:
                    yield await asyncio.wait_for(q.get(), timeout=0.5)
                except TimeoutError:
                    pass
            yield {"kind": "tick"}  # lets the SSE loop send heartbeats and notice closed clients
    finally:
        _local.discard(q)
        if pubsub is not None:
            with contextlib.suppress(Exception):
                await pubsub.aclose()
