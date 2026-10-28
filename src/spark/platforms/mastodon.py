"""Mastodon (any instance) — instance URL + personal access token."""

import asyncio
import logging

from spark.platforms.base import (
    ConnectedAccount,
    Limits,
    MetricsSnapshot,
    PlatformAdapter,
    PlatformError,
    PublishPayload,
    PublishResult,
    register,
)

log = logging.getLogger(__name__)


@register
class MastodonAdapter(PlatformAdapter):
    name = "mastodon"
    label = "Mastodon"
    limits = Limits(max_chars=500, max_media=4)
    connect_mode = "credentials"
    credential_fields = (
        ("instance", "Instance URL (e.g. https://mastodon.social)"),
        ("access_token", "Access token (Preferences → Development → New application)"),
    )

    async def connect_with_credentials(self, data: dict[str, str]) -> list[ConnectedAccount]:
        instance = data["instance"].strip().rstrip("/")
        if not instance.startswith("http"):
            instance = f"https://{instance}"
        tok = data["access_token"].strip()
        me = self.check(
            await self.http.get(
                f"{instance}/api/v1/accounts/verify_credentials",
                headers={"Authorization": f"Bearer {tok}"},
            )
        ).json()
        return [
            ConnectedAccount(
                external_id=me["id"],
                handle=f"{me['acct']}@{instance.split('//')[1]}",
                display_name=me.get("display_name"),
                avatar_url=me.get("avatar"),
                access_token=tok,
                followers=me.get("followers_count"),
                extra={"instance": instance},
            )
        ]

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        base = account.extra["instance"]
        auth = {"Authorization": f"Bearer {account.access_token}"}
        media_ids = []
        for m in payload.media:
            resp = self.check(
                await self.http.post(
                    f"{base}/api/v2/media",
                    headers=auth,
                    files={"file": (m.filename, payload.media_path(m).read_bytes(), m.content_type)},
                    data={"description": m.alt_text or ""},
                )
            )
            media = resp.json()
            # 202 => still processing (video); poll until url is set
            for _ in range(30):
                if resp.status_code != 202 and media.get("url"):
                    break
                await asyncio.sleep(2)
                resp = self.check(await self.http.get(f"{base}/api/v1/media/{media['id']}", headers=auth))
                media = resp.json()
            media_ids.append(media["id"])
        text = payload.text
        if payload.link and payload.link not in text:
            text = f"{text}\n\n{payload.link}"
        res = self.check(
            await self.http.post(
                f"{base}/api/v1/statuses",
                headers=auth,
                json={"status": text, "media_ids": media_ids},
            )
        ).json()
        if payload.first_comment:
            try:
                self.check(await self.http.post(
                    f"{base}/api/v1/statuses", headers=auth,
                    json={"status": payload.first_comment, "in_reply_to_id": res["id"]},
                ))
            except PlatformError as e:
                log.warning("Mastodon first comment failed for %s: %s", res["id"], e)
        return PublishResult(res["id"], res.get("url"))

    async def fetch_metrics(self, account, remote_ids):
        base = account.extra["instance"]
        out = []
        for rid in remote_ids:
            try:
                s = self.check(
                    await self.http.get(
                        f"{base}/api/v1/statuses/{rid}",
                        headers={"Authorization": f"Bearer {account.access_token}"},
                    )
                ).json()
            except PlatformError:
                continue
            out.append(
                MetricsSnapshot(
                    remote_id=rid,
                    likes=s.get("favourites_count", 0),
                    comments=s.get("replies_count", 0),
                    shares=s.get("reblogs_count", 0),
                )
            )
        return out
