"""Apify webhook endpoint. Verified with a shared secret in constant time."""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

from virtualos.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/apify")
async def apify_webhook(request: Request) -> dict[str, str]:
    settings = get_settings()
    if settings.apify_webhook_secret is None:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    provided = request.headers.get("X-Webhook-Secret", "") or request.query_params.get(
        "secret", ""
    )
    expected = settings.apify_webhook_secret.get_secret_value()
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    payload = await request.json()
    event_type = payload.get("eventType", "unknown")
    run_id = (payload.get("resource") or {}).get("id")
    logger.info("apify webhook: %s run=%s", event_type, run_id)
    # MVP runs actors synchronously; async runs will enqueue a processing job here.
    return {"status": "accepted"}
