"""The Ideas board: capture, sort, and turn an idea into a draft post."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Idea, Post, SocialAccount, User
from spark.services.ai import AIUnavailable, ContentAI

COLUMNS = (("idea", "Ideas"), ("drafting", "Drafting"), ("ready", "Ready"), ("done", "Done"))


def parse_tags(raw: str | list[str]) -> list[str]:
    items = raw if isinstance(raw, list) else raw.replace(";", ",").split(",")
    seen, out = set(), []
    for t in items:
        t = str(t).strip().lstrip("#").lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t[:30])
    return out[:8]


async def list_ideas(db: AsyncSession, brand: Brand) -> list[Idea]:
    return (
        (
            await db.execute(
                select(Idea)
                .where(Idea.brand_id == brand.id)
                .order_by(Idea.position, Idea.id.desc())
            )
        )
        .scalars()
        .all()
    )


async def create(
    db: AsyncSession,
    brand: Brand,
    user: User,
    *,
    title: str,
    body: str | None = None,
    tags: list[str] | str = (),
    source_url: str | None = None,
    status: str = "idea",
) -> Idea:
    status = status if status in Idea.STATUSES else "idea"
    top = (await db.scalar(select(func.min(Idea.position)).where(Idea.brand_id == brand.id))) or 0
    idea = Idea(
        brand_id=brand.id,
        author_id=user.id,
        title=title.strip()[:200],
        body=(body or "").strip() or None,
        tags=parse_tags(tags),
        source_url=(source_url or "").strip() or None,
        status=status,
        position=top - 1,
    )
    db.add(idea)
    await db.commit()
    return idea


def update(
    idea: Idea,
    *,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | str | None = None,
    source_url: str | None = None,
) -> None:
    if title is not None:
        idea.title = title.strip()[:200] or idea.title
    if body is not None:
        idea.body = body.strip() or None
    if tags is not None:
        idea.tags = parse_tags(tags)
    if source_url is not None:
        idea.source_url = source_url.strip() or None


def move(idea: Idea, status: str, position: int) -> None:
    if status not in Idea.STATUSES:
        raise ValueError("Unknown column")
    idea.status, idea.position = status, position


async def to_post(db: AsyncSession, brand: Brand, user: User, idea: Idea) -> tuple[Post, bool]:
    """A draft post from the idea; (post, created). A second call returns the same post."""
    if idea.post_id:
        existing = await db.get(Post, idea.post_id)
        if existing and existing.brand_id == brand.id:
            return existing, False
    post = Post(
        brand_id=brand.id,
        author_id=user.id,
        content=idea.body or idea.title,
        link=idea.source_url,
        media_ids=list(idea.media_ids or []),
        source="idea",
        notes=f"From idea: {idea.title}",
    )
    post.targets = []
    db.add(post)
    await db.flush()
    idea.post_id = post.id
    if idea.status in ("idea", "drafting"):
        idea.status = "ready"
    await db.commit()
    await db.refresh(post, ["targets"])
    return post, True


async def ai_expand(db: AsyncSession, brand: Brand, idea: Idea) -> Idea:
    """Expand a one-line idea into a post in the brand voice (raises AIUnavailable)."""
    platforms = sorted(
        {
            a.platform
            for a in (
                await db.execute(
                    select(SocialAccount).where(
                        SocialAccount.brand_id == brand.id, SocialAccount.is_active.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        }
    ) or ["linkedin"]
    drafts = await ContentAI().generate(
        brand, f"{idea.title}\n\n{idea.body or ''}".strip(), platforms[:1], link=idea.source_url
    )
    if not drafts:
        raise AIUnavailable("The AI returned nothing")
    idea.body = drafts[0].text
    if idea.status == "idea":
        idea.status = "drafting"
    await db.commit()
    return idea
