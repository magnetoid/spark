"""What Spark tells the outside world: events on their way to chat and to webhook endpoints."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from spark.db import Base, utcnow


class OutboundEvent(Base):
    """Something that happened (a post failed, a review arrived), written in the same transaction
    as the change itself and picked up by the worker, so nothing is announced that did not happen."""

    __tablename__ = "outbound_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    # set when the worker took it: chat was told and webhook deliveries were queued
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class WebhookEndpoint(Base):
    """An address outside Spark that receives events as signed HTTP POSTs."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    # None: events of every brand
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2000))
    description: Mapped[str] = mapped_column(String(200), default="", server_default="")
    secret: Mapped[str] = mapped_column(Text)  # encrypted; signs every delivery
    events: Mapped[list] = mapped_column(JSON, default=list)  # empty: every event
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # in a row
    disabled_reason: Mapped[str | None] = mapped_column(String(500))
    last_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(500))
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )


class WebhookDelivery(Base):
    """One event on its way to one endpoint: what was sent, how often it was tried, the answer."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_deliveries_due", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[str] = mapped_column(String(40))
    event: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    response_status: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
