"""RSS/Atom feeds → draft or queued posts."""

import html
import logging
import re
from datetime import UTC, datetime

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import (
    Brand,
    Post,
    PostStatus,
    PostTarget,
    RssFeed,
    SocialAccount,
    User,
)
from spark.services.ai import AIUnavailable, ContentAI
from spark.services.scheduler import next_free_slot

log = logging.getLogger(__name__)
TAG_RE = re.compile(r"<[^>]+>")
MAX_SEEN = 500


def clean(text: str) -> str:
    return html.unescape(TAG_RE.sub("", text or "")).strip()


async def fetch_entries(http: httpx.AsyncClient, url: str) -> list[dict]:
    resp = await http.get(url, follow_redirects=True, headers={"User-Agent": "Spark/1.0"})
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    return [
        {
            "id": e.get("id") or e.get("link"),
            "title": clean(e.get("title", "")),
            "link": e.get("link"),
            "summary": clean(e.get("summary", ""))[:2000],
        }
        for e in parsed.entries
    ]


async def process_feed(
    db: AsyncSession, feed: RssFeed, http: httpx.AsyncClient, ai: ContentAI | None = None
) -> int:
    brand = await db.get(Brand, feed.brand_id)
    entries = await fetch_entries(http, feed.url)
    seen = set(feed.seen_ids or [])
    first_run = feed.last_checked_at is None
    new = [e for e in entries if e["id"] and e["id"] not in seen]
    feed.last_checked_at = datetime.now(UTC)
    feed.seen_ids = (list(seen) + [e["id"] for e in new])[-MAX_SEEN:]
    if first_run:
        # Don't flood the queue with the feed's back catalogue on first check.
        await db.commit()
        return 0
    accounts = []
    if feed.account_ids:
        accounts = (
            await db.execute(
                select(SocialAccount).where(
                    SocialAccount.id.in_(feed.account_ids), SocialAccount.is_active.is_(True)
                )
            )
        ).scalars().all()
    owner = await db.scalar(select(User).where(User.role == "owner").limit(1))
    created = 0
    for e in reversed(new):
        text = f"{e['title']}"
        overrides: dict[int, str] = {}
        if feed.use_ai and ai:
            try:
                drafts = await ai.generate(
                    brand,
                    f"Share this new article from our feed: {e['title']}",
                    sorted({a.platform for a in accounts}) or ["x"],
                    source_text=e["summary"],
                    link=e["link"],
                )
                by_platform = {d.platform: d for d in drafts}
                if drafts:
                    text = drafts[0].text
                for a in accounts:
                    if d := by_platform.get(a.platform):
                        overrides[a.id] = d.text
            except AIUnavailable as exc:
                log.info("RSS AI skipped: %s", exc)
        post = Post(
            brand_id=brand.id,
            content=text,
            link=e["link"],
            source="rss",
            author_id=owner.id if owner else None,
            notes=f"From feed: {feed.name or feed.url}",
        )
        post.targets = [
            PostTarget(account_id=a.id, content_override=overrides.get(a.id)) for a in accounts
        ]
        db.add(post)
        if feed.auto_queue and accounts:
            when = await next_free_slot(db, brand)
            post.scheduled_at = when
            post.status = PostStatus.pending_approval if brand.require_approval else PostStatus.scheduled
            for t in post.targets:
                t.status, t.scheduled_at = post.status, when
        await db.flush()
        created += 1
    await db.commit()
    return created
