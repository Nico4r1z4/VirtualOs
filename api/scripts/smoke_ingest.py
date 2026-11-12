"""Phase 1 closure: real ingestion smoke test.

Fetches TikTok CO trends + 20 posts from 3 accounts per platform, normalizes
and stores everything under a smoke-test workspace. Spends real Apify credits:
it prints the plan and requires --yes to run.

Usage:
    uv run python scripts/smoke_ingest.py --yes \
        --tiktok handle1,handle2,handle3 --instagram handle1,handle2,handle3
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from virtualos.connectors.instagram import InstagramProfilesConnector  # noqa: E402
from virtualos.connectors.news import SerperNewsConnector  # noqa: E402
from virtualos.connectors.storage import save_raw  # noqa: E402
from virtualos.connectors.tiktok import TikTokProfilesConnector, TikTokTrendsConnector  # noqa: E402
from virtualos.db.client import close_pool, get_pool, init_pool  # noqa: E402
from virtualos.ingestion.store import insert_trends, upsert_account, upsert_news, upsert_post  # noqa: E402

SMOKE_WS_NAME = "smoke-test"


async def _ensure_workspace() -> str:
    pool = get_pool()
    row = await pool.fetchrow("SELECT id FROM vos.workspaces WHERE name = $1", SMOKE_WS_NAME)
    if row:
        return str(row["id"])
    row = await pool.fetchrow(
        "INSERT INTO vos.workspaces (name, kind) VALUES ($1, 'creator') RETURNING id",
        SMOKE_WS_NAME,
    )
    assert row is not None
    return str(row["id"])


async def main(tiktok: list[str], instagram: list[str], country: str, query: str) -> int:
    await init_pool()
    pool = get_pool()
    ws = await _ensure_workspace()
    print(f"workspace: {ws}")

    # --- TikTok trends ---
    trends_conn = TikTokTrendsConnector()
    raw = await trends_conn.fetch(workspace_id=ws, params={"country": country, "limit": 30})
    await save_raw(ws, raw)
    trends = trends_conn.normalize(raw)
    async with pool.acquire() as conn:
        n = await insert_trends(conn, workspace_id=ws, trends=trends)
    print(f"tiktok trends {country}: {n} stored")

    # --- TikTok posts ---
    if tiktok:
        tt = TikTokProfilesConnector()
        raw = await tt.fetch(
            workspace_id=ws, params={"handles": tiktok, "results_per_profile": 20}
        )
        key = await save_raw(ws, raw)
        posts = tt.normalize(raw)
        async with pool.acquire() as conn:
            for p in posts:
                acc = await upsert_account(
                    conn,
                    workspace_id=ws,
                    niche_profile_id=None,
                    platform="tiktok",
                    handle=p.author_handle or "unknown",
                    followers=p.author_followers,
                    is_seed=True,
                )
                await upsert_post(conn, workspace_id=ws, post=p, account_id=acc, s3_raw_key=key)
        print(f"tiktok posts: {len(posts)} stored from {len(tiktok)} accounts")

    # --- Instagram posts ---
    if instagram:
        ig = InstagramProfilesConnector()
        raw = await ig.fetch(
            workspace_id=ws, params={"handles": instagram, "results_per_profile": 20}
        )
        key = await save_raw(ws, raw)
        posts = ig.normalize(raw)
        async with pool.acquire() as conn:
            for p in posts:
                acc = await upsert_account(
                    conn,
                    workspace_id=ws,
                    niche_profile_id=None,
                    platform="instagram",
                    handle=p.author_handle or "unknown",
                    followers=p.author_followers,
                    is_seed=True,
                )
                await upsert_post(conn, workspace_id=ws, post=p, account_id=acc, s3_raw_key=key)
        print(f"instagram posts: {len(posts)} stored from {len(instagram)} accounts")

    # --- News ---
    if query:
        news_conn = SerperNewsConnector()
        raw = await news_conn.fetch(workspace_id=ws, params={"query": query, "country": country.lower()})
        items = news_conn.normalize(raw)
        async with pool.acquire() as conn:
            n = await upsert_news(conn, workspace_id=ws, niche_profile_id=None, items=items)
        print(f"news: {n} stored")

    usage = await pool.fetch(
        "SELECT provider, calls, units, cost_usd FROM vos.api_usage WHERE workspace_id = $1 AND day = CURRENT_DATE",
        ws,
    )
    print("\napi_usage today:")
    for u in usage:
        print(f"  {u['provider']}: calls={u['calls']} units={u['units']} cost=${u['cost_usd']}")

    await close_pool()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="confirm spending Apify credits")
    parser.add_argument("--tiktok", default="", help="comma-separated TikTok handles")
    parser.add_argument("--instagram", default="", help="comma-separated Instagram handles")
    parser.add_argument("--country", default="CO")
    parser.add_argument("--query", default="", help="news search query")
    args = parser.parse_args()

    if not args.yes:
        print("This script spends real Apify credits. Re-run with --yes to confirm.")
        sys.exit(1)

    tiktok = [h.strip() for h in args.tiktok.split(",") if h.strip()]
    instagram = [h.strip() for h in args.instagram.split(",") if h.strip()]
    sys.exit(asyncio.run(main(tiktok, instagram, args.country, args.query)))
