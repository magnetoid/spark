from spark.platforms import (  # noqa: F401  (import registers adapters)
    bluesky,
    dry_run,
    linkedin,
    mastodon,
    meta,
    pinterest,
    telegram,
    threads,
    tiktok,
    x,
    youtube,
)
from spark.platforms.base import (
    AuthExpired,
    PlatformAdapter,
    PlatformError,
    PublishPayload,
    adapter_for,
    get_adapter,
    registry,
)

__all__ = [
    "AuthExpired",
    "adapter_for",
    "PlatformAdapter",
    "PlatformError",
    "PublishPayload",
    "get_adapter",
    "registry",
]
