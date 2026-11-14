"""What a new install still needs before it publishes reliably: one list, computed on the server,
shown to owners on Today until they dismiss it."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import Settings, get_settings
from spark.models import Post, PostStatus, QueueSlot, SocialAccount, User

WORKER_STALE_S = 300  # the worker says hello every minute; five minutes of silence means it is down
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
CONFIG_DOCS = "https://github.com/magnetoid/spark/blob/main/docs/configuration.md"


@dataclass
class Step:
    key: str
    title: str
    done: bool
    detail: str
    action_url: str
    action_label: str
    optional: bool = False


async def steps(db: AsyncSession, user: User) -> list[Step]:
    from spark.services import heartbeat, webhooks

    s = get_settings()
    zernio = bool(s.zernio_api_key)
    hook = await webhooks.webhook_status() if zernio else None
    channels = await db.scalar(
        select(func.count(SocialAccount.id)).where(
            SocialAccount.is_active.is_(True), SocialAccount.platform != "dry_run"
        )
    )
    slots = await db.scalar(select(func.count(QueueSlot.id)))
    posts = await db.scalar(
        select(func.count(Post.id)).where(
            Post.is_autosave.is_(False),
            Post.status.in_((PostStatus.scheduled, PostStatus.publishing, PostStatus.published)),
        )
    )
    host = (urlsplit(s.base_url).hostname or "").lower()
    seen = await heartbeat.seen_seconds()
    connectors = "/settings?tab=connectors"
    return [
        Step(
            "zernio",
            "Connect Zernio",
            zernio,
            "One Zernio key publishes to 14 networks. Skip it if you only post to Bluesky, "
            "Mastodon or Telegram.",
            f"{connectors}&connector=zernio",
            "Add the key",
            optional=True,
        ),
        Step(
            "webhook",
            "Let Zernio report back",
            bool(hook and not hook.get("missing")),
            "Zernio tells Spark when posts go out, when comments arrive and when a channel "
            "needs reconnecting. Turn it on from the Zernio card, on the server Spark runs on.",
            f"{connectors}&connector=zernio",
            "Open Zernio",
            optional=not zernio,
        ),
        Step(
            "channel",
            "Connect a channel",
            bool(channels),
            "The social accounts Spark publishes to.",
            "/channels",
            "Connect a channel",
        ),
        Step(
            "slots",
            "Set posting times",
            bool(slots),
            "Posts added to the queue go out at these times.",
            "/settings?tab=times",
            "Set times",
        ),
        Step(
            "first_post",
            "Schedule a first post",
            bool(posts),
            "Write one and add it to the queue to see the whole path work.",
            "/publishing",
            "Write a post",
        ),
        Step(
            "email",
            "Send real email",
            s.email_backend != "console",
            "Failed posts, approvals and channel alerts are emailed. Until SMTP or Resend is "
            "set up, emails are only written to the server log.",
            f"{connectors}&connector=email",
            "Set up email",
        ),
        Step(
            "public_url",
            "Set the public address",
            bool(host) and host not in LOCAL_HOSTS,
            "SPARK_BASE_URL must be the address people and networks reach Spark at: "
            "networks fetch images from it and links in emails point to it.",
            CONFIG_DOCS,
            "Read the guide",
        ),
        Step(
            "secret_key",
            "Set a secret key",
            s.secret_key != Settings.model_fields["secret_key"].default,
            "SPARK_SECRET_KEY signs sign-ins and encrypts channel tokens. Set a long random "
            "value before anyone else uses this install.",
            CONFIG_DOCS,
            "Read the guide",
        ),
        Step(
            "worker",
            "Run the background worker",
            seen is not None and seen <= WORKER_STALE_S,
            "The worker publishes scheduled posts, retries failures and sends alerts. "
            "Start it with `spark worker` next to the web process.",
            "/publishing",
            "Check publishing",
        ),
        Step(
            "two_factor",
            "Turn on two-factor",
            bool(user.totp_enabled),
            "A code from an authenticator app at sign-in keeps the owner account safe.",
            "/settings?tab=me",
            "Turn it on",
        ),
    ]


async def summary(db: AsyncSession, user: User) -> dict:
    items = await steps(db, user)
    done = sum(1 for i in items if i.done)
    required = [i for i in items if not i.optional]
    return {
        "steps": [asdict(i) for i in items],
        "done": done,
        "total": len(items),
        "complete": all(i.done for i in required),
    }
