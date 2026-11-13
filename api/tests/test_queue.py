from virtualos.queue.base import Job, JobQueue
from virtualos.queue.postgres import PostgresJobQueue, backoff_for_attempt


def test_backoff_tiers() -> None:
    assert backoff_for_attempt(1) == 30
    assert backoff_for_attempt(2) == 120
    assert backoff_for_attempt(3) == 600
    assert backoff_for_attempt(99) == 600
    assert backoff_for_attempt(0) == 30


def test_paid_kinds_are_not_auto_retried() -> None:
    from virtualos.queue.postgres import default_max_attempts

    # A silent retry of a paid job re-pays the whole scrape/LLM run.
    assert default_max_attempts("ingest_niche") == 1
    assert default_max_attempts("synthesize_hooks") == 1
    assert default_max_attempts("build_weekly_brief") == 1
    assert default_max_attempts("some_free_maintenance_job") == 3


async def test_report_progress_is_noop_outside_a_job(fake_pool) -> None:
    from virtualos.queue.postgres import report_progress

    await report_progress("algo", done=1, total=2)
    assert fake_pool.executed == []


async def test_report_progress_writes_for_current_job(fake_pool) -> None:
    from virtualos.queue.postgres import current_job_id, report_progress

    token = current_job_id.set("job-1")
    try:
        await report_progress("Analizando ganchos", done=3, total=10)
    finally:
        current_job_id.reset(token)
    query, args = fake_pool.executed[-1]
    assert "progress" in query
    assert args[0] == "job-1"
    assert '"done": 3' in args[1] and '"total": 10' in args[1]


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
