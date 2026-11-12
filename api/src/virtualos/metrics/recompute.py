"""Recompute outlier/velocity/rank for a workspace's posts (worker role)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import asyncpg

from virtualos.metrics.scores import outlier_score, rank_score, velocity

logger = logging.getLogger(__name__)


async def recompute_workspace_metrics(conn: asyncpg.Connection, workspace_id: str) -> int:
    """Recompute metrics for every post of the workspace. Returns posts updated."""
    posts = await conn.fetch(
        """
        SELECT id, platform, author_handle, views, published_at
        FROM vos.posts
        WHERE workspace_id = $1
        ORDER BY platform, author_handle, published_at DESC NULLS LAST
        """,
        workspace_id,
    )

    # Author history: most-recent-first views per (platform, author)
    history: dict[tuple[str, str | None], list[int | None]] = {}
    for p in posts:
        history.setdefault((p["platform"], p["author_handle"]), []).append(p["views"])

    snap_rows = await conn.fetch(
        """
        SELECT post_id, captured_at, views
        FROM vos.post_snapshots
        WHERE workspace_id = $1
        ORDER BY post_id, captured_at
        """,
        workspace_id,
    )
    snaps: dict[str, list[tuple[datetime, int | None]]] = {}
    for s in snap_rows:
        snaps.setdefault(str(s["post_id"]), []).append((s["captured_at"], s["views"]))

    now = datetime.now(UTC)
    updated = 0
    for p in posts:
        key = (p["platform"], p["author_handle"])
        # Exclude the post itself from its author baseline.
        baseline = [v for v in history.get(key, []) if v is not None]
        own_views = p["views"]
        if own_views is not None and own_views in baseline:
            baseline = list(baseline)
            baseline.remove(own_views)
        o = outlier_score(own_views, baseline)
        v = velocity(snaps.get(str(p["id"]), []))
        r = rank_score(o, p["published_at"], now=now)
        await conn.execute(
            "UPDATE vos.posts SET outlier_score = $2, velocity = $3, rank_score = $4, updated_at = NOW() WHERE id = $1",
            p["id"],
            o,
            v,
            r,
        )
        updated += 1

    logger.info("metrics recomputed for %s: %d posts", workspace_id, updated)
    return updated
