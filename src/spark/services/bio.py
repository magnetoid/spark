"""The link-in-bio page. Every link is a tracked short link so clicks show per link."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import BioPage, Brand, ShortLink
from spark.services.links import add_utm, create_short_link


async def get_or_create(db: AsyncSession, brand: Brand) -> BioPage:
    page = await db.scalar(select(BioPage).where(BioPage.brand_id == brand.id))
    if page is None:
        page = BioPage(brand_id=brand.id, title=brand.name, links=[])
        db.add(page)
        await db.commit()
    return page


async def links_with_clicks(db: AsyncSession, page: BioPage) -> list[dict]:
    codes = [l.get("code") for l in (page.links or []) if l.get("code")]
    clicks: dict[str, int] = {}
    if codes:
        clicks = {
            l.code: l.clicks
            for l in (
                await db.execute(select(ShortLink).where(ShortLink.code.in_(codes)))
            ).scalars()
        }
    return [{**l, "clicks": clicks.get(l.get("code"), 0)} for l in (page.links or [])]


async def set_links(db: AsyncSession, brand: Brand, page: BioPage, items: list[dict]) -> None:
    """Replace the page's links. A link whose URL is unchanged keeps its code (and click history)."""
    codes = [str(i.get("code") or "") for i in items]
    existing = {
        l.code: l
        for l in (
            await db.execute(
                select(ShortLink).where(
                    ShortLink.brand_id == brand.id, ShortLink.code.in_([c for c in codes if c])
                )
            )
        ).scalars()
    }
    links = []
    for item in items:
        label, url, code = (
            str(item.get("label") or "").strip(),
            str(item.get("url") or "").strip(),
            str(item.get("code") or "").strip(),
        )
        if not label or not url.startswith(("http://", "https://")):
            continue
        tagged = add_utm(url, source="bio", medium="bio")
        link = existing.get(code)
        if link is None or link.destination != tagged:
            link = await create_short_link(db, brand, tagged, title=label)
        else:
            link.title = label
        links.append({"label": label, "url": url, "code": link.code})
    page.links = links
