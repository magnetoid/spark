"""Pydantic models for the API. Datetimes are always timezone-aware UTC on the wire."""

from __future__ import annotations

from datetime import date, datetime
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
    voice_tone: str | None = None
    voice_audience: str | None = None
    voice_rules: str | None = None
    voice_examples: str | None = None
    default_hashtags: str | None = None
    utm_campaign: str | None = None
    role: str
    agent_config: dict[str, Any] = {}
    voice_profile: dict[str, Any] = {}

    @classmethod
    def of(cls, b: Brand, role: str) -> BrandOut:
        return cls(id=b.id, slug=b.slug, name=b.name, color=b.color, timezone=b.timezone, website=b.website,
                   require_approval=b.require_approval, auto_shorten_links=b.auto_shorten_links, voice_tone=b.voice_tone,
                   voice_audience=b.voice_audience, voice_rules=b.voice_rules, voice_examples=b.voice_examples,
                   default_hashtags=b.default_hashtags, utm_campaign=(b.utm_defaults or {}).get("campaign"), role=role,
                   agent_config={"never_say": [], "avoid_topics": [], "keywords": [], "auto_schedule": False, **(b.agent_config or {})},
                   voice_profile=dict(b.voice_profile or {}))


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
    utm_campaign: str | None = None
    agent_config: dict[str, Any] | None = None
    voice_profile: dict[str, Any] | None = None


class Capabilities(BaseModel):
    max: int
    label: str
    requires_media: bool
    first_comment: bool
    threadable: bool
    post_types: list[str] = ["post"]


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
    post_type: str = "post"

    @classmethod
    def of(cls, t: PostTarget) -> TargetOut:
        return cls(id=t.id, account_id=t.account_id, platform=t.account.platform, handle=t.account.handle,
                   status=t.status.value, scheduled_at=_dt(t.scheduled_at), published_at=_dt(t.published_at),
                   remote_url=t.remote_url, error=t.error, content_override=t.content_override,
                   first_comment=t.first_comment, thread=list(t.thread or []), post_type=t.post_type or "post")


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
    comment_count: int = 0
    pillar_id: int | None = None
    evergreen: bool = False
    recycle_every_days: int | None = None
    recycled_from_id: int | None = None
    agent_run_id: int | None = None
    proposed_for: datetime | None = None

    @classmethod
    def of(cls, p: Post) -> PostOut:
        return cls(id=p.id, content=p.content, link=p.link, media_ids=list(p.media_ids or []), status=p.status.value,
                   pillar_id=p.pillar_id, evergreen=bool(p.evergreen), recycle_every_days=p.recycle_every_days, recycled_from_id=p.recycled_from_id,
                   agent_run_id=p.agent_run_id, proposed_for=_dt(p.proposed_for),
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
    plan_ready: int = 0  # drafts the agent proposed, waiting in the plan tray
    replies: int = 0  # open inbox items


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
    post_type: str = "post"


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
    pillar_id: int | None = None
    evergreen: bool | None = None
    recycle_every_days: int | None = Field(default=None, ge=1, le=365)


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
    post_types: dict[str, str] = {}


class ValidateOut(BaseModel):
    problems: dict[str, list[str]]
    warnings: dict[str, list[str]]


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
    width: int | None = None
    height: int | None = None
    tags: list[str] = []
    source: str = "upload"

    @classmethod
    def of(cls, m) -> MediaOut:
        return cls(id=m.id, name=m.filename, url=m.url, content_type=m.content_type, is_video=m.is_video, size=m.size,
                   alt_text=m.alt_text, created_at=_dt(m.created_at), width=m.width, height=m.height, tags=list(m.tags or []),
                   source=m.source or "upload")


class MediaUploadOut(BaseModel):
    items: list[MediaOut]
    rejected: list[dict[str, str]]


class MediaPage(BaseModel):
    items: list[MediaOut]


class MediaUpdate(BaseModel):
    alt_text: str | None = None
    tags: list[str] | None = None


class MediaGenerateIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    size: Literal["square", "portrait", "landscape"] = "square"


class MediaCropIn(BaseModel):
    ratio: Literal["1:1", "4:5", "9:16", "16:9", "2:3", "1.91:1"]
    x: float = Field(0.5, ge=0, le=1)
    y: float = Field(0.5, ge=0, le=1)


class TagCount(BaseModel):
    tag: str
    count: int


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


# ---- phase 4 ----------------------------------------------------------------------------
class TopPost(BaseModel):
    post_id: int
    account_id: int
    handle: str
    platform: str
    engagements: int
    impressions: int
    text: str
    url: str | None
    published_at: datetime | None


class AnalyticsOut(BaseModel):
    days: int
    published: int
    scheduled: int
    failed: int
    followers: int
    impressions: int
    engagements: int
    engagement_rate_pct: float
    link_clicks: int
    totals: dict[str, int]
    change_pct: dict[str, float | None]
    by_platform: dict[str, dict[str, int]]
    series: list[WeekPoint]
    link_clicks_series: list[dict[str, Any]]
    top: list[TopPost]
    best_times: list[dict[str, Any]]


class AiPlanIn(BaseModel):
    account_ids: list[int]
    per_week: int = Field(3, ge=1, le=14)


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str | None = None
    starts_on: str | None = None  # YYYY-MM-DD in the brand's zone
    ends_on: str | None = None
    utm_campaign: str | None = None
    color: Color = "#6366f1"
    ai_plan: AiPlanIn | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = None
    starts_on: str | None = None
    ends_on: str | None = None
    utm_campaign: str | None = None
    color: Color | None = None


class CampaignFull(CampaignOut):
    counts: dict[str, int]
    planned: int = 0


class LinkIn(BaseModel):
    destination: str = Field(min_length=3)
    title: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    campaign_id: int | None = None


class LinkOut(Out):
    id: int
    code: str
    destination: str
    title: str | None
    campaign_id: int | None
    clicks: int
    short_url: str
    created_at: datetime | None


class LinkPage(BaseModel):
    items: list[LinkOut]


class FeedIn(BaseModel):
    url: str = Field(min_length=8)
    name: str | None = None
    use_ai: bool = True
    auto_queue: bool = False
    account_ids: list[int] = []


class FeedUpdate(BaseModel):
    name: str | None = None
    use_ai: bool | None = None
    auto_queue: bool | None = None
    account_ids: list[int] | None = None
    is_active: bool | None = None


class FeedOut(Out):
    id: int
    url: str
    name: str | None
    use_ai: bool
    auto_queue: bool
    account_ids: list[int]
    is_active: bool
    last_checked_at: datetime | None


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ListOut(Out):
    id: int
    name: str
    description: str | None
    contacts: int = 0


class ContactIn(BaseModel):
    email: str
    first_name: str | None = None
    last_name: str | None = None
    list_ids: list[int] = []


class ContactOut(Out):
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    source: str
    subscribed: bool
    lists: list[int]
    created_at: datetime | None


class ContactPage(BaseModel):
    items: list[ContactOut]
    total: int
    subscribed: int


class EmailCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    list_id: int | None = None


class EmailUpdate(BaseModel):
    name: str | None = None
    subject: str | None = None
    preheader: str | None = None
    body_html: str | None = None
    list_id: int | None = None
    action: Literal["save", "send", "schedule", "unschedule"] = "save"
    scheduled_at: datetime | None = None


class EmailOut(Out):
    id: int
    name: str
    subject: str
    preheader: str | None
    body_html: str
    status: str
    list_id: int | None
    scheduled_at: datetime | None
    sent_at: datetime | None
    sent_count: int
    recipients: int = 0
    stats: dict[str, int] = {}
    created_at: datetime | None


class BioLink(BaseModel):
    label: str
    url: str
    code: str | None = None
    clicks: int = 0


class BioOut(BaseModel):
    title: str
    bio: str | None
    theme: str
    capture_email: bool
    capture_list_id: int | None
    avatar_media_id: int | None
    is_published: bool
    views: int
    links: list[BioLink]
    total_clicks: int
    public_url: str


class BioIn(BaseModel):
    title: str = Field(max_length=200)
    bio: str | None = None
    theme: str = "light"
    capture_email: bool = True
    capture_list_id: int | None = None
    avatar_media_id: int | None = None
    is_published: bool = True
    links: list[BioLink] = []


class CredentialField(BaseModel):
    name: str
    label: str


class PlatformOut(BaseModel):
    name: str
    label: str
    connect_mode: str
    credential_fields: list[CredentialField]
    configured: bool
    docs_url: str


class PlatformsOut(BaseModel):
    direct: list[PlatformOut]
    zernio: dict[str, str]
    zernio_ready: bool
    force_dry_run: bool


class ConnectResult(BaseModel):
    message: str
    accounts: list[AccountOut]


class ImportResult(BaseModel):
    imported: int
    accounts: list[AccountOut]
    skipped: list[str] = []



class SlotIn(BaseModel):
    weekdays: list[int] = Field(min_length=1)
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    account_id: int | None = None  # None = every channel


class SlotRow(Out):
    id: int
    weekday: int
    time: str
    account_id: int | None = None


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)
    role: Literal["owner", "editor", "viewer"] = "editor"


class TeamUpdate(BaseModel):
    role: Literal["owner", "editor", "viewer"] | None = None
    is_active: bool | None = None


class TeamOut(Out):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime | None


class ConnectorCard(BaseModel):
    key: str
    name: str
    tagline: str
    kind: str
    tags: list[str]
    configured: bool
    status: str


class ConnectorFieldOut(BaseModel):
    name: str
    label: str
    kind: str
    options: list[list[str]]
    help: str
    placeholder: str
    value: Any
    masked: str
    source: str
    has_value: bool


class ConnectorOut(BaseModel):
    key: str
    name: str
    tagline: str
    description: str
    docs: str | None
    kind: str
    configured: bool
    fields: list[ConnectorFieldOut]
    extra: dict[str, Any] = {}


class ConnectorSave(BaseModel):
    values: dict[str, Any] = {}
    clear: list[str] = []


class TokenOut(Out):
    id: int
    name: str
    prefix: str
    last_used_at: datetime | None
    created_at: datetime | None


class TokenCreated(TokenOut):
    token: str


class InboxAccount(BaseModel):
    id: int
    external_id: str
    platform: str
    handle: str
    avatar: str | None = None


class InboxAuthor(BaseModel):
    name: str
    handle: str | None = None
    picture: str | None = None


class InboxItemOut(BaseModel):
    id: int
    kind: str
    direction: str
    status: str
    external_id: str
    thread_id: str | None
    parent_external_id: str | None
    account: InboxAccount
    author: InboxAuthor
    text: str
    rating: int | None
    permalink: str | None
    post: dict[str, Any]
    attachments: list[Any]
    received_at: datetime | None
    sentiment: str | None
    intent: str | None
    suggestions: list[str]
    draft_reply: str | None
    draft_rule: dict[str, Any] | None
    assignee: Actor | None
    replied_at: datetime | None
    reply_text: str | None


class InboxCounts(BaseModel):
    open: int
    drafts: int
    negative: int
    resolved: int
    by_kind: dict[str, int]


class InboxPage(BaseModel):
    items: list[InboxItemOut]
    counts: InboxCounts
    accounts: list[InboxAccount]
    ready: bool


class InboxThreadOut(BaseModel):
    item: InboxItemOut
    thread: list[InboxItemOut]


class ItemReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    from_draft: bool = False
    saved_reply_id: int | None = None


class InboxStatusIn(BaseModel):
    status: Literal["open", "resolved", "archived"]


class AssignIn(BaseModel):
    user_id: int | None = None


class SuggestionsOut(BaseModel):
    suggestions: list[str]


class ItemLikeIn(BaseModel):
    liked: bool = True


class InboxSyncOut(BaseModel):
    new: int
    updated: int
    errors: list[str]
    synced_at: datetime


class SavedReplyIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=10000)
    shortcut: str | None = Field(default=None, max_length=40)


class SavedReplyUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=10000)
    shortcut: str | None = Field(default=None, max_length=40)


class SavedReplyOut(BaseModel):
    id: int
    title: str
    body: str
    shortcut: str | None
    uses: int


class InboxRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    kinds: list[str] = []
    platforms: list[str] = []
    keywords: list[str] = []
    intents: list[str] = []
    sentiments: list[str] = []
    saved_reply_id: int | None = None
    reply_text: str | None = None
    assign_to_id: int | None = None


class InboxRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    kinds: list[str] | None = None
    platforms: list[str] | None = None
    keywords: list[str] | None = None
    intents: list[str] | None = None
    sentiments: list[str] | None = None
    saved_reply_id: int | None = None
    reply_text: str | None = None
    assign_to_id: int | None = None


class InboxRuleOut(InboxRuleIn):
    id: int
    hits: int


class PaletteItem(BaseModel):
    label: str
    hint: str = ""
    group: str
    to: str | None = None
    action: str | None = None
    params: dict[str, Any] = {}



# ---- phase 6: collaboration ----------------------------------------------------------------
MemberRole = Literal["owner", "editor", "viewer", "client"]


class MemberIn(BaseModel):
    email: EmailStr
    role: MemberRole = "editor"
    name: str | None = None  # with password: create the user when the email is unknown
    password: str | None = Field(default=None, min_length=8)


class MemberUpdate(BaseModel):
    role: MemberRole


class MemberOut(BaseModel):
    id: int | None  # None for workspace owners, who are members of every brand without a row
    user_id: int
    name: str
    email: str
    role: str
    is_active: bool
    workspace_owner: bool = False


class Actor(BaseModel):
    id: int | None
    name: str


class ActivityOut(BaseModel):
    id: int
    actor: Actor
    verb: str
    object_type: str
    object_id: int | None
    summary: str
    data: dict[str, Any]
    created_at: datetime


class ActivityPage(BaseModel):
    items: list[ActivityOut]


class CommentIn(BaseModel):
    body: str


class CommentOut(BaseModel):
    id: int
    author: Actor
    body: str
    kind: str
    created_at: datetime | None


class ShareLinkIn(BaseModel):
    days: int = Field(14, ge=1, le=90)
    post_ids: list[int] | None = None


class ShareLinkOut(BaseModel):
    id: int
    kind: str
    prefix: str
    url_hint: str
    expires_at: datetime | None
    created_at: datetime | None
    last_used_at: datetime | None
    posts: int | None


class ShareLinkCreated(ShareLinkOut):
    token: str
    url: str


class ReviewChannel(BaseModel):
    platform: str
    handle: str
    text: str = ""
    first_comment: str | None = None
    thread: list[str] = []
    post_type: str = "post"


class ReviewActionOut(BaseModel):
    message: str
    status: str


class ReviewPost(BaseModel):
    id: int
    content: str
    link: str | None
    status: str
    scheduled_at: datetime | None
    media: list[str]
    channels: list[ReviewChannel]
    comments: list[CommentOut]


class ReviewPage(BaseModel):
    brand: dict[str, str]
    timezone: str
    expires_at: datetime | None
    posts: list[ReviewPost]


class ReviewAction(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    body: str | None = None


# ---- phase 7: planning ---------------------------------------------------------------------
class PillarIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field("#6D4AE0", pattern=r"^#[0-9a-fA-F]{6}$")
    target_share: int = Field(0, ge=0, le=100)
    description: str | None = None


class PillarUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    target_share: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None
    position: int | None = None


class PillarOut(BaseModel):
    id: int
    name: str
    color: str
    target_share: int
    description: str | None
    position: int
    posts_30d: int


class PostImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=2_000_000)


class ImportRowError(BaseModel):
    row: int
    error: str


class PostImportOut(BaseModel):
    created: int
    errors: list[ImportRowError]


# ---- phase 7: the agent ------------------------------------------------------------------------
RunKind = Literal["ask", "weekly_plan", "voice", "repurpose", "report"]


class AgentRunIn(BaseModel):
    kind: RunKind = "ask"
    prompt: str | None = Field(default=None, max_length=4000)


class AgentRunOut(BaseModel):
    id: int
    kind: str
    status: str
    prompt: str
    janus_run_id: str | None
    output: str | None
    proposal: dict[str, Any]
    events: list[dict[str, Any]]
    usage: dict[str, Any]
    error: str | None
    summary: str
    posts: int
    applied_at: datetime | None
    finished_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    user: Actor | None


class AgentStatusOut(BaseModel):
    configured: bool
    healthy: bool
    version: str | None
    base_url: str | None
    checked_at: datetime
    can_update: bool


class AgentApplyIn(BaseModel):
    post_indexes: list[int] | None = None
    schedule: bool | None = None
    what: Literal["posts", "voice"] | None = None


class AgentApplyOut(BaseModel):
    created: int
    post_ids: list[int]
    voice_applied: bool
    skipped: int = 0


class PlanOut(BaseModel):
    run: AgentRunOut | None
    posts: list[PostOut]


class PlanScheduleIn(BaseModel):
    post_ids: list[int] | None = None


class PlanScheduleOut(BaseModel):
    scheduled: int
    problems: list[str]
    message: str


# ---- phase 8: repurpose, grid -----------------------------------------------------------------
class RepurposeIn(BaseModel):
    source_text: str | None = Field(default=None, max_length=400_000)
    source_url: str | None = None
    source_name: str | None = None
    account_ids: list[int] = []
    notes: str | None = Field(default=None, max_length=2000)


class RepurposeOut(BaseModel):
    mode: Literal["janus", "claude"]
    run_id: int | None = None
    created: int = 0
    post_ids: list[int] = []
    message: str


class GridItem(BaseModel):
    post_id: int
    status: str
    when: datetime | None
    image: str | None
    is_video: bool
    content: str


class GridOut(BaseModel):
    account: AccountOut
    items: list[GridItem]


# ---- phase 10: reports ---------------------------------------------------------------------------
class ReportIn(BaseModel):
    start: date
    end: date
    title: str | None = Field(default=None, max_length=200)


class ReportOut(BaseModel):
    id: int
    title: str
    start: date
    end: date
    data: dict[str, Any]
    summary: dict[str, Any] | None
    created_at: datetime | None


class ReportSummaryOut(BaseModel):
    summary: dict[str, Any]
