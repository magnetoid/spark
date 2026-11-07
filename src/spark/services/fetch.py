"""Fetch the readable text of a public web page (for "write a post about this URL").

Only http(s) URLs whose host resolves to a public address are fetched, and every redirect
hop is checked the same way, so a crafted URL cannot make the server read its own
services (metadata endpoints, Redis, the database) and hand the text to the AI.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit

import httpx

MAX_HOPS = 5
MAX_CHARS = 20000
BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


def _public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
                or addr.is_reserved or addr.is_unspecified or
                (addr.version == 6 and addr.ipv4_mapped is not None and not _public_ip(str(addr.ipv4_mapped))))


def is_public_url(url: str) -> bool:
    """True when `url` is http(s) and its host name resolves only to public addresses."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith((".localhost", ".internal", ".local")):
        return False
    try:
        return _public_ip(host)  # a literal address
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(infos) and all(_public_ip(info[4][0]) for info in infos)


def _readable(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()[:MAX_CHARS]


async def fetch_page_text(url: str, http: httpx.AsyncClient | None = None) -> str | None:
    """Readable text of a public page, or None when it is not public or not reachable."""
    if not is_public_url(url):
        return None
    own = http is None
    http = http or httpx.AsyncClient(timeout=15, follow_redirects=False)
    try:
        for _ in range(MAX_HOPS):
            resp = await http.get(url, headers={"User-Agent": "Spark/1.0 (+https://github.com/magnetoid/spark)"},
                                  follow_redirects=False)
            if resp.is_redirect:
                url = str(resp.next_request.url) if resp.next_request else resp.headers.get("location", "")
                if not is_public_url(url):
                    return None
                continue
            if resp.status_code >= 400:
                return None
            return _readable(resp.text)
        return None
    except httpx.HTTPError:
        return None
    finally:
        if own:
            await http.aclose()
