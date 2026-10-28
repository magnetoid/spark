"""Small JSON endpoints for the client (command palette, later: live widgets)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.models import Brand, Campaign, Post, PostStatus, SocialAccount, User
from spark.web.deps import current_user, require_brand

router = APIRouter()

PAGES = [
    ("Overview", "/", "g o"), ("Ideas", "/ideas", "g i"), ("Queue", "/queue", "g q"),
    ("Calendar", "/calendar", "g c"), ("All posts", "/posts", "g p"), ("Campaigns", "/campaigns", ""),
    ("RSS feeds", "/feeds", ""), ("Inbox", "/inbox", "g n"), ("Analytics", "/analytics", "g a"),
    ("Links", "/links", ""), ("Bio page", "/bio", ""), ("Contacts", "/contacts", ""), ("Email", "/email", ""),
    ("Social accounts", "/accounts", ""), ("Media", "/media", ""), ("Brand & team", "/settings", "g s"),
]


ALLOWED_PREFS = {"onboarding_dismissed", "default_action", "shortcuts"}


@router.post("/me/prefs")
async def set_prefs(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Small per-user UI preferences (dismiss onboarding, default scheduling action, ...)."""
    body = await request.json()
    prefs = dict(user.prefs or {})
    for k, v in body.items():
        if k in ALLOWED_PREFS:
            prefs[k] = v
    user.prefs = prefs
    await db.commit()
    return prefs


@router.get("/api/palette")
async def palette(db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
                  brand: Brand = Depends(require_brand)):
    items = [{"label": "New post", "hint": "c", "action": "compose", "group": "Actions"}]
    if user.can_edit():
        items.append({"label": "Import accounts from Zernio", "hint": "", "href": "/accounts", "group": "Actions"})
    items += [{"label": label, "hint": hint, "href": href, "group": "Go to"} for label, href, hint in PAGES]
    accounts = (await db.execute(select(SocialAccount).where(
        SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True)))).scalars().all()
    items += [{"label": f"Queue · {a.handle}", "hint": a.platform, "href": f"/queue?account={a.id}",
               "group": "Channels"} for a in accounts]
    items += [{"label": f"Post to {a.handle}", "hint": a.platform, "action": "compose",
               "params": {"account": a.id}, "group": "Channels"} for a in accounts]
    campaigns = (await db.execute(select(Campaign).where(Campaign.brand_id == brand.id)
                                  .order_by(Campaign.id.desc()).limit(10))).scalars().all()
    items += [{"label": f"Campaign · {c.name}", "hint": "", "href": f"/calendar?campaign={c.id}",
               "group": "Campaigns"} for c in campaigns]
    recent = (await db.execute(select(Post).where(Post.brand_id == brand.id, Post.status != PostStatus.draft)
                               .order_by(Post.updated_at.desc()).limit(15))).scalars().all()
    items += [{"label": (p.content or "(no text)")[:80], "hint": p.status.value.replace("_", " "),
               "href": f"/posts/{p.id}/edit", "group": "Recent posts"} for p in recent]
    return items
