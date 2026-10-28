import enum

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.db import Base, TimestampMixin


class Role(enum.StrEnum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False), default=Role.editor)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Per-user UI preferences: {"onboarding_dismissed": bool, "default_action": "queue", ...}
    prefs: Mapped[dict] = mapped_column(JSON, default=dict)

    def can_edit(self) -> bool:
        return self.role in (Role.owner, Role.editor)

    def can_approve(self) -> bool:
        return self.role == Role.owner


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    color: Mapped[str] = mapped_column(String(16), default="#f97316")

    # Brand voice used for every AI prompt
    voice_tone: Mapped[str | None] = mapped_column(Text)
    voice_audience: Mapped[str | None] = mapped_column(Text)
    voice_rules: Mapped[str | None] = mapped_column(Text)
    voice_examples: Mapped[str | None] = mapped_column(Text)
    default_hashtags: Mapped[str | None] = mapped_column(Text)

    # Zernio profile that holds this brand's Zernio-connected accounts
    zernio_profile_id: Mapped[str | None] = mapped_column(String(64))

    require_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_shorten_links: Mapped[bool] = mapped_column(Boolean, default=False)
    utm_defaults: Mapped[dict] = mapped_column(JSON, default=dict)

    accounts: Mapped[list["SocialAccount"]] = relationship(  # noqa: F821
        back_populates="brand", cascade="all, delete-orphan"
    )

    def voice_prompt(self) -> str:
        parts = [f"Brand: {self.name}"]
        if self.website:
            parts.append(f"Website: {self.website}")
        for label, value in (
            ("Tone of voice", self.voice_tone),
            ("Target audience", self.voice_audience),
            ("Rules (do / don't)", self.voice_rules),
            ("Example posts in the brand's voice", self.voice_examples),
            ("Preferred hashtags", self.default_hashtags),
        ):
            if value:
                parts.append(f"{label}:\n{value.strip()}")
        return "\n\n".join(parts)


class Media(TimestampMixin, Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(default=0)
    alt_text: Mapped[str | None] = mapped_column(Text)

    @property
    def is_video(self) -> bool:
        return self.content_type.startswith("video/")

    @property
    def url(self) -> str:
        return f"/media/{self.path}"
