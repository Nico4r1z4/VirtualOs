"""Shared fixtures. No network, no real DB (hard rule: tests use fixtures)."""

from __future__ import annotations

import os

import pytest

# Set before any virtualos import: api.main builds the app at import time.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from virtualos.config.settings import get_settings


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic settings for every test; never reads a real .env."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakePool:
    """Minimal asyncpg.Pool stand-in for endpoint tests."""

    def __init__(self, rows: dict[str, object] | None = None) -> None:
        self.rows = rows or {}
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def fetchval(self, query: str, *args: object) -> object:
        return 1

    async def fetchrow(self, query: str, *args: object) -> object:
        return None

    async def fetch(self, query: str, *args: object) -> list[object]:
        return []

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "OK"


@pytest.fixture
def fake_pool(monkeypatch: pytest.MonkeyPatch) -> FakePool:
    from virtualos.db import client as db_client

    pool = FakePool()
    monkeypatch.setattr(db_client, "_pool", pool)
    return pool
