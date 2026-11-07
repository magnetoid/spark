"""Agent runs: one row per Janus run Spark started, with what it returned and what the team did with it."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.db import Base, TimestampMixin
from spark.models.core import User


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"
    KINDS = ("ask", "weekly_plan", "voice", "repurpose", "report")
    STATUSES = ("queued", "running", "waiting_approval", "completed", "failed", "cancelled")

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(24), default="ask")
    prompt: Mapped[str] = mapped_column(Text, default="")
    janus_run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    session_key: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    output: Mapped[str | None] = mapped_column(Text)  # the agent's final text
    proposal: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # parsed spark-proposal block, channels resolved
    events: Mapped[list] = mapped_column(JSON, default=list)  # the last events, trimmed
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User | None] = relationship(lazy="selectin")
