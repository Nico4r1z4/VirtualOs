"""Create the demo niche profile in the (only) real user workspace and enqueue
its ingestion. Idempotent: reuses the profile if it already exists.

Usage: uv run python scripts/demo_setup.py --yes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from dotenv import load_dotenv

load_dotenv()

from virtualos.db.client import close_pool, get_pool, init_pool  # noqa: E402
from virtualos.queue.postgres import PostgresJobQueue  # noqa: E402

PROFILE = {
    "name": "Finanzas personales Colombia",
    "kind": "creator",
    "platforms": ["tiktok", "instagram"],
    "countries": ["CO"],
    "languages": ["es"],
    "keywords": ["finanzas personales", "ahorro", "inversion", "presupuesto"],
    "hashtags": ["finanzaspersonales", "ahorro", "inversion"],
    "seed_accounts": {
        "tiktok": [
            "mispropiasfinanzas",
            "finanzas.e.inversiones",
            "finanzas.emocionales",
            "finanzasyalgomas_",
        ],
        "instagram": ["mispropiasfinanzas", "finanzas.emocionales"],
    },
    "goals": "Crecer audiencia con contenido educativo de finanzas en Colombia",
    "tone": "Cercano, claro, sin tecnicismos innecesarios",
}


async def main() -> int:
    await init_pool()
    pool = get_pool()

    ws = await pool.fetchrow(
        """
        SELECT w.id, w.name FROM vos.workspaces w
        WHERE EXISTS (SELECT 1 FROM vos.workspace_members m WHERE m.workspace_id = w.id)
        ORDER BY w.created_at LIMIT 1
        """
    )
    if ws is None:
        print("ERROR: no user workspace found. Log into the web app first.", file=sys.stderr)
        return 1
    workspace_id = str(ws["id"])
    print(f"workspace: {ws['name']} ({workspace_id})")

    profile = await pool.fetchrow(
        "SELECT id FROM vos.niche_profiles WHERE workspace_id = $1 AND name = $2",
        workspace_id,
        PROFILE["name"],
    )
    if profile is None:
        profile = await pool.fetchrow(
            """
            INSERT INTO vos.niche_profiles
                (workspace_id, kind, name, platforms, countries, languages, keywords, hashtags, seed_accounts, goals, tone)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11)
            RETURNING id
            """,
            workspace_id,
            PROFILE["kind"],
            PROFILE["name"],
            PROFILE["platforms"],
            PROFILE["countries"],
            PROFILE["languages"],
            PROFILE["keywords"],
            PROFILE["hashtags"],
            json.dumps(PROFILE["seed_accounts"]),
            PROFILE["goals"],
            PROFILE["tone"],
        )
        print("niche profile created")
    else:
        print("niche profile already exists")
    assert profile is not None

    queue = PostgresJobQueue(pool)
    job_id = await queue.enqueue(
        workspace_id=workspace_id,
        kind="ingest_niche",
        payload={"niche_profile_id": str(profile["id"])},
    )
    print(f"ingestion job queued: {job_id}")
    await close_pool()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if not args.yes:
        print("This enqueues a real (paid) ingestion. Re-run with --yes.")
        sys.exit(1)
    sys.exit(asyncio.run(main()))
