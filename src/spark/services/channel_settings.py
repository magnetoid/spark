"""Per-channel settings that publishing reads from `SocialAccount.extra`: the Pinterest board,
the subreddit, and who can see TikTok and YouTube posts. Only these keys can be changed."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from spark.models import SocialAccount

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SettingField:
    key: str
    label: str
    kind: str  # choice | text
    help: str = ""
    options: tuple[tuple[str, str], ...] = ()  # (value, label)
    default: str | None = None
    pattern: str | None = None  # for text values


FIELDS: dict[str, tuple[SettingField, ...]] = {
    "tiktok": (
        SettingField(
            "privacy_level",
            "Who can see posts",
            "choice",
            "TikTok asks for this on every post.",
            (
                ("PUBLIC_TO_EVERYONE", "Everyone"),
                ("MUTUAL_FOLLOW_FRIENDS", "Friends"),
                ("FOLLOWER_OF_CREATOR", "Followers"),
                ("SELF_ONLY", "Only me"),
            ),
            "PUBLIC_TO_EVERYONE",
        ),
    ),
    "youtube": (
        SettingField(
            "privacy_status",
            "Who can see videos",
            "choice",
            "",
            (("public", "Public"), ("unlisted", "Unlisted"), ("private", "Private")),
            "public",
        ),
    ),
    "pinterest": (
        SettingField(
            "board_id",
            "Board",
            "choice",
            "Pins go to this board. Without one Pinterest picks a board itself.",
            pattern=r"^[0-9A-Za-z_-]{1,64}$",
        ),
    ),
    "reddit": (
        SettingField(
            "subreddit",
            "Subreddit",
            "text",
            "Posts go to this community, for example SmallBusiness.",
            pattern=r"^[A-Za-z0-9_]{2,21}$",
        ),
    ),
}


class InvalidSetting(ValueError):
    pass


@dataclass
class FieldView:
    field: SettingField
    options: list[tuple[str, str]] = field(default_factory=list)


def fields_for(acc: SocialAccount) -> tuple[SettingField, ...]:
    return FIELDS.get(acc.platform, ())


def values(acc: SocialAccount) -> dict[str, str]:
    extra = acc.extra or {}
    return {f.key: str(extra[f.key]) for f in fields_for(acc) if extra.get(f.key)}


def _clean(f: SettingField, value) -> str:
    v = str(value).strip()
    if f.key == "subreddit":
        v = re.sub(r"^/?r/", "", v)
    if f.options and v not in {o for o, _ in f.options}:
        raise InvalidSetting(f"{f.label}: choose one of {', '.join(o for o, _ in f.options)}")
    if f.pattern and not re.fullmatch(f.pattern, v):
        raise InvalidSetting(f"{f.label}: “{v[:40]}” is not a valid value")
    return v


def update(acc: SocialAccount, changes: dict) -> dict[str, str]:
    """Apply `changes` (None removes a value). Raises InvalidSetting for unknown keys or values."""
    allowed = {f.key: f for f in fields_for(acc)}
    extra = dict(acc.extra or {})
    for key, value in changes.items():
        f = allowed.get(key)
        if f is None:
            raise InvalidSetting(f"{acc.platform} channels have no setting “{key}”")
        if value is None or str(value).strip() == "":
            extra.pop(key, None)
        else:
            extra[key] = _clean(f, value)
    acc.extra = extra
    return values(acc)


async def choices(acc: SocialAccount) -> list[FieldView]:
    """The fields with their options; Pinterest boards are read from Zernio when it can answer."""
    out = []
    for f in fields_for(acc):
        opts = list(f.options)
        if f.key == "board_id" and acc.provider == "zernio":
            from spark.platforms.zernio import ZernioAdapter

            try:
                boards = await ZernioAdapter().pinterest_boards(acc.external_id)
                opts = [
                    (str(b["id"]), b.get("name") or str(b["id"])) for b in boards if b.get("id")
                ]
            except Exception:
                log.warning(
                    "Could not list Pinterest boards for %s", acc.external_id, exc_info=True
                )
        out.append(FieldView(f, opts))
    return out
