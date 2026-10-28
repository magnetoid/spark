"""Fake adapter: records posts locally and invents metrics. Used for demos,
local development (SPARK_FORCE_DRY_RUN=true) and tests."""

import hashlib
import logging
import random

import httpx

from spark.platforms.base import (
    ConnectedAccount,
    Limits,
    MetricsSnapshot,
    PlatformAdapter,
    PublishPayload,
    PublishResult,
    register,
)
from spark.security import token

log = logging.getLogger(__name__)


@register
class DryRunAdapter(PlatformAdapter):
    name = "dry_run"
    label = "Dry run (test)"
    limits = Limits(max_chars=5000, max_media=10)
    connect_mode = "credentials"
    credential_fields = (("handle", "Handle to display"),)

    def __init__(self, http: httpx.AsyncClient | None = None, impersonate=None):
        super().__init__(http)
        if impersonate is not None:
            self.limits = impersonate.limits
            self.label = f"{impersonate.label} (dry run)"

    async def connect_with_credentials(self, data: dict[str, str]) -> list[ConnectedAccount]:
        handle = (data.get("handle") or "test-account").strip()
        return [
            ConnectedAccount(
                external_id=f"dry-{handle}",
                handle=handle,
                display_name=handle,
                access_token=token(),
                followers=random.randint(100, 5000),
            )
        ]

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        if "#fail" in payload.text:
            from spark.platforms.base import PlatformError

            raise PlatformError("Dry-run forced failure (#fail in text)", retryable=False)
        remote_id = hashlib.sha1(f"{account.id}:{payload.text}:{token(4)}".encode()).hexdigest()[:16]
        log.info("[dry-run] %s/%s: %s", account.platform, account.handle, payload.text[:80])
        return PublishResult(remote_id=remote_id, url=f"https://example.com/{account.handle}/{remote_id}")

    async def fetch_metrics(self, account, remote_ids: list[str]) -> list[MetricsSnapshot]:
        out = []
        for rid in remote_ids:
            rng = random.Random(rid)
            imp = rng.randint(200, 20000)
            out.append(
                MetricsSnapshot(
                    remote_id=rid,
                    impressions=imp,
                    likes=int(imp * rng.uniform(0.01, 0.06)),
                    comments=int(imp * rng.uniform(0.001, 0.01)),
                    shares=int(imp * rng.uniform(0.001, 0.008)),
                    clicks=int(imp * rng.uniform(0.005, 0.03)),
                )
            )
        return out
