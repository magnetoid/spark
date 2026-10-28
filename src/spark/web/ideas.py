"""Ideas board — Buffer's "Create" space: a kanban of content ideas with tags that
turn into posts when they're ready."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.db import get_db
from spark.models import Brand, Idea, Post, SocialAccount, User
from spark.services.ai import AIUnavailable, ContentAI
from spark.web.deps import current_user, editor, flash, render, require_brand, templates

router = APIRouter()
COLUMNS = (("idea", "Ideas"), ("drafting", "Drafting"), ("ready", "Ready"), ("done", "Done"))
TAG_COLORS = ("#2E5BE8", "#1E8A5A", "#C73A33", "#F2A516", "#7C3AED", "#0891B2", "#DB2777", "#65A30D")


def parse_tags(raw: str) -> list[str]:
    seen, out = set(), []
    for t in raw.replace(";", ",").split(","):
        t = t.strip().lstrip("#").lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t[:30])
    return out[:8]


def tag_color(tag: str) -> str:
    return TAG_COLORS[sum(map(ord, tag)) % len(TAG_COLORS)]


async def _idea(db: AsyncSession, brand: Brand, idea_id: int) -> Idea:
    idea = await db.get(Idea, idea_id)
    if not idea or idea.brand_id != brand.id:
        raise HTTPException(404)
    return idea


async def _board_context(db: AsyncSession, brand: Brand, tag: str | None) -> dict:
    ideas = (await db.execute(
        select(Idea).where(Idea.brand_id == brand.id).order_by(Idea.position, Idea.id.desc())
    )).scalars().all()
    all_tags = sorted({t for i in ideas for t in (i.tags or [])})
    if tag:
        ideas = [i for i in ideas if tag in (i.tags or [])]
    columns = [(key, label, [i for i in ideas if i.status == key]) for key, label in COLUMNS]
    return {"columns": columns, "all_tags": all_tags, "tag": tag, "tag_color": tag_color,
            "ai_enabled": bool(get_settings().anthropic_api_key), "total": len(ideas)}


@router.get("/ideas/board")
async def board_partial(request: Request, tag: str | None = None, db: AsyncSession = Depends(get_db),
                        user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    ctx = await _board_context(db, brand, tag)
    return templates.TemplateResponse(request, "partials/ideas_board.html", {"user": user, "brand": brand, **ctx})


@router.get("/ideas")
async def board(request: Request, tag: str | None = None, db: AsyncSession = Depends(get_db),
                user: User = Depends(current_user), brand: Brand = Depends(require_brand)):
    ctx = await _board_context(db, brand, tag)
    return await render(request, "ideas.html", db, user, brand, **ctx)


@router.post("/ideas")
async def create(request: Request, title: str = Form(...), body: str = Form(""), tags: str = Form(""),
                 source_url: str = Form(""), status: str = Form("idea"),
                 db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                 brand: Brand = Depends(require_brand)):
    status = status if status in Idea.STATUSES else "idea"
    pos = (await db.scalar(select(func.min(Idea.position)).where(Idea.brand_id == brand.id))) or 0
    db.add(Idea(brand_id=brand.id, author_id=user.id, title=title.strip()[:200], body=body.strip() or None,
                tags=parse_tags(tags), source_url=source_url.strip() or None, status=status, position=pos - 1))
    await db.commit()
    return RedirectResponse("/ideas", 303)


@router.post("/ideas/{idea_id}")
async def update(idea_id: int, request: Request, title: str = Form(...), body: str = Form(""),
                 tags: str = Form(""), db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                 brand: Brand = Depends(require_brand)):
    idea = await _idea(db, brand, idea_id)
    idea.title, idea.body, idea.tags = title.strip()[:200], body.strip() or None, parse_tags(tags)
    await db.commit()
    return RedirectResponse("/ideas", 303)


@router.post("/ideas/{idea_id}/move")
async def move(idea_id: int, request: Request, status: str = Form(...), position: int = Form(0),
               db: AsyncSession = Depends(get_db), user: User = Depends(editor),
               brand: Brand = Depends(require_brand)):
    """Drag & drop between columns (JSON) or the arrow buttons (redirect)."""
    idea = await _idea(db, brand, idea_id)
    if status not in Idea.STATUSES:
        raise HTTPException(400, "Unknown column")
    idea.status, idea.position = status, position
    await db.commit()
    if request.headers.get("accept", "").startswith("application/json") or request.headers.get("HX-Request"):
        return JSONResponse({"ok": True})
    return RedirectResponse("/ideas", 303)


@router.post("/ideas/{idea_id}/delete")
async def delete(idea_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(editor),
                 brand: Brand = Depends(require_brand)):
    idea = await _idea(db, brand, idea_id)
    await db.delete(idea)
    await db.commit()
    return RedirectResponse("/ideas", 303)


@router.post("/ideas/{idea_id}/to-post")
async def to_post(idea_id: int, request: Request, db: AsyncSession = Depends(get_db),
                  user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    """Turn an idea into a draft post and open it in the composer."""
    idea = await _idea(db, brand, idea_id)
    if idea.post_id and await db.get(Post, idea.post_id):
        return RedirectResponse(f"/posts/{idea.post_id}/edit", 303)
    content = idea.body or idea.title
    post = Post(brand_id=brand.id, author_id=user.id, content=content, link=idea.source_url,
                media_ids=list(idea.media_ids or []), source="idea", notes=f"From idea: {idea.title}")
    post.targets = []
    db.add(post)
    await db.flush()
    idea.post_id = post.id
    if idea.status in ("idea", "drafting"):
        idea.status = "ready"
    await db.commit()
    flash(request, "Draft created from your idea — pick channels and schedule it")
    return RedirectResponse(f"/posts/{post.id}/edit", 303)


@router.post("/ideas/{idea_id}/ai")
async def ai_draft(idea_id: int, request: Request, db: AsyncSession = Depends(get_db),
                   user: User = Depends(editor), brand: Brand = Depends(require_brand)):
    """Expand a one-line idea into a post with the brand voice."""
    idea = await _idea(db, brand, idea_id)
    platforms = sorted({a.platform for a in (await db.execute(
        select(SocialAccount).where(SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True))
    )).scalars().all()}) or ["linkedin"]
    try:
        drafts = await ContentAI().generate(
            brand, f"{idea.title}\n\n{idea.body or ''}".strip(), platforms[:1], link=idea.source_url)
    except AIUnavailable as e:
        flash(request, str(e), "error")
        return RedirectResponse("/ideas", 303)
    if drafts:
        idea.body = drafts[0].text
        if idea.status == "idea":
            idea.status = "drafting"
        await db.commit()
        flash(request, "Draft written — review it on the card")
    return RedirectResponse("/ideas", 303)
