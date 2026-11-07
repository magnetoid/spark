"""Pydantic models for the API. Datetimes are always timezone-aware UTC on the wire."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from spark.models import Brand, Post, PostTarget, SocialAccount, User
from spark.services.posts import channel_capabilities
from spark.services.publisher import as_utc

Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
PostStatusName = Literal["draft", "pending_approval", "scheduled", "publishing", "published", "failed"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(Out):
    id: int
    name: str
    email: str
    role: str
    prefs: dict[str, Any] = {}

    @classmethod
    def of(cls, u: User) -> UserOut:
        return cls(id=u.id, name=u.name, email=u.email, role=u.role.value, prefs=u.prefs or {})


class BrandOut(Out):
    id: int
    slug: str
    name: str
    color: str
    timezone: str
    website: str | None = None
    require_approval: bool
    auto_shorten_links: bool
    role: str

    @classmethod
    def of(cls, b: Brand, role: str) -> BrandOut:
        return cls(id=b.id, slug=b.slug, name=b.name, color=b.color, timezone=b.timezone, website=b.website,
                   require_approval=b.require_approval, auto_shorten_links=b.auto_shorten_links, role=role)


class SessionOut(BaseModel):
    user: UserOut | None
    csrf_token: str
    brands: list[BrandOut]
    needs_setup: bool
    features: dict[str, bool]


class LoginIn(BaseModel):
    email: str
    password: str


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)


class MeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    prefs: dict[str, Any] | None = None


class PasswordChange(BaseModel):
    current: str
    new: str = Field(min_length=10)


class BrandCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    website: str | None = None
    timezone: str = "UTC"
    color: Color | None = None


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    website: str | None = None
    timezone: str | None = None
    color: Color | None = None
    require_approval: bool | None = None
    auto_shorten_links: bool | None = None
    voice_tone: str | None = None
    voice_audience: str | None = None
    voice_rules: str | None = None
    voice_examples: str | None = None
    default_hashtags: str | None = None


class Capabilities(BaseModel):
    max: int
    label: str
    requires_media: bool
    first_comment: bool
    threadable: bool


class AccountOut(Out):
    id: int
    platform: str
    provider: str
    handle: str
    display_name: str | None
    avatar_url: str | None
    is_active: bool
    followers: int | None
    last_error: str | None
    capabilities: Capabilities

    @classmethod
    def of(cls, a: SocialAccount) -> AccountOut:
        caps = channel_capabilities(a)
        return cls(id=a.id, platform=a.platform, provider=a.provider, handle=a.handle, display_name=a.display_name,
                   avatar_url=a.avatar_url, is_active=a.is_active, followers=a.followers, last_error=a.last_error,
                   capabilities=Capabilities(**{k: caps[k] for k in Capabilities.model_fields}))


def _dt(value: datetime | None) -> datetime | None:
    return as_utc(value) if value else None


class TargetOut(Out):
    id: int
    account_id: int
    platform: str
    handle: str
    status: str
    scheduled_at: datetime | None
    published_at: datetime | None
    remote_url: str | None
    error: str | None
    content_override: str | None
    first_comment: str | None
    thread: list[str]

    @classmethod
    def of(cls, t: PostTarget) -> TargetOut:
        return cls(id=t.id, account_id=t.account_id, platform=t.account.platform, handle=t.account.handle,
                   status=t.status.value, scheduled_at=_dt(t.scheduled_at), published_at=_dt(t.published_at),
                   remote_url=t.remote_url, error=t.error, content_override=t.content_override,
                   first_comment=t.first_comment, thread=list(t.thread or []))


class PostOut(Out):
    id: int
    content: str
    link: str | None
    media_ids: list[int]
    status: str
    scheduled_at: datetime | None
    source: str
    campaign_id: int | None
    author_id: int | None
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None
    targets: list[TargetOut]

    @classmethod
    def of(cls, p: Post) -> PostOut:
        return cls(id=p.id, content=p.content, link=p.link, media_ids=list(p.media_ids or []), status=p.status.value,
                   scheduled_at=_dt(p.scheduled_at), source=p.source, campaign_id=p.campaign_id, author_id=p.author_id,
                   notes=p.notes, created_at=_dt(p.created_at), updated_at=_dt(p.updated_at),
                   targets=[TargetOut.of(t) for t in p.targets])


class PostPage(BaseModel):
    items: list[PostOut]
    total: int
    limit: int
    offset: int


class TimelineChannel(BaseModel):
    account_id: int
    platform: str
    handle: str
    status: str


class TimelineItem(BaseModel):
    post_id: int
    at: datetime
    status: str
    content: str
    channels: list[TimelineChannel]


class NeedsYou(BaseModel):
    approvals: int
    failed: int
    drafts: int


class WeekPoint(BaseModel):
    day: str
    impressions: int
    engagements: int


class WeekOut(BaseModel):
    published: int
    impressions: int
    engagements: int
    engagement_rate_pct: float
    change_pct: dict[str, float | None]
    series: list[WeekPoint]


class TodayOut(BaseModel):
    date: str
    timezone: str
    now: datetime
    timeline: list[TimelineItem]
    free_slots_today: int
    needs_you: NeedsYou
    week: WeekOut

    @field_validator("timeline")
    @classmethod
    def _sorted(cls, v: list[TimelineItem]) -> list[TimelineItem]:
        return sorted(v, key=lambda i: i.at)


# ---- writes ---------------------------------------------------------------------------
ActionName = Literal["draft", "queue", "next", "schedule", "now"]


class TargetIn(BaseModel):
    account_id: int
    override: str | None = None
    first_comment: str | None = None
    thread: list[str] = []


class PostWrite(BaseModel):
    content: str = ""
    link: str | None = None
    media_ids: list[int] = []
    campaign_id: int | None = None
    notes: str | None = None
    source: str = "manual"
    targets: list[TargetIn] = []
    action: ActionName = "draft"
    scheduled_at: datetime | None = None
    idea_id: int | None = None


class PlaceIn(BaseModel):
    action: ActionName
    scheduled_at: datetime | None = None


class MoveIn(BaseModel):
    day: str | None = None  # ISO date: keep the time of day
    when: datetime | None = None  # exact slot


class PostResult(BaseModel):
    message: str
    post: PostOut


class RetryResult(PostResult):
    retried: int


class AutosaveIn(BaseModel):
    post_id: int | None = None
    content: str = ""
    link: str | None = None
    media_ids: list[int] = []
    source: str = "manual"
    targets: list[TargetIn] = []


class AutosaveOut(BaseModel):
    post_id: int | None
    saved_at: datetime


class ValidateIn(BaseModel):
    targets: dict[str, str]
    media_ids: list[int] = []
    link: str | None = None


class SlotOut(BaseModel):
    weekday: int
    time: str


class QueueItem(BaseModel):
    when: datetime
    post: PostOut | None
    target_id: int | None


class QueueOut(BaseModel):
    account: AccountOut
    items: list[QueueItem]
    slots: list[SlotOut]
    counts: dict[str, int]


class IdeaIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str | None = None
    tags: list[str] = []
    source_url: str | None = None
    status: Literal["idea", "drafting", "ready", "done"] = "idea"


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = None
    tags: list[str] | None = None
    source_url: str | None = None


class IdeaMove(BaseModel):
    status: str
    position: int = 0


class IdeaOut(Out):
    id: int
    title: str
    body: str | None
    tags: list[str]
    status: str
    source_url: str | None
    position: int
    post_id: int | None
    media_ids: list[int]
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def of(cls, i) -> IdeaOut:
        return cls(id=i.id, title=i.title, body=i.body, tags=list(i.tags or []), status=i.status, source_url=i.source_url,
                   position=i.position, post_id=i.post_id, media_ids=list(i.media_ids or []),
                   created_at=_dt(i.created_at), updated_at=_dt(i.updated_at))


class IdeaBoard(BaseModel):
    items: list[IdeaOut]
    tags: list[str]


class MediaOut(Out):
    id: int
    name: str
    url: str
    content_type: str
    is_video: bool
    size: int
    alt_text: str | None
    created_at: datetime | None

    @classmethod
    def of(cls, m) -> MediaOut:
        return cls(id=m.id, name=m.filename, url=m.url, content_type=m.content_type, is_video=m.is_video, size=m.size,
                   alt_text=m.alt_text, created_at=_dt(m.created_at))


class MediaUploadOut(BaseModel):
    items: list[MediaOut]
    rejected: list[dict[str, str]]


class MediaPage(BaseModel):
    items: list[MediaOut]


class MediaUpdate(BaseModel):
    alt_text: str | None = None


class HashtagGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    tags: list[str] = []


class HashtagGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    tags: list[str] | None = None


class HashtagGroupOut(Out):
    id: int
    name: str
    tags: list[str]


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    body: str = ""
    category: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = None
    category: str | None = None


class TemplateOut(Out):
    id: int
    name: str
    body: str
    category: str | None


class CampaignOut(Out):
    id: int
    name: str
    color: str
    goal: str | None
    utm_campaign: str | None
    starts_on: datetime | None
    ends_on: datetime | None


class GenerateIn(BaseModel):
    brief: str = ""
    platforms: list[str] = []
    url: str | None = None
    link: str | None = None
    variants: int = Field(1, ge=1, le=3)


class RewriteIn(BaseModel):
    text: str
    instruction: str = "Improve it"
    platform: str | None = None


class HashtagsIn(BaseModel):
    text: str
