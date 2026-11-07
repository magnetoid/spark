"""Reports for a period and the daily follower counts they draw on."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
