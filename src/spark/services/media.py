"""The media library on local disk: upload, describe, delete."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import Brand, Media
from spark.security import token

ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4", "video/quicktime"}


@dataclass
class Upload:
    name: str
    content_type: str
    data: bytes


async def list_media(db: AsyncSession, brand: Brand, limit: int = 500) -> list[Media]:
    return (await db.execute(select(Media).where(Media.brand_id == brand.id)
                             .order_by(Media.id.desc()).limit(limit))).scalars().all()


async def save_uploads(db: AsyncSession, brand: Brand, uploads: list[Upload]) -> tuple[list[Media], list[dict]]:
    """Store accepted files; returns (saved, rejected [{name, reason}])."""
    s = get_settings()
    saved, rejected = [], []
    for u in uploads:
        if u.content_type not in ALLOWED_MEDIA:
            rejected.append({"name": u.name, "reason": f"unsupported type {u.content_type}"})
            continue
        if len(u.data) > s.max_upload_mb * 1024 * 1024:
            rejected.append({"name": u.name, "reason": f"larger than {s.max_upload_mb} MB"})
            continue
        ext = Path(u.name or "").suffix.lower()[:8] or ".bin"
        rel = f"{brand.id}/{token(12)}{ext}"
        dest = s.media_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(u.data)
        m = Media(brand_id=brand.id, filename=u.name or rel, path=rel, content_type=u.content_type, size=len(u.data))
        db.add(m)
        saved.append(m)
    await db.commit()
    return saved, rejected


async def delete_media(db: AsyncSession, m: Media) -> None:
    (get_settings().media_dir / m.path).unlink(missing_ok=True)
    await db.delete(m)
    await db.commit()
