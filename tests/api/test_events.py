import asyncio
import json

from spark.api.routes.events import event_lines
from spark.services import events
from tests.api.conftest import API


async def test_event_lines_say_hello_and_relay_published_events():
    """The SSE body is tested as a generator: httpx's ASGI transport buffers whole responses."""
    closed = False

    async def disconnected():
        return closed

    gen = event_lines(7, disconnected)
    assert (await gen.__anext__()).startswith("event: hello")
    asyncio.get_running_loop().call_later(
        0.2, lambda: asyncio.ensure_future(events.publish("posts", 1, ids=[42]))
    )
    line = await asyncio.wait_for(gen.__anext__(), timeout=5)
    assert line.startswith("event: update")
    data = json.loads(line.split("data: ", 1)[1].strip())
    assert data["kind"] == "posts" and data["brand_id"] == 1 and data["ids"] == [42]
    closed = True
    await gen.aclose()


async def test_event_stream_needs_a_user(anon):
    r = await anon.get(f"{API}/events")
    assert r.status_code == 401
