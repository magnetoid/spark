"""HTTP client for the Janus agent (github.com/magnetoid/Janus-Agent) that runs next to Spark.

Spark starts runs (`POST /v1/runs`), follows their events (SSE on `GET /v1/runs/{id}/events`),
answers approval prompts and stops runs. Memory is scoped per brand with `X-Janus-Session-Key`.
Janus has no version in its health routes; `GET /v1/config` carries one when it is allowed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx

from spark.config import get_settings

log = logging.getLogger("spark.janus")


class JanusError(Exception):
    pass


class JanusUnavailable(JanusError):
    """Janus is not configured. Settings → Connectors → Janus."""


def configured() -> bool:
    s = get_settings()
    return bool(s.janus_base_url and s.janus_api_key)


class Janus:
    def __init__(
        self, base_url: str | None = None, api_key: str | None = None, timeout: float = 30.0
    ):
        s = get_settings()
        self.base_url = (base_url or s.janus_base_url or "").rstrip("/")
        self.api_key = api_key or s.janus_api_key or ""
        if not self.base_url or not self.api_key:
            raise JanusUnavailable(
                "Janus is not set up. Add its address and API key under Settings → Connectors → Janus."
            )
        self.timeout = timeout

    def _headers(self, session_key: str | None = None) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if session_key:
            h["X-Janus-Session-Key"] = session_key[:256]
        return h

    # ---- status --------------------------------------------------------------------------
    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self.base_url}/health")
            return r.status_code == 200 and (r.json().get("status") == "ok")
        except Exception as e:  # unreachable, DNS, TLS: the UI shows "unreachable"
            log.info("Janus health failed: %s", e)
            return False

    async def version(self) -> str | None:
        """The running Janus version, or None when the install hides its config (409) or refuses."""
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self.base_url}/v1/config", headers=self._headers())
            if r.status_code == 200:
                return str(r.json().get("version") or "") or None
        except Exception as e:
            log.info("Janus version failed: %s", e)
        return None

    # ---- runs -------------------------------------------------------------------------------
    async def start_run(
        self,
        *,
        input: str,
        instructions: str,
        session_key: str,
        session_id: str | None = None,
        history: list[dict] | None = None,
    ) -> str:
        body: dict = {"input": input, "instructions": instructions}
        if session_id:
            body["session_id"] = session_id
        if history:
            body["conversation_history"] = history
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(
                f"{self.base_url}/v1/runs", json=body, headers=self._headers(session_key)
            )
        if r.status_code == 429:
            raise JanusError("Janus is busy (too many runs at once). Try again in a minute.")
        if r.status_code >= 400:
            raise JanusError(_error_text(r))
        run_id = r.json().get("run_id")
        if not run_id:
            raise JanusError("Janus did not return a run id")
        return str(run_id)

    async def events(self, run_id: str) -> AsyncIterator[dict]:
        """Yield the run's events until the stream closes. Frames are `data: <json>`; comments are keepalives."""
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=120.0)) as c,
            c.stream(
                "GET",
                f"{self.base_url}/v1/runs/{run_id}/events",
                headers={**self._headers(), "Accept": "text/event-stream"},
            ) as r,
        ):
            if r.status_code >= 400:
                await r.aread()
                raise JanusError(_error_text(r))
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(ev, dict):
                    ev.setdefault("received_at", datetime.now(UTC).isoformat())
                    yield ev

    async def status(self, run_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.base_url}/v1/runs/{run_id}", headers=self._headers())
        if r.status_code >= 400:
            raise JanusError(_error_text(r))
        return r.json()

    async def approve(self, run_id: str, choice: str = "deny", all_pending: bool = True) -> dict:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{self.base_url}/v1/runs/{run_id}/approval",
                json={"choice": choice, "all": all_pending},
                headers=self._headers(),
            )
        if r.status_code >= 400:
            raise JanusError(_error_text(r))
        return r.json()

    async def put_config(self, body: dict) -> dict:
        """Change Janus's configuration (raw YAML, api keys, restart) through its config API."""
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.put(f"{self.base_url}/v1/config", json=body, headers=self._headers())
        if r.status_code >= 400:
            raise JanusError(_error_text(r))
        return r.json() if r.content else {}

    async def stop(self, run_id: str) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{self.base_url}/v1/runs/{run_id}/stop", headers=self._headers())


def _error_text(r: httpx.Response) -> str:
    try:
        err = r.json().get("error") or {}
        return f"Janus {r.status_code}: {err.get('message') or r.text[:200]}"
    except Exception:
        return f"Janus {r.status_code}: {r.text[:200]}"
