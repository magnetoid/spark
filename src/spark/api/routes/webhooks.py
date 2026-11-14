"""Outbound webhooks: addresses that receive Spark's events as signed HTTP POSTs. Owners only."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api import deps
from spark.api.errors import ApiError, not_found
from spark.api.schemas import (
    DeliveryList,
    DeliveryOut,
    WebhookCreated,
    WebhookEventInfo,
    WebhookIn,
    WebhookList,
    WebhookOut,
    WebhookUpdate,
)
from spark.db import get_db
from spark.models import Brand, User, WebhookDelivery, WebhookEndpoint
from spark.services import hooks, outbox
from spark.services.publisher import as_utc

router = APIRouter(tags=["webhooks"])


def _out(ep: WebhookEndpoint) -> dict:
    return {
        "id": ep.id,
        "url": ep.url,
        "description": ep.description or "",
        "brand_id": ep.brand_id,
        "events": list(ep.events or []),
        "enabled": ep.enabled,
        "failures": ep.failures or 0,
        "last_status": ep.last_status,
        "last_error": ep.last_error,
        "last_delivery_at": as_utc(ep.last_delivery_at),
        "disabled_reason": ep.disabled_reason,
        "created_at": as_utc(ep.created_at),
    }


def _delivery(d: WebhookDelivery) -> DeliveryOut:
    return DeliveryOut(
        id=d.id,
        event=d.event,
        event_id=d.event_id,
        status=d.status,
        attempts=d.attempts,
        response_status=d.response_status,
        error=d.error,
        created_at=as_utc(d.created_at),
        delivered_at=as_utc(d.delivered_at),
        next_attempt_at=as_utc(d.next_attempt_at) if d.status == "pending" else None,
    )


async def _endpoint(db: AsyncSession, webhook_id: int) -> WebhookEndpoint:
    ep = await db.get(WebhookEndpoint, webhook_id)
    if ep is None:
        raise not_found("Webhook not found")
    return ep


async def _check_url(url: str) -> str:
    if problem := await hooks.url_problem(url):
        raise ApiError(422, "invalid_url", problem)
    return url.strip()


def _check_events(events: list[str]) -> list[str]:
    unknown = sorted(set(events) - set(outbox.EVENTS))
    if unknown:
        raise ApiError(422, "unknown_event", f"Spark has no event called {', '.join(unknown)}")
    return sorted(set(events))


async def _check_brand(db: AsyncSession, brand_id: int | None) -> int | None:
    if brand_id is not None and await db.get(Brand, brand_id) is None:
        raise not_found("Brand not found")
    return brand_id


@router.get("/webhooks", response_model=WebhookList)
async def list_webhooks(db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)):
    rows = (await db.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.id))).scalars().all()
    return WebhookList(
        items=[WebhookOut(**_out(ep)) for ep in rows],
        events=[WebhookEventInfo(name=k, description=v) for k, v in outbox.EVENTS.items()],
    )


@router.post("/webhooks", response_model=WebhookCreated, status_code=201)
async def create_webhook(
    body: WebhookIn, db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)
):
    url = await _check_url(body.url)
    events = _check_events(body.events)
    brand_id = await _check_brand(db, body.brand_id)
    ep, secret = await hooks.create(db, url, brand_id, events, body.description, user.id)
    return WebhookCreated(**_out(ep), secret=secret)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: int,
    body: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.owner),
):
    ep = await _endpoint(db, webhook_id)
    sent = body.model_fields_set
    if "url" in sent and body.url is not None:
        ep.url = await _check_url(body.url)
    if "events" in sent and body.events is not None:
        ep.events = _check_events(body.events)
    if "brand_id" in sent:
        ep.brand_id = await _check_brand(db, body.brand_id)
    if "description" in sent and body.description is not None:
        ep.description = body.description.strip()
    if "enabled" in sent and body.enabled is not None:
        ep.enabled = body.enabled
        if body.enabled:  # a fresh start
            ep.failures, ep.disabled_reason = 0, None
    await db.commit()
    return WebhookOut(**_out(ep))


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)
):
    await hooks.remove(db, await _endpoint(db, webhook_id))
    return Response(status_code=204)


@router.post("/webhooks/{webhook_id}/test", response_model=DeliveryOut)
async def test_webhook(
    webhook_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)
):
    return _delivery(await hooks.send_test(db, await _endpoint(db, webhook_id)))


@router.get("/webhooks/{webhook_id}/deliveries", response_model=DeliveryList)
async def list_deliveries(
    webhook_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(deps.owner)
):
    ep = await _endpoint(db, webhook_id)
    rows = (
        (
            await db.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.endpoint_id == ep.id)
                .order_by(WebhookDelivery.id.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return DeliveryList(items=[_delivery(d) for d in rows])
