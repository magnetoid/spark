import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.db import Base, TimestampMixin
from spark.security import decrypt, encrypt


class SocialAccount(TimestampMixin, Base):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("brand_id", "platform", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    # "direct" = our own developer app talks to the platform; "zernio" = via Zernio API
    provider: Mapped[str] = mapped_column(String(16), default="direct")
    external_id: Mapped[str] = mapped_column(String(255))
    handle: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    _access_token: Mapped[str | None] = mapped_column("access_token", Text)
    _refresh_token: Mapped[str | None] = mapped_column("refresh_token", Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Platform-specific data: instance url, page id, board id, chat id, ...
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    followers: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)

    brand: Mapped["Brand"] = relationship(back_populates="accounts")  # noqa: F821

    @property
    def access_token(self) -> str | None:
        return decrypt(self._access_token)

    @access_token.setter
    def access_token(self, value: str | None) -> None:
        self._access_token = encrypt(value)

    @property
    def refresh_token(self) -> str | None:
        return decrypt(self._refresh_token)

    @refresh_token.setter
    def refresh_token(self, value: str | None) -> None:
        self._refresh_token = encrypt(value)


class PostStatus(enum.StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"
    scheduled = "scheduled"
    publishing = "publishing"
    published = "published"
    failed = "failed"


class Campaign(TimestampMixin, Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str | None] = mapped_column(Text)
    starts_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    utm_campaign: Mapped[str | None] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(16), default="#6366f1")


class Post(TimestampMixin, Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(2000))
    media_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, native_enum=False), default=PostStatus.draft, index=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual | ai | rss | idea
    # Written by the composer's autosave; hidden from lists until the user saves for real
    is_autosave: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # When owners were emailed that this post waits for approval (None = not yet)
    approval_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    targets: Mapped[list["PostTarget"]] = relationship(
        back_populates="post", cascade="all, delete-orphan", lazy="selectin"
    )
    campaign: Mapped[Campaign | None] = relationship(lazy="selectin")

    def refresh_status(self) -> None:
        """Roll up target statuses into the post status."""
        statuses = {t.status for t in self.targets}
        if not statuses:
            return
        for s in (PostStatus.publishing, PostStatus.scheduled, PostStatus.pending_approval):
            if s in statuses:
                self.status = s
                return
        if statuses == {PostStatus.published}:
            self.status = PostStatus.published
        elif PostStatus.failed in statuses:
            self.status = PostStatus.failed
        elif statuses == {PostStatus.draft}:
            self.status = PostStatus.draft
        else:
            self.status = PostStatus.published


class PostTarget(TimestampMixin, Base):
    __tablename__ = "post_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True
    )
    content_override: Mapped[str | None] = mapped_column(Text)
    # Posted as the first reply right after publishing (Buffer's "first comment")
    first_comment: Mapped[str | None] = mapped_column(Text)
    # Follow-up items of a thread (the root is `text`); X, Threads, Bluesky, Mastodon
    thread: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, native_enum=False), default=PostStatus.draft, index=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remote_id: Mapped[str | None] = mapped_column(String(255))
    remote_url: Mapped[str | None] = mapped_column(String(1000))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    # When the team was emailed about this target's final failure (None = not yet)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    post: Mapped[Post] = relationship(back_populates="targets")
    account: Mapped[SocialAccount] = relationship(lazy="selectin")

    @property
    def text(self) -> str:
        return self.content_override if self.content_override else self.post.content


class QueueSlot(Base):
    """Weekly recurring posting time for a brand (local to brand timezone)."""

    __tablename__ = "queue_slots"
    __table_args__ = (UniqueConstraint("brand_id", "weekday", "time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    time: Mapped[str] = mapped_column(String(5))  # "HH:MM"


class RssFeed(TimestampMixin, Base):
    __tablename__ = "rss_feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    name: Mapped[str | None] = mapped_column(String(200))
    use_ai: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_queue: Mapped[bool] = mapped_column(Boolean, default=False)
    account_ids: Mapped[list] = mapped_column(JSON, default=list)
    seen_ids: Mapped[list] = mapped_column(JSON, default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Metric(Base):
    """Point-in-time metrics snapshot for a published target."""

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(
        ForeignKey("post_targets.id", ondelete="CASCADE"), index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def engagements(self) -> int:
        return self.likes + self.comments + self.shares + self.clicks


class WebhookEvent(Base):
    """Ids of provider webhook deliveries we already processed (at-least-once delivery)."""

    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
