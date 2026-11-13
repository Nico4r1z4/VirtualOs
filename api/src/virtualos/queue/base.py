"""JobQueue interface. MVP backend is Postgres; SQS is the planned second impl."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class Job:
    id: str
    workspace_id: str
    kind: str
    payload: dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    run_after: datetime


@runtime_checkable
class JobQueue(Protocol):
    async def enqueue(
        self,
        *,
        workspace_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int | None = None,
    ) -> str: ...

    async def enqueue_or_get(
        self,
        *,
        workspace_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int | None = None,
    ) -> tuple[str, bool]: ...

    async def claim(self, kinds: list[str] | None = None) -> Job | None: ...

    async def complete(self, job_id: str, result: dict[str, Any] | None = None) -> None: ...

    async def fail(self, job_id: str, error: str) -> None: ...

    async def get(self, job_id: str) -> Job | None: ...
