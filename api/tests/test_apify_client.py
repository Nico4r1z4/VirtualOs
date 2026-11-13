"""Apify client tests with pytest-httpx — no real network."""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from virtualos.connectors import apify
from virtualos.connectors.apify import ApifyError, run_actor_sync

RUN_START = re.compile(r".*/acts/foo~bar/runs\?.*")
RUN_STATUS = re.compile(r".*/actor-runs/run-1.*")
DATASET = re.compile(r".*/datasets/ds-1/items.*")


@pytest.fixture(autouse=True)
def _apify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from virtualos.config.settings import get_settings

    monkeypatch.setenv("APIFY_TOKEN", "test-token")
    get_settings.cache_clear()
    monkeypatch.setattr(apify, "_SETTLE_DELAY_S", 0)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    costs: list[float] = []

    async def fake_record(workspace_id: str, provider: str, **kw: float) -> None:
        costs.append(kw["cost_usd"])

    monkeypatch.setattr(apify, "record_usage", fake_record)
    return costs


def _run(status: str, usd: float | None) -> dict:
    return {
        "data": {"id": "run-1", "status": status, "defaultDatasetId": "ds-1", "usageTotalUsd": usd}
    }


async def test_run_records_settled_cost_of_its_own_run(httpx_mock: HTTPXMock, recorded) -> None:
    # Start returns RUNNING; status poll -> SUCCEEDED with usage still settling.
    httpx_mock.add_response(method="POST", url=RUN_START, json=_run("RUNNING", 0.0))
    httpx_mock.add_response(method="GET", url=RUN_STATUS, json=_run("SUCCEEDED", 0.001))
    httpx_mock.add_response(method="GET", url=RUN_STATUS, json=_run("SUCCEEDED", 0.223))
    httpx_mock.add_response(method="GET", url=RUN_STATUS, json=_run("SUCCEEDED", 0.223))
    httpx_mock.add_response(method="GET", url=DATASET, json=[{"id": "1"}, {"id": "2"}])

    items = await run_actor_sync("foo/bar", {"x": 1}, workspace_id="ws-1", max_items=2)

    assert items == [{"id": "1"}, {"id": "2"}]
    # Regression 2026-11-13: must record the settled 0.223, not the early 0.001.
    assert recorded == [0.223]
    # Never reads "last run" (could be another workspace's concurrent run).
    assert not any("/runs/last" in str(r.url) for r in httpx_mock.get_requests())


async def test_token_only_in_header(httpx_mock: HTTPXMock, recorded) -> None:
    httpx_mock.add_response(method="POST", url=RUN_START, json=_run("SUCCEEDED", 0.05))
    httpx_mock.add_response(method="GET", url=RUN_STATUS, json=_run("SUCCEEDED", 0.05))
    httpx_mock.add_response(method="GET", url=DATASET, json=[])
    await run_actor_sync("foo/bar", {}, workspace_id="ws-1")
    for req in httpx_mock.get_requests():
        assert "test-token" not in str(req.url)
        assert req.headers["Authorization"] == "Bearer test-token"


async def test_failed_run_raises_but_still_records_cost(httpx_mock: HTTPXMock, recorded) -> None:
    httpx_mock.add_response(method="POST", url=RUN_START, json=_run("FAILED", 0.02))
    httpx_mock.add_response(method="GET", url=RUN_STATUS, json=_run("FAILED", 0.02))
    with pytest.raises(ApifyError, match="FAILED"):
        await run_actor_sync("foo/bar", {}, workspace_id="ws-1")
    assert recorded == [0.02]


async def test_start_error_is_not_retried(httpx_mock: HTTPXMock, recorded) -> None:
    # A retried start could launch and bill a second run: exactly one POST.
    httpx_mock.add_response(
        method="POST", url=RUN_START, status_code=402, text="insufficient credits"
    )
    with pytest.raises(ApifyError, match="402"):
        await run_actor_sync("foo/bar", {}, workspace_id="ws-1")
    assert len([r for r in httpx_mock.get_requests() if r.method == "POST"]) == 1
    assert recorded == []


async def test_webhook_rejects_bad_secret(monkeypatch: pytest.MonkeyPatch, fake_pool) -> None:
    import httpx as httpx_lib

    from virtualos.config.settings import get_settings

    monkeypatch.setenv("APIFY_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()

    from virtualos.api.main import create_app

    app = create_app()
    transport = httpx_lib.ASGITransport(app=app)
    async with httpx_lib.AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post("/webhooks/apify", json={}, headers={"X-Webhook-Secret": "wrong"})
        ok = await client.post(
            "/webhooks/apify",
            json={"eventType": "ACTOR.RUN.SUCCEEDED", "resource": {"id": "r1"}},
            headers={"X-Webhook-Secret": "s3cret"},
        )
    assert bad.status_code == 401
    assert ok.status_code == 200
