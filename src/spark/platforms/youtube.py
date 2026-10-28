"""YouTube Data API v3 — resumable video uploads (Shorts when vertical & < 3 min)."""

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

API = "https://www.googleapis.com/youtube/v3"
TOKEN = "https://oauth2.googleapis.com/token"


@register
class YouTubeAdapter(PlatformAdapter):
    name = "youtube"
    label = "YouTube"
    limits = Limits(max_chars=5000, max_media=1, requires_media=True)
    docs_url = "https://console.cloud.google.com/apis/credentials"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.google_client_id and s.google_client_secret)

    def validate(self, payload: PublishPayload) -> list[str]:
        problems = super().validate(payload)
        if payload.media and not payload.media[0].is_video:
            problems.append("YouTube: attach a video")
        return problems

    def oauth_start(self, state: str) -> OAuthStart:
        return OAuthStart(
            build_url(
                "https://accounts.google.com/o/oauth2/v2/auth",
                {
                    "client_id": get_settings().google_client_id,
                    "redirect_uri": self.redirect_uri(),
                    "response_type": "code",
                    "scope": "https://www.googleapis.com/auth/youtube.upload "
                    "https://www.googleapis.com/auth/youtube.readonly",
                    "access_type": "offline",
                    "prompt": "consent",
                    "state": state,
                },
            )
        )

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        s = get_settings()
        tok = await token_request(
            self.http,
            TOKEN,
            {
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": self.redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        chans = self.check(
            await self.http.get(
                f"{API}/channels",
                params={"part": "snippet,statistics", "mine": "true"},
                headers={"Authorization": f"Bearer {tok['access_token']}"},
            )
        ).json()
        return [
            ConnectedAccount(
                external_id=c["id"],
                handle=c["snippet"].get("customUrl") or c["snippet"]["title"],
                display_name=c["snippet"]["title"],
                avatar_url=c["snippet"].get("thumbnails", {}).get("default", {}).get("url"),
                access_token=tok["access_token"],
                refresh_token=tok.get("refresh_token"),
                expires_at=expires_at(tok.get("expires_in")),
                followers=int(c.get("statistics", {}).get("subscriberCount", 0) or 0),
                extra={"privacy_status": "public"},
            )
            for c in chans.get("items", [])
        ]

    async def refresh(self, account) -> bool:
        if not account.refresh_token:
            return False
        s = get_settings()
        tok = await token_request(
            self.http,
            TOKEN,
            {
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "refresh_token": account.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        account.access_token = tok["access_token"]
        account.token_expires_at = expires_at(tok.get("expires_in"))
        return True

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        m = payload.media[0]
        data = payload.media_path(m).read_bytes()
        title, _, rest = payload.text.partition("\n")
        description = rest.strip()
        if payload.link:
            description = f"{description}\n\n{payload.link}".strip()
        meta = {
            "snippet": {"title": title[:100] or m.filename, "description": description[:5000]},
            "status": {
                "privacyStatus": account.extra.get("privacy_status", "public"),
                "selfDeclaredMadeForKids": False,
            },
        }
        h = {"Authorization": f"Bearer {account.access_token}"}
        init = self.check(
            await self.http.post(
                "https://www.googleapis.com/upload/youtube/v3/videos",
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={
                    **h,
                    "X-Upload-Content-Type": m.content_type,
                    "X-Upload-Content-Length": str(len(data)),
                },
                json=meta,
            )
        )
        location = init.headers.get("location")
        if not location:
            raise PlatformError("YouTube did not return an upload URL")
        res = self.check(
            await self.http.put(location, content=data, headers={**h, "Content-Type": m.content_type})
        ).json()
        return PublishResult(res["id"], f"https://www.youtube.com/watch?v={res['id']}")

    async def fetch_metrics(self, account, remote_ids):
        out = []
        for i in range(0, len(remote_ids), 50):
            resp = self.check(
                await self.http.get(
                    f"{API}/videos",
                    params={"part": "statistics", "id": ",".join(remote_ids[i : i + 50])},
                    headers={"Authorization": f"Bearer {account.access_token}"},
                )
            )
            for v in resp.json().get("items", []):
                st = v.get("statistics", {})
                out.append(
                    MetricsSnapshot(
                        remote_id=v["id"],
                        impressions=int(st.get("viewCount", 0)),
                        likes=int(st.get("likeCount", 0)),
                        comments=int(st.get("commentCount", 0)),
                    )
                )
        return out
