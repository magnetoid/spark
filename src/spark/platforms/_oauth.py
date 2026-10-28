"""Small OAuth2 helpers shared by adapters."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from spark.platforms.base import PlatformError
from spark.security import token


def pkce_pair() -> tuple[str, str]:
    verifier = token(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


def build_url(base: str, params: dict) -> str:
    return f"{base}?{urlencode({k: v for k, v in params.items() if v is not None})}"


def basic_auth(client_id: str, client_secret: str) -> str:
    return "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


def expires_at(seconds: int | None) -> datetime | None:
    if not seconds:
        return None
    return datetime.now(UTC) + timedelta(seconds=int(seconds))


async def token_request(
    http: httpx.AsyncClient, url: str, data: dict, headers: dict | None = None
) -> dict:
    resp = await http.post(url, data=data, headers=headers or {})
    if resp.status_code >= 400:
        raise PlatformError(f"Token exchange failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()
