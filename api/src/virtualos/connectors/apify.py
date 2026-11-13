"""Thin async Apify client: run an actor synchronously and read its dataset.

Cost: Apify reports usageTotalUsd per run; it is recorded per workspace in
vos.api_usage. Only this module talks to the Apify API.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from virtualos.config.settings import get_settings
from virtualos.observability.usage import record_usage

logger = logging.getLogger(__name__)

_BASE = "https://api.apify.com/v2"
# Actor runs can take minutes; waitForFinish caps at 300s per request so we poll.
_RUN_TIMEOUT = httpx.Timeout(330.0, connect=15.0)


class ApifyError(Exception):
    pass


def _token() -> str:
    settings = get_settings()
    if settings.apify_token is None:
        raise ApifyError("APIFY_TOKEN is not configured")
    return settings.apify_token.get_secret_value()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=20), reraise=True)
async def run_actor_sync(
    actor_id: str,
    run_input: dict[str, Any],
    *,
    workspace_id: str,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """Start an actor run, wait for it, return its dataset items.

    Uses the run-sync-get-dataset-items endpoint: one call, blocking until
    the run finishes (or the HTTP timeout hits, which tenacity retries once).
    """
    slug = actor_id.replace("/", "~")
    params: dict[str, Any] = {}
    if max_items is not None:
        params["maxItems"] = max_items

    # Token goes in the Authorization header, NEVER the query string:
    # URLs end up in logs (httpx, proxies, Apify request logs).
    async with httpx.AsyncClient(timeout=_RUN_TIMEOUT, headers=_auth_headers()) as client:
        resp = await client.post(
            f"{_BASE}/acts/{slug}/run-sync-get-dataset-items",
            params=params,
            json=run_input,
        )
        if resp.status_code >= 400:
            raise ApifyError(f"Apify {actor_id} failed: {resp.status_code} {resp.text[:300]}")
        items = resp.json()

    # The sync endpoint does not return run stats; fetch the last run for cost.
    cost_usd = await _last_run_cost(actor_id)
    await record_usage(
        workspace_id,
        "apify",
        units=cost_usd or 0.0,
        unit_label="USD",
        cost_usd=cost_usd or 0.0,
    )
    logger.info("apify run %s: %d items, cost=%s", actor_id, len(items), cost_usd)
    return items if isinstance(items, list) else []


async def _last_run_cost(actor_id: str) -> float | None:
    """Best-effort cost of the actor's most recent run. Never raises."""
    try:
        slug = actor_id.replace("/", "~")
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0), headers=_auth_headers()
        ) as client:
            resp = await client.get(f"{_BASE}/acts/{slug}/runs/last")
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return data.get("usageTotalUsd")
    except Exception:
        logger.debug("could not fetch apify run cost for %s", actor_id)
        return None
