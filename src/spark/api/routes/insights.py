"""Analytics for a brand: totals, trend, by platform, top posts, link clicks, best times."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.schemas import AnalyticsOut, TopPost, WeekPoint
from spark.db import get_db
from spark.services import analytics, scheduler
from spark.services.publisher import as_utc

router = APIRouter(tags=["analytics"])
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@router.get("/brands/{brand_id}/analytics", response_model=AnalyticsOut)
async def overview(
    db: AsyncSession = Depends(get_db),
    ctx: deps.BrandCtx = Depends(deps.brand_ctx),
    days: int = Query(30, ge=1, le=365),
):
    data = await analytics.overview(db, ctx.brand.id, days=days)
    prev = await analytics.compare(db, ctx.brand.id, days=days)
    clicks = await analytics.link_clicks_series(db, ctx.brand.id, days=days)
    best = await scheduler.best_times(db, ctx.brand.id)
    s = data["series"]
    return AnalyticsOut(
        days=days,
        published=data["published"],
        scheduled=data["scheduled"],
        failed=data["failed"],
        followers=data["followers"],
        impressions=data["totals"]["impressions"],
        engagements=data["engagements"],
        engagement_rate_pct=round(data["engagement_rate"], 2),
        link_clicks=data["link_clicks"],
        totals=data["totals"],
        change_pct={
            "impressions": prev["impressions"],
            "engagements": prev["engagements"],
            "rate": prev["rate"] - prev["rate_prev"] if prev.get("rate_prev") is not None else None,
        },
        by_platform={k: dict(v) for k, v in data["by_platform"].items()},
        series=[
            WeekPoint(day=d, impressions=i, engagements=e)
            for d, i, e in zip(s["days"], s["impressions"], s["engagements"], strict=False)
        ],
        link_clicks_series=[
            {"day": d, "clicks": c} for d, c in zip(clicks["days"], clicks["clicks"], strict=False)
        ],
        top=[
            TopPost(
                post_id=t["target"].post_id,
                account_id=t["account"].id,
                handle=t["account"].handle,
                platform=t["account"].platform,
                engagements=t["engagements"],
                impressions=t["metric"].impressions,
                text=(t["target"].post.content if t["target"].post else "")[:280],
                url=t["target"].remote_url,
                published_at=as_utc(t["target"].published_at) if t["target"].published_at else None,
            )
            for t in data["top"]
        ],
        best_times=[
            {
                "weekday": b["weekday"],
                "day": DAYS[b["weekday"]],
                "hour": b["hour"],
                "score": round(b["score"], 4),
                "posts": b["posts"],
            }
            for b in best
        ],
    )


@router.post("/brands/{brand_id}/analytics/refresh")
async def refresh(
    db: AsyncSession = Depends(get_db), ctx: deps.BrandCtx = Depends(deps.editor_brand)
):
    n = await analytics.collect_metrics(db, brand_id=ctx.brand.id)
    return {"collected": n, "message": f"Pulled {n} metric snapshot(s)"}
