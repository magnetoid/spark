"""Platform adapter contract.

Every social network implements `PlatformAdapter`. The publisher, OAuth flow,
composer validation and analytics only ever talk to this interface.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import httpx

from spark.config import get_settings

if TYPE_CHECKING:
    from spark.models import Media, SocialAccount


class PlatformError(Exception):
    """Publishing/API failure. `retryable=False` marks permanent failures."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class AuthExpired(PlatformError):
    def __init__(self, message: str = "Access token expired or revoked"):
        super().__init__(message, retryable=False)


@dataclass(frozen=True)
class Limits:
    max_chars: int
    max_media: int = 4
    supports_video: bool = True
    requires_media: bool = False
    image_types: tuple[str, ...] = ("image/jpeg", "image/png", "image/gif", "image/webp")
    video_types: tuple[str, ...] = ("video/mp4", "video/quicktime")


@dataclass
class PublishResult:
    remote_id: str
    url: str | None = None


@dataclass
class MetricsSnapshot:
    remote_id: str
    impressions: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    clicks: int = 0


@dataclass
class ConnectedAccount:
    external_id: str
    handle: str
    access_token: str
    display_name: str | None = None
    avatar_url: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None
    extra: dict = field(default_factory=dict)
    followers: int | None = None


@dataclass
class OAuthStart:
    url: str
    # State the callback needs (PKCE verifier etc.), stored in the user session
    session_data: dict = field(default_factory=dict)


@dataclass
class PublishPayload:
    text: str
    media: list[Media]
    link: str | None = None
    first_comment: str | None = None  # posted as the first reply after publishing, if supported

    def media_path(self, m: Media) -> Path:
        return get_settings().media_dir / m.path

    def media_url(self, m: Media) -> str:
        return f"{get_settings().base_url.rstrip('/')}{m.url}"


class PlatformAdapter(abc.ABC):
    name: ClassVar[str]
    label: ClassVar[str]
    limits: ClassVar[Limits]
    # "oauth" -> redirect flow; "credentials" -> form with fields below
    connect_mode: ClassVar[str] = "oauth"
    credential_fields: ClassVar[tuple[tuple[str, str], ...]] = ()
    docs_url: ClassVar[str] = ""

    def __init__(self, http: httpx.AsyncClient | None = None):
        self._http = http

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=60)
        return self._http

    # ---- configuration ------------------------------------------------
    def is_configured(self) -> bool:
        """True when the developer-app credentials for this platform are set."""
        return True

    def redirect_uri(self) -> str:
        return f"{get_settings().base_url.rstrip('/')}/accounts/callback/{self.name}"

    # ---- connect --------------------------------------------------------
    def oauth_start(self, state: str) -> OAuthStart:
        raise NotImplementedError

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        raise NotImplementedError

    async def connect_with_credentials(self, data: dict[str, str]) -> list[ConnectedAccount]:
        raise NotImplementedError

    async def refresh(self, account: SocialAccount) -> bool:
        """Refresh tokens in place. Return True if refreshed."""
        return False

    # ---- content --------------------------------------------------------
    def validate(self, payload: PublishPayload) -> list[str]:
        problems: list[str] = []
        lim = self.limits
        if len(payload.text) > lim.max_chars:
            problems.append(f"{self.label}: {len(payload.text)}/{lim.max_chars} characters")
        if len(payload.media) > lim.max_media:
            problems.append(f"{self.label}: max {lim.max_media} media items")
        if lim.requires_media and not payload.media:
            problems.append(f"{self.label}: requires an image or video")
        for m in payload.media:
            allowed = lim.image_types + (lim.video_types if lim.supports_video else ())
            if m.content_type not in allowed:
                problems.append(f"{self.label}: {m.content_type} not supported")
        if sum(1 for m in payload.media if m.is_video) > 1:
            problems.append(f"{self.label}: only one video per post")
        return problems

    @abc.abstractmethod
    async def publish(self, account: SocialAccount, payload: PublishPayload) -> PublishResult: ...

    async def fetch_metrics(
        self, account: SocialAccount, remote_ids: list[str]
    ) -> list[MetricsSnapshot]:
        return []

    # ---- helpers --------------------------------------------------------
    @staticmethod
    def check(resp: httpx.Response) -> httpx.Response:
        if resp.status_code in (401, 403):
            raise AuthExpired(f"{resp.status_code}: {resp.text[:300]}")
        if resp.status_code == 429 or resp.status_code >= 500:
            raise PlatformError(f"{resp.status_code}: {resp.text[:300]}", retryable=True)
        if resp.status_code >= 400:
            raise PlatformError(f"{resp.status_code}: {resp.text[:300]}", retryable=False)
        return resp


_REGISTRY: dict[str, type[PlatformAdapter]] = {}


def register(cls: type[PlatformAdapter]) -> type[PlatformAdapter]:
    _REGISTRY[cls.name] = cls
    return cls


def registry() -> dict[str, type[PlatformAdapter]]:
    import spark.platforms  # noqa: F401  (populates registry)

    return _REGISTRY


def get_adapter(
    name: str, http: httpx.AsyncClient | None = None, provider: str = "direct"
) -> PlatformAdapter:
    """Adapter for a platform.

    `provider="zernio"` routes through the Zernio API regardless of platform;
    `SPARK_FORCE_DRY_RUN` swaps in the fake adapter while keeping the platform's limits.
    """
    from spark.platforms.zernio import ZERNIO_PLATFORMS, ZernioAdapter

    reg = registry()
    if name not in reg and name not in ZERNIO_PLATFORMS:
        raise KeyError(f"Unknown platform: {name}")
    if get_settings().force_dry_run:
        from spark.platforms.dry_run import DryRunAdapter

        return DryRunAdapter(http, impersonate=reg.get(name) or ZernioAdapter.for_platform(name))
    if provider == "zernio" or name not in reg:
        return ZernioAdapter.for_platform(name, http)
    return reg[name](http)


def adapter_for(account, http: httpx.AsyncClient | None = None) -> PlatformAdapter:
    return get_adapter(account.platform, http, provider=getattr(account, "provider", "direct"))
