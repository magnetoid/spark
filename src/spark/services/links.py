"""UTM tagging and short links."""

import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import Brand, ShortLink
from spark.security import short_code

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")
# Link previews and crawlers: they still get the redirect, but are not counted as clicks.
BOT_RE = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|preview|facebookexternalhit|facebookcatalog|embedly|"
    r"whatsapp|telegrambot|discordbot|skypeuripreview|pinterest/|vkshare|redditbot|"
    r"bitlybot|quora link preview|outbrain|google-inspectiontool|headlesschrome|python-|"
    r"curl/|wget/|go-http-client|okhttp|axios/|node-fetch",
    re.I,
)


def add_utm(url: str, **params: str | None) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value:
            query.setdefault(f"utm_{key}", value)
    return urlunsplit(parts._replace(query=urlencode(query)))


def set_utm(url: str, **params: str | None) -> str:
    """Like `add_utm`, but replaces tags the URL already has."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value:
            query[f"utm_{key}"] = value
    return urlunsplit(parts._replace(query=urlencode(query)))


def is_bot(user_agent: str | None) -> bool:
    return bool(user_agent and BOT_RE.search(user_agent))


def mark_for_target(text: str | None, target_id: int | None) -> str | None:
    """Point Spark short links in `text` at /l/{code}/{target_id}, so a click shows which
    published post and channel it came from."""
    if not text or not target_id:
        return text
    base = re.escape(get_settings().base_url.rstrip("/"))
    pattern = re.compile(base + r"/l/([A-Za-z0-9][A-Za-z0-9_-]{1,63})(?![A-Za-z0-9_/-])")
    return pattern.sub(lambda m: f"{m.group(0)}/{target_id}", text)


def short_url(link: ShortLink) -> str:
    return f"{get_settings().base_url.rstrip('/')}/l/{link.code}"


async def create_short_link(
    db: AsyncSession,
    brand: Brand,
    destination: str,
    *,
    title: str | None = None,
    campaign_id: int | None = None,
    code: str | None = None,
    post_id: int | None = None,
    expires_at: datetime | None = None,
) -> ShortLink:
    """A new short link. A chosen `code` must already be checked with `code_taken`."""
    while code is None:
        code = short_code()
        if await code_taken(db, code):
            code = None
    link = ShortLink(
        brand_id=brand.id,
        code=code,
        destination=destination,
        title=title,
        campaign_id=campaign_id,
        post_id=post_id,
        expires_at=expires_at,
    )
    db.add(link)
    await db.flush()
    return link


async def code_taken(db: AsyncSession, code: str) -> bool:
    # Codes are matched without regard to case so /l/Sale and /l/sale cannot both exist.
    return bool(
        await db.scalar(select(ShortLink.id).where(func.lower(ShortLink.code) == code.lower()))
    )


async def shorten_in_text(
    db: AsyncSession,
    brand: Brand,
    text: str,
    *,
    source: str,
    campaign: str | None = None,
    campaign_id: int | None = None,
    created: list[ShortLink] | None = None,
) -> str:
    """Replace every external URL in `text` with a UTM-tagged tracked short link. New links are
    appended to `created` so the caller can tie them to the post once it has an id."""
    base = get_settings().base_url.rstrip("/")
    out, last = [], 0
    for m in URL_RE.finditer(text):
        url = m.group()
        if url.startswith(base):
            continue
        tagged = add_utm(
            url,
            source=source,
            medium="social",
            campaign=campaign or brand.utm_defaults.get("campaign"),
        )
        link = await create_short_link(db, brand, tagged, campaign_id=campaign_id)
        if created is not None:
            created.append(link)
        out += [text[last : m.start()], short_url(link)]
        last = m.end()
    out.append(text[last:])
    return "".join(out)
