"""Inbound provider webhooks. No session, no CSRF: authenticated by signature."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.services import webhooks

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhooks/zernio")
async def zernio_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    sig = request.headers.get("X-Zernio-Signature") or request.headers.get("X-Late-Signature")
    if not webhooks.verify_signature(raw, sig):
        raise HTTPException(401, "Bad signature")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "Body is not JSON") from None
    event = payload.get("event") or request.headers.get("X-Zernio-Event") or ""
    event_id = payload.get("id") or request.headers.get("X-Zernio-Event-Id") or ""
    if not await webhooks.remember(db, event_id, event):
        return {"ok": True, "result": "duplicate"}
    try:
        result = await webhooks.handle_zernio_event(db, payload)
    except Exception:
        # Zernio retries on non-2xx; a bug in a handler should not make it hammer us.
        log.exception("Zernio webhook %s (%s) failed", event, event_id)
        await db.rollback()
        result = "error"
    else:
        await db.commit()
    log.info("Zernio webhook %s -> %s", event, result)
    return {"ok": True, "result": result}
