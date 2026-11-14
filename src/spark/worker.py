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
from spark.services import (
    agent,
    analytics,
    email,
    evergreen,
    hooks,
    inbox,
    notify,
    outbox,
    publisher,
    reports,
    rss,
)
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


async def follow_agent_run(ctx, run_id: int) -> str:
    async with SessionLocal() as db:
        return await agent.follow(db, run_id)


async def sync_janus(ctx) -> dict:
    s = get_settings()
    if not s.janus_managed:
        return {"result": "skipped"}
    from spark.services import janus_setup

    async with SessionLocal() as db:
        return await janus_setup.sync(db)


async def update_janus(ctx) -> dict:
    """Monday 05:00 UTC: restart the built-in Janus so it pulls the latest release on the way up."""
    s = get_settings()
    if not s.janus_managed:
        return {"result": "skipped"}
    from spark.services import janus_setup

    try:
        return await janus_setup.restart_for_update()
    except Exception as e:  # Janus down: the next weekly pass tries again
        log.warning("Weekly Janus update skipped: %s", e)
        return {"result": "failed"}


async def sweep_agent_runs(ctx) -> int:
    async with SessionLocal() as db:
        return await agent.sweep_stale(db)


async def start_weekly_plans(ctx) -> int:
    async with SessionLocal() as db:
        return await agent.start_due_weekly_plans(db)


async def sync_inbox(ctx) -> dict:
    async with SessionLocal() as db:
        return await inbox.sync_all(db)


async def classify_inbox(ctx) -> int:
    async with SessionLocal() as db:
        return await inbox.classify_pending(db)


async def snapshot_followers(ctx) -> int:
    async with SessionLocal() as db:
        return await reports.snapshot_followers(db)


async def recycle_evergreen(ctx) -> int:
    async with SessionLocal() as db:
        return await evergreen.recycle(db)


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
        feeds = (
            (await db.execute(select(RssFeed).where(RssFeed.is_active.is_(True)))).scalars().all()
        )
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
            (
                await db.execute(
                    select(EmailCampaign.id).where(
                        EmailCampaign.status == "scheduled",
                        EmailCampaign.scheduled_at <= datetime.now(UTC),
                    )
                )
            )
            .scalars()
            .all()
        )
    for cid in due:
        async with SessionLocal() as db:
            await email.send_campaign(db, cid)


async def send_notifications(ctx) -> int:
    """Failed posts and pending approvals, once each."""
    async with SessionLocal() as db:
        sent = await notify.notify_failed(db) + await notify.notify_approvals(db)
        await outbox.process(db)
        return sent


async def worker_beat(ctx) -> None:
    """Every minute: tell /healthz and the setup checklist that the worker runs."""
    from spark.services import heartbeat

    try:
        await heartbeat.beat()
    except Exception:
        log.warning("Could not write the worker heartbeat", exc_info=True)


async def sync_channels(ctx) -> int:
    """Hourly: ask Zernio which channels need reconnecting or run out soon; alert once."""
    from spark.services import channel_health

    async with SessionLocal() as db:
        return await channel_health.sync_channels(db)


async def deliver_outbox(ctx) -> int:
    """Events on their way out: chat messages now, webhook deliveries queued and sent."""
    async with SessionLocal() as db:
        n = await outbox.process(db)
        return n + await hooks.deliver_due(db)


async def prune_webhook_log(ctx) -> int:
    async with SessionLocal() as db:
        return await hooks.prune(db)


async def send_weekly_digest(ctx) -> int:
    async with SessionLocal() as db:
        return await notify.weekly_digest(db)


async def load_connectors(ctx) -> None:
    """Pick up connector values saved in Settings → Connectors (cached for 30 s)."""
    from spark.services import connectors

    try:
        async with SessionLocal() as db:
            await connectors.refresh(db)
    except Exception:
        log.exception("Could not load connector settings")


class WorkerSettings:
    on_startup = load_connectors
    on_job_start = load_connectors
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions = [publish_now, send_email_campaign, follow_agent_run]
    cron_jobs = [
        cron(publish_due, second={0, 30}, run_at_startup=True),
        cron(send_scheduled_emails, second=15),
        cron(recover_stuck, minute={0, 15, 30, 45}),
        cron(poll_feeds, minute={5, 35}),
        cron(collect_metrics, hour={0, 6, 12, 18}, minute=20),
        cron(recycle_evergreen, hour={6}, minute=10),
        cron(start_weekly_plans, hour={7}, minute=5),
        cron(sweep_agent_runs, minute=set(range(1, 60, 5))),
        cron(sync_janus, minute={7, 37}),
        cron(update_janus, weekday=0, hour={5}, minute=0),
        cron(sync_inbox, minute={12, 42}),
        cron(snapshot_followers, hour={0}, minute=35),
        cron(classify_inbox, minute=set(range(2, 60, 5))),
        cron(send_notifications, second=50),
        cron(deliver_outbox, second={5, 20, 35}),
        cron(sync_channels, minute={27}),
        cron(worker_beat, second={0}, run_at_startup=True),
        cron(prune_webhook_log, hour={3}, minute=40),
        cron(send_weekly_digest, weekday=0, hour=7, minute=0),  # Mondays 07:00 UTC
    ]
    max_jobs = 10
    job_timeout = 600
