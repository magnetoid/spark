"""X (Twitter) API v2 — OAuth 2.0 with PKCE, media upload v2, public metrics."""

import logging

from spark.config import get_settings
from spark.platforms._oauth import (
    basic_auth,
    build_url,
    expires_at,
    pkce_pair,
    token_request,
)
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

log = logging.getLogger(__name__)
API = "https://api.x.com/2"
SCOPES = "tweet.read tweet.write users.read media.write offline.access"
CHUNK = 4 * 1024 * 1024


@register
class XAdapter(PlatformAdapter):
    name = "x"
    label = "X / Twitter"
    limits = Limits(max_chars=280, max_media=4)
    docs_url = "https://developer.x.com/en/portal/dashboard"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.x_client_id and s.x_client_secret)

    def _auth(self) -> str:
        s = get_settings()
        return basic_auth(s.x_client_id or "", s.x_client_secret or "")

    def oauth_start(self, state: str) -> OAuthStart:
        verifier, challenge = pkce_pair()
        url = build_url(
            "https://x.com/i/oauth2/authorize",
            {
                "response_type": "code",
                "client_id": get_settings().x_client_id,
                "redirect_uri": self.redirect_uri(),
                "scope": SCOPES,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        return OAuthStart(url=url, session_data={"verifier": verifier})

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        tok = await token_request(
            self.http,
            f"{API}/oauth2/token",
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri(),
                "code_verifier": session_data["verifier"],
            },
            {"Authorization": self._auth()},
        )
        me = self.check(
            await self.http.get(
                f"{API}/users/me",
                params={"user.fields": "profile_image_url,public_metrics"},
                headers={"Authorization": f"Bearer {tok['access_token']}"},
            )
        ).json()["data"]
        return [
            ConnectedAccount(
                external_id=me["id"],
                handle=me["username"],
                display_name=me.get("name"),
                avatar_url=me.get("profile_image_url"),
                access_token=tok["access_token"],
                refresh_token=tok.get("refresh_token"),
                expires_at=expires_at(tok.get("expires_in")),
                followers=me.get("public_metrics", {}).get("followers_count"),
            )
        ]

    async def refresh(self, account) -> bool:
        if not account.refresh_token:
            return False
        tok = await token_request(
            self.http,
            f"{API}/oauth2/token",
            {"grant_type": "refresh_token", "refresh_token": account.refresh_token},
            {"Authorization": self._auth()},
        )
        account.access_token = tok["access_token"]
        account.refresh_token = tok.get("refresh_token", account.refresh_token)
        account.token_expires_at = expires_at(tok.get("expires_in"))
        return True

    async def _upload(self, headers: dict, payload: PublishPayload, m) -> str:
        data = payload.media_path(m).read_bytes()
        if not m.is_video:
            category = "tweet_gif" if m.content_type == "image/gif" else "tweet_image"
            resp = self.check(
                await self.http.post(
                    f"{API}/media/upload",
                    headers=headers,
                    files={"media": (m.filename, data, m.content_type)},
                    data={"media_category": category},
                )
            )
            return resp.json()["data"]["id"]

        init = self.check(
            await self.http.post(
                f"{API}/media/upload/initialize",
                headers=headers,
                json={
                    "media_type": m.content_type,
                    "total_bytes": len(data),
                    "media_category": "tweet_video",
                },
            )
        ).json()["data"]
        media_id = init["id"]
        for i in range(0, len(data), CHUNK):
            self.check(
                await self.http.post(
                    f"{API}/media/upload/{media_id}/append",
                    headers=headers,
                    files={"media": ("chunk", data[i : i + CHUNK], "application/octet-stream")},
                    data={"segment_index": str(i // CHUNK)},
                )
            )
        fin = self.check(
            await self.http.post(f"{API}/media/upload/{media_id}/finalize", headers=headers)
        ).json()["data"]
        await self._wait_processing(headers, media_id, fin.get("processing_info"))
        return media_id

    async def _wait_processing(self, headers, media_id, info) -> None:
        import asyncio

        for _ in range(60):
            if not info or info.get("state") == "succeeded":
                return
            if info.get("state") == "failed":
                raise PlatformError(f"X video processing failed: {info}", retryable=False)
            await asyncio.sleep(info.get("check_after_secs", 3))
            info = (
                self.check(
                    await self.http.get(
                        f"{API}/media/upload",
                        headers=headers,
                        params={"command": "STATUS", "media_id": media_id},
                    )
                )
                .json()["data"]
                .get("processing_info")
            )
        raise PlatformError("X video processing timed out")

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        headers = {"Authorization": f"Bearer {account.access_token}"}
        body: dict = {"text": payload.text}
        if payload.media:
            ids = [await self._upload(headers, payload, m) for m in payload.media]
            body["media"] = {"media_ids": ids}
        data = self.check(await self.http.post(f"{API}/tweets", headers=headers, json=body)).json()
        tweet_id = data["data"]["id"]
        if payload.first_comment:
            # First comment = a reply to the fresh tweet; a failure here must not undo the post.
            try:
                self.check(await self.http.post(
                    f"{API}/tweets", headers=headers,
                    json={"text": payload.first_comment, "reply": {"in_reply_to_tweet_id": tweet_id}},
                ))
            except PlatformError as e:
                log.warning("X first comment failed for %s: %s", tweet_id, e)
        return PublishResult(tweet_id, f"https://x.com/{account.handle}/status/{tweet_id}")

    async def fetch_metrics(self, account, remote_ids):
        out = []
        for i in range(0, len(remote_ids), 100):
            resp = self.check(
                await self.http.get(
                    f"{API}/tweets",
                    headers={"Authorization": f"Bearer {account.access_token}"},
                    params={
                        "ids": ",".join(remote_ids[i : i + 100]),
                        "tweet.fields": "public_metrics",
                    },
                )
            )
            for t in resp.json().get("data", []):
                pm = t.get("public_metrics", {})
                out.append(
                    MetricsSnapshot(
                        remote_id=t["id"],
                        impressions=pm.get("impression_count", 0),
                        likes=pm.get("like_count", 0),
                        comments=pm.get("reply_count", 0),
                        shares=pm.get("retweet_count", 0) + pm.get("quote_count", 0),
                    )
                )
        return out
