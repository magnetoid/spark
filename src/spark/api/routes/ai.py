"""Quick AI helpers used while composing: generate, rewrite, hashtags. Long jobs go to Janus later."""

from fastapi import APIRouter, Depends

from spark.api import deps
from spark.api.errors import ApiError
from spark.api.schemas import GenerateIn, HashtagsIn, RewriteIn
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
