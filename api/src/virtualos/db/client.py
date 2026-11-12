"""asyncpg pool + workspace-scoped transaction helper for the `vos` schema.

Pool lifecycle is managed by the FastAPI lifespan (api/main.py) and by the
worker entrypoint. Credentials come from config/settings.py only.

Adapted from orkiza-captacion db/client.py (pool + session-pooler validation).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

import asyncpg

from virtualos.config.settings import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _validate_session_pooler(dsn: str) -> None:
    """Reject Supabase's transaction pooler (port 6543).

    asyncpg uses prepared statements, which PgBouncer's transaction mode
    does not support. Use the session pooler (port 5432/6432).
    """
    parsed = urlparse(dsn)
    if parsed.port == 6543:
        raise ValueError(
            "DATABASE_URL points at the transaction pooler (port 6543). "
            "Use the session pooler (port 5432/6432) so prepared statements work."
        )


async def init_pool() -> asyncpg.Pool:
    """Create and return the asyncpg pool. Idempotent."""
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()
    dsn = settings.database_url
    _validate_session_pooler(dsn)

    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=10,
        command_timeout=30,
        server_settings={"search_path": "vos,extensions,public"},
    )
    logger.info("asyncpg pool initialized")
    return _pool


async def close_pool() -> None:
    """Close the asyncpg pool. Idempotent."""
    global _pool
    if _pool is not None:
        await _pool.close()
        logger.info("asyncpg pool closed")
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the asyncpg pool. Raises if not initialized."""
    if _pool is None:
        raise RuntimeError("asyncpg pool not initialized. Missing FastAPI lifespan?")
    return _pool


@asynccontextmanager
async def user_tx(claims: dict[str, Any]) -> AsyncIterator[asyncpg.Connection]:
    """Transaction that enforces RLS as the authenticated Supabase user.

    Sets the `authenticated` role and `request.jwt.claims` locally so that
    `auth.uid()` and the `vos.is_member(...)` policies apply, exactly as they
    would behind PostgREST. The worker does NOT use this: it runs as the owner
    role and filters by workspace_id explicitly.
    """
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SET LOCAL ROLE authenticated")
        await conn.execute(
            "SELECT set_config('request.jwt.claims', $1, true)",
            json.dumps(claims),
        )
        yield conn
