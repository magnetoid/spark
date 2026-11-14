"""Working together on a brand: who may see it, what happened, what was said, and review
links for people without an account."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.db import Base, TimestampMixin
from spark.models.core import User


class BrandMember(TimestampMixin, Base):
    """A user's role within one brand: owner, editor, viewer or client (reads and approves)."""

    __tablename__ = "brand_members"
    __table_args__ = (UniqueConstraint("brand_id", "user_id"),)
    ROLES = ("owner", "editor", "viewer", "client")

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="editor")

    user: Mapped[User] = relationship(lazy="selectin")


class ActivityLog(Base):
    """Who did what, per brand. Written by the API and by review links; read on Today and Activity."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_name: Mapped[str] = mapped_column(String(160), default="")
    verb: Mapped[str] = mapped_column(String(40))  # created, placed, approved, requested changes, …
    object_type: Mapped[str] = mapped_column(
        String(32)
    )  # post, member, channel, campaign, share_link, …
    object_id: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(String(500), default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PostComment(TimestampMixin, Base):
    """A note on a post from a team member or, through a review link, from a client."""

    __tablename__ = "post_comments"
    KINDS = ("comment", "approval", "change_request")

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    guest_name: Mapped[str | None] = mapped_column(String(160))
    share_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("share_links.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="comment")

    author: Mapped[User | None] = relationship(lazy="selectin")


class ShareLink(TimestampMixin, Base):
    """A login-free link for reviewing a brand's upcoming posts. Only the token's hash is stored."""

    __tablename__ = "share_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(12))
    kind: Mapped[str] = mapped_column(String(16), default="approval")
    scope: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {"post_ids": [...]} or {} = everything awaiting review
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
