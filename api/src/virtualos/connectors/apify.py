"""Thin async Apify client: run an actor, wait for it, read its dataset.

Cost: every run's real usageTotalUsd is recorded per workspace in
vos.api_usage (CLAUDE.md hard rule 7). Only this module talks to Apify.

Why runs are tracked by ID (bug found live 2026-11-13): the previous version
used the run-sync endpoint and then read `/acts/{id}/runs/last` for cost.
Apify finalizes usage a few seconds AFTER the run ends, so the value read was
incomplete (0.001 USD recorded for a 0.223 USD run), and with two workspaces
ingesting concurrently "last" could even be the other workspace's run.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from virtualos.config.settings import get_settings
from virtualos.observability.usage import record_usage

logger = logging.getLogger(__name__)

_BASE = "https://api.apify.com/v2"
_TIMEOUT = httpx.Timeout(90.0, connect=15.0)
_WAIT_S = 60  # Apify long-poll window per status request (max 60 for this param)
_RUN_DEADLINE_S = 15 * 60
_TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}
# Cost settling: Apify updates usageTotalUsd shortly after the run ends.
_SETTLE_DELAY_S = 3.0
_SETTLE_MAX_READS = 6


class ApifyError(Exception):
    pass


def _token() -> str:
    settings = get_settings()
    if settings.apify_token is None:
        raise ApifyError("APIFY_TOKEN is not configured")
    return settings.apify_token.get_secret_value()


def _auth_headers() -> dict[str, str]:
    # Token goes in the Authorization header, NEVER the query string:
    # URLs end up in logs (httpx, proxies, Apify request logs).
    return {"Authorization": f"Bearer {_token()}"}


async def _get_json(client: httpx.AsyncClient, url: str, **params: Any) -> dict[str, Any]:
    """GET with a few retries on transient errors (reads are idempotent)."""
    last: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.get(url, params=params or None)
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)
            if resp.status_code >= 400:
                raise ApifyError(f"Apify GET {url} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last = exc
            await asyncio.sleep(2 * (attempt + 1))
    raise ApifyError(f"Apify GET {url} failed after retries: {last}") from last


async def run_actor_sync(
    actor_id: str,
    run_input: dict[str, Any],
    *,
    workspace_id: str,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """Start an actor run, wait for it, return its dataset items, record its cost.

    The start request is NOT retried: a retry after a lost response would
    launch (and bill) a second run.
    """
    slug = actor_id.replace("/", "~")
    start_params: dict[str, Any] = {"waitForFinish": _WAIT_S}
    if max_items is not None:
        start_params["maxItems"] = max_items

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_auth_headers()) as client:
        resp = await client.post(f"{_BASE}/acts/{slug}/runs", params=start_params, json=run_input)
        if resp.status_code >= 400:
            raise ApifyError(
                f"Apify {actor_id} failed to start: {resp.status_code} {resp.text[:300]}"
            )
        run = resp.json()["data"]
        run_id = run["id"]

        deadline = time.monotonic() + _RUN_DEADLINE_S
        while run.get("status") not in _TERMINAL:
            if time.monotonic() > deadline:
                raise ApifyError(f"Apify {actor_id} run {run_id} did not finish in time")
            run = (await _get_json(client, f"{_BASE}/actor-runs/{run_id}", waitForFinish=_WAIT_S))[
                "data"
            ]

        # Record cost even for failed runs: Apify bills them too.
        cost_usd = await _settled_cost(client, run_id, run.get("usageTotalUsd"))
        await record_usage(
            workspace_id, "apify", units=cost_usd, unit_label="USD", cost_usd=cost_usd
        )

        if run.get("status") != "SUCCEEDED":
            raise ApifyError(f"Apify {actor_id} run {run_id} ended {run.get('status')}")

        item_params: dict[str, Any] = {"clean": "true", "format": "json"}
        if max_items is not None:
            item_params["limit"] = max_items
        dataset_id = run["defaultDatasetId"]
        items_resp = await client.get(f"{_BASE}/datasets/{dataset_id}/items", params=item_params)
        if items_resp.status_code >= 400:
            raise ApifyError(
                f"Apify dataset {dataset_id} read failed: {items_resp.status_code} {items_resp.text[:300]}"
            )
        items = items_resp.json()

    logger.info(
        "apify run %s (%s): %d items, cost=%.4f USD", actor_id, run_id, len(items), cost_usd
    )
    return items if isinstance(items, list) else []


async def _settled_cost(client: httpx.AsyncClient, run_id: str, initial: Any) -> float:
    """Re-read the run until usageTotalUsd stops changing. Never raises."""
    last = float(initial or 0.0)
    for _ in range(_SETTLE_MAX_READS):
        await asyncio.sleep(_SETTLE_DELAY_S)
        try:
            data = (await _get_json(client, f"{_BASE}/actor-runs/{run_id}"))["data"]
            current = float(data.get("usageTotalUsd") or 0.0)
        except Exception:
            logger.debug("could not re-read cost for run %s", run_id)
            break
        if current > 0 and abs(current - last) < 1e-9:
            return current
        last = current
    return last
