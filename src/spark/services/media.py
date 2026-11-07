"""The media library on local disk: upload, describe, delete."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import Brand, Media
from spark.security import token
from spark.services.images import dimensions

ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4", "video/quicktime", "application/pdf"}
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "video/mp4": ".mp4",
              "video/quicktime": ".mov", "application/pdf": ".pdf"}
_IMAGE_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}


def sniff(data: bytes, declared: str) -> str | None:
    """The media type the bytes really are, when it agrees with the declared family; else None.
    Browsers would otherwise run an HTML file uploaded as image/png from the app's own origin."""
    if declared.startswith("image/"):
        try:
            import io

            from PIL import Image

            with Image.open(io.BytesIO(data)) as im:
                return _IMAGE_FORMATS.get(im.format or "")
        except Exception:
            return None
    if declared.startswith("video/"):
        head = data[:16]
        return declared if b"ftyp" in head or head.startswith(b"\x00\x00\x00") else None
    if declared == "application/pdf":
        return declared if data.startswith(b"%PDF") else None
    return None


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
        real = sniff(u.data, u.content_type)
        if real is None:
            kind = "an image" if u.content_type.startswith("image/") else "a video" if u.content_type.startswith("video/") else "a PDF"
            rejected.append({"name": u.name, "reason": f"not {kind}: the file's content does not match its type"})
            continue
        ext = EXTENSIONS[real]
        rel = f"{brand.id}/{token(12)}{ext}"
        dest = s.media_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(u.data)
        w, h = dimensions(u.data, real)
        m = Media(brand_id=brand.id, filename=u.name or rel, path=rel, content_type=real, size=len(u.data), width=w, height=h,
                  source="upload", tags=[])
        db.add(m)
        saved.append(m)
    await db.commit()
    return saved, rejected


async def delete_media(db: AsyncSession, m: Media) -> None:
    (get_settings().media_dir / m.path).unlink(missing_ok=True)
    await db.delete(m)
    await db.commit()
