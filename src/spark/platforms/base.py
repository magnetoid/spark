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

    def __init__(self, message: str, *, retryable: bool = True, answered: bool = False):
        super().__init__(message)
        self.retryable = retryable
        # True when the network took the request and answered that the post failed. A retry
        # then needs a fresh idempotency key; after a timeout or a 5xx it must reuse the old one.
        self.answered = answered


class AuthExpired(PlatformError):
    def __init__(self, message: str = "Access token expired or revoked", *, answered: bool = False):
        super().__init__(message, retryable=False, answered=answered)


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
    thread: list[str] = field(default_factory=list)  # follow-up items; `text` is the root
    post_type: str = "post"  # post | carousel | reel | story | document; shapes the media checks
    # ai_generated (bool), paid_partnership (bool), collaborators ([handle]),
    # poll ({question, options, days}). An adapter reads only the keys it lists in `option_keys`.
    options: dict = field(default_factory=dict)
    # Same value for every attempt at the same logical post; adapters that support it send it
    idempotency_key: str | None = None

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
    # What this adapter actually sends: the composer only offers what the adapter can deliver
    supports_first_comment: ClassVar[bool] = False  # a reply posted right after publishing
    supports_thread: ClassVar[bool] = False  # follow-up items as a thread of replies
    post_types: ClassVar[tuple[str, ...]] = ("post",)  # formats the composer may offer
    # Extras this adapter sends: ai_generated | paid_partnership | collaborators | poll
    option_keys: ClassVar[tuple[str, ...]] = ()
    poll_option_chars: ClassVar[int] = 25
    poll_question_chars: ClassVar[int] = 0  # 0 = the poll has no question of its own

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
            if m.content_type == "application/pdf" and "document" in self.post_types:
                continue
            if m.content_type not in allowed:
                problems.append(f"{self.label}: {m.content_type} not supported")
        if sum(1 for m in payload.media if m.is_video) > 1:
            problems.append(f"{self.label}: only one video per post")
        problems += self.validate_format(payload)
        problems += self.validate_options(payload)
        return problems

    def validate_options(self, payload: PublishPayload) -> list[str]:
        """Extras the network would refuse, said before publishing. Only what this adapter sends."""
        opts = payload.options or {}
        story = payload.post_type == "story"
        problems: list[str] = []
        if story and self.supports_first_comment and payload.first_comment:
            problems.append(f"{self.label}: a story cannot carry a first comment")
        if "paid_partnership" in self.option_keys and story and opts.get("paid_partnership"):
            problems.append(f"{self.label}: a story cannot carry the paid partnership label")
        people = opts.get("collaborators") or []
        if "collaborators" in self.option_keys and people:
            if story:
                problems.append(f"{self.label}: a story cannot have collaborators")
            if len(people) > 3:
                problems.append(f"{self.label}: at most 3 collaborators")
        poll = opts.get("poll")
        if "poll" in self.option_keys and poll:
            choices = poll.get("options") or []
            if not 2 <= len(choices) <= 4:
                problems.append(f"{self.label}: a poll needs 2 to 4 options")
            if any(len(c) > self.poll_option_chars for c in choices):
                problems.append(
                    f"{self.label}: a poll option can be up to {self.poll_option_chars} characters"
                )
            if self.poll_question_chars and len(poll.get("question") or "") > (
                self.poll_question_chars
            ):
                problems.append(
                    f"{self.label}: a poll question can be up to "
                    f"{self.poll_question_chars} characters"
                )
            if payload.media:
                problems.append(f"{self.label}: a poll cannot have images or video")
            if payload.thread:
                problems.append(f"{self.label}: a poll cannot be part of a thread")
        return problems

    def validate_format(self, payload: PublishPayload) -> list[str]:
        """What a chosen post format needs from the media. Networks infer the format from it."""
        kind = payload.post_type or "post"
        if kind == "post":
            return []
        if kind not in self.post_types:
            return [f"{self.label}: {kind} posts are not available here"]
        images = [m for m in payload.media if m.content_type.startswith("image/")]
        videos = [m for m in payload.media if m.is_video]
        docs = [m for m in payload.media if m.content_type == "application/pdf"]
        if kind == "carousel" and (len(images) < 2 or videos or docs):
            return [f"{self.label}: a carousel needs two or more images"]
        if kind in ("reel", "story") and kind == "reel" and (len(videos) != 1 or images or docs):
            return [f"{self.label}: a reel is one video"]
        if kind == "story" and len(payload.media) != 1:
            return [f"{self.label}: a story is one image or one video"]
        if kind == "document" and (len(docs) != 1 or images or videos):
            return [f"{self.label}: a document post is one PDF"]
        return []

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
    if provider == "zernio" or name not in reg:
        real: PlatformAdapter = ZernioAdapter.for_platform(name, http)
    else:
        real = reg[name](http)
    if get_settings().force_dry_run:
        from spark.platforms.dry_run import DryRunAdapter

        # stands in for the connector this channel really uses, so the composer offers the same
        return DryRunAdapter(http, impersonate=real)
    return real


def adapter_for(account, http: httpx.AsyncClient | None = None) -> PlatformAdapter:
    return get_adapter(account.platform, http, provider=getattr(account, "provider", "direct"))
