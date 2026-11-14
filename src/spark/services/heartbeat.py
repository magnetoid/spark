"""The worker says it is alive once a minute; /healthz and the setup checklist read it."""

from __future__ import annotations

import asyncio
import logging
import time

from spark.config import get_settings

log = logging.getLogger(__name__)
KEY = "spark:worker:beat"


def _redis():
    import redis.asyncio as redis

    return redis.from_url(get_settings().redis_url, socket_connect_timeout=1)


async def beat() -> None:
    r = _redis()
    try:
        await asyncio.wait_for(r.set(KEY, str(time.time()), ex=3600), timeout=1.0)
    finally:
        await r.aclose()


async def seen_seconds() -> int | None:
    """Seconds since the worker last said it was alive; None when it never did (or Redis is down)."""
    try:
        r = _redis()
        try:
            raw = await asyncio.wait_for(r.get(KEY), timeout=1.0)
        finally:
            await r.aclose()
    except Exception as e:
        log.debug("no worker heartbeat: %s", e)
        return None
    return max(0, int(time.time() - float(raw))) if raw else None


async def redis_ok() -> bool:
    try:
        r = _redis()
        try:
            return bool(await asyncio.wait_for(r.ping(), timeout=1.0))
        finally:
            await r.aclose()
    except Exception:
        return False


def version() -> str:
    """The package version, plus the commit when the deploy says which one it built."""
    import os
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    try:
        v = pkg_version("spark")
    except PackageNotFoundError:
        v = "dev"
    commit = (os.environ.get("SOURCE_COMMIT") or os.environ.get("SPARK_COMMIT") or "")[:7]
    return f"{v}+{commit}" if commit else v
