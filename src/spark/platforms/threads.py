"""Threads API (graph.threads.net)."""

import asyncio

from spark.config import get_settings
from spark.platforms._oauth import build_url, expires_at, token_request
from spark.platforms.base import (
    ConnectedAccount,
    Limits,
    MetricsSnapshot,
    OAuthStart,
    PlatformAdapter,
    PlatformError,
    PublishPayload,
    PublishResult,
    register,
)

API = "https://graph.threads.net/v1.0"


@register
class ThreadsAdapter(PlatformAdapter):
    name = "threads"
    label = "Threads"
    limits = Limits(max_chars=500, max_media=10)
    docs_url = "https://developers.facebook.com/docs/threads"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.threads_app_id and s.threads_app_secret)

    def oauth_start(self, state: str) -> OAuthStart:
        return OAuthStart(
            build_url(
                "https://threads.net/oauth/authorize",
                {
                    "client_id": get_settings().threads_app_id,
                    "redirect_uri": self.redirect_uri(),
                    "scope": "threads_basic,threads_content_publish,threads_manage_insights",
                    "response_type": "code",
                    "state": state,
                },
            )
        )

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        s = get_settings()
        short = await token_request(
            self.http,
            "https://graph.threads.net/oauth/access_token",
            {
                "client_id": s.threads_app_id,
                "client_secret": s.threads_app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri(),
                "code": code,
            },
        )
        long = self.check(
            await self.http.get(
                "https://graph.threads.net/access_token",
                params={
                    "grant_type": "th_exchange_token",
                    "client_secret": s.threads_app_secret,
                    "access_token": short["access_token"],
                },
            )
        ).json()
        me = self.check(
            await self.http.get(
                f"{API}/me",
                params={
                    "fields": "id,username,threads_profile_picture_url",
                    "access_token": long["access_token"],
                },
            )
        ).json()
        return [
            ConnectedAccount(
                external_id=me["id"],
                handle=me["username"],
                display_name=me["username"],
                avatar_url=me.get("threads_profile_picture_url"),
                access_token=long["access_token"],
                expires_at=expires_at(long.get("expires_in")),
            )
        ]

    async def refresh(self, account) -> bool:
        resp = self.check(
            await self.http.get(
                "https://graph.threads.net/refresh_access_token",
                params={"grant_type": "th_refresh_token", "access_token": account.access_token},
            )
        ).json()
        account.access_token = resp["access_token"]
        account.token_expires_at = expires_at(resp.get("expires_in"))
        return True

    async def _create(self, account, **data) -> str:
        res = self.check(
            await self.http.post(
                f"{API}/{account.external_id}/threads",
                data={"access_token": account.access_token, **data},
            )
        ).json()
        return res["id"]

    async def _wait(self, account, cid: str) -> None:
        for _ in range(40):
            st = self.check(
                await self.http.get(
                    f"{API}/{cid}",
                    params={"fields": "status,error_message", "access_token": account.access_token},
                )
            ).json()
            if st.get("status") in ("FINISHED", "PUBLISHED", None):
                return
            if st.get("status") in ("ERROR", "EXPIRED"):
                raise PlatformError(f"Threads: {st.get('error_message')}", retryable=False)
            await asyncio.sleep(3)

    def _media_args(self, payload, m) -> dict:
        if m.is_video:
            return {"media_type": "VIDEO", "video_url": payload.media_url(m)}
        return {"media_type": "IMAGE", "image_url": payload.media_url(m)}

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        if not payload.media:
            cid = await self._create(account, media_type="TEXT", text=payload.text)
        elif len(payload.media) == 1:
            cid = await self._create(
                account, text=payload.text, **self._media_args(payload, payload.media[0])
            )
        else:
            children = []
            for m in payload.media:
                c = await self._create(account, is_carousel_item="true", **self._media_args(payload, m))
                await self._wait(account, c)
                children.append(c)
            cid = await self._create(
                account, media_type="CAROUSEL", children=",".join(children), text=payload.text
            )
        await self._wait(account, cid)
        res = self.check(
            await self.http.post(
                f"{API}/{account.external_id}/threads_publish",
                data={"creation_id": cid, "access_token": account.access_token},
            )
        ).json()
        mid = res["id"]
        link = (
            self.check(
                await self.http.get(
                    f"{API}/{mid}",
                    params={"fields": "permalink", "access_token": account.access_token},
                )
            )
            .json()
            .get("permalink")
        )
        return PublishResult(mid, link)

    async def fetch_metrics(self, account, remote_ids):
        out = []
        for rid in remote_ids:
            try:
                d = self.check(
                    await self.http.get(
                        f"{API}/{rid}/insights",
                        params={
                            "metric": "views,likes,replies,reposts,quotes",
                            "access_token": account.access_token,
                        },
                    )
                ).json()
            except PlatformError:
                continue
            v = {i["name"]: i["values"][0]["value"] for i in d.get("data", [])}
            out.append(
                MetricsSnapshot(
                    remote_id=rid,
                    impressions=v.get("views", 0),
                    likes=v.get("likes", 0),
                    comments=v.get("replies", 0),
                    shares=v.get("reposts", 0) + v.get("quotes", 0),
                )
            )
        return out
