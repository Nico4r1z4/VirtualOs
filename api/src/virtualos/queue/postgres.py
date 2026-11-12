"""Postgres JobQueue over vos.jobs using FOR UPDATE SKIP LOCKED."""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from virtualos.queue.base import Job

# Exponential backoff in seconds per retry attempt (1-based).
BACKOFF_SECONDS = [30, 120, 600]


def backoff_for_attempt(attempt: int) -> int:
    """Seconds to wait before retry N (1-based). Clamps to the last tier."""
    if attempt < 1:
        return BACKOFF_SECONDS[0]
    return BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1]


def _row_to_job(row: asyncpg.Record) -> Job:
    payload = row["payload"]
    return Job(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        kind=row["kind"],
        payload=json.loads(payload) if isinstance(payload, str) else (payload or {}),
        status=row["status"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        run_after=row["run_after"],
    )


class PostgresJobQueue:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def enqueue(
        self,
        *,
        workspace_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> str:
        row = await self._pool.fetchrow(
            """
            INSERT INTO vos.jobs (workspace_id, kind, payload, max_attempts)
            VALUES ($1, $2, $3::jsonb, $4)
            RETURNING id
            """,
            workspace_id,
            kind,
            json.dumps(payload or {}),
            max_attempts,
        )
        assert row is not None
        return str(row["id"])

    async def claim(self, kinds: list[str] | None = None) -> Job | None:
        """Atomically claim the oldest runnable job, or None if the queue is idle."""
        row = await self._pool.fetchrow(
            """
            UPDATE vos.jobs SET
                status = 'running',
                attempts = attempts + 1,
                started_at = NOW()
            WHERE id = (
                SELECT id FROM vos.jobs
                WHERE status = 'pending'
                  AND run_after <= NOW()
                  AND ($1::text[] IS NULL OR kind = ANY($1))
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, workspace_id, kind, payload, status, attempts, max_attempts, run_after
            """,
            kinds,
        )
        return _row_to_job(row) if row else None

    async def complete(self, job_id: str) -> None:
        await self._pool.execute(
            "UPDATE vos.jobs SET status = 'done', finished_at = NOW(), error = NULL WHERE id = $1",
            job_id,
        )

    async def fail(self, job_id: str, error: str) -> None:
        """Mark failed; requeue with backoff while attempts remain."""
        await self._pool.execute(
            """
            UPDATE vos.jobs SET
                status = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'pending' END,
                run_after = CASE WHEN attempts >= max_attempts THEN run_after
                                 ELSE NOW() + make_interval(secs =>
                                     CASE LEAST(attempts, 3) WHEN 1 THEN 30 WHEN 2 THEN 120 ELSE 600 END)
                            END,
                finished_at = CASE WHEN attempts >= max_attempts THEN NOW() ELSE NULL END,
                error = $2
            WHERE id = $1
            """,
            job_id,
            error[:2000],
        )

    async def get(self, job_id: str) -> Job | None:
        row = await self._pool.fetchrow(
            """
            SELECT id, workspace_id, kind, payload, status, attempts, max_attempts, run_after
            FROM vos.jobs WHERE id = $1
            """,
            job_id,
        )
        return _row_to_job(row) if row else None
