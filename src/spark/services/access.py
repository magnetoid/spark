"""Who may see and do what on a brand.

Workspace owners (`User.role == owner`) see every brand as owners. Everyone else sees the
brands they are a member of, with the membership's role: editor, viewer or client (a client
reads and approves, nothing else).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, BrandMember, Role, User

EDIT_ROLES = ("owner", "editor")
APPROVE_ROLES = ("owner", "client")


def can_edit(role: str | None) -> bool:
    return role in EDIT_ROLES


def can_approve(role: str | None) -> bool:
    return role in APPROVE_ROLES


def can_manage(role: str | None) -> bool:
    return role == "owner"


async def roles_for(db: AsyncSession, user: User) -> dict[int, str]:
    """{brand_id: role} for every brand the user may see."""
    if user.role in (Role.owner, Role.agent):
        ids = (await db.execute(select(Brand.id))).scalars().all()
        return dict.fromkeys(ids, "owner" if user.role == Role.owner else "viewer")
    rows = (await db.execute(select(BrandMember.brand_id, BrandMember.role).where(BrandMember.user_id == user.id))).all()
    return {bid: role for bid, role in rows}


async def role_for(db: AsyncSession, user: User, brand_id: int) -> str | None:
    if user.role == Role.owner:
        return "owner"
    if user.role == Role.agent:
        return "viewer"
    return await db.scalar(select(BrandMember.role).where(BrandMember.user_id == user.id, BrandMember.brand_id == brand_id))


async def visible_brands(db: AsyncSession, user: User) -> list[tuple[Brand, str]]:
    roles = await roles_for(db, user)
    if not roles:
        return []
    brands = (await db.execute(select(Brand).where(Brand.id.in_(roles)).order_by(Brand.name))).scalars().all()
    return [(b, roles[b.id]) for b in brands]


async def add_member(db: AsyncSession, brand: Brand, user: User, role: str) -> BrandMember:
    m = BrandMember(brand_id=brand.id, user_id=user.id, role=role)
    db.add(m)
    await db.flush()
    return m
