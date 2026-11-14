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
from datetime import UTC, datetime, timedelta

import httpx

from spark.config import get_settings
from spark.platforms.base import (
    AuthExpired,
    ConnectedAccount,
    Limits,
    MetricsSnapshot,
    NotAvailable,
    PlatformAdapter,
    PlatformError,
    PublishPayload,
    PublishResult,
    RateLimited,
)

log = logging.getLogger(__name__)

# How far back post numbers are read; Spark stops reading a post 30 days after it went out
METRICS_WINDOW_DAYS = 31

# What each network reports, from Zernio's analytics table. Zernio sends 0 for a number the
# network does not report; Spark keeps those empty instead, so 0 always means a real zero.
# Bluesky reposts arrive as shares and Reddit upvotes as likes.
REPORTS: dict[str, set[str]] = {
    "instagram": {"impressions", "reach", "likes", "comments", "shares", "saves", "views"},
    "facebook": {"impressions", "likes", "comments", "shares", "clicks", "views"},
    "linkedin": {"impressions", "reach", "likes", "comments", "shares", "clicks", "saves"},
    "tiktok": {"likes", "comments", "shares", "views"},
    "youtube": {"likes", "comments", "views"},
    "x": {"impressions", "likes", "comments", "shares", "saves", "clicks", "views"},
    "pinterest": {"impressions", "saves", "clicks"},
    "threads": {"likes", "comments", "shares", "views"},
    "bluesky": {"likes", "comments", "shares"},
    "snapchat": {"views", "reach", "shares"},
    "reddit": {"likes", "comments"},
    "googlebusiness": set(),
}


def snapshot_from(remote_id: str, platform: str, a: dict) -> MetricsSnapshot:
    """One Zernio analytics object as a snapshot: saves, views and reach kept apart, and
    numbers the network does not report left empty."""
    reports = REPORTS.get(platform)

    def num(key: str) -> int:
        return int(a.get(key) or 0)

    def maybe(key: str) -> int | None:
        if reports is not None and key not in reports:
            return None
        return num(key)

    return MetricsSnapshot(
        remote_id=remote_id,
        impressions=num("impressions"),
        likes=num("likes"),
        comments=num("comments"),
        shares=num("shares"),
        clicks=num("clicks"),
        reach=maybe("reach"),
        views=maybe("views"),
        saves=maybe("saves"),
    )


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
        self.calls = 0  # requests made by fetch_metrics, for the per-run budget
        meta = ZERNIO_PLATFORMS.get(platform)
        if meta:
            self.label = f"{meta.label} (Zernio)"
            self.limits = meta.limits
            self.video_only = meta.video_only
        else:
            self.video_only = False
        z = to_zernio(platform)
        self.supports_first_comment = z in self.FIRST_COMMENT_PLATFORMS
        self.post_types = self.FORMATS_BY_PLATFORM.get(z, ("post",))
        self.supports_thread = z in self.THREAD_PLATFORMS
        self.option_keys = self.OPTIONS_BY_PLATFORM.get(z, ())
        if z == "linkedin":
            self.poll_option_chars, self.poll_question_chars = 30, 140

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
                "token_expires_at": a.get("tokenExpiresAt"),
            },
        )

    async def list_accounts(
        self, profile_id: str | None = None
    ) -> list[tuple[str, ConnectedAccount]]:
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

    async def pinterest_boards(self, account_id: str) -> list[dict]:
        """The boards a Pinterest account can pin to: [{id, name, ...}]."""
        data = (await self._req("GET", f"/accounts/{account_id}/pinterest-boards")).json()
        return data.get("boards") or []

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
        put = await self.http.put(
            pre["uploadUrl"], content=data, headers={"Content-Type": m.content_type}
        )
        if put.status_code >= 400:
            raise PlatformError(f"Zernio media upload failed ({put.status_code})")
        item = {
            "url": pre["publicUrl"],
            "type": "video"
            if m.is_video
            else "document"
            if m.content_type == "application/pdf"
            else ("gif" if m.content_type == "image/gif" else "image"),
            "filename": m.filename,
            "mimeType": m.content_type,
            "size": m.size,
        }
        if m.alt_text:
            item["altText"] = m.alt_text
        return item

    # Zernio has `platformSpecificData.firstComment` and `threadItems` only for these
    FIRST_COMMENT_PLATFORMS = {"threads", "facebook", "instagram", "linkedin", "youtube"}
    THREAD_PLATFORMS = {"twitter", "threads", "bluesky"}
    # Zernio infers most formats from the media: several images = carousel, a PDF = LinkedIn
    # document, one video on Instagram = Reel. A Story needs `contentType: "story"`, and so does
    # a Facebook Reel (`"reel"`); without it Facebook publishes the video as a feed post.
    FORMATS_BY_PLATFORM = {
        "instagram": ("post", "carousel", "reel", "story"),
        "facebook": ("post", "carousel", "reel", "story"),
        "linkedin": ("post", "document"),
    }
    # Labels and extras Zernio documents per network. Facebook and Threads have none of them.
    OPTIONS_BY_PLATFORM = {
        "instagram": ("ai_generated", "paid_partnership", "collaborators"),
        "twitter": ("ai_generated", "paid_partnership", "poll"),
        "youtube": ("ai_generated",),
        "tiktok": ("ai_generated", "paid_partnership"),
        "linkedin": ("poll",),
    }
    LINKEDIN_POLL_DAYS = ((1, "ONE_DAY"), (3, "THREE_DAYS"), (7, "SEVEN_DAYS"))

    @staticmethod
    def _poll(payload: PublishPayload) -> tuple[list[str], int, str] | None:
        """(options, days, question) of a poll that can go out, else None."""
        poll = (payload.options or {}).get("poll") or {}
        choices = [str(c).strip() for c in poll.get("options") or [] if str(c).strip()]
        if len(choices) < 2 or payload.media or payload.thread:
            return None
        return choices[:4], int(poll.get("days") or 3), str(poll.get("question") or "").strip()

    def _tiktok_settings(self, account, payload: PublishPayload) -> dict:
        """TikTok refuses a post without these; Zernio reads them from the top of the request."""
        opts = payload.options or {}
        privacy = (account.extra or {}).get("privacy_level", "PUBLIC_TO_EVERYONE")
        video = any(m.is_video for m in payload.media)
        out: dict = {"privacy_level": privacy, "allow_comment": True}
        if video:
            out |= {"allow_duet": True, "allow_stitch": True}
        elif payload.media:
            out["media_type"] = "photo"
        # The author saw the post in the composer and chose to publish it
        out |= {"content_preview_confirmed": True, "express_consent_given": True}
        if video and opts.get("ai_generated"):
            out["video_made_with_ai"] = True  # TikTok refuses the label on photo posts
        if opts.get("paid_partnership"):
            if privacy == "SELF_ONLY":
                raise PlatformError(
                    "TikTok: a paid partnership cannot be posted as visible only to you",
                    retryable=False,
                )
            out["commercialContentType"] = "brand_content"
        return out

    def _platform_data(self, account, payload: PublishPayload) -> dict:
        z = to_zernio(account.platform)
        extra = account.extra or {}
        data: dict = {}
        if z == "youtube":
            title, _, _ = payload.text.partition("\n")
            data = {
                "title": (title or "Video")[:100],
                "visibility": extra.get("privacy_status", "public"),
            }
        elif z == "pinterest" and extra.get("board_id"):
            data = {"boardId": extra["board_id"]}
        elif z == "reddit" and extra.get("subreddit"):
            title, _, _ = payload.text.partition("\n")
            data = {"subreddit": extra["subreddit"], "title": title[:300]}
        opts = payload.options or {}
        ai, paid = bool(opts.get("ai_generated")), bool(opts.get("paid_partnership"))
        story = payload.post_type == "story" and "story" in self.post_types
        poll = self._poll(payload)
        if z == "instagram":
            if story:
                data["contentType"] = "story"
            if ai:
                data["isAiGenerated"] = True
            # A Story with either of these comes back as a 400
            people = [str(p) for p in opts.get("collaborators") or [] if str(p).strip()]
            if paid and not story:
                data["isPaidPartnership"] = True
            if people and not story:
                data["collaborators"] = people[:3]
        elif z == "facebook" and payload.post_type in ("story", "reel"):
            data["contentType"] = payload.post_type
        elif z == "twitter":
            if ai:
                data["madeWithAi"] = True
            if paid:
                data["paidPartnership"] = True
            if poll:
                choices, days, _ = poll
                data["poll"] = {"options": choices, "duration_minutes": min(days, 7) * 1440}
        elif z == "youtube" and ai:
            data["containsSyntheticMedia"] = True
        elif z == "linkedin" and poll:
            choices, days, question = poll
            first_line, _, _ = payload.text.partition("\n")
            data["poll"] = {
                "question": (question or first_line.strip())[:140],
                "options": choices,
                "duration": next(
                    (name for limit, name in self.LINKEDIN_POLL_DAYS if days <= limit),
                    "FOURTEEN_DAYS",
                ),
            }
        if payload.first_comment and z in self.FIRST_COMMENT_PLATFORMS and not story:
            data["firstComment"] = payload.first_comment[:500]
        return data

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        if account.extra.get("needs_reconnection"):
            raise AuthExpired("Zernio reports this account needs reconnection")
        text = payload.text
        # Zernio's create-post has no link field: the URL must be in the text on every network
        # (Facebook and LinkedIn build their preview card from it).
        if payload.link and payload.link not in text:
            text = f"{text}\n\n{payload.link}".strip()
        body: dict = {
            "content": text,
            "publishNow": True,
            "platforms": [
                {"platform": to_zernio(account.platform), "accountId": account.external_id}
            ],
            "metadata": {"source": "spark"},
        }
        media_items = (
            [await self._upload(payload, m) for m in payload.media] if payload.media else []
        )
        pdata = self._platform_data(account, payload)
        if to_zernio(account.platform) == "tiktok":
            body["tiktokSettings"] = self._tiktok_settings(account, payload)
        if payload.thread and to_zernio(account.platform) in self.THREAD_PLATFORMS:
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

        key = payload.idempotency_key or str(uuid.uuid4())
        resp = await self._req("POST", "/posts", json=body, headers={"Idempotency-Key": key})
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
                raise AuthExpired(f"Zernio: {msg}", answered=True)
            retryable = (
                cat in ("platform_error", "platform_rate_limit", "")
                and t.get("errorSource") != "user"
            )
            raise PlatformError(f"Zernio: {msg}", retryable=retryable, answered=True)
        if not post_id:
            raise PlatformError(f"Zernio returned no post id: {str(data)[:200]}")
        return PublishResult(remote_id=post_id, url=t.get("platformPostUrl"))

    # ---- engagement inbox (comments) --------------------------------------------
    async def commented_posts(
        self, account_ids: set[str], since: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Posts with comments across the key's accounts, filtered to `account_ids`
        (Zernio account ids). Each row: id, platform, accountId, accountUsername,
        content, picture, permalink, createdTime, commentCount, likeCount."""
        params: dict = {"limit": min(limit, 100), "sortBy": "date", "sortOrder": "desc"}
        if since:
            params["since"] = since
        out: list[dict] = []
        while True:
            data = (await self._req("GET", "/inbox/comments", params=params)).json()
            out += [
                r
                for r in data.get("data", [])
                if r.get("accountId") in account_ids and not r.get("isAd")
            ]
            page = data.get("pagination") or {}
            if not page.get("hasMore") or not page.get("nextCursor") or len(out) >= limit:
                return out[:limit]
            params["cursor"] = page["nextCursor"]

    async def post_comments(self, post_id: str, account_id: str, cursor: str | None = None) -> dict:
        params: dict = {"accountId": account_id, "limit": 50}
        if cursor:
            params["cursor"] = cursor
        return (await self._req("GET", f"/inbox/comments/{post_id}", params=params)).json()

    async def reply(
        self,
        post_id: str,
        account_id: str,
        message: str,
        comment_id: str | None = None,
        bluesky: dict | None = None,
    ) -> dict:
        import uuid

        body: dict = {"accountId": account_id, "message": message}
        if comment_id:
            body["commentId"] = comment_id
        if bluesky:
            body.update({k: v for k, v in bluesky.items() if v})
        return (
            await self._req(
                "POST",
                f"/inbox/comments/{post_id}",
                json=body,
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
        ).json()

    async def like_comment(
        self, post_id: str, comment_id: str, account_id: str, liked: bool
    ) -> None:
        method = "POST" if liked else "DELETE"
        await self._req(
            method, f"/inbox/comments/{post_id}/{comment_id}/like", json={"accountId": account_id}
        )

    async def _page(
        self, path: str, account_ids: set[str], params: dict, limit: int, key: str = "data"
    ) -> list[dict]:
        out: list[dict] = []
        params = dict(params)
        while True:
            data = (await self._req("GET", path, params=params)).json()
            out += [
                r for r in data.get(key, []) if not account_ids or r.get("accountId") in account_ids
            ]
            page = data.get("pagination") or {}
            if (
                not page.get("hasMore")
                or not (page.get("nextCursor") or page.get("cursor"))
                or len(out) >= limit
            ):
                return out[:limit]
            params["cursor"] = page.get("nextCursor") or page.get("cursor")

    async def conversations(self, account_ids: set[str], limit: int = 50) -> list[dict]:
        """Direct-message conversations across the key's accounts (Facebook, Instagram, X, Bluesky, Reddit, Telegram, WhatsApp…)."""
        return await self._page(
            "/inbox/conversations",
            account_ids,
            {"limit": min(limit, 100), "sortOrder": "desc"},
            limit,
        )

    async def conversation_messages(
        self, conversation_id: str, account_id: str, limit: int = 50
    ) -> list[dict]:
        data = (
            await self._req(
                "GET",
                f"/inbox/conversations/{conversation_id}/messages",
                params={"accountId": account_id, "limit": min(limit, 100), "sortOrder": "asc"},
            )
        ).json()
        return data.get("messages") or []

    async def send_message(self, conversation_id: str, account_id: str, text: str) -> dict:
        import uuid

        return (
            await self._req(
                "POST",
                f"/inbox/conversations/{conversation_id}/messages",
                json={"accountId": account_id, "message": text},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
        ).json()

    async def mark_read(self, conversation_id: str, account_id: str) -> None:
        await self._req(
            "POST", f"/inbox/conversations/{conversation_id}/read", json={"accountId": account_id}
        )

    async def reviews(self, account_ids: set[str], limit: int = 50) -> list[dict]:
        """Google Business and Facebook reviews. Each row: id, platform, accountId, rating, text, reviewer, created, hasReply, reply."""
        return await self._page(
            "/inbox/reviews",
            account_ids,
            {"limit": min(limit, 100), "sortBy": "date", "sortOrder": "desc"},
            limit,
        )

    async def reply_review(self, review_id: str, account_id: str, text: str) -> dict:
        from urllib.parse import quote

        return (
            await self._req(
                "POST",
                f"/inbox/reviews/{quote(review_id, safe='')}/reply",
                json={"accountId": account_id, "message": text},
            )
        ).json()

    async def follower_stats(self, account_ids: set[str]) -> dict[str, int]:
        """Latest follower count per Zernio account id from /accounts/follower-stats (analytics add-on).
        Rows carry accountId plus followers/followersCount and a date; the newest row per account wins."""
        data = (
            await self._req(
                "GET",
                "/accounts/follower-stats",
                params={"accountIds": ",".join(sorted(account_ids))},
            )
        ).json()
        rows: list = []
        body = data.get("data", data.get("stats")) if isinstance(data, dict) else data
        if isinstance(body, dict):  # {"<accountId>": {...}} or {"stats": [...]}
            inner = body.get("stats") or body.get("data")
            rows = (
                list(inner)
                if isinstance(inner, list)
                else [{"accountId": k, **v} for k, v in body.items() if isinstance(v, dict)]
            )
        elif isinstance(body, list):
            rows = body
        out: dict[str, tuple[str, int]] = {}
        for r in rows:
            if not isinstance(r, dict):
                continue  # the add-on answers with plain ids when it has no stats
            aid = r.get("accountId") or r.get("account_id")
            n = r.get("followers", r.get("followersCount", r.get("count")))
            if aid not in account_ids or n is None:
                continue
            try:
                n = int(n)
            except (TypeError, ValueError):
                continue
            day = str(r.get("date") or r.get("day") or "")
            if aid not in out or day >= out[aid][0]:
                out[aid] = (day, n)
        return {k: v[1] for k, v in out.items()}

    async def mentions(self, account_ids: set[str], limit: int = 50) -> list[dict]:
        """Mentions of the accounts in other people's posts and comments (last 7 days; needs Zernio's Inbox add-on)."""
        try:
            return await self._page(
                "/inbox/mentions", account_ids, {"limit": min(limit, 100)}, limit
            )
        except PlatformError as e:  # the add-on is optional: no mentions is not an error
            if any(code in str(e) for code in ("403", "404", "402")):
                return []
            raise

    # ---- webhooks (POST /webhooks/settings etc.) -------------------------------------
    async def list_webhooks(self) -> list[dict]:
        r = await self._req("GET", "/webhooks/settings")
        data = r.json()
        return data.get("webhooks") or data.get("data") or (data if isinstance(data, list) else [])

    async def upsert_webhook(
        self, url: str, secret: str, events: list[str], name: str = "Spark"
    ) -> dict:
        """Create our endpoint, or bring an existing one for the same URL up to date."""
        for w in await self.list_webhooks():
            if w.get("url") == url:
                r = await self._req(
                    "PUT",
                    "/webhooks/settings",
                    json={
                        "webhookId": w.get("_id"),
                        "name": name,
                        "url": url,
                        "secret": secret,
                        "events": events,
                        "isActive": True,
                    },
                )
                return r.json().get("webhook") or w
        r = await self._req(
            "POST",
            "/webhooks/settings",
            json={"name": name, "url": url, "secret": secret, "events": events, "isActive": True},
        )
        return r.json().get("webhook") or r.json()

    async def test_webhook(self, webhook_id: str, event: str = "post.published") -> dict:
        r = await self._req(
            "POST", "/webhooks/test", json={"webhookId": webhook_id, "event": event}
        )
        return r.json()

    async def resolve_url(self, remote_id: str) -> str | None:
        """Scheduled/async publishes get their URL later; fetch it."""
        post = (await self._req("GET", f"/posts/{remote_id}")).json().get("post", {})
        for t in post.get("platforms", []):
            if t.get("platformPostUrl"):
                return t["platformPostUrl"]
        return None

    async def fetch_metrics(self, account, remote_ids: list[str]) -> list[MetricsSnapshot]:
        """Pages through the account's posts made through Zernio, newest first, until every
        asked-for post is found. Zernio answers from its own store (synced about hourly), so
        this costs no network quota; `self.calls` counts the requests for Spark's budget."""
        wanted, out = set(remote_ids), []
        platform = account.platform
        page, pages = 1, 1
        since = (datetime.now(UTC) - timedelta(days=METRICS_WINDOW_DAYS)).date().isoformat()
        while wanted and page <= pages:
            resp = await self.http.get(
                self._url("/analytics"),
                headers=self._headers(),
                params={
                    "accountId": account.external_id,
                    "source": "late",
                    "fromDate": since,
                    "sortBy": "date",
                    "order": "desc",
                    "view": "summary",
                    "limit": 50,
                    "page": page,
                },
            )
            self.calls += 1
            if resp.status_code == 429:
                try:
                    wait = int(float(resp.headers.get("Retry-After") or 60))
                except ValueError:
                    wait = 60
                raise RateLimited("Zernio asked Spark to slow down (429)", retry_after=wait)
            if resp.status_code == 402:
                raise NotAvailable(
                    "Zernio answered 402: this plan has no Analytics add-on, so post numbers "
                    "cannot be read. Add it in Zernio, or move to a usage-based plan."
                )
            self.check(resp)
            data = resp.json()
            pages = int((data.get("pagination") or {}).get("pages") or 1)
            for item in data.get("posts") or []:
                rid = next(
                    (i for i in (item.get("latePostId"), item.get("_id")) if i in wanted), None
                )
                if rid is None:
                    continue
                wanted.discard(rid)
                a = next(
                    (
                        pa.get("analytics") or {}
                        for pa in item.get("platformAnalytics") or []
                        if pa.get("accountId") == account.external_id
                    ),
                    None,
                ) or (item.get("analytics") or {})
                snap = snapshot_from(rid, platform, a)
                snap.url = item.get("platformPostUrl")
                out.append(snap)
            page += 1
        return out
