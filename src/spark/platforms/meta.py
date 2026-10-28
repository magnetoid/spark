"""Meta Graph API — Facebook Pages and Instagram professional accounts.

One Meta login connects every Page the user manages (Facebook adapter) and
every Instagram business/creator account linked to those Pages (Instagram).
Instagram fetches media by public URL, so SPARK_BASE_URL must be reachable.
"""

import asyncio

from spark.config import get_settings
from spark.platforms._oauth import build_url, token_request
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

GRAPH = "https://graph.facebook.com/v21.0"
SCOPES = ",".join(
    [
        "pages_show_list",
        "pages_manage_posts",
        "pages_read_engagement",
        "read_insights",
        "instagram_basic",
        "instagram_content_publish",
        "instagram_manage_insights",
        "business_management",
    ]
)


class _MetaBase(PlatformAdapter):
    docs_url = "https://developers.facebook.com/apps"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.meta_app_id and s.meta_app_secret)

    def oauth_start(self, state: str) -> OAuthStart:
        return OAuthStart(
            build_url(
                "https://www.facebook.com/v21.0/dialog/oauth",
                {
                    "client_id": get_settings().meta_app_id,
                    "redirect_uri": self.redirect_uri(),
                    "scope": SCOPES,
                    "state": state,
                    "response_type": "code",
                },
            )
        )

    async def _pages(self, code: str) -> list[dict]:
        s = get_settings()
        short = await token_request(
            self.http,
            f"{GRAPH}/oauth/access_token",
            {
                "client_id": s.meta_app_id,
                "client_secret": s.meta_app_secret,
                "redirect_uri": self.redirect_uri(),
                "code": code,
            },
        )
        long = await token_request(
            self.http,
            f"{GRAPH}/oauth/access_token",
            {
                "grant_type": "fb_exchange_token",
                "client_id": s.meta_app_id,
                "client_secret": s.meta_app_secret,
                "fb_exchange_token": short["access_token"],
            },
        )
        # Page tokens derived from a long-lived user token do not expire.
        resp = self.check(
            await self.http.get(
                f"{GRAPH}/me/accounts",
                params={
                    "access_token": long["access_token"],
                    "fields": "id,name,access_token,fan_count,picture{url},"
                    "instagram_business_account{id,username,profile_picture_url,followers_count}",
                    "limit": 100,
                },
            )
        )
        return resp.json().get("data", [])

    async def _get(self, path: str, token: str, **params) -> dict:
        return self.check(
            await self.http.get(f"{GRAPH}/{path}", params={"access_token": token, **params})
        ).json()

    async def _post(self, path: str, token: str, **data) -> dict:
        return self.check(
            await self.http.post(f"{GRAPH}/{path}", data={"access_token": token, **data})
        ).json()


@register
class FacebookAdapter(_MetaBase):
    name = "facebook"
    label = "Facebook Page"
    limits = Limits(max_chars=63206, max_media=10)

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        return [
            ConnectedAccount(
                external_id=p["id"],
                handle=p["name"],
                display_name=p["name"],
                avatar_url=p.get("picture", {}).get("data", {}).get("url"),
                access_token=p["access_token"],
                followers=p.get("fan_count"),
            )
            for p in await self._pages(code)
        ]

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        tok, page = account.access_token, account.external_id
        videos = [m for m in payload.media if m.is_video]
        if videos:
            res = await self._post(
                f"{page}/videos",
                tok,
                file_url=payload.media_url(videos[0]),
                description=payload.text,
            )
            vid = res["id"]
            return PublishResult(vid, f"https://www.facebook.com/{page}/videos/{vid}")
        data: dict = {"message": payload.text}
        if payload.link:
            data["link"] = payload.link
        if len(payload.media) == 1:
            res = await self._post(
                f"{page}/photos", tok, url=payload.media_url(payload.media[0]), caption=payload.text
            )
            pid = res.get("post_id") or res["id"]
            return PublishResult(pid, f"https://www.facebook.com/{pid}")
        for i, m in enumerate(payload.media):
            res = await self._post(
                f"{page}/photos", tok, url=payload.media_url(m), published="false"
            )
            data[f"attached_media[{i}]"] = f'{{"media_fbid":"{res["id"]}"}}'
        res = await self._post(f"{page}/feed", tok, **data)
        return PublishResult(res["id"], f"https://www.facebook.com/{res['id']}")

    async def fetch_metrics(self, account, remote_ids):
        out = []
        for rid in remote_ids:
            try:
                d = await self._get(
                    rid,
                    account.access_token,
                    fields="shares,reactions.summary(true),comments.summary(true),"
                    "insights.metric(post_impressions,post_clicks)",
                )
            except PlatformError:
                continue
            ins = {i["name"]: i["values"][0]["value"] for i in d.get("insights", {}).get("data", [])}
            out.append(
                MetricsSnapshot(
                    remote_id=rid,
                    impressions=ins.get("post_impressions", 0),
                    clicks=ins.get("post_clicks", 0),
                    likes=d.get("reactions", {}).get("summary", {}).get("total_count", 0),
                    comments=d.get("comments", {}).get("summary", {}).get("total_count", 0),
                    shares=d.get("shares", {}).get("count", 0),
                )
            )
        return out


@register
class InstagramAdapter(_MetaBase):
    name = "instagram"
    label = "Instagram"
    limits = Limits(max_chars=2200, max_media=10, requires_media=True)

    async def oauth_callback(self, code: str, session_data: dict) -> list[ConnectedAccount]:
        out = []
        for p in await self._pages(code):
            ig = p.get("instagram_business_account")
            if not ig:
                continue
            out.append(
                ConnectedAccount(
                    external_id=ig["id"],
                    handle=ig.get("username", ig["id"]),
                    display_name=ig.get("username"),
                    avatar_url=ig.get("profile_picture_url"),
                    access_token=p["access_token"],
                    followers=ig.get("followers_count"),
                    extra={"page_id": p["id"]},
                )
            )
        if not out:
            raise PlatformError(
                "No Instagram professional account is linked to your Facebook Pages",
                retryable=False,
            )
        return out

    async def _container(self, ig: str, tok: str, payload, m, *, carousel: bool) -> str:
        data: dict = {}
        if m.is_video:
            data |= {"media_type": "REELS", "video_url": payload.media_url(m)}
        else:
            data["image_url"] = payload.media_url(m)
        if carousel:
            data["is_carousel_item"] = "true"
        else:
            data["caption"] = payload.text
        res = await self._post(f"{ig}/media", tok, **data)
        await self._wait(res["id"], tok)
        return res["id"]

    async def _wait(self, container_id: str, tok: str) -> None:
        for _ in range(60):
            st = await self._get(container_id, tok, fields="status_code")
            code = st.get("status_code")
            if code in ("FINISHED", "PUBLISHED", None):
                return
            if code in ("ERROR", "EXPIRED"):
                raise PlatformError(f"Instagram media container {code}", retryable=False)
            await asyncio.sleep(5)
        raise PlatformError("Instagram media processing timed out")

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        ig, tok = account.external_id, account.access_token
        if len(payload.media) == 1:
            creation = await self._container(ig, tok, payload, payload.media[0], carousel=False)
        else:
            children = [
                await self._container(ig, tok, payload, m, carousel=True) for m in payload.media
            ]
            res = await self._post(
                f"{ig}/media",
                tok,
                media_type="CAROUSEL",
                children=",".join(children),
                caption=payload.text,
            )
            await self._wait(res["id"], tok)
            creation = res["id"]
        res = await self._post(f"{ig}/media_publish", tok, creation_id=creation)
        media_id = res["id"]
        link = (await self._get(media_id, tok, fields="permalink")).get("permalink")
        return PublishResult(media_id, link)

    async def fetch_metrics(self, account, remote_ids):
        out = []
        for rid in remote_ids:
            try:
                d = await self._get(rid, account.access_token, fields="like_count,comments_count")
                ins = await self._get(
                    f"{rid}/insights", account.access_token, metric="views,shares,saved"
                )
            except PlatformError:
                continue
            vals = {i["name"]: i["values"][0]["value"] for i in ins.get("data", [])}
            out.append(
                MetricsSnapshot(
                    remote_id=rid,
                    impressions=vals.get("views", 0),
                    likes=d.get("like_count", 0),
                    comments=d.get("comments_count", 0),
                    shares=vals.get("shares", 0) + vals.get("saved", 0),
                )
            )
        return out
