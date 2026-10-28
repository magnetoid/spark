"""Zernio connector (https://docs.zernio.com).

Zernio is a unified social API: one API key, Zernio hosts the OAuth apps for
every platform, hosts media, and publishes. Spark keeps its own scheduling,
approvals and calendar; at publish time the worker asks Zernio to publish now
and stores the native post URL that comes back.

Account mapping: SocialAccount.provider == "zernio", external_id == Zernio
accountId, brand.zernio_profile_id == the Zernio profile holding the brand's
accounts. Platform keys are Spark's ("x"), translated to Zernio's ("twitter").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from spark.config import get_settings
from spark.platforms.base import (
    AuthExpired,
    ConnectedAccount,
    Limits,
    MetricsSnapshot,
    PlatformAdapter,
    PlatformError,
    PublishPayload,
    PublishResult,
)

log = logging.getLogger(__name__)

# spark key -> zernio key (identity when absent)
TO_ZERNIO = {"x": "twitter"}
FROM_ZERNIO = {v: k for k, v in TO_ZERNIO.items()}


@dataclass(frozen=True)
class ZPlatform:
    label: str
    limits: Limits
    video_only: bool = False


# Platforms publishable through Zernio's POST /v1/posts. Limits mirror the
# direct adapters where one exists so the composer counters agree.
ZERNIO_PLATFORMS: dict[str, ZPlatform] = {
    "x": ZPlatform("X / Twitter", Limits(max_chars=280, max_media=4)),
    "linkedin": ZPlatform("LinkedIn", Limits(max_chars=3000, max_media=9)),
    "facebook": ZPlatform("Facebook Page", Limits(max_chars=63206, max_media=10)),
    "instagram": ZPlatform("Instagram", Limits(max_chars=2200, max_media=10, requires_media=True)),
    "threads": ZPlatform("Threads", Limits(max_chars=500, max_media=10)),
    "tiktok": ZPlatform("TikTok", Limits(max_chars=2200, max_media=35, requires_media=True)),
    "youtube": ZPlatform("YouTube", Limits(max_chars=5000, max_media=1, requires_media=True), True),
    "pinterest": ZPlatform("Pinterest", Limits(max_chars=500, max_media=1, requires_media=True)),
    "bluesky": ZPlatform("Bluesky", Limits(max_chars=300, max_media=4)),
    "reddit": ZPlatform("Reddit", Limits(max_chars=40000, max_media=1)),
    "telegram": ZPlatform("Telegram", Limits(max_chars=4096, max_media=10)),
    "mastodon": ZPlatform("Mastodon", Limits(max_chars=500, max_media=4)),
    "googlebusiness": ZPlatform("Google Business", Limits(max_chars=1500, max_media=1)),
    "snapchat": ZPlatform("Snapchat", Limits(max_chars=250, max_media=1, requires_media=True)),
}


def to_zernio(platform: str) -> str:
    return TO_ZERNIO.get(platform, platform)


def from_zernio(platform: str) -> str:
    return FROM_ZERNIO.get(platform, platform)


class ZernioAdapter(PlatformAdapter):
    name = "zernio"
    label = "Zernio"
    limits = Limits(max_chars=5000, max_media=10)
    connect_mode = "oauth"
    docs_url = "https://docs.zernio.com/quickstart"

    def __init__(self, http: httpx.AsyncClient | None = None, platform: str = "x"):
        super().__init__(http)
        self.platform = platform
        meta = ZERNIO_PLATFORMS.get(platform)
        if meta:
            self.label = f"{meta.label} (Zernio)"
            self.limits = meta.limits
            self.video_only = meta.video_only
        else:
            self.video_only = False

    @classmethod
    def for_platform(cls, platform: str, http: httpx.AsyncClient | None = None) -> ZernioAdapter:
        return cls(http, platform)

    # ---- http ---------------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(get_settings().zernio_api_key)

    def _url(self, path: str) -> str:
        return f"{get_settings().zernio_base_url.rstrip('/')}/{path.lstrip('/')}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {get_settings().zernio_api_key}"}

    async def _req(self, method: str, path: str, **kw) -> httpx.Response:
        if not self.is_configured():
            raise PlatformError("SPARK_ZERNIO_API_KEY is not set", retryable=False)
        headers = {**self._headers(), **kw.pop("headers", {})}
        resp = await self.http.request(method, self._url(path), headers=headers, **kw)
        if resp.status_code == 401:
            raise PlatformError("Zernio rejected the API key (401)", retryable=False)
        if resp.status_code == 402:
            raise PlatformError("Zernio: plan limit reached (402)", retryable=False)
        return self.check(resp)

    # ---- profiles / accounts -------------------------------------------------
    async def ensure_profile(self, brand) -> str:
        """Return the Zernio profile id for a brand, creating one named after it."""
        if brand.zernio_profile_id:
            return brand.zernio_profile_id
        ext = f"spark-brand-{brand.id}"
        found = (await self._req("GET", "/profiles", params={"externalId": ext})).json()
        for p in found.get("profiles", []):
            if p.get("externalId") == ext:
                brand.zernio_profile_id = p["_id"]
                return p["_id"]
        resp = await self._req(
            "POST",
            "/profiles",
            json={"name": f"{brand.name} (Spark)", "externalId": ext, "color": brand.color},
        )
        brand.zernio_profile_id = resp.json()["profile"]["_id"]
        return brand.zernio_profile_id

    def connect_url_params(self, profile_id: str, state: str) -> dict:
        base = get_settings().base_url.rstrip("/")
        return {
            "profileId": profile_id,
            "redirect_url": f"{base}/accounts/zernio/callback?state={state}",
        }

    async def connect_url(self, profile_id: str, state: str) -> str:
        resp = await self._req(
            "GET",
            f"/connect/{to_zernio(self.platform)}",
            params=self.connect_url_params(profile_id, state),
        )
        return resp.json()["authUrl"]

    @staticmethod
    def _to_connected(a: dict) -> ConnectedAccount:
        return ConnectedAccount(
            external_id=a["_id"],
            handle=(a.get("username") or a.get("displayName") or a["_id"]).lstrip("@"),
            display_name=a.get("displayName"),
            avatar_url=a.get("profilePicture"),
            access_token="zernio",  # tokens live in Zernio; nothing to store locally
            followers=int(a["followersCount"]) if a.get("followersCount") is not None else None,
            extra={
                "zernio_platform": a.get("platform"),
                "profile_url": a.get("profileUrl"),
                "needs_reconnection": a.get("needsReconnection", False),
            },
        )

    async def list_accounts(self, profile_id: str | None = None) -> list[tuple[str, ConnectedAccount]]:
        """Accounts as (spark_platform, account) pairs — one Zernio profile, or every
        profile when `profile_id` is None (accounts connected in Zernio's own UI sit in
        the Default profile, not in the per-brand one Spark creates)."""
        out = []
        base: dict = {"limit": 200, "excludeHidden": "true", "includeOverLimit": "true"}
        if profile_id:
            base["profileId"] = profile_id
        params = dict(base)
        while True:
            data = (await self._req("GET", "/accounts", params=params)).json()
            for a in data.get("accounts", []):
                platform = from_zernio(a.get("platform", ""))
                if platform not in ZERNIO_PLATFORMS:
                    continue
                acc = self._to_connected(a)
                prof = a.get("profileId")
                if isinstance(prof, dict):
                    acc.extra["zernio_profile_id"] = prof.get("_id")
                    acc.extra["zernio_profile_name"] = prof.get("name")
                elif prof:
                    acc.extra["zernio_profile_id"] = prof
                out.append((platform, acc))
            cursor = (data.get("pagination") or {}).get("nextCursor")
            if not cursor:
                return out
            params = {**base, "cursor": cursor}

    async def get_account(self, account_id: str) -> ConnectedAccount | None:
        data = (await self._req("GET", "/accounts", params={"search": account_id})).json()
        for a in data.get("accounts", []):
            if a["_id"] == account_id:
                return self._to_connected(a)
        return None

    async def disconnect(self, account_id: str) -> None:
        try:
            await self._req("DELETE", f"/accounts/{account_id}")
        except PlatformError as e:
            log.info("Zernio disconnect %s: %s", account_id, e)

    # ---- publishing -----------------------------------------------------------
    def validate(self, payload: PublishPayload) -> list[str]:
        problems = super().validate(payload)
        if self.video_only and payload.media and not payload.media[0].is_video:
            problems.append(f"{self.label}: attach a video")
        return problems

    async def _upload(self, payload: PublishPayload, m) -> dict:
        """Upload local media to Zernio storage; returns a mediaItems entry."""
        pre = (
            await self._req(
                "POST",
                "/media/presign",
                json={"filename": m.filename, "contentType": m.content_type, "size": m.size},
            )
        ).json()
        data = payload.media_path(m).read_bytes()
        put = await self.http.put(pre["uploadUrl"], content=data, headers={"Content-Type": m.content_type})
        if put.status_code >= 400:
            raise PlatformError(f"Zernio media upload failed ({put.status_code})")
        item = {
            "url": pre["publicUrl"],
            "type": "video" if m.is_video else ("gif" if m.content_type == "image/gif" else "image"),
            "filename": m.filename,
            "mimeType": m.content_type,
            "size": m.size,
        }
        if m.alt_text:
            item["altText"] = m.alt_text
        return item

    FIRST_COMMENT_PLATFORMS = {"threads", "facebook", "instagram", "linkedin", "youtube"}

    def _platform_data(self, account, payload: PublishPayload) -> dict:
        z = to_zernio(account.platform)
        extra = account.extra or {}
        data: dict = {}
        if z == "youtube":
            title, _, _ = payload.text.partition("\n")
            data = {"title": (title or "Video")[:100], "visibility": extra.get("privacy_status", "public")}
        elif z == "pinterest" and extra.get("board_id"):
            data = {"boardId": extra["board_id"]}
        elif z == "reddit" and extra.get("subreddit"):
            title, _, _ = payload.text.partition("\n")
            data = {"subreddit": extra["subreddit"], "title": title[:300]}
        if payload.first_comment and z in self.FIRST_COMMENT_PLATFORMS:
            data["firstComment"] = payload.first_comment[:500]
        return data

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        if account.extra.get("needs_reconnection"):
            raise AuthExpired("Zernio reports this account needs reconnection")
        text = payload.text
        if payload.link and payload.link not in text and account.platform not in ("facebook", "linkedin"):
            text = f"{text}\n\n{payload.link}".strip()
        body: dict = {
            "content": text,
            "publishNow": True,
            "platforms": [{"platform": to_zernio(account.platform), "accountId": account.external_id}],
            "metadata": {"source": "spark"},
        }
        media_items = [await self._upload(payload, m) for m in payload.media] if payload.media else []
        pdata = self._platform_data(account, payload)
        if payload.thread and to_zernio(account.platform) in ("twitter", "threads", "bluesky"):
            # threadItems[0] is the root and carries the media; top-level content is display-only.
            root: dict = {"content": text}
            if media_items:
                root["mediaItems"] = media_items
            pdata["threadItems"] = [root] + [{"content": t} for t in payload.thread]
        elif media_items:
            body["mediaItems"] = media_items
        if pdata:
            body["platforms"][0]["platformSpecificData"] = pdata
        import uuid

        resp = await self._req(
            "POST", "/posts", json=body, headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        data = resp.json()
        post = data.get("post") or data
        post_id = post.get("_id") or data.get("postId")
        targets = post.get("platforms") or []
        t = targets[0] if targets else {}
        status = t.get("status") or post.get("status")
        if status == "failed" or resp.status_code == 207:
            msg = t.get("errorMessage") or post.get("status") or "Zernio could not publish"
            cat = t.get("errorCategory", "")
            if cat == "auth_expired":
                raise AuthExpired(f"Zernio: {msg}")
            retryable = cat in ("platform_error", "platform_rate_limit", "") and t.get("errorSource") != "user"
            raise PlatformError(f"Zernio: {msg}", retryable=retryable)
        if not post_id:
            raise PlatformError(f"Zernio returned no post id: {str(data)[:200]}")
        return PublishResult(remote_id=post_id, url=t.get("platformPostUrl"))

    async def resolve_url(self, remote_id: str) -> str | None:
        """Scheduled/async publishes get their URL later; fetch it."""
        post = (await self._req("GET", f"/posts/{remote_id}")).json().get("post", {})
        for t in post.get("platforms", []):
            if t.get("platformPostUrl"):
                return t["platformPostUrl"]
        return None

    async def fetch_metrics(self, account, remote_ids: list[str]) -> list[MetricsSnapshot]:
        out = []
        for rid in remote_ids:
            resp = await self.http.get(
                self._url("/analytics"), headers=self._headers(), params={"postId": rid}
            )
            if resp.status_code in (202, 404, 424):
                continue  # sync pending / unknown / all platforms failed
            try:
                self.check(resp)
            except PlatformError as e:
                log.info("Zernio analytics %s: %s", rid, e)
                continue
            data = resp.json()
            a = data.get("analytics") or {}
            if not a and data.get("platformAnalytics"):
                a = next(iter(data["platformAnalytics"].values()), {}) if isinstance(
                    data["platformAnalytics"], dict) else (data["platformAnalytics"][0] or {})
            out.append(
                MetricsSnapshot(
                    remote_id=rid,
                    impressions=int(a.get("impressions") or a.get("views") or 0),
                    likes=int(a.get("likes") or 0),
                    comments=int(a.get("comments") or 0),
                    shares=int(a.get("shares") or 0) + int(a.get("saves") or 0),
                    clicks=int(a.get("clicks") or 0),
                )
            )
        return out
