"""Janus as Spark's built-in agent service.

In the compose stack Janus runs as the `janus` service; compose hands both sides the same
generated API key and Spark its address, so nobody types either. What Spark pushes to Janus:
its whole configuration, through Janus's config API (`PUT /v1/config` with the YAML), including
the Spark MCP server with a token for a read-only agent user, the model, the reasoning effort,
the approvals mode and the personality. Janus's own options live in Settings → Connectors →
Janus and are pushed again on save.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
from datetime import UTC, datetime

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.models import ConnectorSetting, Role, User
from spark.security import decrypt, encrypt, hash_password, token
from spark.services import tokens
from spark.services.janus import Janus, JanusError

log = logging.getLogger("spark.janus")

AGENT_EMAIL = "janus@spark.local"
AGENT_NAME = "Janus (agent)"
TOKEN_KEY = "janus_mcp_token"
PUSHED_KEY = "janus_pushed_hash"
READ_TOOLS = [
    "list_brands",
    "list_channels",
    "list_posts",
    "get_post",
    "list_ideas",
    "best_posting_times",
    "get_analytics",
]
DEFAULT_SOUL = """# Who you are inside Spark

You are the planning assistant of a small marketing team that runs several brands in Spark, a
social media scheduler. Every request arrives with the brand's voice, guardrails, content
pillars, channels and posting times; treat them as the brief, not as suggestions.

- You read Spark through its tools (posts, ideas, best times, analytics, channels). You never
  create, schedule, publish or delete anything: a person reviews what you propose in Spark.
- Write finished posts, not outlines. Match the brand's voice and the network's habits.
- Respect the guardrails to the letter. If a request collides with them, say so and propose
  the closest thing that fits.
- Spread posts across pillars by their target share and across channels by their posting
  times. Avoid repeating what went out in the last two weeks.
- Keep the written answer short; the `spark-proposal` block at the end is what Spark reads.
- Memory is per brand. Do not mention or reuse anything from another brand.
"""


# ---- small encrypted key/value store (reuses connector_settings) --------------------------------
async def _get(db: AsyncSession, key: str) -> str | None:
    row = await db.get(ConnectorSetting, key)
    if row is None:
        return None
    raw = decrypt(row.value)
    return json.loads(raw) if raw else None


async def _set(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(ConnectorSetting, key)
    if row is None:
        db.add(
            ConnectorSetting(
                key=key, value=encrypt(json.dumps(value)), updated_at=datetime.now(UTC)
            )
        )
    else:
        row.value, row.updated_at = encrypt(json.dumps(value)), datetime.now(UTC)


# ---- the agent user and its token ------------------------------------------------------------------
async def ensure_agent(db: AsyncSession) -> tuple[User, str]:
    """The read-only user Janus acts as, and the API token it uses. Made once, reused after."""
    user = await db.scalar(select(User).where(User.email == AGENT_EMAIL))
    if user is None:
        user = User(
            email=AGENT_EMAIL,
            name=AGENT_NAME,
            role=Role.agent,
            password_hash=hash_password(token(32)),
        )
        db.add(user)
        await db.flush()
    elif user.role != Role.agent:
        user.role = Role.agent
    raw = await _get(db, TOKEN_KEY)
    if not raw or await tokens.user_for_token(db, raw) is None:
        raw, _row = await tokens.create_token(db, user, "Janus (built in)")
        await _set(db, TOKEN_KEY, raw)
    await db.commit()
    return user, raw


# ---- the configuration -------------------------------------------------------------------------------
def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


async def desired_config(db: AsyncSession) -> str:
    """Janus's config.yaml as Spark wants it, with the person's extra YAML merged on top."""
    s = get_settings()
    _user, token = await ensure_agent(db)
    cfg: dict = {
        "model": {"provider": "anthropic", "default": s.janus_model or s.ai_model},
        "agent": {
            "reasoning_effort": s.janus_effort or "medium",
            "disabled_toolsets": ["terminal", "code_execution"],
        },
        "approvals": {"mode": s.janus_approvals or "manual", "gateway_timeout": 30},
        "platforms": {"api_server": {"enabled": True, "extra": {"host": "0.0.0.0", "port": 8642}}},
        "platform_toolsets": {"api_server": ["spark"]},
        "mcp_servers": {
            "spark": {
                "url": s.base_url.rstrip("/") + "/mcp",
                "headers": {"Authorization": f"Bearer {token}"},
                "timeout": 120,
                "connect_timeout": 30,
                "tools": {"include": list(READ_TOOLS), "resources": False, "prompts": False},
            }
        },
        "personalities": {"spark": {"system_prompt": (s.janus_soul or DEFAULT_SOUL).strip()}},
        "display": {"personality": "spark"},
        "skills": {"external_dirs": []},
    }
    if s.janus_extra_yaml and s.janus_extra_yaml.strip():
        try:
            extra = yaml.safe_load(s.janus_extra_yaml) or {}
            if isinstance(extra, dict):
                cfg = _merge(cfg, extra)
        except yaml.YAMLError as e:
            log.warning("Janus extra YAML ignored: %s", e)
    return (
        "# Written by Spark. Change it in Spark → Settings → Connectors → Janus; edits here are overwritten.\n"
        + yaml.safe_dump(cfg, sort_keys=False)
    )


def _fingerprint(raw: str, api_keys: dict) -> str:
    return hashlib.sha256((raw + json.dumps(api_keys, sort_keys=True)).encode()).hexdigest()


# ---- pushing it ----------------------------------------------------------------------------------------
async def sync(db: AsyncSession, force: bool = False) -> dict:
    """Push the configuration when it changed (or `force`). Returns {result, detail}."""
    s = get_settings()
    if not (s.janus_base_url and s.janus_api_key):
        return {"result": "unconfigured", "detail": "Janus has no address or key"}
    client = Janus()
    raw = await desired_config(db)
    api_keys = {"ANTHROPIC_API_KEY": s.anthropic_api_key} if s.anthropic_api_key else {}
    fp = _fingerprint(raw, api_keys)
    if not force and await _get(db, PUSHED_KEY) == fp:
        return {"result": "unchanged", "detail": "Janus already has this configuration"}
    if not await client.health():
        return {
            "result": "unreachable",
            "detail": f"Janus at {client.base_url} is not answering yet",
        }
    body: dict = {"raw": raw, "restart": True}
    if api_keys:
        body["api_keys"] = api_keys
    try:
        res = await client.put_config(body)
    except JanusError as e:
        log.warning("Janus config push failed: %s", e)
        return {"result": "failed", "detail": str(e)}
    await _set(db, PUSHED_KEY, fp)
    await db.commit()
    from spark.services import agent

    agent.forget_status()
    log.info("Janus configured (%s)", ", ".join(res.get("applied") or ["raw"]))
    return {
        "result": "pushed",
        "detail": "Janus restarts with the new configuration",
        "warnings": res.get("warnings") or [],
    }


async def sync_when_up(attempts: int = 60, every: float = 10.0) -> None:
    """At startup: wait for the janus service to answer, then push the configuration once."""
    from spark.db import SessionLocal

    for _ in range(attempts):
        try:
            async with SessionLocal() as db:
                out = await sync(db)
            if out["result"] != "unreachable":
                log.info("Janus startup sync: %s", out["result"])
                return
        except Exception:
            log.exception("Janus startup sync failed; retrying")
        await asyncio.sleep(every)
    log.warning(
        "Janus did not come up in time; Settings → Connectors → Janus can push the configuration later"
    )


async def restart_for_update() -> dict:
    """Restart the gateway; the service pulls the latest Janus from the repository on its way back up."""
    client = Janus()
    res = await client.put_config({"restart": True})
    from spark.services import agent

    agent.forget_status()
    return res
