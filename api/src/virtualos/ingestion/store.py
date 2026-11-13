"""Persistence of normalized models into the vos schema (worker/owner role).

All writes filter/carry workspace_id explicitly — the worker does not go
through RLS (it runs as the owner role), so scoping here is mandatory.
"""

from __future__ import annotations

import json

import asyncpg

from virtualos.connectors.models import NewsItem, PlatformTrend, Post


async def upsert_account(
    conn: asyncpg.Connection,
    *,
    workspace_id: str,
    niche_profile_id: str | None,
    platform: str,
    handle: str,
    followers: int | None = None,
    is_seed: bool = False,
) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO vos.accounts (workspace_id, niche_profile_id, platform, handle, followers, is_seed)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (workspace_id, platform, handle) DO UPDATE SET
            followers = COALESCE(EXCLUDED.followers, vos.accounts.followers),
            is_seed   = vos.accounts.is_seed OR EXCLUDED.is_seed,
            niche_profile_id = COALESCE(EXCLUDED.niche_profile_id, vos.accounts.niche_profile_id),
            updated_at = NOW()
        RETURNING id
        """,
        workspace_id,
        niche_profile_id,
        platform,
        handle,
        followers,
        is_seed,
    )
    assert row is not None
    return str(row["id"])


async def upsert_post(
    conn: asyncpg.Connection,
    *,
    workspace_id: str,
    post: Post,
    account_id: str | None = None,
    s3_raw_key: str | None = None,
) -> tuple[str, bool]:
    """Upsert by (workspace, platform, external_id). Returns (post_id, inserted)."""
    row = await conn.fetchrow(
        """
        INSERT INTO vos.posts (
            workspace_id, account_id, platform, external_id, author_handle, url,
            published_at, views, likes, comments, shares, caption, hashtags,
            sound_id, sound_name, duration_s, thumbnail_url, raw, s3_raw_key
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18::jsonb, $19)
        ON CONFLICT (workspace_id, platform, external_id) DO UPDATE SET
            views = EXCLUDED.views, likes = EXCLUDED.likes,
            comments = EXCLUDED.comments, shares = EXCLUDED.shares,
            caption = COALESCE(EXCLUDED.caption, vos.posts.caption),
            account_id = COALESCE(EXCLUDED.account_id, vos.posts.account_id),
            updated_at = NOW()
        RETURNING id, (xmax = 0) AS inserted
        """,
        workspace_id,
        account_id,
        post.platform,
        post.external_id,
        post.author_handle,
        post.url,
        post.published_at,
        post.views,
        post.likes,
        post.comments,
        post.shares,
        post.caption,
        post.hashtags,
        post.sound_id,
        post.sound_name,
        post.duration_s,
        post.thumbnail_url,
        json.dumps(post.raw, default=str),
        s3_raw_key,
    )
    assert row is not None
    post_id = str(row["id"])
    await conn.execute(
        """
        INSERT INTO vos.post_snapshots (workspace_id, post_id, views, likes, comments, shares)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        workspace_id,
        post_id,
        post.views,
        post.likes,
        post.comments,
        post.shares,
    )
    return post_id, bool(row["inserted"])


async def insert_trends(
    conn: asyncpg.Connection, *, workspace_id: str, trends: list[PlatformTrend]
) -> int:
    count = 0
    for t in trends:
        await conn.execute(
            """
            INSERT INTO vos.platform_trends
                (workspace_id, platform, country, trend_type, name, external_id, rank, metrics)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            """,
            workspace_id,
            t.platform,
            t.country,
            t.trend_type,
            t.name,
            t.external_id,
            t.rank,
            json.dumps(t.metrics, default=str),
        )
        count += 1
    return count


async def upsert_news(
    conn: asyncpg.Connection,
    *,
    workspace_id: str,
    niche_profile_id: str | None,
    items: list[NewsItem],
) -> int:
    """Returns how many items were NEW (already-stored URLs are skipped and
    not counted, so a refresh reports real news, not re-reads)."""
    count = 0
    for n in items:
        status = await conn.execute(
            """
            INSERT INTO vos.news_items
                (workspace_id, niche_profile_id, title, url, source, snippet, published_at, raw)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (workspace_id, url) DO NOTHING
            """,
            workspace_id,
            niche_profile_id,
            n.title,
            n.url,
            n.source,
            n.snippet,
            n.published_at,
            json.dumps(n.raw, default=str),
        )
        if status.endswith(" 1"):  # "INSERT 0 1" = inserted; "INSERT 0 0" = existed
            count += 1
    return count
