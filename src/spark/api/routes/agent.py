"""The agent: Janus runs per brand, their proposals, and the plan tray."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    Actor,
    AgentApplyIn,
    AgentApplyOut,
    AgentRunIn,
    AgentRunOut,
    AgentStatusOut,
    PlanOut,
    PlanScheduleIn,
    PlanScheduleOut,
    PostOut,
)
from spark.db import get_db
from spark.models import AgentRun
from spark.services import agent
from spark.services.janus import JanusError, JanusUnavailable
from spark.services.publisher import as_utc

router = APIRouter(prefix="/brands/{brand_id}/agent", tags=["agent"])


def _out(r: AgentRun, full: bool = True) -> AgentRunOut:
    return AgentRunOut(
        id=r.id,
        kind=r.kind,
        status=r.status,
        prompt=r.prompt,
        janus_run_id=r.janus_run_id,
        output=r.output if full else None,
        proposal=r.proposal or {},
        events=(r.events or []) if full else [],
        usage=r.usage or {},
        error=r.error,
        summary=(r.proposal or {}).get("summary") or "",
        posts=len((r.proposal or {}).get("posts") or []),
        applied_at=as_utc(r.applied_at),
        finished_at=as_utc(r.finished_at),
        created_at=as_utc(r.created_at),
        updated_at=as_utc(r.updated_at),
        user=Actor(id=r.user.id, name=r.user.name) if r.user else None,
    )


async def _run(db: AsyncSession, ctx: deps.BrandCtx, run_id: int) -> AgentRun:
    r = await db.get(AgentRun, run_id)
    if r is None or r.brand_id != ctx.brand.id:
        raise not_found("No such run")
    return r


@router.get("/status", response_model=AgentStatusOut)
async def agent_status(force: bool = False, ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    return AgentStatusOut(**await agent.status(force))


@router.get("/runs", response_model=list[AgentRunOut])
async def list_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
):
    rows = (
        (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.brand_id == ctx.brand.id)
                .order_by(AgentRun.id.desc())
                .limit(min(limit, 100))
            )
        )
        .scalars()
        .all()
    )
    return [_out(r, full=False) for r in rows]


@router.post("/runs", response_model=AgentRunOut, status_code=202)
async def start_run(
    body: AgentRunIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    try:
        run = await agent.start(db, ctx.brand, ctx.user, body.kind, body.prompt)
    except JanusUnavailable as e:
        raise ApiError(409, "janus_not_configured", str(e)) from e
    except JanusError as e:
        raise ApiError(502, "janus_error", str(e)) from e
    return _out(run)


@router.get("/runs/{run_id}", response_model=AgentRunOut)
async def get_run(
    run_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)
):
    return _out(await _run(db, ctx, run_id))


@router.post("/runs/{run_id}/stop", response_model=AgentRunOut)
async def stop_run(
    run_id: int, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)
):
    r = await _run(db, ctx, run_id)
    if r.status in ("queued", "running", "waiting_approval") and r.janus_run_id:
        try:
            await agent.Janus().stop(r.janus_run_id)
        except JanusError as e:
            raise ApiError(502, "janus_error", str(e)) from e
    return _out(r)


@router.post("/runs/{run_id}/apply", response_model=AgentApplyOut)
async def apply_run(
    run_id: int,
    body: AgentApplyIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    r = await _run(db, ctx, run_id)
    what = body.what or ("posts" if (r.proposal or {}).get("posts") else "voice")
    if what == "voice" and not ctx.can_manage():
        raise ApiError(403, "forbidden", "Only owners change the brand voice")
    try:
        out = await agent.apply(db, ctx.brand, ctx.user, r, body.post_indexes, body.schedule, what)
    except agent.NotApplicable as e:
        raise ApiError(409, "not_applicable", str(e)) from e
    return AgentApplyOut(**out)


# ---- the plan tray ------------------------------------------------------------------------------
@router.get("/plan", response_model=PlanOut)
async def plan(db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.brand_ctx)):
    posts = await agent.plan_posts(db, ctx.brand)
    latest = await db.scalar(
        select(AgentRun)
        .where(AgentRun.brand_id == ctx.brand.id, AgentRun.kind == "weekly_plan")
        .order_by(AgentRun.id.desc())
        .limit(1)
    )
    return PlanOut(
        run=_out(latest, full=False) if latest else None, posts=[PostOut.of(p) for p in posts]
    )


@router.post("/plan/schedule", response_model=PlanScheduleOut)
async def schedule_plan(
    body: PlanScheduleIn,
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.editor_brand),
):
    n, problems = await agent.schedule_plan(db, ctx.brand, ctx.user, body.post_ids)
    msg = f"Scheduled {n} {'post' if n == 1 else 'posts'}" + (
        f"; {len(problems)} kept as drafts" if problems else ""
    )
    return PlanScheduleOut(scheduled=n, problems=problems, message=msg)
