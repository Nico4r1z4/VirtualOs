"""Apify client tests with pytest-httpx — no real network."""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from virtualos.connectors.apify import ApifyError, run_actor_sync


@pytest.fixture(autouse=True)
def _apify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from virtualos.config.settings import get_settings

    monkeypatch.setenv("APIFY_TOKEN", "test-token")
    get_settings.cache_clear()


async def test_run_actor_sync_returns_items(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*/acts/foo~bar/run-sync-get-dataset-items.*"),
        json=[{"id": "1"}, {"id": "2"}],
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*/acts/foo~bar/runs/last.*"),
        json={"data": {"usageTotalUsd": 0.031}},
    )
    items = await run_actor_sync("foo/bar", {"x": 1}, workspace_id="ws-1")
    assert items == [{"id": "1"}, {"id": "2"}]


async def test_run_actor_sync_error_raises(httpx_mock: HTTPXMock) -> None:
    # Both tenacity attempts must be mocked.
    for _ in range(2):
        httpx_mock.add_response(
            method="POST",
            url=re.compile(r".*/acts/foo~bar/run-sync-get-dataset-items.*"),
            status_code=402,
            text="insufficient credits",
        )
    with pytest.raises(ApifyError, match="402"):
        await run_actor_sync("foo/bar", {}, workspace_id="ws-1")


async def test_webhook_rejects_bad_secret(monkeypatch: pytest.MonkeyPatch, fake_pool) -> None:
    import httpx as httpx_lib

    from virtualos.config.settings import get_settings

    monkeypatch.setenv("APIFY_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()

    from virtualos.api.main import create_app

    app = create_app()
    transport = httpx_lib.ASGITransport(app=app)
    async with httpx_lib.AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post(
            "/webhooks/apify", json={}, headers={"X-Webhook-Secret": "wrong"}
        )
        ok = await client.post(
            "/webhooks/apify",
            json={"eventType": "ACTOR.RUN.SUCCEEDED", "resource": {"id": "r1"}},
            headers={"X-Webhook-Secret": "s3cret"},
        )
    assert bad.status_code == 401
    assert ok.status_code == 200
