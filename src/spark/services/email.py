"""Email sending (console / SMTP / Resend) and campaign delivery with tracking."""

from __future__ import annotations

import asyncio
import logging
import re
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import Settings, get_settings
from spark.models import Brand, Contact, ContactList, EmailCampaign, EmailSend
from spark.security import token

log = logging.getLogger(__name__)
HREF_RE = re.compile(r'href="(https?://[^"]+)"')


class EmailSender:
    async def send(self, to: str, subject: str, html: str, text: str | None = None,
                   headers: dict | None = None) -> None:
        raise NotImplementedError


class ConsoleSender(EmailSender):
    sent: list[dict] = []

    async def send(self, to, subject, html, text=None, headers=None):
        ConsoleSender.sent.append({"to": to, "subject": subject, "html": html})
        log.info("[email] to=%s subject=%s", to, subject)


class SmtpSender(EmailSender):
    def __init__(self, s: Settings):
        self.s = s

    def _send_sync(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=30) as smtp:
            if self.s.smtp_tls:
                smtp.starttls()
            if self.s.smtp_user:
                smtp.login(self.s.smtp_user, self.s.smtp_password or "")
            smtp.send_message(msg)

    async def send(self, to, subject, html, text=None, headers=None):
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.s.email_from, to, subject
        for k, v in (headers or {}).items():
            msg[k] = v
        msg.set_content(text or re.sub(r"<[^>]+>", "", html))
        msg.add_alternative(html, subtype="html")
        await asyncio.to_thread(self._send_sync, msg)


class ResendSender(EmailSender):
    def __init__(self, s: Settings, http: httpx.AsyncClient | None = None):
        self.s = s
        self.http = http or httpx.AsyncClient(timeout=30)

    async def send(self, to, subject, html, text=None, headers=None):
        resp = await self.http.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {self.s.resend_api_key}"},
            json={"from": self.s.email_from, "to": [to], "subject": subject, "html": html,
                  "headers": headers or {}},
        )
        resp.raise_for_status()


def get_sender() -> EmailSender:
    s = get_settings()
    if s.email_backend == "smtp":
        return SmtpSender(s)
    if s.email_backend == "resend":
        return ResendSender(s)
    return ConsoleSender()


def render(campaign: EmailCampaign, brand: Brand, contact: Contact, send: EmailSend) -> str:
    base = get_settings().base_url.rstrip("/")
    body = campaign.body_html
    for key, value in {
        "first_name": contact.first_name or "there",
        "last_name": contact.last_name or "",
        "email": contact.email,
        "brand": brand.name,
    }.items():
        body = body.replace(f"{{{{{key}}}}}", value).replace(f"{{{{ {key} }}}}", value)
    body = HREF_RE.sub(
        lambda m: f'href="{base}/e/c/{send.token}?u={quote(m.group(1), safe="")}"', body
    )
    unsub = f"{base}/e/u/{contact.unsubscribe_token}"
    pre = (
        f'<div style="display:none;max-height:0;overflow:hidden">{campaign.preheader}</div>'
        if campaign.preheader
        else ""
    )
    return (
        f'{pre}<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;'
        f'margin:0 auto;padding:24px;color:#111;line-height:1.55">{body}'
        f'<hr style="border:none;border-top:1px solid #eee;margin:32px 0 12px">'
        f'<p style="font-size:12px;color:#888">You are receiving this from {brand.name}. '
        f'<a href="{unsub}" style="color:#888">Unsubscribe</a></p></div>'
        f'<img src="{base}/e/o/{send.token}.gif" width="1" height="1" alt="">'
    )


async def send_campaign(db: AsyncSession, campaign_id: int, sender: EmailSender | None = None) -> int:
    sender = sender or get_sender()
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or campaign.status == "sent" or not campaign.list_id:
        return 0
    brand = await db.get(Brand, campaign.brand_id)
    clist = await db.get(ContactList, campaign.list_id)
    campaign.status = "sending"
    await db.commit()
    already = set(
        (await db.execute(select(EmailSend.contact_id).where(EmailSend.campaign_id == campaign.id)))
        .scalars()
        .all()
    )
    base = get_settings().base_url.rstrip("/")
    sent = 0
    for contact in clist.contacts:
        if not contact.subscribed or contact.id in already:
            continue
        send = EmailSend(campaign_id=campaign.id, contact_id=contact.id, token=token(16))
        db.add(send)
        try:
            await sender.send(
                contact.email,
                campaign.subject,
                render(campaign, brand, contact, send),
                headers={
                    "List-Unsubscribe": f"<{base}/e/u/{contact.unsubscribe_token}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            )
            send.sent_at = datetime.now(UTC)
            sent += 1
        except Exception as e:  # keep going; record per-recipient failure
            log.warning("Email to %s failed: %s", contact.email, e)
            send.error = str(e)[:500]
        await db.commit()
    campaign.status = "sent"
    campaign.sent_at = datetime.now(UTC)
    campaign.sent_count = (campaign.sent_count or 0) + sent
    await db.commit()
    return sent
