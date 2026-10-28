"""LinkedIn — OpenID Connect sign-in + Posts API (member profiles)."""

from urllib.parse import quote

from spark.config import get_settings
from spark.platforms._oauth import build_url, expires_at, token_request
from spark.platforms.base import (
    ConnectedAccount,
    Limits,
    OAuthStart,
    PlatformAdapter,
    PublishPayload,
    PublishResult,
    register,
)

REST = "https://api.linkedin.com/rest"
VERSION = "202601"


@register
class LinkedInAdapter(PlatformAdapter):
    name = "linkedin"
    label = "LinkedIn"
    limits = Limits(max_chars=3000, max_media=9)
    docs_url = "https://www.linkedin.com/developers/apps"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.linkedin_client_id and s.linkedin_client_secret)

    def _headers(self, account) -> dict:
        return {
            "Authorization": f"Bearer {account.access_token}",
            "LinkedIn-Version": VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def oauth_start(self, state: str) -> OAuthStart:
        return OAuthStart(
            build_url(
                "https://www.linkedin.com/oauth/v2/authorization",
                {
                    "response_type": "code",
                    "client_id": get_settings().linkedin_client_id,
                    "redirect_uri": self.redirect_uri(),
                    "scope": "openid profile w_member_social",
                    "state": state,
                },
            )
        )

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        s = get_settings()
        tok = await token_request(
            self.http,
            "https://www.linkedin.com/oauth/v2/accessToken",
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri(),
                "client_id": s.linkedin_client_id,
                "client_secret": s.linkedin_client_secret,
            },
        )
        me = self.check(
            await self.http.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {tok['access_token']}"},
            )
        ).json()
        return [
            ConnectedAccount(
                external_id=me["sub"],
                handle=me.get("name") or me["sub"],
                display_name=me.get("name"),
                avatar_url=me.get("picture"),
                access_token=tok["access_token"],
                refresh_token=tok.get("refresh_token"),
                expires_at=expires_at(tok.get("expires_in")),
                extra={"author": f"urn:li:person:{me['sub']}"},
            )
        ]

    async def refresh(self, account) -> bool:
        if not account.refresh_token:
            return False
        s = get_settings()
        tok = await token_request(
            self.http,
            "https://www.linkedin.com/oauth/v2/accessToken",
            {
                "grant_type": "refresh_token",
                "refresh_token": account.refresh_token,
                "client_id": s.linkedin_client_id,
                "client_secret": s.linkedin_client_secret,
            },
        )
        account.access_token = tok["access_token"]
        account.refresh_token = tok.get("refresh_token", account.refresh_token)
        account.token_expires_at = expires_at(tok.get("expires_in"))
        return True

    async def _upload(self, account, payload, m) -> str:
        author = account.extra["author"]
        kind = "videos" if m.is_video else "images"
        data = payload.media_path(m).read_bytes()
        req = {"owner": author}
        if m.is_video:
            req |= {"fileSizeBytes": len(data), "uploadCaptions": False, "uploadThumbnail": False}
        init = self.check(
            await self.http.post(
                f"{REST}/{kind}?action=initializeUpload",
                headers=self._headers(account),
                json={"initializeUploadRequest": req},
            )
        ).json()["value"]
        if m.is_video:
            etags = []
            for inst in init["uploadInstructions"]:
                part = data[inst["firstByte"] : inst["lastByte"] + 1]
                r = self.check(await self.http.put(inst["uploadUrl"], content=part))
                etags.append(r.headers.get("etag"))
            self.check(
                await self.http.post(
                    f"{REST}/videos?action=finalizeUpload",
                    headers=self._headers(account),
                    json={
                        "finalizeUploadRequest": {
                            "video": init["video"],
                            "uploadToken": init.get("uploadToken", ""),
                            "uploadedPartIds": etags,
                        }
                    },
                )
            )
            return init["video"]
        self.check(
            await self.http.put(
                init["uploadUrl"],
                content=data,
                headers={"Authorization": f"Bearer {account.access_token}"},
            )
        )
        return init["image"]

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        author = account.extra["author"]
        body: dict = {
            "author": author,
            "commentary": payload.text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if payload.media:
            ids = [await self._upload(account, payload, m) for m in payload.media]
            if len(ids) == 1:
                body["content"] = {"media": {"id": ids[0]}}
            else:
                body["content"] = {"multiImage": {"images": [{"id": i} for i in ids]}}
        elif payload.link:
            body["content"] = {"article": {"source": payload.link, "title": payload.link}}
        resp = self.check(
            await self.http.post(f"{REST}/posts", headers=self._headers(account), json=body)
        )
        urn = resp.headers.get("x-restli-id", "")
        return PublishResult(urn, f"https://www.linkedin.com/feed/update/{quote(urn)}")
