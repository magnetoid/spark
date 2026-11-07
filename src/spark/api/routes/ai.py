"""Quick AI helpers used while composing: generate, rewrite, hashtags. Long jobs go to Janus later."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError
from spark.api.schemas import GenerateIn, HashtagsIn, RepurposeIn, RepurposeOut, RewriteIn
from spark.db import get_db
from spark.services import activity
from spark.services import posts as svc
from spark.services.ai import AIUnavailable, ContentAI
from spark.services.fetch import fetch_page_text

router = APIRouter(tags=["ai"])
B = "/brands/{brand_id}"


def _ai() -> ContentAI:
    return ContentAI()


def _client() -> ContentAI:
    try:
        return _ai()
    except AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e))


@router.post(B + "/ai/generate")
async def generate(body: GenerateIn, ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    ai = _client()
    source = await fetch_page_text(body.url) if body.url else None
    try:
        drafts = await ai.generate(ctx.brand, body.brief, body.platforms or ["x", "linkedin"], source_text=source,
                                   link=body.link or body.url, variants=body.variants)
    except AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e))
    return {"drafts": [d.model_dump() for d in drafts]}


@router.post(B + "/ai/repurpose", response_model=RepurposeOut)
async def repurpose_source(body: RepurposeIn, db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    """A page, pasted text or a transcript becomes a series of drafts: through Janus when it is
    connected, otherwise with a direct Claude call."""
    from spark.services import agent, repurpose
    from spark.services.janus import JanusError, configured

    try:
        text, link = await repurpose.resolve_source(source_text=body.source_text, source_url=body.source_url, source_name=body.source_name)
    except repurpose.SourceError as e:
        raise ApiError(422, "bad_source", str(e)) from e
    accounts = await svc.active_accounts(db, ctx.brand)
    if body.account_ids:
        accounts = [a for a in accounts if a.id in body.account_ids]
    if not accounts:
        raise ApiError(422, "no_channels", "Pick at least one channel")
    if configured():
        try:
            run = await agent.start(db, ctx.brand, ctx.user, "repurpose", body.notes, extra={"text": text, "link": link, "accounts": accounts})
        except JanusError as e:
            raise ApiError(502, "janus_error", str(e)) from e
        return RepurposeOut(mode="janus", run_id=run.id, message="Janus is reading the source")
    try:
        ids = await repurpose.direct(db, ctx.brand, ctx.user, text, link, accounts, body.notes)
    except AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e)) from e
    activity.record(db, ctx.brand.id, ctx.user, "repurposed", "post", None, (body.source_name or body.source_url or "pasted text")[:120], {"posts": len(ids)})
    await db.commit()
    return RepurposeOut(mode="claude", created=len(ids), post_ids=ids, message=f"{len(ids)} {'draft' if len(ids) == 1 else 'drafts'} written from the source")


@router.post(B + "/ai/rewrite")
async def rewrite(body: RewriteIn, ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    ai = _client()
    try:
        return {"text": await ai.rewrite(ctx.brand, body.text, body.instruction, body.platform)}
    except AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e))


@router.post(B + "/ai/hashtags")
async def hashtags(body: HashtagsIn, ctx: deps.BrandCtx = Depends(deps.editor_brand)):
    ai = _client()
    try:
        return {"hashtags": await ai.hashtags(ctx.brand, body.text)}
    except AIUnavailable as e:
        raise ApiError(400, "ai_unavailable", str(e))
