"""The inbox: comments, messages, reviews and mentions kept in Spark, plus saved replies and rules."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.db import Base, TimestampMixin
from spark.models.core import User


class InboxItem(TimestampMixin, Base):
    """One thing someone said to the brand (or the brand said back)."""

    __tablename__ = "inbox_items"
    __table_args__ = (UniqueConstraint("account_id", "kind", "external_id", name="uq_inbox_item"),)
    KINDS = ("comment", "message", "review", "mention")
    STATUSES = ("open", "resolved", "archived")

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    thread_id: Mapped[str | None] = mapped_column(
        String(255), index=True
    )  # post id, conversation id, location
    parent_external_id: Mapped[str | None] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(8), default="incoming")  # incoming | outgoing
    author_external_id: Mapped[str | None] = mapped_column(String(255))
    author_name: Mapped[str] = mapped_column(String(200), default="")
    author_handle: Mapped[str | None] = mapped_column(String(200))
    author_picture: Mapped[str | None] = mapped_column(String(1000))
    text: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[int | None] = mapped_column(Integer)
    permalink: Mapped[str | None] = mapped_column(String(1000))
    post: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {id, content, image, permalink} for comments
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    sentiment: Mapped[str | None] = mapped_column(String(16))  # positive | neutral | negative
    intent: Mapped[str | None] = mapped_column(
        String(24)
    )  # question | complaint | praise | lead | spam | other
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    suggested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    draft_reply: Mapped[str | None] = mapped_column(Text)  # prepared by a rule, waits for a person
    draft_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("inbox_rules.id", ondelete="SET NULL")
    )
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_text: Mapped[str | None] = mapped_column(Text)
    replied_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="selectin")


class SavedReply(TimestampMixin, Base):
    __tablename__ = "saved_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    shortcut: Mapped[str | None] = mapped_column(String(40))
    uses: Mapped[int] = mapped_column(Integer, default=0)


class InboxRule(TimestampMixin, Base):
    """When an incoming item matches, prepare a reply that a person approves before it goes out."""

    __tablename__ = "inbox_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    kinds: Mapped[list] = mapped_column(JSON, default=list)  # [] = any
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)  # any of these, case-insensitive
    intents: Mapped[list] = mapped_column(JSON, default=list)  # applied once the item is classified
    sentiments: Mapped[list] = mapped_column(JSON, default=list)
    saved_reply_id: Mapped[int | None] = mapped_column(
        ForeignKey("saved_replies.id", ondelete="SET NULL")
    )
    reply_text: Mapped[str | None] = mapped_column(Text)  # used when no saved reply
    assign_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    hits: Mapped[int] = mapped_column(Integer, default=0)
