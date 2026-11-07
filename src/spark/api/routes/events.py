"""Server-sent events for the app: `event: hello` on connect, `event: update` hints, heartbeats."""

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from spark.api import deps
from spark.api.errors import login_required
from spark.services import events

router = APIRouter(tags=["events"])
HEARTBEAT_SECONDS = 20


async def event_lines(
    user_id: int, is_disconnected: Callable[[], Awaitable[bool]], brand_ids: set[int] | None = None
) -> AsyncIterator[str]:
    """The SSE body: hello, then one `update` per published event, with pings while quiet.
    `brand_ids` limits hints to those brands (None = every brand, for workspace owners)."""
    yield f"event: hello\ndata: {json.dumps({'user_id': user_id})}\n\n"
    last = time.monotonic()
    async for ev in events.subscribe():
        if await is_disconnected():
            break
        if (
            brand_ids is not None
            and ev.get("brand_id") is not None
            and ev.get("brand_id") not in brand_ids
        ):
            continue
        if ev.get("kind") == "tick":
            if time.monotonic() - last >= HEARTBEAT_SECONDS:
                last = time.monotonic()
                yield ": ping\n\n"
            continue
        last = time.monotonic()
        yield f"event: update\ndata: {json.dumps(ev)}\n\n"


async def _who(request: Request) -> tuple[int, set[int] | None]:
    """Resolve the user with a short-lived session that is closed before the stream starts, so an
    open tab never holds a database connection."""
    from spark.db import SessionLocal
    from spark.models import Role
    from spark.services import access

    async with SessionLocal() as db:
        user = await deps.optional_user(request, db)
        if user is None:
            raise login_required()
        allowed = None if user.role == Role.owner else set(await access.roles_for(db, user))
    return user.id, allowed


@router.get("/events")
async def stream(request: Request, who: tuple[int, set[int] | None] = Depends(_who)):
    user_id, allowed = who
    return StreamingResponse(
        event_lines(user_id, request.is_disconnected, allowed),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
