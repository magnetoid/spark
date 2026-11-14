"""Reports for a period and the daily follower counts they draw on."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from spark.db import Base, TimestampMixin


class FollowerSnapshot(Base):
    """One follower count per account per day, from Zernio's follower stats when it has them, else the
    account's last known count. The report's growth line reads these."""

    __tablename__ = "follower_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "day", name="uq_follower_snapshot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date, index=True)
    followers: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="spark")  # spark | zernio
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Report(TimestampMixin, Base):
    """A period's numbers frozen at the time the report was made, plus an optional AI summary."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ReportSchedule(TimestampMixin, Base):
    """A report made and emailed on a cadence: weekly (the last Monday to Sunday) or monthly (the
    last calendar month), at an hour of the brand's day, with a link that opens without login."""

    __tablename__ = "report_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    cadence: Mapped[str] = mapped_column(String(16), default="weekly")  # weekly | monthly
    hour: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    with_summary: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    share_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # The end of the last period sent, so a period goes out once even if the worker restarts
    last_period_end: Mapped[date | None] = mapped_column(Date)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
