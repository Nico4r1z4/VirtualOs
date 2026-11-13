"""Postgres JobQueue over vos.jobs using FOR UPDATE SKIP LOCKED.

Cost guards (2026-11-13):
- At most one active job per (workspace, kind): enforced by the partial unique
  index uq_jobs_one_active_per_kind (migration 0002). enqueue_or_get() returns
  the already-active job instead of creating a duplicate.
- Paid, user-triggered kinds are NOT auto-retried: a silent retry of an
  ingestion re-pays all the scraping. They fail visibly instead.
"""

from __future__ import annotations

import contextvars
import json
import logging
from typing import Any

import asyncpg

from virtualos.queue.base import Job

logger = logging.getLogger(__name__)

# Exponential backoff in seconds per retry attempt (1-based).
BACKOFF_SECONDS = [30, 120, 600]

# Kinds that spend money on every attempt: one attempt only.
NO_AUTO_RETRY_KINDS = frozenset({"ingest_niche", "synthesize_hooks", "build_weekly_brief"})

# Set by the worker while a job runs, so handlers can report progress
# without changing their signature.
current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_job_id", default=None
)


def backoff_for_attempt(attempt: int) -> int:
    """Seconds to wait before retry N (1-based). Clamps to the last tier."""
    if attempt < 1:
        return BACKOFF_SECONDS[0]
    return BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1]


def default_max_attempts(kind: str) -> int:
    return 1 if kind in NO_AUTO_RETRY_KINDS else 3


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
        max_attempts: int | None = None,
    ) -> str:
        job_id, _ = await self.enqueue_or_get(
            workspace_id=workspace_id, kind=kind, payload=payload, max_attempts=max_attempts
        )
        return job_id

    async def enqueue_or_get(
        self,
        *,
        workspace_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int | None = None,
    ) -> tuple[str, bool]:
        """Create the job, or return the already-active one of the same kind.

        Returns (job_id, created). Race-free: the unique partial index decides.
        """
        attempts = max_attempts if max_attempts is not None else default_max_attempts(kind)
        row = await self._pool.fetchrow(
            """
            INSERT INTO vos.jobs (workspace_id, kind, payload, max_attempts)
            VALUES ($1, $2, $3::jsonb, $4)
            ON CONFLICT (workspace_id, kind) WHERE status IN ('pending', 'running')
            DO NOTHING
            RETURNING id
            """,
            workspace_id,
            kind,
            json.dumps(payload or {}),
            attempts,
        )
        if row is not None:
            return str(row["id"]), True

        existing = await self._pool.fetchrow(
            """
            SELECT id FROM vos.jobs
            WHERE workspace_id = $1 AND kind = $2 AND status IN ('pending', 'running')
            ORDER BY created_at LIMIT 1
            """,
            workspace_id,
            kind,
        )
        if existing is not None:
            return str(existing["id"]), False
        # The active job finished between the two statements: enqueue again.
        return await self.enqueue_or_get(
            workspace_id=workspace_id, kind=kind, payload=payload, max_attempts=max_attempts
        )

    async def claim(self, kinds: list[str] | None = None) -> Job | None:
        """Atomically claim the oldest runnable job, or None if the queue is idle."""
        row = await self._pool.fetchrow(
            """
            UPDATE vos.jobs SET
                status = 'running',
                attempts = attempts + 1,
                started_at = NOW(),
                progress = '{"stage": "Iniciando"}'::jsonb
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

    async def complete(self, job_id: str, result: dict[str, Any] | None = None) -> None:
        await self._pool.execute(
            """
            UPDATE vos.jobs SET status = 'done', finished_at = NOW(), error = NULL,
                   progress = progress || jsonb_build_object('stage', 'Listo', 'result', $2::jsonb)
            WHERE id = $1
            """,
            job_id,
            json.dumps(result or {}, default=str),
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


async def report_progress(stage: str, *, done: int | None = None, total: int | None = None) -> None:
    """Update the running job's progress (shown in the UI). Never raises; no-op
    outside a worker job."""
    job_id = current_job_id.get()
    if job_id is None:
        return
    progress: dict[str, Any] = {"stage": stage}
    if done is not None:
        progress["done"] = done
    if total is not None:
        progress["total"] = total
    try:
        from virtualos.db.client import get_pool

        await get_pool().execute(
            "UPDATE vos.jobs SET progress = $2::jsonb WHERE id = $1",
            job_id,
            json.dumps(progress),
        )
    except Exception:
        logger.debug("report_progress failed for job %s", job_id)


async def ingestions_today(pool: asyncpg.Pool, workspace_id: str) -> tuple[int, int | None]:
    """(ingestions started today, plan daily limit or None)."""
    row = await pool.fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM vos.jobs
            WHERE workspace_id = $1 AND kind = 'ingest_niche'
              AND created_at >= date_trunc('day', NOW())
              AND (status <> 'failed' OR error NOT LIKE 'superseded%')) AS used,
          (SELECT pl.ingestions_per_day FROM vos.workspaces w
             JOIN vos.plan_limits pl ON pl.plan = w.plan WHERE w.id = $1) AS lim
        """,
        workspace_id,
    )
    if row is None:
        return 0, None
    return int(row["used"] or 0), row["lim"]
