"""UTM tagging and short links."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import Brand, ShortLink
from spark.security import short_code

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def add_utm(url: str, **params: str | None) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value:
            query.setdefault(f"utm_{key}", value)
    return urlunsplit(parts._replace(query=urlencode(query)))


def short_url(link: ShortLink) -> str:
    return f"{get_settings().base_url.rstrip('/')}/l/{link.code}"


async def create_short_link(
    db: AsyncSession,
    brand: Brand,
    destination: str,
    *,
    title: str | None = None,
    campaign_id: int | None = None,
) -> ShortLink:
    while True:
        code = short_code()
        if not await db.scalar(select(ShortLink.id).where(ShortLink.code == code)):
            break
    link = ShortLink(
        brand_id=brand.id, code=code, destination=destination, title=title, campaign_id=campaign_id
    )
    db.add(link)
    await db.flush()
    return link


async def shorten_in_text(
    db: AsyncSession,
    brand: Brand,
    text: str,
    *,
    source: str,
    campaign: str | None = None,
    campaign_id: int | None = None,
) -> str:
    """Replace every external URL in `text` with a UTM-tagged tracked short link."""
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
        out += [text[last : m.start()], short_url(link)]
        last = m.end()
    out.append(text[last:])
    return "".join(out)
