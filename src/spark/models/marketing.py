from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.db import Base, TimestampMixin

list_members = Table(
    "contact_list_members",
    Base.metadata,
    Column("list_id", ForeignKey("contact_lists.id", ondelete="CASCADE"), primary_key=True),
    Column("contact_id", ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
)


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("brand_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(50), default="manual")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    lists: Mapped[list["ContactList"]] = relationship(
        secondary=list_members, back_populates="contacts", lazy="selectin"
    )


class ContactList(TimestampMixin, Base):
    __tablename__ = "contact_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)

    contacts: Mapped[list[Contact]] = relationship(
        secondary=list_members, back_populates="lists", lazy="selectin"
    )


class EmailCampaign(TimestampMixin, Base):
    __tablename__ = "email_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    list_id: Mapped[int | None] = mapped_column(ForeignKey("contact_lists.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300), default="")
    preheader: Mapped[str | None] = mapped_column(String(300))
    body_html: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|scheduled|sending|sent
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_count: Mapped[int] = mapped_column(Integer, default=0)


class EmailSend(Base):
    __tablename__ = "email_sends"
    __table_args__ = (UniqueConstraint("campaign_id", "contact_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("email_campaigns.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class ShortLink(TimestampMixin, Base):
    __tablename__ = "short_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    destination: Mapped[str] = mapped_column(String(2000))
    title: Mapped[str | None] = mapped_column(String(200))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    clicks: Mapped[int] = mapped_column(Integer, default=0)


class LinkClick(Base):
    __tablename__ = "link_clicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("short_links.id", ondelete="CASCADE"), index=True)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    referrer: Mapped[str | None] = mapped_column(String(1000))
    user_agent: Mapped[str | None] = mapped_column(String(500))


class HashtagGroup(TimestampMixin, Base):
    """Named set of hashtags inserted from the composer (Buffer's saved hashtag groups)."""

    __tablename__ = "hashtag_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    tags: Mapped[list] = mapped_column(JSON, default=list)

    @property
    def text(self) -> str:
        return " ".join(f"#{t}" for t in self.tags)


class PostTemplate(TimestampMixin, Base):
    """Reusable post skeleton with {{placeholders}} the composer fills in by hand."""

    __tablename__ = "post_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(40))  # tip, story, question, how-to, ...


class Idea(TimestampMixin, Base):
    """Content scratchpad entry (Buffer's "Create"): moves idea → drafting → ready → done."""

    __tablename__ = "ideas"
    STATUSES = ("idea", "drafting", "ready", "done")

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="idea", index=True)
    media_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    position: Mapped[int] = mapped_column(Integer, default=0)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"))


class BioPage(TimestampMixin, Base):
    __tablename__ = "bio_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), unique=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    # [{"label": "...", "url": "..."}]
    links: Mapped[list] = mapped_column(JSON, default=list)
    capture_email: Mapped[bool] = mapped_column(Boolean, default=True)
    capture_list_id: Mapped[int | None] = mapped_column(
        ForeignKey("contact_lists.id", ondelete="SET NULL")
    )
    theme: Mapped[str] = mapped_column(String(20), default="light")
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
