"""Small text helpers shared by the API and services."""

from __future__ import annotations

import re

from spark.security import token


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or token(4).lower()


def parse_hashtags(raw: str | list[str]) -> list[str]:
    """Distinct tags without '#', first spelling wins, at most 30."""
    items = raw if isinstance(raw, list) else raw.replace(",", " ").split()
    out, seen = [], set()
    for t in items:
        t = str(t).strip().lstrip("#")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t[:50])
    return out[:30]
