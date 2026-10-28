"""Bluesky (AT Protocol) — handle + app password."""

import re
from datetime import UTC, datetime

from spark.platforms.base import (
    AuthExpired,
    ConnectedAccount,
    Limits,
    MetricsSnapshot,
    PlatformAdapter,
    PublishPayload,
    PublishResult,
    register,
)

URL_RE = re.compile(rb"https?://[^\s\)\]]+")
TAG_RE = re.compile(rb"(?:^|\s)(#[^\d\s]\S*)")
APPVIEW = "https://public.api.bsky.app/xrpc"


def facets(text: str) -> list[dict]:
    """Link and hashtag facets with UTF-8 byte offsets, as the protocol requires."""
    raw = text.encode()
    out = []
    for m in URL_RE.finditer(raw):
        out.append(
            {
                "index": {"byteStart": m.start(), "byteEnd": m.end()},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group().decode()}],
            }
        )
    for m in TAG_RE.finditer(raw):
        tag = m.group(1)
        out.append(
            {
                "index": {"byteStart": m.start(1), "byteEnd": m.end(1)},
                "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag[1:].decode()}],
            }
        )
    return out


@register
class BlueskyAdapter(PlatformAdapter):
    name = "bluesky"
    label = "Bluesky"
    limits = Limits(max_chars=300, max_media=4, supports_video=False)
    connect_mode = "credentials"
    credential_fields = (
        ("handle", "Handle (e.g. brand.bsky.social)"),
        ("app_password", "App password (Settings → App passwords)"),
        ("service", "PDS URL (optional, default https://bsky.social)"),
    )
    docs_url = "https://bsky.app/settings/app-passwords"

    async def _session(self, service: str, handle: str, password: str) -> dict:
        resp = await self.http.post(
            f"{service}/xrpc/com.atproto.server.createSession",
            json={"identifier": handle, "password": password},
        )
        if resp.status_code in (400, 401):
            raise AuthExpired(f"Bluesky login failed: {resp.text[:200]}")
        return self.check(resp).json()

    async def connect_with_credentials(self, data: dict[str, str]) -> list[ConnectedAccount]:
        service = (data.get("service") or "https://bsky.social").rstrip("/")
        handle = data["handle"].strip().lstrip("@")
        sess = await self._session(service, handle, data["app_password"].strip())
        prof = (
            await self.http.get(f"{APPVIEW}/app.bsky.actor.getProfile", params={"actor": sess["did"]})
        ).json()
        return [
            ConnectedAccount(
                external_id=sess["did"],
                handle=sess["handle"],
                display_name=prof.get("displayName"),
                avatar_url=prof.get("avatar"),
                access_token=data["app_password"].strip(),
                followers=prof.get("followersCount"),
                extra={"service": service},
            )
        ]

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        service = account.extra.get("service", "https://bsky.social")
        sess = await self._session(service, account.handle, account.access_token)
        auth = {"Authorization": f"Bearer {sess['accessJwt']}"}
        text = payload.text
        if payload.link and payload.link not in text:
            text = f"{text}\n{payload.link}".strip()
        record: dict = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "langs": ["en"],
        }
        if f := facets(text):
            record["facets"] = f
        if payload.media:
            images = []
            for m in payload.media:
                blob = self.check(
                    await self.http.post(
                        f"{service}/xrpc/com.atproto.repo.uploadBlob",
                        content=payload.media_path(m).read_bytes(),
                        headers={**auth, "Content-Type": m.content_type},
                    )
                ).json()["blob"]
                images.append({"alt": m.alt_text or "", "image": blob})
            record["embed"] = {"$type": "app.bsky.embed.images", "images": images}
        res = self.check(
            await self.http.post(
                f"{service}/xrpc/com.atproto.repo.createRecord",
                headers=auth,
                json={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record},
            )
        ).json()
        rkey = res["uri"].rsplit("/", 1)[-1]
        return PublishResult(res["uri"], f"https://bsky.app/profile/{account.handle}/post/{rkey}")

    async def fetch_metrics(self, account, remote_ids):
        out = []
        for i in range(0, len(remote_ids), 25):
            resp = await self.http.get(
                f"{APPVIEW}/app.bsky.feed.getPosts", params={"uris": remote_ids[i : i + 25]}
            )
            for p in self.check(resp).json().get("posts", []):
                out.append(
                    MetricsSnapshot(
                        remote_id=p["uri"],
                        likes=p.get("likeCount", 0),
                        comments=p.get("replyCount", 0),
                        shares=p.get("repostCount", 0) + p.get("quoteCount", 0),
                    )
                )
        return out
