from virtualos.queue.base import Job, JobQueue
from virtualos.queue.postgres import PostgresJobQueue, backoff_for_attempt


def test_backoff_tiers() -> None:
    assert backoff_for_attempt(1) == 30
    assert backoff_for_attempt(2) == 120
    assert backoff_for_attempt(3) == 600
    assert backoff_for_attempt(99) == 600
    assert backoff_for_attempt(0) == 30


def test_postgres_queue_satisfies_protocol() -> None:
    # Structural check: PostgresJobQueue implements the JobQueue protocol.
    assert isinstance(PostgresJobQueue(pool=None), JobQueue)  # type: ignore[arg-type]


def test_job_dataclass_shape() -> None:
    from datetime import UTC, datetime

    job = Job(
        id="x",
        workspace_id="w",
        kind="ingest_niche",
        payload={"profile_id": "p"},
        status="pending",
        attempts=0,
        max_attempts=3,
        run_after=datetime.now(UTC),
    )
    assert job.kind == "ingest_niche"
