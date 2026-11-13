"""Worker: claims jobs from the queue and dispatches handlers.

Run with: uv run python -m virtualos.worker
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import Any

from virtualos.db.client import close_pool, get_pool, init_pool
from virtualos.ingestion.pipeline import ingest_niche, refresh_news
from virtualos.observability.logs import setup_logging
from virtualos.queue.postgres import PostgresJobQueue, current_job_id
from virtualos.synthesis.brief import build_weekly_brief
from virtualos.synthesis.hooks import synthesize_hooks

logger = logging.getLogger(__name__)

HANDLERS: dict[str, Any] = {
    "ingest_niche": ingest_niche,
    "refresh_news": refresh_news,
    "synthesize_hooks": synthesize_hooks,
    "build_weekly_brief": build_weekly_brief,
}

IDLE_SLEEP_S = 2.0


async def run_worker(stop: asyncio.Event) -> None:
    await init_pool()
    queue = PostgresJobQueue(get_pool())
    logger.info("worker started; handlers: %s", list(HANDLERS))

    while not stop.is_set():
        job = await queue.claim(list(HANDLERS))
        if job is None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=IDLE_SLEEP_S)
            continue

        handler = HANDLERS[job.kind]
        logger.info("job %s (%s) attempt %d", job.id, job.kind, job.attempts)
        token = current_job_id.set(job.id)
        try:
            result = await handler(job.workspace_id, job.payload)
            await queue.complete(job.id, result if isinstance(result, dict) else None)
            logger.info("job %s done: %s", job.id, result)
        except Exception as exc:
            logger.exception("job %s failed", job.id)
            await queue.fail(job.id, f"{type(exc).__name__}: {exc}")
        finally:
            current_job_id.reset(token)

    await close_pool()
    logger.info("worker stopped")


def main() -> None:
    setup_logging()
    stop = asyncio.Event()

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Windows: add_signal_handler is unavailable; KeyboardInterrupt covers it.
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)
        await run_worker(stop)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("interrupted")


if __name__ == "__main__":
    main()
