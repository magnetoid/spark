"""Items for the command palette: actions, pages, channels, campaigns, recent posts."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.schemas import PaletteItem
from spark.db import get_db
from spark.models import Campaign, Post, PostStatus, SocialAccount

router = APIRouter(tags=["palette"])
PAGES = [("Today", "/"), ("Publishing", "/publishing"), ("Calendar", "/publishing?view=calendar"), ("Inbox", "/inbox"),
         ("Ideas", "/ideas"), ("Library", "/library"), ("Analytics", "/analytics"), ("Campaigns", "/campaigns"),
         ("Links", "/links"), ("Audience", "/audience"), ("Channels", "/channels"), ("Settings", "/settings")]


@router.get("/brands/{brand_id}/palette", response_model=list[PaletteItem])
async def palette(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    items = [PaletteItem(label="New post", hint="c", action="compose", group="Actions")]
    items += [PaletteItem(label=label, to=to, group="Go to") for label, to in PAGES]
    accounts = (await db.execute(select(SocialAccount).where(SocialAccount.brand_id == ctx.brand.id, SocialAccount.is_active.is_(True)))).scalars().all()
    items += [PaletteItem(label=f"Queue · {a.handle}", hint=a.platform, to=f"/publishing?view=queue&account={a.id}", group="Channels") for a in accounts]
    if ctx.can_edit():
        items += [PaletteItem(label=f"Post to {a.handle}", hint=a.platform, action="compose", params={"account": a.id}, group="Channels") for a in accounts]
    campaigns = (await db.execute(select(Campaign).where(Campaign.brand_id == ctx.brand.id).order_by(Campaign.id.desc()).limit(10))).scalars().all()
    items += [PaletteItem(label=f"Campaign · {c.name}", to=f"/publishing?view=calendar&campaign={c.id}", group="Campaigns") for c in campaigns]
    recent = (await db.execute(select(Post).where(Post.brand_id == ctx.brand.id, Post.is_autosave.is_(False), Post.status != PostStatus.draft)
                               .order_by(Post.updated_at.desc()).limit(15))).scalars().all()
    items += [PaletteItem(label=(p.content or "(no text)")[:80], hint=p.status.value.replace("_", " "), action="edit", params={"post_id": p.id}, group="Recent posts") for p in recent]
    return items
