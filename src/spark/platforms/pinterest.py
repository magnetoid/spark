"""Pinterest API v5 — each board is connected as its own account."""

from spark.config import get_settings
from spark.platforms._oauth import basic_auth, build_url, expires_at, token_request
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

API = "https://api.pinterest.com/v5"


@register
class PinterestAdapter(PlatformAdapter):
    name = "pinterest"
    label = "Pinterest"
    limits = Limits(max_chars=500, max_media=1, supports_video=False, requires_media=True)
    docs_url = "https://developers.pinterest.com/apps/"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.pinterest_client_id and s.pinterest_client_secret)

    def _auth(self) -> str:
        s = get_settings()
        return basic_auth(s.pinterest_client_id or "", s.pinterest_client_secret or "")

    def oauth_start(self, state: str) -> OAuthStart:
        return OAuthStart(
            build_url(
                "https://www.pinterest.com/oauth/",
                {
                    "client_id": get_settings().pinterest_client_id,
                    "redirect_uri": self.redirect_uri(),
                    "response_type": "code",
                    "scope": "boards:read,pins:read,pins:write,user_accounts:read",
                    "state": state,
                },
            )
        )

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        tok = await token_request(
            self.http,
            f"{API}/oauth/token",
            {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri()},
            {"Authorization": self._auth()},
        )
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        me = self.check(await self.http.get(f"{API}/user_account", headers=h)).json()
        boards = self.check(
            await self.http.get(f"{API}/boards", headers=h, params={"page_size": 100})
        ).json()
        return [
            ConnectedAccount(
                external_id=b["id"],
                handle=f"{me['username']} / {b['name']}",
                display_name=b["name"],
                avatar_url=me.get("profile_image"),
                access_token=tok["access_token"],
                refresh_token=tok.get("refresh_token"),
                expires_at=expires_at(tok.get("expires_in")),
                followers=me.get("follower_count"),
                extra={"board_id": b["id"], "username": me["username"]},
            )
            for b in boards.get("items", [])
        ]

    async def refresh(self, account) -> bool:
        if not account.refresh_token:
            return False
        tok = await token_request(
            self.http,
            f"{API}/oauth/token",
            {"grant_type": "refresh_token", "refresh_token": account.refresh_token},
            {"Authorization": self._auth()},
        )
        account.access_token = tok["access_token"]
        account.token_expires_at = expires_at(tok.get("expires_in"))
        return True

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        m = payload.media[0]
        title, _, rest = payload.text.partition("\n")
        body = {
            "board_id": account.extra["board_id"],
            "title": title[:100],
            "description": (rest.strip() or payload.text)[:500],
            "media_source": {"source_type": "image_url", "url": payload.media_url(m)},
            "alt_text": m.alt_text,
        }
        if payload.link:
            body["link"] = payload.link
        res = self.check(
            await self.http.post(
                f"{API}/pins",
                headers={"Authorization": f"Bearer {account.access_token}"},
                json=body,
            )
        ).json()
        return PublishResult(res["id"], f"https://www.pinterest.com/pin/{res['id']}/")

    async def fetch_metrics(self, account, remote_ids):
        out = []
        for rid in remote_ids:
            try:
                d = self.check(
                    await self.http.get(
                        f"{API}/pins/{rid}",
                        headers={"Authorization": f"Bearer {account.access_token}"},
                        params={"pin_metrics": "true"},
                    )
                ).json()
            except PlatformError:
                continue
            lt = (d.get("pin_metrics") or {}).get("lifetime_metrics", {})
            out.append(
                MetricsSnapshot(
                    remote_id=rid,
                    impressions=lt.get("impression", 0),
                    likes=lt.get("reaction", 0),
                    comments=lt.get("comment", 0),
                    shares=lt.get("save", 0),
                    clicks=lt.get("pin_click", 0) + lt.get("outbound_click", 0),
                )
            )
        return out
