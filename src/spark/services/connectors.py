"""Connectors: the outside services Spark talks to, configured from Settings → Connectors.

Each connector owns a few `Settings` fields. A value saved in the UI lives (encrypted) in
`connector_settings` and wins over the SPARK_* environment variable; clearing it falls back
to the environment again. Values are applied onto the shared settings object, so every
existing `get_settings().zernio_api_key`-style read sees them without changes.

Web and worker processes reload saved values at most every REFRESH_SECONDS, so a change made
in the UI reaches the worker within half a minute.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import ConnectorSetting
from spark.security import decrypt, encrypt

log = logging.getLogger(__name__)
REFRESH_SECONDS = 30


@dataclass(frozen=True)
class Field:
    name: str  # Settings attribute
    label: str
    kind: str = "text"  # text | secret | select | number | bool | textarea
    options: tuple[tuple[str, str], ...] = ()
    help: str = ""
    placeholder: str = ""


@dataclass(frozen=True)
class Connector:
    key: str
    name: str
    tagline: str
    description: str
    docs: str | None = None
    fields: tuple[Field, ...] = ()
    required: tuple[str, ...] = ()
    # connectors without saved fields (MCP access, direct platform apps) get their own page body
    kind: str = "service"
    tags: tuple[str, ...] = field(default_factory=tuple)


CONNECTORS: tuple[Connector, ...] = (
    Connector(
        key="zernio",
        name="Zernio",
        tagline="Publish to 14 networks with one API key",
        description="Zernio hosts the platform apps: X, LinkedIn, Instagram, Facebook, Threads, TikTok, "
        "YouTube, Pinterest, Bluesky, Reddit, Telegram, Google Business and more. Spark "
        "publishes, reads comments and pulls analytics through it.",
        docs="https://docs.zernio.com",
        fields=(
            Field(
                "zernio_api_key",
                "API key",
                "secret",
                placeholder="sk_…",
                help="Zernio dashboard → Settings → API keys.",
            ),
            Field(
                "zernio_base_url",
                "API base URL",
                help="Leave as is unless Zernio tells you otherwise.",
            ),
        ),
        required=("zernio_api_key",),
        tags=("Publishing", "Inbox", "Analytics"),
    ),
    Connector(
        key="janus",
        name="Janus agent",
        tagline="Plans the week, learns the voice, answers “Ask Spark”",
        description="Your Janus Agent (github.com/magnetoid/Janus-Agent) runs as its own service next to Spark and "
        "reads Spark through MCP. It proposes; people approve. Point Spark at its address and API key. "
        "The update webhook lets Spark rebuild Janus from its latest main branch.",
        docs="https://github.com/magnetoid/Janus-Agent",
        fields=(
            Field(
                "janus_base_url",
                "Address",
                placeholder="http://janus:8642",
                help="Only for a Janus that runs elsewhere; the built-in service needs nothing here.",
            ),
            Field(
                "janus_api_key",
                "API key",
                "secret",
                help="Only for a Janus that runs elsewhere: its API_SERVER_KEY.",
            ),
            Field(
                "janus_model",
                "Model",
                placeholder="claude-opus-5-5",
                help="Empty = the same model as Claude AI.",
            ),
            Field(
                "janus_effort",
                "Reasoning effort",
                "select",
                options=(("low", "Low"), ("medium", "Medium"), ("high", "High")),
                help="How long Janus thinks per step. Medium suits planning; high for voice learning and reports.",
            ),
            Field(
                "janus_approvals",
                "Shell approvals",
                "select",
                options=(("manual", "Ask (Spark denies)"), ("off", "Off")),
                help="Janus has no shell toolset here, so this rarely matters; leave it on Ask.",
            ),
            Field(
                "janus_soul",
                "Personality",
                "textarea",
                help="Who Janus is inside Spark. Empty = the built-in text; the brand's voice and guardrails are added per run.",
            ),
            Field(
                "janus_extra_yaml",
                "Extra configuration (YAML)",
                "textarea",
                placeholder="skills:\n  external_dirs: [/data/janus/skills]",
                help="Merged over the configuration Spark writes: extra MCP servers, skills, memory, anything from Janus's config.yaml.",
            ),
            Field(
                "janus_update_webhook",
                "Update webhook",
                "secret",
                help="Only for a Janus that runs elsewhere: a deploy hook that rebuilds it.",
            ),
            Field(
                "janus_update_token",
                "Update token",
                "secret",
                help="Only for a Janus that runs elsewhere.",
            ),
        ),
        required=("janus_base_url", "janus_api_key"),
        tags=("Agent", "Planning", "Voice"),
    ),
    Connector(
        key="anthropic",
        name="Claude AI",
        tagline="Writes, rewrites and plans posts in your brand voice",
        description="Powers Generate, Rewrite, hashtags, campaign plans and email drafts. Uses your "
        "Anthropic API key; nothing is sent until someone presses an AI button.",
        docs="https://docs.claude.com",
        fields=(
            Field(
                "anthropic_api_key",
                "Anthropic API key",
                "secret",
                placeholder="sk-ant-…",
                help="console.anthropic.com → API keys.",
            ),
            Field(
                "ai_model",
                "Model",
                "select",
                options=(
                    ("claude-opus-5-5", "Claude Opus 5.5 (best writing)"),
                    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (faster, cheaper)"),
                    ("claude-haiku-5-5", "Claude Haiku 5.5 (fastest)"),
                    ("claude-fable-5-1", "Claude Fable 5.1 (most capable)"),
                ),
            ),
            Field(
                "ai_effort",
                "Effort",
                "select",
                options=(("low", "Low"), ("medium", "Medium"), ("high", "High")),
            ),
        ),
        required=("anthropic_api_key",),
        tags=("AI",),
    ),
    Connector(
        key="images",
        name="Image generation",
        tagline="Pictures for posts from a prompt",
        description="Claude writes but does not draw. With an OpenAI key Spark generates images from the composer and the "
        "Library, in square, portrait or landscape. Alt text comes from Claude vision through the Claude AI connector.",
        docs="https://developers.openai.com/api/docs/guides/image-generation",
        fields=(
            Field("openai_api_key", "OpenAI API key", "secret", placeholder="sk-…"),
            Field(
                "image_model",
                "Model",
                placeholder="gpt-image-2.6-flare",
                help="Flare is quick and cheap, gpt-image-2.6-sunburst edits more precisely. OpenAI retires image models "
                "about once a year; change the ID here when it does.",
            ),
        ),
        required=("openai_api_key",),
        tags=("Images", "Composer", "Library"),
    ),
    Connector(
        key="email",
        name="Email delivery",
        tagline="Notifications, digests and email campaigns",
        description="Console mode only logs emails. Pick SMTP or Resend to actually deliver failure "
        "alerts, approval requests, the weekly digest and your email campaigns.",
        fields=(
            Field(
                "email_backend",
                "Send with",
                "select",
                options=(("console", "Console (log only)"), ("smtp", "SMTP"), ("resend", "Resend")),
            ),
            Field("email_from", "From", placeholder="Spark <noreply@yourdomain.com>"),
            Field(
                "resend_api_key",
                "Resend API key",
                "secret",
                placeholder="re_…",
                help="Only for Resend.",
            ),
            Field("smtp_host", "SMTP host", help="Only for SMTP."),
            Field("smtp_port", "SMTP port", "number"),
            Field("smtp_user", "SMTP user"),
            Field("smtp_password", "SMTP password", "secret"),
            Field("smtp_tls", "Use STARTTLS", "bool"),
        ),
        tags=("Email",),
    ),
    Connector(
        key="chat",
        name="Chat notifications",
        tagline="Approvals, failed posts and reviews in Slack, Discord, Teams or Telegram",
        description="Spark posts a short message with a link where the team already talks: when a post waits for approval, "
        "when one fails to publish and when a new review arrives. One destination is enough; fill in several "
        "and each gets every message. Email notifications keep working next to this.",
        fields=(
            Field(
                "chat_slack_webhook",
                "Slack webhook URL",
                "secret",
                placeholder="https://hooks.slack.com/services/…",
                help="Slack: Apps → Incoming Webhooks → Add to a channel. A Mattermost incoming webhook works here too.",
            ),
            Field(
                "chat_discord_webhook",
                "Discord webhook URL",
                "secret",
                placeholder="https://discord.com/api/webhooks/…",
                help="Discord: channel settings → Integrations → Webhooks → New webhook.",
            ),
            Field(
                "chat_teams_webhook",
                "Microsoft Teams workflow URL",
                "secret",
                help="Teams: Workflows → “Send webhook alerts to a channel”, then copy the URL it gives you.",
            ),
            Field(
                "chat_telegram_token",
                "Telegram bot token",
                "secret",
                placeholder="123456:ABC…",
                help="From @BotFather. Add the bot to the group or channel that should get the messages.",
            ),
            Field(
                "chat_telegram_chat_id",
                "Telegram chat ID",
                placeholder="-1001234567890",
                help="The group, channel or person the bot writes to.",
            ),
            Field("chat_on_approval", "Posts waiting for approval", "bool"),
            Field("chat_on_failed", "Posts that failed to publish", "bool"),
            Field("chat_on_review", "New reviews", "bool"),
            Field("chat_on_published", "Published posts", "bool"),
            Field("chat_on_channel", "Channels that need reconnecting or are running out", "bool"),
        ),
        tags=("Notifications",),
    ),
    Connector(
        key="mcp",
        name="MCP access",
        tagline="Let Claude and other AI assistants run Spark",
        description="Spark is an MCP server. Connect Claude Code, Claude Desktop or any MCP client "
        "with a personal token to draft, schedule and review posts, ideas and analytics.",
        docs="https://modelcontextprotocol.io",
        kind="mcp",
        tags=("AI", "API"),
    ),
    Connector(
        key="direct",
        name="Direct platform apps",
        tagline="Your own X, LinkedIn, Meta… developer apps",
        description="Optional. Spark can also post through developer apps you register with each "
        "network. These need OAuth redirect URLs, so they stay in the server environment.",
        kind="direct",
        tags=("Publishing",),
    ),
)
BY_KEY = {c.key: c for c in CONNECTORS}
# workspace rules saved the same way (encrypted, overriding SPARK_*), without a connector page
WORKSPACE_FIELDS = (Field("require_two_factor", "Require two-factor sign-in", "bool"),)
FIELDS = {f.name: f for c in CONNECTORS for f in c.fields} | {f.name: f for f in WORKSPACE_FIELDS}

DIRECT_APPS = (  # label, client id setting, secret setting
    ("X", "x_client_id", "x_client_secret"),
    ("LinkedIn", "linkedin_client_id", "linkedin_client_secret"),
    ("Facebook & Instagram", "meta_app_id", "meta_app_secret"),
    ("Threads", "threads_app_id", "threads_app_secret"),
    ("Pinterest", "pinterest_client_id", "pinterest_client_secret"),
    ("TikTok", "tiktok_client_key", "tiktok_client_secret"),
    ("YouTube", "google_client_id", "google_client_secret"),
)

# ---- applying saved values onto the shared settings object -------------------------------
_env_values: dict[str, Any] = {}  # what the environment said, before any override
_applied: set[str] = set()
_loaded_at = 0.0


def apply(saved: dict[str, Any]) -> None:
    s = get_settings()
    for name in FIELDS:
        if name not in _env_values:
            _env_values[name] = getattr(s, name)
    for name in list(_applied - saved.keys()):
        setattr(s, name, _env_values[name])  # cleared in the UI: back to the environment
        _applied.discard(name)
    for name, value in saved.items():
        if name in FIELDS:
            setattr(s, name, value)
            _applied.add(name)


def env_value(name: str) -> Any:
    return _env_values.get(name, getattr(get_settings(), name))


def source(name: str) -> str:
    """'saved' (UI), 'env' (SPARK_* variable) or 'default'."""
    if name in _applied:
        return "saved"
    default = type(get_settings()).model_fields[name].default
    return "env" if env_value(name) not in (None, "", default) else "default"


async def load(db: AsyncSession) -> dict[str, Any]:
    rows = (await db.execute(select(ConnectorSetting))).scalars().all()
    out = {}
    for r in rows:
        raw = decrypt(r.value)
        if raw is None:
            log.warning("Connector setting %s could not be decrypted (secret key changed?)", r.key)
            continue
        out[r.key] = json.loads(raw)
    return out


async def refresh(db: AsyncSession, force: bool = False) -> None:
    global _loaded_at
    if not force and time.monotonic() - _loaded_at < REFRESH_SECONDS:
        return
    _loaded_at = time.monotonic()
    saved = await load(db)
    if saved or _applied:
        apply(saved)


def _coerce(f: Field, raw: str | None) -> Any:
    if f.kind == "bool":
        return raw in ("true", "on", "1")
    if f.kind == "number":
        return int(raw) if raw and raw.strip().isdigit() else None
    return (raw or "").strip()


async def save(
    db: AsyncSession, connector: Connector, form: dict, user_id: int | None
) -> list[str]:
    """Save a connector form. Blank secrets keep the saved value; `clear_<field>` removes it."""
    changed = []
    now = datetime.now(UTC)
    for f in connector.fields:
        if form.get(f"clear_{f.name}"):
            await db.execute(delete(ConnectorSetting).where(ConnectorSetting.key == f.name))
            changed.append(f.name)
            continue
        value = _coerce(f, form.get(f.name))
        if f.kind == "secret" and not value:
            continue  # blank = keep what is there
        if f.kind != "bool" and value in ("", None):
            if source(f.name) == "saved":
                await db.execute(delete(ConnectorSetting).where(ConnectorSetting.key == f.name))
                changed.append(f.name)
            continue
        if value == getattr(get_settings(), f.name) and source(f.name) != "saved":
            continue  # same as the environment: nothing to store
        row = await db.get(ConnectorSetting, f.name)
        if row is None:
            row = ConnectorSetting(key=f.name)
            db.add(row)
        row.value = encrypt(json.dumps(value))
        row.updated_at, row.updated_by = now, user_id
        changed.append(f.name)
    await db.commit()
    await refresh(db, force=True)
    return changed


async def save_value(db: AsyncSession, name: str, value: Any, user_id: int | None) -> None:
    """Save one workspace rule (a WORKSPACE_FIELDS name) and apply it to this process now."""
    row = await db.get(ConnectorSetting, name)
    if row is None:
        row = ConnectorSetting(key=name)
        db.add(row)
    row.value = encrypt(json.dumps(value))
    row.updated_at, row.updated_by = datetime.now(UTC), user_id
    await db.commit()
    await refresh(db, force=True)


def is_configured(connector: Connector) -> bool:
    s = get_settings()
    if connector.key == "email":
        return s.email_backend != "console"
    if connector.key == "direct":
        return any(getattr(s, cid) for _label, cid, _sec in DIRECT_APPS)
    if connector.key == "chat":
        from spark.services import chat

        return bool(chat.destinations())
    return all(getattr(s, name) for name in connector.required)


def mask(value: str | None) -> str:
    if not value:
        return ""
    return f"{value[:4]}…{value[-4:]}" if len(value) > 12 else "•" * 8


async def test(connector: Connector, user_email: str | None = None) -> tuple[bool, str]:
    """Try the connection. Returns (ok, message for a toast)."""
    s = get_settings()
    try:
        if connector.key == "zernio":
            from spark.platforms.zernio import ZernioAdapter

            z = ZernioAdapter()
            profiles = (await z._req("GET", "/profiles")).json().get("profiles", [])
            accounts = await z.list_accounts()
            return (
                True,
                f"Zernio answered: {len(profiles)} profile(s), {len(accounts)} connected account(s)",
            )
        if connector.key == "janus":
            from spark.services.janus import Janus

            j = Janus()
            if not await j.health():
                return False, f"Janus at {j.base_url} did not answer /health" + (
                    " (it may still be starting)" if s.janus_managed else ""
                )
            v = await j.version()
            return (
                True,
                f"Janus answered: healthy{', version ' + v if v else ''}{' · built in' if s.janus_managed else ''}",
            )
        if connector.key == "anthropic":
            import anthropic

            if not s.anthropic_api_key:
                return False, "Add an API key first"
            client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
            m = await client.models.retrieve(s.ai_model)
            return (
                True,
                f"Anthropic answered: {getattr(m, 'display_name', None) or s.ai_model} is available",
            )
        if connector.key == "images":
            from spark.services.images import test_connection

            return await test_connection()
        if connector.key == "email":
            from spark.services.email import get_sender
            from spark.services.notify import layout

            if not user_email:
                return False, "No address to send to"
            await get_sender().send(
                user_email,
                "Spark test email",
                layout("It works", "Spark can deliver email from this server.", ""),
            )
            where = (
                "logged in the server output"
                if s.email_backend == "console"
                else f"sent to {user_email}"
            )
            return True, f"Test email {where} (backend: {s.email_backend})"
        if connector.key == "chat":
            from spark.services import chat

            if not chat.destinations():
                return (
                    False,
                    "Add a destination first: a Slack, Discord or Teams webhook, or a Telegram bot and chat",
                )
            results = await chat.send(
                "Spark is connected. Approvals, failed posts and new reviews will show up here.",
                url=s.base_url.rstrip("/"),
                label="Open Spark",
            )
            ok = [name for name, err in results.items() if err is None]
            bad = [f"{name}: {err}" for name, err in results.items() if err]
            if bad:
                return False, (f"Sent to {', '.join(ok)}. " if ok else "") + "; ".join(bad)
            return True, f"Test message sent to {', '.join(ok)}"
    except Exception as e:  # surfaced to the owner as a toast
        return False, f"{connector.name}: {e}"[:300]
    return False, "Nothing to test"
