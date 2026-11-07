"""Spark's side of the agent: start a Janus run with the brand's context, follow it, and turn
what it proposes into drafts once a person agrees.

Janus only gets read tools; it answers with a `spark-proposal` JSON block. Nothing is created,
scheduled or published until `apply`, and even then posts are drafts (a brand can opt into
auto-scheduling). Shell approval prompts from Janus are denied: the agent has no business
running commands for a marketing team.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.config import get_settings
from spark.models import (
    AgentRun,
    Brand,
    ContentPillar,
    Post,
    PostStatus,
    PostTarget,
    SocialAccount,
    User,
)
from spark.services import activity, events, guardrails, jobs, scheduler
from spark.services import posts as svc
from spark.services.janus import Janus, JanusError, JanusUnavailable, configured
from spark.services.publisher import as_utc

log = logging.getLogger("spark.agent")
MAX_EVENTS = 200
INLINE_FOLLOW = True  # follow in-process when no worker picks the job up (dev, single container)
VERBS = {
    "ask": "asked Spark",
    "weekly_plan": "started a weekly plan",
    "voice": "started voice learning",
    "repurpose": "started a repurpose run",
    "report": "asked for a report",
}

PROPOSAL_FORMAT = (
    "End your answer with exactly one fenced code block tagged `spark-proposal` holding JSON of this shape:\n"
    '{"summary": "one line", "posts": [{"content": "the post text", "channels": ["handle or platform"], '
    '"when": "ISO 8601 with timezone, or null", "pillar": "pillar name or null", "link": "url or null"}], '
    '"voice_profile": {"tone": "", "audience": "", "rules": "", "examples": "", "summary": ""}}\n'
    "Leave `posts` empty when nothing should be written; leave out `voice_profile` unless you were asked for the voice. "
    "You cannot create, schedule or publish anything yourself: a person reviews the proposal in Spark."
)


# ---- context the agent gets -----------------------------------------------------------------
async def _context(
    db: AsyncSession, brand: Brand
) -> tuple[list[SocialAccount], list[ContentPillar], str]:
    accounts = await svc.active_accounts(db, brand)
    pillars = (
        (
            await db.execute(
                select(ContentPillar)
                .where(ContentPillar.brand_id == brand.id)
                .order_by(ContentPillar.position)
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(ZoneInfo(brand.timezone))
    lines = [
        f"You are Spark's planning assistant for the brand {brand.name}. Today is {now:%A %d %B %Y, %H:%M} ({brand.timezone}).",
        "",
        brand.voice_prompt(),
    ]
    g = guardrails.prompt_block(brand)
    if g:
        lines += ["", "Guardrails:", g]
    if pillars:
        lines += ["", "Content pillars (name, target share of posts):"] + [
            f"- {p.name} ({p.target_share}%){': ' + p.description if p.description else ''}"
            for p in pillars
        ]
    if accounts:
        lines += ["", "Channels (handle, platform):"] + [
            f"- {a.handle} ({a.platform})" for a in accounts
        ]
    slots = await scheduler.brand_slots(db, brand)
    upcoming = scheduler.next_slot_times(slots, brand.timezone, datetime.now(UTC), count=14)
    if upcoming:
        lines += [
            "",
            "Upcoming posting times (brand timezone): "
            + ", ".join(
                f"{t.astimezone(ZoneInfo(brand.timezone)):%a %d %b %H:%M}" for t in upcoming
            ),
        ]
    lines += [
        "",
        "You have read-only Spark tools (list_posts, list_ideas, best_posting_times, get_analytics, list_channels); use them when they help.",
        "",
        PROPOSAL_FORMAT,
    ]
    return accounts, pillars, "\n".join(lines)


async def _task(db: AsyncSession, brand: Brand, kind: str, prompt: str | None) -> str:
    cfg = guardrails.config(brand)
    if kind == "weekly_plan":
        wp = cfg.get("weekly_plan") or {}
        n = int(wp.get("posts") or 5)
        zone = ZoneInfo(brand.timezone)
        monday = (datetime.now(zone) + timedelta(days=7 - datetime.now(zone).weekday())).date()
        return (
            f"Propose {n} posts for next week, {monday:%A %d %B} to {monday + timedelta(days=6):%A %d %B}. Spread them across the channels "
            f"and the content pillars by their target share, give every post a `when` on one of the posting times, and write each post "
            f"in full in the brand's voice. Look at recent posts and ideas first so nothing repeats."
            + (f"\n\nNotes from the team: {prompt}" if prompt else "")
        )
    if kind == "voice":
        rows = (
            (
                await db.execute(
                    select(Post)
                    .where(
                        Post.brand_id == brand.id,
                        Post.status == PostStatus.published,
                        Post.is_autosave.is_(False),
                    )
                    .order_by(Post.scheduled_at.desc())
                    .limit(15)
                )
            )
            .scalars()
            .all()
        )
        samples = "\n\n".join(f"- {p.content.strip()}" for p in rows if p.content.strip())
        return (
            "Read the brand's published posts below (and get_analytics / list_posts for how they performed) and describe its voice so a "
            "writer could match it: tone, audience, rules (do / don't), three short example lines in that voice, and a one-line summary. "
            "Return it as `voice_profile` and leave `posts` empty.\n\nPublished posts:\n"
            + (samples or "(none yet; infer from the brand profile)")
        )
    return (prompt or "").strip() or "Suggest what the brand should post next."


# ---- starting ------------------------------------------------------------------------------------
async def start(
    db: AsyncSession, brand: Brand, user: User | None, kind: str, prompt: str | None = None
) -> AgentRun:
    if kind not in AgentRun.KINDS:
        raise ValueError(f"Unknown run kind {kind!r}")
    if not configured():
        raise JanusUnavailable(
            "Janus is not set up. Add its address and API key under Settings → Connectors → Janus."
        )
    run = AgentRun(
        brand_id=brand.id,
        user_id=user.id if user else None,
        kind=kind,
        prompt=(prompt or "")[:4000],
        session_key=f"spark-brand-{brand.id}",
        status="queued",
    )
    db.add(run)
    await db.flush()
    _accounts, _pillars, instructions = await _context(db, brand)
    task = await _task(db, brand, kind, prompt)
    try:
        run.janus_run_id = await Janus().start_run(
            input=task,
            instructions=instructions,
            session_key=run.session_key,
            session_id=f"spark-run-{run.id}",
        )
        run.status = "running"
    except JanusError as e:
        run.status, run.error, run.finished_at = "failed", str(e), datetime.now(UTC)
    activity.record(
        db,
        brand.id,
        user,
        VERBS.get(kind, "started a run"),
        "agent_run",
        run.id,
        (prompt or kind)[:120],
        {"kind": kind},
    )
    await db.commit()
    await events.publish("agent", brand.id, ids=[run.id])
    if run.status == "running":
        queued = await jobs.enqueue("follow_agent_run", run.id)
        if not queued and INLINE_FOLLOW:
            asyncio.get_running_loop().create_task(_follow_in_own_session(run.id))
    return run


async def _follow_in_own_session(run_id: int) -> None:
    from spark.db import SessionLocal

    async with SessionLocal() as db:
        try:
            await follow(db, run_id)
        except Exception:
            log.exception("Following agent run %s failed", run_id)


# ---- following ------------------------------------------------------------------------------------
def _merge_event(evs: list, ev: dict) -> list:
    out = list(evs)
    if ev.get("event") == "message.delta" and out and out[-1].get("event") == "message.delta":
        out[-1] = {**out[-1], "delta": (out[-1].get("delta") or "") + (ev.get("delta") or "")}
    else:
        out.append(ev)
    return out[-MAX_EVENTS:]


async def follow(db: AsyncSession, run_id: int) -> str:
    """Consume the run's event stream until it ends; returns the final status."""
    run = await db.get(AgentRun, run_id)
    if run is None:
        return "missing"
    if run.status not in ("queued", "running", "waiting_approval") or not run.janus_run_id:
        return run.status
    brand = await db.get(Brand, run.brand_id)
    client = Janus()
    try:
        async for ev in client.events(run.janus_run_id):
            name = ev.get("event")
            run.events = _merge_event(run.events or [], ev)
            if name == "approval.request":
                run.status = "waiting_approval"
                try:
                    await client.approve(run.janus_run_id, "deny")
                    log.info("Denied a shell approval for run %s: %s", run.id, ev.get("command"))
                except JanusError as e:
                    log.warning("Could not deny approval for run %s: %s", run.id, e)
                run.status = "running"
            elif name == "run.completed":
                run.output = str(ev.get("output") or "")
                run.usage = ev.get("usage") or {}
                run.proposal = await parse_proposal(db, brand, run.output)
                run.status, run.finished_at = "completed", datetime.now(UTC)
            elif name == "run.failed":
                run.status, run.error, run.finished_at = (
                    "failed",
                    str(ev.get("error") or "The agent failed"),
                    datetime.now(UTC),
                )
            elif name == "run.cancelled":
                run.status, run.finished_at = "cancelled", datetime.now(UTC)
            await db.commit()
            await events.publish("agent", run.brand_id, ids=[run.id])
    except JanusError as e:
        run.status, run.error, run.finished_at = "failed", str(e), datetime.now(UTC)
    except Exception as e:  # network drop mid-stream: keep what we have, mark failed
        log.exception("Agent run %s stream broke", run.id)
        run.status, run.error, run.finished_at = (
            "failed",
            f"Lost the connection to Janus: {e}",
            datetime.now(UTC),
        )
    if run.status in ("running", "waiting_approval"):  # the stream closed without a terminal event
        run.status, run.error, run.finished_at = (
            "failed",
            "Janus closed the stream before finishing",
            datetime.now(UTC),
        )
    await db.commit()
    await events.publish("agent", run.brand_id, ids=[run.id])
    if run.status == "completed":
        activity.record(
            db,
            run.brand_id,
            None,
            "finished",
            "agent_run",
            run.id,
            (run.proposal or {}).get("summary", "")[:120],
            {"kind": run.kind, "posts": len((run.proposal or {}).get("posts") or [])},
        )
        await db.commit()
    return run.status


# ---- the proposal -----------------------------------------------------------------------------------
_FENCE = re.compile(r"```\s*spark-proposal\s*\n(.*?)```", re.S | re.I)


def _extract_json(text: str) -> dict | None:
    m = _FENCE.search(text or "")
    candidates = [m.group(1)] if m else []
    if not candidates:  # a bare JSON object at the end of the answer
        i = (text or "").rfind('{"summary"')
        if i >= 0:
            candidates.append(text[i:])
    for c in candidates:
        c = c.strip()
        for end in (len(c), c.rfind("}") + 1):
            try:
                data = json.loads(c[:end])
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, ValueError):
                continue
    return None


async def parse_proposal(db: AsyncSession, brand: Brand, output: str) -> dict:
    """Normalise the agent's JSON: channels → account ids, pillar → id, when → UTC ISO."""
    data = _extract_json(output) or {}
    accounts = await svc.active_accounts(db, brand)
    pillars = (
        (await db.execute(select(ContentPillar).where(ContentPillar.brand_id == brand.id)))
        .scalars()
        .all()
    )
    by_name = {p.name.lower(): p for p in pillars}
    posts = []
    for raw in (data.get("posts") or [])[:50]:
        if not isinstance(raw, dict) or not str(raw.get("content") or "").strip():
            continue
        wanted = [str(c).strip().lower() for c in (raw.get("channels") or []) if str(c).strip()]
        ids = [
            a.id
            for a in accounts
            if a.handle.lower() in wanted
            or a.platform.lower() in wanted
            or (a.display_name or "").lower() in wanted
        ]
        when = None
        if raw.get("when"):
            try:
                dt = datetime.fromisoformat(str(raw["when"]).replace("Z", "+00:00"))
                when = (
                    (dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo(brand.timezone)))
                    .astimezone(UTC)
                    .isoformat()
                )
            except ValueError:
                when = None
        pillar = by_name.get(str(raw.get("pillar") or "").strip().lower())
        posts.append(
            {
                "content": str(raw["content"]).strip(),
                "link": (str(raw.get("link")).strip() or None) if raw.get("link") else None,
                "channels": wanted,
                "channel_ids": ids or [a.id for a in accounts],
                "when": when,
                "pillar": raw.get("pillar"),
                "pillar_id": pillar.id if pillar else None,
            }
        )
    out: dict = {
        "summary": str(data.get("summary") or "").strip()[:300]
        or (output or "").strip().split("\n")[0][:300],
        "posts": posts,
    }
    vp = data.get("voice_profile")
    if isinstance(vp, dict) and any(
        str(vp.get(k) or "").strip() for k in ("tone", "audience", "rules", "examples", "summary")
    ):
        out["voice_profile"] = {
            k: str(vp.get(k) or "").strip()
            for k in ("tone", "audience", "rules", "examples", "summary")
        }
    return out


# ---- applying ----------------------------------------------------------------------------------------
class NotApplicable(Exception):
    pass


async def apply(
    db: AsyncSession,
    brand: Brand,
    user: User,
    run: AgentRun,
    indexes: list[int] | None = None,
    schedule: bool | None = None,
) -> dict:
    if run.status != "completed":
        raise NotApplicable("This run has no finished proposal to apply")
    if run.applied_at is not None:
        raise NotApplicable("This proposal was already applied")
    proposal = run.proposal or {}
    auto = guardrails.config(brand).get("auto_schedule", False) if schedule is None else schedule
    created: list[int] = []
    for i, item in enumerate(proposal.get("posts") or []):
        if indexes is not None and i not in indexes:
            continue
        post = await svc.save_post(
            db,
            brand,
            user,
            None,
            content=item["content"],
            link=item.get("link"),
            media_ids=[],
            campaign_id=None,
            notes=None,
            source="janus",
            targets=[svc.TargetInput(account_id=a) for a in item.get("channel_ids") or []],
            pillar_id=item.get("pillar_id"),
        )
        post.agent_run_id = run.id
        post.proposed_for = datetime.fromisoformat(item["when"]) if item.get("when") else None
        if auto and post.proposed_for and post.proposed_for > datetime.now(UTC):
            try:
                await svc.place_post(db, brand, user, post, "schedule", post.proposed_for)
            except svc.PlaceError:
                pass  # stays a draft in the plan tray
        created.append(post.id)
    voice_applied = False
    vp = proposal.get("voice_profile")
    if vp:
        brand.voice_profile = {**vp, "learned_at": datetime.now(UTC).isoformat(), "run_id": run.id}
        for field in ("tone", "audience", "rules", "examples"):
            if vp.get(field):
                setattr(brand, f"voice_{field}", vp[field])
        voice_applied = True
    run.applied_at = datetime.now(UTC)
    activity.record(
        db,
        brand.id,
        user,
        "applied",
        "agent_run",
        run.id,
        proposal.get("summary", "")[:120],
        {"posts": len(created), "voice": voice_applied, "scheduled": bool(auto)},
    )
    await db.commit()
    await events.publish("posts", brand.id, ids=created)
    await events.publish("agent", brand.id, ids=[run.id])
    return {"created": len(created), "post_ids": created, "voice_applied": voice_applied}


# ---- the plan tray ------------------------------------------------------------------------------------
async def plan_posts(db: AsyncSession, brand: Brand) -> list[Post]:
    return (
        (
            await db.execute(
                select(Post)
                .options(selectinload(Post.targets).selectinload(PostTarget.account))
                .where(
                    Post.brand_id == brand.id,
                    Post.agent_run_id.is_not(None),
                    Post.status == PostStatus.draft,
                    Post.is_autosave.is_(False),
                )
                .order_by(Post.proposed_for.is_(None), Post.proposed_for, Post.id)
            )
        )
        .scalars()
        .all()
    )


async def schedule_plan(
    db: AsyncSession, brand: Brand, user: User, post_ids: list[int] | None = None
) -> tuple[int, list[str]]:
    """Place the plan's drafts: at their proposed time when it is still ahead, otherwise in the queue."""
    now = datetime.now(UTC)
    n, problems = 0, []
    for post in await plan_posts(db, brand):
        if post_ids is not None and post.id not in post_ids:
            continue
        when = as_utc(post.proposed_for)
        try:
            if when and when > now:
                await svc.place_post(db, brand, user, post, "schedule", when)
            else:
                await svc.place_post(db, brand, user, post, "queue", None)
            n += 1
        except svc.PlaceError as e:
            problems.append(f"#{post.id}: " + "; ".join(e.problems))
    if n:
        activity.record(db, brand.id, user, "scheduled the plan", "agent_run", None, f"{n} posts")
    await db.commit()
    for post in await plan_posts(db, brand):
        await svc.enqueue_due(post)
    await events.publish("posts", brand.id)
    return n, problems


# ---- weekly plans on a schedule -----------------------------------------------------------------------
async def start_due_weekly_plans(db: AsyncSession) -> int:
    """Start a weekly_plan run for every brand whose plan day is today and that has none this week."""
    if not configured():
        return 0
    started = 0
    for brand in (await db.execute(select(Brand))).scalars().all():
        wp = (brand.agent_config or {}).get("weekly_plan") or {}
        if not wp.get("enabled"):
            continue
        today = datetime.now(ZoneInfo(brand.timezone)).weekday()
        if int(wp.get("weekday", 0)) != today:
            continue
        since = datetime.now(UTC) - timedelta(days=6)
        recent = await db.scalar(
            select(AgentRun.id)
            .where(
                AgentRun.brand_id == brand.id,
                AgentRun.kind == "weekly_plan",
                AgentRun.created_at >= since,
            )
            .limit(1)
        )
        if recent:
            continue
        try:
            await start(db, brand, None, "weekly_plan")
            started += 1
        except JanusError as e:
            log.warning("Weekly plan for %s not started: %s", brand.slug, e)
    return started


# ---- status for the UI ------------------------------------------------------------------------------------
_status_cache: dict = {"at": None, "value": None}


async def status(force: bool = False) -> dict:
    now = datetime.now(UTC)
    if not force and _status_cache["at"] and now - _status_cache["at"] < timedelta(seconds=60):
        return _status_cache["value"]
    s = get_settings()
    out = {
        "configured": configured(),
        "healthy": False,
        "version": None,
        "base_url": s.janus_base_url,
        "checked_at": now,
        "can_update": bool(s.janus_update_webhook),
    }
    if out["configured"]:
        client = Janus()
        out["healthy"] = await client.health()
        if out["healthy"]:
            out["version"] = await client.version()
    _status_cache.update(at=now, value=out)
    return out


def forget_status() -> None:
    _status_cache.update(at=None, value=None)
