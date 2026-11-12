"""Facebook connector — stub (out of MVP). Returns empty batches with a warning."""

from __future__ import annotations

import logging
from typing import Any

from virtualos.connectors.base import RawBatch
from virtualos.connectors.models import Post

logger = logging.getLogger(__name__)


class FacebookPagesConnector:
    source = "facebook_pages"

    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch:
        logger.warning("Facebook connector is a stub (out of MVP); returning no items")
        return RawBatch(source="stub:facebook", items=[], meta=params)

    def normalize(self, raw: RawBatch) -> list[Post]:
        return []
