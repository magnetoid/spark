"""Hand-off to the ARQ worker. Every job is also picked up by a cron sweep, so a failed
enqueue (Redis down, worker not deployed yet) only delays the work."""

from __future__ import annotations

import logging

from spark.config import get_settings

log = logging.getLogger(__name__)


async def enqueue(job: str, *args) -> bool:
    """Best-effort immediate job; the worker's cron picks it up anyway."""
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        await pool.enqueue_job(job, *args)
        await pool.aclose()
        return True
    except Exception as e:
        log.info("Could not enqueue %s (%s); cron will handle it", job, e)
        return False
