"""Pictures: measure uploads, crop to a network's ratio, generate with an image model, describe with Claude vision."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from pathlib import Path

import httpx
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import Brand, Media
from spark.security import token

log = logging.getLogger("spark.images")
Image.MAX_IMAGE_PIXELS = 40_000_000  # a decompression bomb would otherwise take hundreds of MB

RATIOS = {
    "1:1": (1, 1),
    "4:5": (4, 5),
    "9:16": (9, 16),
    "16:9": (16, 9),
    "2:3": (2, 3),
    "1.91:1": (191, 100),
}
SIZES = {"square": "1024x1024", "portrait": "1024x1536", "landscape": "1536x1024"}
# OpenAI retires image models on a schedule (developers.openai.com/api/docs/deprecations). The model
# is a setting, so nothing here pins one; a saved ID that OpenAI already shut down uses the default.
DEFAULT_MODEL = "gpt-image-2.6-flare"
RETIRED_MODELS = frozenset({"gpt-image-1", "dall-e-2", "dall-e-3"})


def model() -> str:
    m = (get_settings().image_model or "").strip()
    return DEFAULT_MODEL if not m or m in RETIRED_MODELS else m


class BadImage(Exception):
    """The bytes are not an image Pillow can read."""


class ImagesUnavailable(Exception):
    """No image provider configured. Settings → Connectors → Image generation."""


def configured() -> bool:
    return bool(get_settings().openai_api_key)


def dimensions(data: bytes, content_type: str) -> tuple[int | None, int | None]:
    if not content_type.startswith("image/"):
        return None, None
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.width, im.height
    except Exception:
        return None, None


def _store(brand: Brand, data: bytes, name: str, content_type: str, source: str, **extra) -> Media:
    s = get_settings()
    ext = Path(name).suffix.lower()[:8] or ".png"
    rel = f"{brand.id}/{token(12)}{ext}"
    dest = s.media_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    w, h = dimensions(data, content_type)
    return Media(
        brand_id=brand.id,
        filename=name,
        path=rel,
        content_type=content_type,
        size=len(data),
        width=w,
        height=h,
        source=source,
        **extra,
    )


def crop_bytes(data: bytes, ratio: str, x: float = 0.5, y: float = 0.5) -> tuple[bytes, int, int]:
    """Largest crop of the given ratio, centred at (x, y) in 0..1 of the image, as PNG."""
    rw, rh = RATIOS[ratio]
    with Image.open(io.BytesIO(data)) as im:
        im = (
            im.convert("RGBA")
            if im.mode in ("P", "LA")
            else im.convert("RGB")
            if im.mode != "RGBA"
            else im
        )
        W, H = im.size
        if W / H > rw / rh:
            ch, cw = H, int(round(H * rw / rh))
        else:
            cw, ch = W, int(round(W * rh / rw))
        left = min(max(int(round(W * x - cw / 2)), 0), W - cw)
        top = min(max(int(round(H * y - ch / 2)), 0), H - ch)
        out = im.crop((left, top, left + cw, top + ch))
        buf = io.BytesIO()
        out.save(buf, "PNG", optimize=True)
        return buf.getvalue(), cw, ch


async def crop(db: AsyncSession, brand: Brand, src: Media, ratio: str, x: float, y: float) -> Media:
    data = (get_settings().media_dir / src.path).read_bytes()
    try:
        out, w, h = await asyncio.to_thread(crop_bytes, data, ratio, x, y)
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise BadImage("That file is not an image Spark can crop") from e
    stem = Path(src.filename).stem
    m = _store(
        brand,
        out,
        f"{stem}-{ratio.replace(':', 'x')}.png",
        "image/png",
        "crop",
        alt_text=src.alt_text,
        tags=list(src.tags or []),
    )
    db.add(m)
    await db.commit()
    return m


async def generate(db: AsyncSession, brand: Brand, prompt: str, size: str = "square") -> Media:
    s = get_settings()
    if not s.openai_api_key:
        raise ImagesUnavailable(
            "Image generation is not set up. Add a key under Settings → Connectors → Image generation."
        )
    full = prompt.strip()
    if brand.voice_tone:
        full += f"\n\nBrand mood: {brand.voice_tone[:200]}"
    body = {
        "model": model(),
        "prompt": full[:4000],
        "size": SIZES.get(size, SIZES["square"]),
        "n": 1,
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            "https://api.openai.com/v1/images/generations",
            json=body,
            headers={"Authorization": f"Bearer {s.openai_api_key}"},
        )
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {}) or {}
            msg, code = err.get("message") or r.text[:200], err.get("code") or ""
        except Exception:
            msg, code = r.text[:200], ""
        if r.status_code == 404 or code == "model_not_found":
            raise ImagesUnavailable(
                f"OpenAI does not offer the image model {body['model']} (retired or misspelled). "
                "Pick a current one under Settings → Connectors → Image generation."
            )
        raise ImagesUnavailable(f"The image service answered {r.status_code}: {msg}")
    item = (r.json().get("data") or [{}])[0]
    if item.get("b64_json"):
        data = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        async with httpx.AsyncClient(timeout=60) as c:
            data = (await c.get(item["url"])).content
    else:
        raise ImagesUnavailable("The image service returned no picture")
    name = "-".join(prompt.lower().split()[:5])[:40] or "generated"
    m = _store(
        brand, data, f"{name}.png", "image/png", "generated", alt_text=None, tags=["generated"]
    )
    db.add(m)
    await db.commit()
    return m


async def test_connection() -> tuple[bool, str]:
    s = get_settings()
    if not s.openai_api_key:
        return False, "Add an API key first"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"https://api.openai.com/v1/models/{model()}",
            headers={"Authorization": f"Bearer {s.openai_api_key}"},
        )
    if r.status_code == 200:
        return True, f"OpenAI answered: {model()} is available"
    if r.status_code == 404:
        return (
            False,
            f"OpenAI does not offer {model()} (retired or misspelled). Change the model below.",
        )
    return False, f"OpenAI answered {r.status_code}: {r.text[:160]}"


VISION_MAX_PX = 1568


def _shrink(data: bytes, max_px: int = VISION_MAX_PX) -> bytes:
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85, optimize=True)
        return buf.getvalue()


async def for_vision(data: bytes, content_type: str) -> tuple[bytes, str]:
    """A copy small enough for the vision API: JPEG, longest side 1568px."""
    try:
        return await asyncio.to_thread(_shrink, data), "image/jpeg"
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise BadImage("That file is not an image Spark can describe") from e
