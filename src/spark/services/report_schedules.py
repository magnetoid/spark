"""Reports made and emailed on a schedule. Weekly covers the last Monday to Sunday, monthly the
last calendar month, both in the brand's timezone; each period is sent once, at or after the
schedule's hour, with a link that opens the report without an account."""

from __future__ import annotations

import html
import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.models import Brand, Report, ReportSchedule
from spark.services import ai as ai_svc
from spark.services import notify, reports
from spark.services.email import EmailSender, get_sender

log = logging.getLogger("spark.report_schedules")

CADENCES = ("weekly", "monthly")


def period_for(cadence: str, today: date) -> tuple[date, date]:
    """The last complete period before `today` (a date in the brand's timezone)."""
    if cadence == "monthly":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(days=7), monday - timedelta(days=1)


def _following(cadence: str, end: date) -> tuple[date, date]:
    start = end + timedelta(days=1)
    if cadence == "monthly":
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, nxt - timedelta(days=1)
    return start, start + timedelta(days=6)


def next_period(s: ReportSchedule, brand: Brand, now: datetime | None = None) -> dict:
    """The period the schedule sends next, and when (UTC)."""
    tz = ZoneInfo(brand.timezone or "UTC")
    now = now or datetime.now(UTC)
    start, end = period_for(s.cadence, now.astimezone(tz).date())
    if s.last_period_end and s.last_period_end >= end:
        start, end = _following(s.cadence, end)
    send = datetime.combine(end + timedelta(days=1), time(s.hour), tzinfo=tz)
    return {
        "start": start,
        "end": end,
        "days": (end - start).days + 1,
        "send_at": max(send, now).astimezone(UTC),
    }


def start_from_next(s: ReportSchedule, brand: Brand, now: datetime | None = None) -> None:
    """For a new schedule, or one whose cadence changed: the period that already ended counts as
    sent, unless its send time is still ahead today, so the first report is the next one and
    not last week's arriving within the hour."""
    tz = ZoneInfo(brand.timezone or "UTC")
    now = now or datetime.now(UTC)
    _, end = period_for(s.cadence, now.astimezone(tz).date())
    send = datetime.combine(end + timedelta(days=1), time(s.hour), tzinfo=tz)
    s.last_period_end = end if now >= send else None


def _fmt(n: int | float | None) -> str:
    return "–" if n is None else f"{n:,}"


def _email(brand: Brand, rep: Report, url: str, days: int) -> tuple[str, str]:
    d = rep.data or {}
    t, f, cmp = d.get("totals", {}), d.get("followers", {}), d.get("compare", {})

    def change(key: str) -> str:
        pct = (cmp.get(key) or {}).get("pct")
        return (
            f" ({'+' if pct >= 0 else ''}{pct:.0f}% vs the period before)"
            if pct is not None
            else ""
        )

    rows = [
        ("Posts published", f"{t.get('published', 0)}{change('published')}"),
        ("Seen", f"{_fmt(t.get('seen', t.get('impressions', 0)))}{change('seen')}"),
        (
            "Engagements",
            f"{_fmt(t.get('engagements', 0))} · {t.get('engagement_rate_pct', 0)}% rate",
        ),
        ("Link clicks", _fmt(t.get("link_clicks"))),
        ("Followers", f"{_fmt(f.get('end', 0))} ({f.get('delta', 0):+,})"),
    ]
    period = f"{rep.start:%d %b} – {rep.end:%d %b %Y}"
    summary = rep.summary or {}
    body = (
        (
            f'<p style="font-size:16px;font-weight:600;margin:0 0 12px">'
            f"{html.escape(summary['headline'])}</p>"
            if summary.get("headline")
            else ""
        )
        + '<table style="width:100%;border-collapse:collapse;font-size:14px">'
        + "".join(
            f'<tr><td style="padding:6px 0;color:#666;width:40%">{html.escape(k)}</td>'
            f'<td style="padding:6px 0;font-weight:600">{html.escape(v)}</td></tr>'
            for k, v in rows
        )
        + "</table>"
    )
    subject = f"[{brand.name}] Social media report, {period}"
    footer = (
        f"{html.escape(brand.name)} sends you this report through Spark. The link works for "
        f"{days} days. To stop receiving it, ask the team that manages {html.escape(brand.name)}."
    )
    return subject, notify.layout(
        f"{brand.name}: {period}",
        "The numbers for the period, with the full report a click away.",
        body,
        url,
        "Open the report",
        footer=footer,
    )


async def send_one(
    db: AsyncSession, s: ReportSchedule, brand: Brand, start: date, end: date, sender: EmailSender
) -> int:
    """Make the report, share it and email it. Returns how many emails went out."""
    label = "Weekly" if s.cadence == "weekly" else "Monthly"
    rep = await reports.create(
        db,
        brand,
        None,
        start,
        end,
        f"{brand.name} · {label} report · {start:%d %b} – {end:%d %b %Y}",
    )
    if s.with_summary:
        try:
            await reports.summarize(db, brand, rep)
        except ai_svc.AIUnavailable:
            pass  # the numbers go out without a written summary
        except Exception:  # noqa: BLE001  an AI hiccup must not hold back the report
            log.exception("Summary for report %s failed", rep.id)
    _, token = await reports.share(db, brand, rep, None, s.share_days)
    subject, body = _email(brand, rep, reports.report_url(token), s.share_days)
    sent, failed = 0, []
    for to in s.recipients or []:
        try:
            await sender.send(to, subject, body)
            sent += 1
        except Exception as e:  # noqa: BLE001  one bad address must not stop the others
            log.warning("Report email to %s failed: %s", to, e)
            failed.append(to)
    s.last_period_end = end
    s.last_sent_at = datetime.now(UTC)
    s.last_error = f"Could not send to {', '.join(failed)}"[:500] if failed else None
    await db.commit()
    return sent


async def send_due(
    db: AsyncSession, sender: EmailSender | None = None, now: datetime | None = None
) -> int:
    """Send every schedule whose period has ended and whose hour has come. Returns how many
    schedules sent a report."""
    sender = sender or get_sender()
    now = now or datetime.now(UTC)
    rows = (
        await db.execute(
            select(ReportSchedule, Brand)
            .join(Brand, Brand.id == ReportSchedule.brand_id)
            .where(ReportSchedule.is_active.is_(True))
            .order_by(ReportSchedule.id)
        )
    ).all()
    done = 0
    for s, brand in rows:
        local = now.astimezone(ZoneInfo(brand.timezone or "UTC"))
        start, end = period_for(s.cadence, local.date())
        if (s.last_period_end and s.last_period_end >= end) or local.hour < s.hour:
            continue
        try:
            await send_one(db, s, brand, start, end, sender)
            done += 1
        except Exception as e:  # noqa: BLE001  one brand's failure must not stop the rest
            await db.rollback()
            log.exception("Scheduled report %s failed", s.id)
            s.last_error = f"Could not make the report: {e}"[:500]
            await db.commit()
    return done
