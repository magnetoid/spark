"""Background worker (ARQ). Run with: `spark worker` or `arq spark.worker.WorkerSettings`."""

import logging
from datetime import UTC, datetime, timedelta

import httpx
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from spark.config import get_settings
from spark.db import SessionLocal
from spark.models import EmailCampaign, RssFeed
from spark.services import analytics, email, notify, publisher, rss
from spark.services.ai import AIUnavailable, ContentAI

log = logging.getLogger("spark.worker")


async def publish_due(ctx) -> int:
    n = await publisher.publish_due(SessionLocal)
    if n:
        log.info("Published %d target(s)", n)
    return n


async def publish_now(ctx, target_id: int) -> None:
    async with SessionLocal() as db:
        await publisher.publish_target(db, target_id)


async def recover_stuck(ctx) -> None:
    async with SessionLocal() as db:
        await publisher.recover_stuck(db)


async def collect_metrics(ctx) -> int:
    async with SessionLocal() as db:
        return await analytics.collect_metrics(db)


async def poll_feeds(ctx) -> int:
    try:
        ai = ContentAI()
    except AIUnavailable:
        ai = None
    created = 0
    async with httpx.AsyncClient(timeout=30) as http, SessionLocal() as db:
        cutoff = datetime.now(UTC) - timedelta(minutes=30)
        feeds = (await db.execute(select(RssFeed).where(RssFeed.is_active.is_(True)))).scalars().all()
        for feed in feeds:
            last = publisher.as_utc(feed.last_checked_at)
            if last and last > cutoff:
                continue
            try:
                created += await rss.process_feed(db, feed, http, ai)
            except Exception:
                log.exception("Feed %s failed", feed.url)
                await db.rollback()
    return created


async def send_email_campaign(ctx, campaign_id: int) -> int:
    async with SessionLocal() as db:
        return await email.send_campaign(db, campaign_id)


async def send_scheduled_emails(ctx) -> None:
    async with SessionLocal() as db:
        due = (
            await db.execute(
                select(EmailCampaign.id).where(
                    EmailCampaign.status == "scheduled",
                    EmailCampaign.scheduled_at <= datetime.now(UTC),
                )
            )
        ).scalars().all()
    for cid in due:
        async with SessionLocal() as db:
            await email.send_campaign(db, cid)


async def send_notifications(ctx) -> int:
    """Failed posts and pending approvals, once each."""
    async with SessionLocal() as db:
        return await notify.notify_failed(db) + await notify.notify_approvals(db)


async def send_weekly_digest(ctx) -> int:
    async with SessionLocal() as db:
        return await notify.weekly_digest(db)


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions = [publish_now, send_email_campaign]
    cron_jobs = [
        cron(publish_due, second={0, 30}, run_at_startup=True),
        cron(send_scheduled_emails, second=15),
        cron(recover_stuck, minute={0, 15, 30, 45}),
        cron(poll_feeds, minute={5, 35}),
        cron(collect_metrics, hour={0, 6, 12, 18}, minute=20),
        cron(send_notifications, second=50),
        cron(send_weekly_digest, weekday=0, hour=7, minute=0),  # Mondays 07:00 UTC
    ]
    max_jobs = 10
    job_timeout = 600
