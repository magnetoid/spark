"""Telegram channels/groups via a bot (bot must be an admin of the channel)."""

import json

from spark.platforms.base import (
    ConnectedAccount,
    Limits,
    PlatformAdapter,
    PlatformError,
    PublishPayload,
    PublishResult,
    register,
)


@register
class TelegramAdapter(PlatformAdapter):
    name = "telegram"
    label = "Telegram"
    limits = Limits(max_chars=4096, max_media=10)
    connect_mode = "credentials"
    credential_fields = (
        ("bot_token", "Bot token from @BotFather"),
        ("chat_id", "Channel @username or numeric chat id"),
    )

    def _api(self, tok: str, method: str) -> str:
        return f"https://api.telegram.org/bot{tok}/{method}"

    async def _call(self, tok: str, method: str, **kwargs) -> dict:
        resp = await self.http.post(self._api(tok, method), **kwargs)
        data = resp.json()
        if not data.get("ok"):
            code = data.get("error_code", resp.status_code)
            raise PlatformError(
                f"Telegram {method}: {data.get('description')}", retryable=code == 429 or code >= 500
            )
        return data["result"]

    async def connect_with_credentials(self, data: dict[str, str]) -> list[ConnectedAccount]:
        tok, chat = data["bot_token"].strip(), data["chat_id"].strip()
        info = await self._call(tok, "getChat", json={"chat_id": chat})
        count = await self._call(tok, "getChatMemberCount", json={"chat_id": chat})
        return [
            ConnectedAccount(
                external_id=str(info["id"]),
                handle=info.get("username") or info.get("title") or chat,
                display_name=info.get("title"),
                access_token=tok,
                followers=count,
                extra={"chat_id": chat, "username": info.get("username")},
            )
        ]

    async def publish(self, account, payload: PublishPayload) -> PublishResult:
        tok, chat = account.access_token, account.extra["chat_id"]
        text = payload.text
        if payload.link and payload.link not in text:
            text = f"{text}\n\n{payload.link}"
        media = payload.media
        if not media:
            msg = await self._call(tok, "sendMessage", json={"chat_id": chat, "text": text})
        elif len(media) == 1:
            m = media[0]
            method, field = ("sendVideo", "video") if m.is_video else ("sendPhoto", "photo")
            msg = await self._call(
                tok,
                method,
                data={"chat_id": chat, "caption": text[:1024]},
                files={field: (m.filename, payload.media_path(m).read_bytes(), m.content_type)},
            )
        else:
            files, group = {}, []
            for i, m in enumerate(media):
                key = f"file{i}"
                files[key] = (m.filename, payload.media_path(m).read_bytes(), m.content_type)
                item = {"type": "video" if m.is_video else "photo", "media": f"attach://{key}"}
                if i == 0:
                    item["caption"] = text[:1024]
                group.append(item)
            msgs = await self._call(
                tok,
                "sendMediaGroup",
                data={"chat_id": chat, "media": json.dumps(group)},
                files=files,
            )
            msg = msgs[0]
        mid = str(msg["message_id"])
        username = account.extra.get("username")
        return PublishResult(mid, f"https://t.me/{username}/{mid}" if username else None)
