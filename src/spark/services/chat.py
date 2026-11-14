"""Notifications to the team's chat: Slack (or Mattermost), Discord, Microsoft Teams and Telegram.

Every destination is a URL someone pasted into Settings → Connectors → Chat notifications, so
each one is checked to be a public address before Spark posts to it, redirects are not
followed, and errors never repeat the URL or the bot token (both are secrets).
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from spark.config import get_settings
from spark.services import fetch

log = logging.getLogger(__name__)
TIMEOUT = 10
TELEGRAM_API = "https://api.telegram.org"
WEBHOOKS = (  # name, setting
    ("Slack", "chat_slack_webhook"),
    ("Discord", "chat_discord_webhook"),
    ("Teams", "chat_teams_webhook"),
)


def destinations() -> list[str]:
    """Names of the destinations that are filled in, in the order messages go out."""
    s = get_settings()
    out = [name for name, setting in WEBHOOKS if getattr(s, setting)]
    if s.chat_telegram_token and s.chat_telegram_chat_id:
        out.append("Telegram")
    return out


def _slack(text: str, url: str | None, label: str) -> dict:
    # Slack reads <…> as links and mentions; escaped, a review that says <!channel> pings nobody
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return {"text": f"{safe}\n<{url}|{label}>" if url else safe}


def _discord(text: str, url: str | None, label: str) -> dict:
    tail = f"\n[{label}]({url})" if url else ""
    return {"content": text[: 2000 - len(tail)] + tail, "allowed_mentions": {"parse": []}}


def _teams(text: str, url: str | None, label: str) -> dict:
    card: dict = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [{"type": "TextBlock", "text": text, "wrap": True}],
    }
    if url:
        card["actions"] = [{"type": "Action.OpenUrl", "title": label, "url": url}]
    return {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
    }


def _telegram(text: str, url: str | None, label: str) -> dict:
    return {
        "chat_id": get_settings().chat_telegram_chat_id,
        "text": (f"{text}\n{label}: {url}" if url else text)[:4096],
        "disable_web_page_preview": True,
    }


SHAPES = {"Slack": _slack, "Discord": _discord, "Teams": _teams}


async def _post(
    http: httpx.AsyncClient, url: str, body: dict, check_public: bool = True
) -> str | None:
    """None when the destination took the message, otherwise a short reason without the URL."""
    if check_public and not await asyncio.to_thread(fetch.is_public_url, url):
        return "the address is not a public http(s) address"
    try:
        r = await http.post(url, json=body)
    except httpx.TimeoutException:
        return f"no answer in {TIMEOUT} seconds"
    except httpx.HTTPError as e:
        return f"could not connect ({type(e).__name__})"
    if 200 <= r.status_code < 300:
        return None
    detail = ""
    try:
        detail = str(r.json().get("description") or "")  # Telegram explains itself here
    except Exception:
        detail = r.text if len(r.text) < 120 else ""
    return f"answered {r.status_code}" + (f": {detail.strip()[:120]}" if detail.strip() else "")


async def send(
    text: str, url: str | None = None, label: str = "Open Spark"
) -> dict[str, str | None]:
    """Send one message to every destination. Returns {destination: None or why it failed}."""
    s = get_settings()
    names = destinations()
    if not names:
        return {}
    results: dict[str, str | None] = {}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as http:
        for name in names:
            if name == "Telegram":
                results[name] = await _post(
                    http,
                    f"{TELEGRAM_API}/bot{s.chat_telegram_token}/sendMessage",
                    _telegram(text, url, label),
                    check_public=False,
                )
            else:
                setting = dict(WEBHOOKS)[name]
                results[name] = await _post(
                    http, getattr(s, setting).strip(), SHAPES[name](text, url, label)
                )
            if results[name]:
                log.warning("Chat notification to %s failed: %s", name, results[name])
    return results
