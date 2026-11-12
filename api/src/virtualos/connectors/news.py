"""News connector: Serper first, DuckDuckGo fallback.

Adapted from orkiza-captacion web_research.py. No arbitrary URL fetching —
only the search APIs; results land in vos.news_items as untrusted text.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from virtualos.config.settings import get_settings
from virtualos.connectors.base import RawBatch
from virtualos.connectors.models import NewsItem
from virtualos.observability.usage import record_usage

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0)


class SerperNewsConnector:
    source = "news"

    async def fetch(self, *, workspace_id: str, params: dict[str, Any]) -> RawBatch:
        query: str = params["query"]
        gl: str = params.get("country", get_settings().serper_gl)
        hl: str = params.get("language", get_settings().serper_hl)

        settings = get_settings()
        if settings.serper_api_key:
            try:
                items = await self._serper_news(query, gl, hl, workspace_id)
                return RawBatch(source="serper:news", items=items, meta={"query": query})
            except Exception as exc:
                logger.warning("Serper failed (%s), falling back to DuckDuckGo", exc)

        items = await self._ddg_news(query, workspace_id)
        return RawBatch(source="ddg:news", items=items, meta={"query": query})

    def normalize(self, raw: RawBatch) -> list[NewsItem]:
        out: list[NewsItem] = []
        for item in raw.items:
            url = item.get("link") or item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            out.append(
                NewsItem(
                    title=str(title),
                    url=str(url),
                    source=item.get("source"),
                    snippet=item.get("snippet") or item.get("body"),
                    raw=item,
                )
            )
        return out

    async def _serper_news(
        self, query: str, gl: str, hl: str, workspace_id: str
    ) -> list[dict[str, Any]]:
        settings = get_settings()
        headers = {
            "X-API-KEY": settings.serper_api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "gl": gl, "hl": hl, "num": 10}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post("https://google.serper.dev/news", headers=headers, json=payload)
            await record_usage(workspace_id, "serper", units=1, unit_label="credits")
            resp.raise_for_status()
            data = resp.json()
        return list(data.get("news", []))

    async def _ddg_news(self, query: str, workspace_id: str) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                return list(ddgs.news(query, max_results=10))

        await record_usage(workspace_id, "duckduckgo")
        return await asyncio.to_thread(_sync)
