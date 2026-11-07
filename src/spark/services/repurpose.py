"""Repurpose one source (a page, pasted text, a transcript) into a series of drafts.

With Janus connected the source goes into an agent run (`kind="repurpose"`); otherwise a
direct Claude call writes one draft per channel. Transcripts (.srt, .vtt) lose their timing.
"""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, SocialAccount, User
from spark.services import ai as ai_svc
from spark.services import posts as svc
from spark.services.fetch import fetch_page_text

MIN_CHARS = 80
MAX_CHARS = 40_000
_TIMING = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->.*$")
_INDEX = re.compile(r"^\s*\d+\s*$")
_TAG = re.compile(r"<[^>]+>")


def to_text(name: str, content: str) -> str:
    """Plain text of a .txt, .srt or .vtt file: cues joined with spaces, markup and timing dropped."""
    ext = (name or "").lower().rsplit(".", 1)[-1] if "." in (name or "") else ""
    if ext not in ("srt", "vtt"):
        return " ".join(line.strip() for line in content.splitlines() if line.strip())
    out: list[str] = []
    for line in content.splitlines():
        s = line.strip()
        if (
            not s
            or s.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION"))
            or _TIMING.match(s)
            or _INDEX.match(s)
        ):
            continue
        s = _TAG.sub("", s).strip()
        if s:
            out.append(s)
    return " ".join(out)


class SourceError(Exception):
    pass


async def resolve_source(
    *, source_text: str | None, source_url: str | None, source_name: str | None
) -> tuple[str, str | None]:
    """(text, link) for the request: pasted/uploaded text wins; a URL is fetched (public hosts only)."""
    text = ""
    if source_text:
        text = to_text(source_name or "", source_text)
    elif source_url:
        text = (await fetch_page_text(source_url)) or ""
        if not text:
            raise SourceError("Could not read that page. Paste the text instead.")
    text = text.strip()
    if len(text) < MIN_CHARS:
        raise SourceError(f"That source is too short to repurpose (under {MIN_CHARS} characters).")
    return text[:MAX_CHARS], source_url or None


def task_text(text: str, link: str | None, accounts: list[SocialAccount], notes: str | None) -> str:
    chans = ", ".join(f"{a.handle} ({a.platform})" for a in accounts) or "every channel"
    return (
        f"Turn the source below into a series of posts for {chans}: one post per channel at least, more if the material "
        f"carries several distinct ideas. Each post stands alone, in the brand's voice, and fits the network. "
        f"Fill `channels` for each post and leave `when` null."
        + (f"\n\nNotes from the team: {notes}" if notes else "")
        + (f"\n\nSource link (added to the posts automatically): {link}" if link else "")
        + f"\n\n<source>\n{text}\n</source>"
    )


async def direct(
    db: AsyncSession,
    brand: Brand,
    user: User,
    text: str,
    link: str | None,
    accounts: list[SocialAccount],
    notes: str | None,
) -> list[int]:
    """Without Janus: one draft per channel from a direct Claude call."""
    ai = ai_svc.ContentAI()
    platforms = sorted({a.platform for a in accounts})
    drafts = await ai.generate(
        brand,
        notes or "Repurpose this material into a post for each platform.",
        platforms,
        source_text=text,
        link=link,
        variants=1,
    )
    ids: list[int] = []
    for d in drafts:
        targets = [svc.TargetInput(account_id=a.id) for a in accounts if a.platform == d.platform]
        if not targets:
            continue
        body = d.text + (("\n\n" + " ".join(d.hashtags)) if d.hashtags else "")
        post = await svc.save_post(
            db,
            brand,
            user,
            None,
            content=body,
            link=link,
            media_ids=[],
            campaign_id=None,
            notes=None,
            source="repurpose",
            targets=targets,
        )
        ids.append(post.id)
    await db.commit()
    return ids
