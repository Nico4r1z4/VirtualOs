"""SourceConnector: the ONLY door to external data sources (CLAUDE.md rule 4).

No other module may know about Apify, Serper or any provider. Connectors
fetch raw batches and normalize them into domain models; cost is recorded
in vos.api_usage by the underlying clients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from virtualos.connectors.models import NewsItem, PlatformTrend, Post


@dataclass(slots=True)
class RawBatch:
    """Raw provider output + provenance, before normalization."""

    source: str  # e.g. "apify:clockworks/tiktok-scraper"
    items: list[dict[str, Any]]
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PostConnector(Protocol):
    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch: ...

    def normalize(self, raw: RawBatch) -> list[Post]: ...


@runtime_checkable
class TrendConnector(Protocol):
    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch: ...

    def normalize(self, raw: RawBatch) -> list[PlatformTrend]: ...


@runtime_checkable
class NewsConnector(Protocol):
    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch: ...

    def normalize(self, raw: RawBatch) -> list[NewsItem]: ...
