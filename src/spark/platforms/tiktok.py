"""TikTok Content Posting API (direct post, video pulled from public URL).

Unaudited apps can only post with privacy SELF_ONLY; set account extra
`privacy_level` to PUBLIC_TO_EVERYONE after TikTok approves your app.
"""

import asyncio

from spark.config import get_settings
from spark.platforms._oauth import build_url, expires_at, pkce_pair, token_request
from spark.platforms.base import (
    ConnectedAccount,
    Limits,
    OAuthStart,
    PlatformAdapter,
    PlatformError,
    PublishPayload,
    PublishResult,
    register,
)

API = "https://open.tiktokapis.com/v2"


@register
class TikTokAdapter(PlatformAdapter):
    name = "tiktok"
    label = "TikTok"
    limits = Limits(max_chars=2200, max_media=1, requires_media=True)
    docs_url = "https://developers.tiktok.com/apps"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.tiktok_client_key and s.tiktok_client_secret)

    def validate(self, payload: PublishPayload) -> list[str]:
        problems = super().validate(payload)
        if payload.media and not payload.media[0].is_video:
            problems.append("TikTok: attach a video")
        return problems

    def oauth_start(self, state: str) -> OAuthStart:
        verifier, challenge = pkce_pair()
        return OAuthStart(
            build_url(
                "https://www.tiktok.com/v2/auth/authorize/",
                {
                    "client_key": get_settings().tiktok_client_key,
                    "scope": "user.info.basic,video.publish",
                    "response_type": "code",
                    "redirect_uri": self.redirect_uri(),
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                },
            ),
            {"verifier": verifier},
        )

    async def _token(self, data: dict) -> dict:
        s = get_settings()
        return await token_request(
            self.http,
            f"{API}/oauth/token/",
            {"client_key": s.tiktok_client_key, "client_secret": s.tiktok_client_secret, **data},
            {"Content-Type": "application/x-www-form-urlencoded"},
        )

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        tok = await self._token(
            {
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri(),
                "code_verifier": session_data.get("verifier"),
            }
        )
        info = self.check(
            await self.http.get(
                f"{API}/user/info/",
                params={"fields": "open_id,display_name,avatar_url,username,follower_count"},
                headers={"Authorization": f"Bearer {tok['access_token']}"},
            )
        ).json()["data"]["user"]
        return [
            ConnectedAccount(
                external_id=tok["open_id"],
                handle=info.get("username") or info.get("display_name", tok["open_id"]),
                display_name=info.get("display_name"),
                avatar_url=info.get("avatar_url"),
                access_token=tok["access_token"],
                refresh_token=tok.get("refresh_token"),
                expires_at=expires_at(tok.get("expires_in")),
                followers=info.get("follower_count"),
                extra={"privacy_level": "SELF_ONLY"},
            )
        ]

    async def refresh(self, account) -> bool:
        if not account.refresh_token:
            return False
        tok = await self._token(
            {"grant_type": "refresh_token", "refresh_token": account.refresh_token}
        )
        account.access_token = tok["access_token"]
        account.refresh_token = tok.get("refresh_token", account.refresh_token)
        account.token_expires_at = expires_at(tok.get("expires_in"))
        return True

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        h = {"Authorization": f"Bearer {account.access_token}"}
        init = self.check(
            await self.http.post(
                f"{API}/post/publish/video/init/",
                headers=h,
                json={
                    "post_info": {
                        "title": payload.text[:2200],
                        "privacy_level": account.extra.get("privacy_level", "SELF_ONLY"),
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": payload.media_url(payload.media[0]),
                    },
                },
            )
        ).json()
        publish_id = init["data"]["publish_id"]
        for _ in range(60):
            st = self.check(
                await self.http.post(
                    f"{API}/post/publish/status/fetch/", headers=h, json={"publish_id": publish_id}
                )
            ).json()["data"]
            status = st.get("status")
            if status == "PUBLISH_COMPLETE":
                ids = st.get("publicaly_available_post_id") or []
                post_id = str(ids[0]) if ids else publish_id
                url = f"https://www.tiktok.com/@{account.handle}/video/{post_id}" if ids else None
                return PublishResult(post_id, url)
            if status == "FAILED":
                raise PlatformError(f"TikTok: {st.get('fail_reason')}", retryable=False)
            await asyncio.sleep(5)
        raise PlatformError("TikTok publishing timed out")
