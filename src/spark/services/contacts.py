"""Contacts and lists for email campaigns: add, import from CSV, export."""

from __future__ import annotations

import csv
import io

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Contact, ContactList
from spark.security import token


async def lists_for(db: AsyncSession, brand: Brand, ids: list[int]) -> list[ContactList]:
    if not ids:
        return []
    return (await db.execute(select(ContactList).where(ContactList.id.in_(ids), ContactList.brand_id == brand.id))).scalars().all()


async def upsert(db: AsyncSession, brand: Brand, email: str, first: str = "", last: str = "",
                 source: str = "manual", lists: list[ContactList] | None = None) -> Contact | None:
    """Create or refresh a contact by email; None when the email is not an address."""
    email = (email or "").strip().lower()
    if "@" not in email or " " in email:
        return None
    c = await db.scalar(select(Contact).where(Contact.brand_id == brand.id, Contact.email == email))
    if c is None:
        c = Contact(brand_id=brand.id, email=email, source=source, unsubscribe_token=token(16), lists=[])
        db.add(c)
        await db.flush()
    c.first_name = (first or "").strip() or c.first_name
    c.last_name = (last or "").strip() or c.last_name
    for lst in lists or []:
        if lst not in c.lists:
            c.lists.append(lst)
    return c


async def import_csv(db: AsyncSession, brand: Brand, data: bytes, lists: list[ContactList]) -> int:
    """CSV with an `email` column; optional first_name/last_name (or name). Returns how many were kept."""
    text = data.decode("utf-8-sig", errors="replace")
    n = 0
    for row in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
        email = row.get("email") or row.get("e-mail") or ""
        first = row.get("first_name") or row.get("firstname") or ""
        last = row.get("last_name") or row.get("lastname") or ""
        if not first and row.get("name"):
            first, _, last = row["name"].partition(" ")
        if await upsert(db, brand, email, first, last, "import", lists):
            n += 1
    await db.commit()
    return n


async def export_csv(db: AsyncSession, brand: Brand) -> str:
    rows = (await db.execute(select(Contact).where(Contact.brand_id == brand.id).order_by(Contact.id))).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "first_name", "last_name", "subscribed", "source", "lists"])
    for c in rows:
        w.writerow([c.email, c.first_name or "", c.last_name or "", c.subscribed, c.source, ";".join(lst.name for lst in c.lists)])
    return buf.getvalue()


async def search(db: AsyncSession, brand: Brand, q: str = "", list_id: int | None = None, limit: int = 200,
                 offset: int = 0) -> tuple[list[Contact], int, int]:
    stmt = select(Contact).where(Contact.brand_id == brand.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Contact.email).like(like) | func.lower(Contact.first_name).like(like)
                          | func.lower(Contact.last_name).like(like))
    if list_id:
        stmt = stmt.where(Contact.lists.any(ContactList.id == list_id))
    rows = (await db.execute(stmt.order_by(Contact.id.desc()).limit(limit).offset(offset))).scalars().all()
    total = await db.scalar(select(func.count(Contact.id)).where(Contact.brand_id == brand.id)) or 0
    subscribed = await db.scalar(select(func.count(Contact.id)).where(Contact.brand_id == brand.id, Contact.subscribed.is_(True))) or 0
    return rows, total, subscribed
