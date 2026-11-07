"""Server-sent events for the app: `event: hello` on connect, `event: update` hints, heartbeats."""

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from spark.api import deps
from spark.models import User
from spark.services import events

router = APIRouter(tags=["events"])
HEARTBEAT_SECONDS = 20


async def event_lines(user_id: int, is_disconnected: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
    """The SSE body: hello, then one `update` per published event, with pings while quiet."""
    yield f"event: hello\ndata: {json.dumps({'user_id': user_id})}\n\n"
    last = time.monotonic()
    async for ev in events.subscribe():
        if await is_disconnected():
            break
        if ev.get("kind") == "tick":
            if time.monotonic() - last >= HEARTBEAT_SECONDS:
                last = time.monotonic()
                yield ": ping\n\n"
            continue
        last = time.monotonic()
        yield f"event: update\ndata: {json.dumps(ev)}\n\n"


@router.get("/events")
async def stream(request: Request, user: User = Depends(deps.current_user)):
    return StreamingResponse(event_lines(user.id, request.is_disconnected), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
