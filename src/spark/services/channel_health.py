"""Channel health: is each connected channel able to publish, and will it still be next week?

`health` reads what Spark already knows about a channel. `check` compares that with the last
alert sent (`SocialAccount.alerted_for`) and writes one outbox event per change, so the team
hears about a broken channel once, about running-out access at 7, 3 and 1 days, and once more
when it works again. The outbox turns those events into chat messages, emails and webhooks.

`sync_channels` asks Zernio about every channel once an hour; Zernio's account webhooks and a
publish that failed for lack of access call `check` too, so all three agree.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import SocialAccount
from spark.services import outbox

log = logging.getLogger(__name__)

STATES = ("ok", "expiring", "reconnect", "paused")
EXPIRY_STEPS = (7, 3, 1)  # days before access runs out when the team is told
WARN = timedelta(days=EXPIRY_STEPS[0])
RECONNECT_ERRORS = ("Reconnect needed", "Disconnected in Zernio")


def _parse(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def expires_at(acc: SocialAccount) -> datetime | None:
    """When the channel's access runs out without anyone doing anything. None: it does not, or
    Spark renews it itself (a direct channel with a refresh token)."""
    if acc.provider == "zernio":
        return _parse((acc.extra or {}).get("token_expires_at"))
    if acc.refresh_token:
        return None
    return _parse(acc.token_expires_at)


def needs_reconnect(acc: SocialAccount) -> bool:
    return bool((acc.extra or {}).get("needs_reconnection")) or (acc.last_error or "").startswith(
        RECONNECT_ERRORS
    )


def health(acc: SocialAccount, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    exp = expires_at(acc)
    if needs_reconnect(acc) or (exp is not None and exp <= now):
        return "reconnect"
    if not acc.is_active:
        return "paused"  # switched off by the team
    if exp is not None and exp - now <= WARN:
        return "expiring"
    return "ok"


def _alert_key(acc: SocialAccount, now: datetime) -> tuple[str | None, int | None]:
    state = health(acc, now)
    if state == "reconnect":
        return "reconnect", None
    if state == "expiring":
        left = (expires_at(acc) - now).total_seconds() / 86400
        step = min(s for s in EXPIRY_STEPS if left <= s)
        return f"expiring:{step}", int(left)
    return None, None


def channel_data(acc: SocialAccount, days_left: int | None = None) -> dict:
    exp = expires_at(acc)
    return {
        "channel": {
            "id": acc.id,
            "platform": acc.platform,
            "handle": acc.handle,
            "provider": acc.provider,
            "health": health(acc),
            "days_left": days_left,
            "expires_at": exp.isoformat() if exp else None,
            "error": acc.last_error,
            "url": f"{get_settings().base_url.rstrip('/')}/channels",
        }
    }


def check(db: AsyncSession, acc: SocialAccount, now: datetime | None = None) -> str | None:
    """Record the check and announce a change. Returns the event written, if any. The caller commits."""
    now = now or datetime.now(UTC)
    acc.checked_at = now
    key, days_left = _alert_key(acc, now)
    if key == acc.alerted_for:
        return None
    before, acc.alerted_for = acc.alerted_for, key
    if key is None:
        if before is None:
            return None
        event = "channel.recovered"
    elif key == "reconnect":
        event = "channel.reconnect_needed"
    else:
        event = "channel.expiring"
    outbox.emit(db, acc.brand_id, event, channel_data(acc, days_left))
    return event


def apply_zernio(acc: SocialAccount, extra: dict) -> None:
    """Take what Zernio says about a channel: does it need reconnecting, when does access end."""
    flagged = bool(extra.get("needs_reconnection"))
    acc.extra = {
        **(acc.extra or {}),
        "needs_reconnection": flagged,
        "token_expires_at": extra.get("token_expires_at"),
    }
    if not flagged and (acc.last_error or "").startswith("Reconnect needed"):
        acc.last_error = None


async def sync_channels(db: AsyncSession) -> int:
    """One call to Zernio for every channel of every brand, then a check of each channel.
    Returns how many alerts were written."""
    from spark.platforms.zernio import ZernioAdapter

    rows = (await db.execute(select(SocialAccount))).scalars().all()
    zernio = ZernioAdapter()
    if zernio.is_configured() and any(a.provider == "zernio" for a in rows):
        try:
            remote = {c.external_id: c for _, c in await zernio.list_accounts()}
        except Exception:  # Zernio down: keep what is known, check again next hour
            log.warning("Could not read channels from Zernio", exc_info=True)
            remote = {}
        for acc in rows:
            if acc.provider == "zernio" and acc.external_id in remote:
                apply_zernio(acc, remote[acc.external_id].extra)
    written = sum(1 for acc in rows if check(db, acc))
    await db.commit()
    return written
