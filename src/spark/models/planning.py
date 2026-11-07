"""Planning: content pillars (the themes a brand keeps returning to)."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from spark.db import Base, TimestampMixin


class ContentPillar(TimestampMixin, Base):
    """A theme with a colour and the share of posts it should get, e.g. Education 40%."""

    __tablename__ = "content_pillars"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(16), default="#6D4AE0")
    target_share: Mapped[int] = mapped_column(Integer, default=0)  # percent of posts, 0 = no target
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
