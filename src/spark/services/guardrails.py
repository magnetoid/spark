"""Brand guardrails: phrases a brand never says, topics it avoids, keywords it wants found for.

`never_say` hits are problems (the post stays a draft); the rest are warnings the composer shows
but does not enforce. The same config goes to the agent in every run.
"""

from __future__ import annotations

import re

from spark.models import Brand

DEFAULT_CONFIG: dict = {"never_say": [], "avoid_topics": [], "keywords": [], "auto_schedule": False}


def config(brand: Brand) -> dict:
    return {**DEFAULT_CONFIG, **(brand.agent_config or {})}


def _hits(text: str, phrases: list[str]) -> list[str]:
    low = text.lower()
    return [
        p for p in phrases if p and re.search(r"(?<!\w)" + re.escape(p.lower()) + r"(?!\w)", low)
    ]


def check(brand: Brand, text: str) -> tuple[list[str], list[str]]:
    """(problems, warnings) for one text in this brand."""
    cfg = config(brand)
    problems = [f'Avoid "{p}": {brand.name} never says it' for p in _hits(text, cfg["never_say"])]
    warnings = [
        f'Touches "{t}", a topic {brand.name} avoids' for t in _hits(text, cfg["avoid_topics"])
    ]
    keywords = [k for k in cfg["keywords"] if k]
    if keywords and text.strip() and not _hits(text, keywords):
        warnings.append(
            "None of the brand's keywords appear ("
            + ", ".join(keywords[:5])
            + ("…" if len(keywords) > 5 else "")
            + ")"
        )
    return problems, warnings


def prompt_block(brand: Brand) -> str:
    """The guardrails as a paragraph for AI prompts."""
    cfg = config(brand)
    parts = []
    if cfg["never_say"]:
        parts.append("Never use these words or phrases: " + ", ".join(cfg["never_say"]))
    if cfg["avoid_topics"]:
        parts.append("Avoid these topics: " + ", ".join(cfg["avoid_topics"]))
    if cfg["keywords"]:
        parts.append(
            "Where it reads naturally, use these keywords (people search for them): "
            + ", ".join(cfg["keywords"])
        )
    return "\n".join(parts)
