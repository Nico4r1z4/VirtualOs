"""Ingestion job: fetch a niche profile's sources, store, recompute metrics.

Runs in the worker (owner role, explicit workspace_id scoping). Cost funnel:
code filters and ranks here; the LLM only ever sees outliers (Phase 3).
"""

from __future__ import annotations

import logging
from typing import Any

from virtualos.connectors.instagram import InstagramProfilesConnector
from virtualos.connectors.news import SerperNewsConnector
from virtualos.connectors.storage import save_raw
from virtualos.connectors.tiktok import TikTokProfilesConnector, TikTokTrendsConnector
from virtualos.db.client import get_pool
from virtualos.ingestion.store import insert_trends, upsert_account, upsert_news, upsert_post
from virtualos.metrics.recompute import recompute_workspace_metrics
from virtualos.queue.postgres import report_progress

logger = logging.getLogger(__name__)


async def ingest_niche(workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Handler for 'ingest_niche' jobs. payload: {"niche_profile_id": "..."}"""
    pool = get_pool()
    profile = await pool.fetchrow(
        "SELECT * FROM vos.niche_profiles WHERE id = $1 AND workspace_id = $2",
        payload["niche_profile_id"],
        workspace_id,
    )
    if profile is None:
        raise ValueError("niche profile not found in workspace")

    import json as _json

    seed_accounts: dict[str, list[str]] = {}
    raw_seed = profile["seed_accounts"]
    if raw_seed:
        seed_accounts = _json.loads(raw_seed) if isinstance(raw_seed, str) else dict(raw_seed)
    platforms: list[str] = list(profile["platforms"] or [])
    countries: list[str] = list(profile["countries"] or ["CO"])
    keywords: list[str] = list(profile["keywords"] or [])
    stats: dict[str, Any] = {"posts": 0, "trends": 0, "news": 0}

    # --- Posts from seed accounts ---
    per_profile = int(payload.get("results_per_profile", 20))
    connectors: list[tuple[str, Any]] = []
    if "tiktok" in platforms and seed_accounts.get("tiktok"):
        connectors.append(("tiktok", TikTokProfilesConnector()))
    if "instagram" in platforms and seed_accounts.get("instagram"):
        connectors.append(("instagram", InstagramProfilesConnector()))

    names = {"tiktok": "TikTok", "instagram": "Instagram"}
    for step, (platform, conn_impl) in enumerate(connectors, start=1):
        handles = seed_accounts[platform]
        await report_progress(
            f"Descargando posts de {names[platform]} ({len(handles)} cuentas)",
            done=step - 1,
            total=len(connectors),
        )
        raw = await conn_impl.fetch(
            workspace_id=workspace_id,
            params={"handles": handles, "results_per_profile": per_profile},
        )
        key = await save_raw(workspace_id, raw)
        posts = conn_impl.normalize(raw)
        async with pool.acquire() as conn:
            for p in posts:
                acc = await upsert_account(
                    conn,
                    workspace_id=workspace_id,
                    niche_profile_id=str(profile["id"]),
                    platform=platform,
                    handle=p.author_handle or "unknown",
                    followers=p.author_followers,
                    is_seed=True,
                )
                await upsert_post(
                    conn, workspace_id=workspace_id, post=p, account_id=acc, s3_raw_key=key
                )
        stats["posts"] += len(posts)
        logger.info("ingested %d %s posts for %s", len(posts), platform, workspace_id)

    # --- Platform trends per country (TikTok Creative Center) ---
    if "tiktok" in platforms:
        await report_progress(f"Buscando tendencias ({', '.join(countries)})")
        trends_conn = TikTokTrendsConnector()
        for country in countries:
            try:
                raw = await trends_conn.fetch(
                    workspace_id=workspace_id, params={"country": country, "limit": 30}
                )
                await save_raw(workspace_id, raw)
                trends = trends_conn.normalize(raw)
                async with pool.acquire() as conn:
                    stats["trends"] += await insert_trends(
                        conn, workspace_id=workspace_id, trends=trends
                    )
            except Exception:
                logger.exception("trends ingestion failed for %s", country)

    # --- News on profile keywords ---
    if keywords:
        await report_progress("Buscando noticias del nicho")
        news_conn = SerperNewsConnector()
        query = " ".join(keywords[:4])
        try:
            raw = await news_conn.fetch(
                workspace_id=workspace_id,
                params={"query": query, "country": (countries[0] if countries else "co").lower()},
            )
            items = news_conn.normalize(raw)
            async with pool.acquire() as conn:
                stats["news"] += await upsert_news(
                    conn,
                    workspace_id=workspace_id,
                    niche_profile_id=str(profile["id"]),
                    items=items,
                )
        except Exception:
            logger.exception("news ingestion failed")

    # --- Metrics ---
    await report_progress(f"Calculando outliers sobre {stats['posts']} posts")
    async with pool.acquire() as conn:
        stats["metrics_updated"] = await recompute_workspace_metrics(conn, workspace_id)

    return stats
