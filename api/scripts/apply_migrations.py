"""Apply db/migrations/*.sql against DATABASE_URL.

Idempotent: tracked in vos._migrations (auto-created, sha256 checksums).
Files run in lexicographic order, one transaction each. Migrations are
immutable — a changed checksum aborts with an error.

Usage:
    uv run python scripts/apply_migrations.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"

BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS vos;
CREATE TABLE IF NOT EXISTS vos._migrations (
    filename   TEXT PRIMARY KEY,
    checksum   TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


async def apply_migrations(database_url: str) -> int:
    if not MIGRATIONS_DIR.is_dir():
        print(f"ERROR: missing {MIGRATIONS_DIR}", file=sys.stderr)
        return 1

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print(f"WARNING: no migrations in {MIGRATIONS_DIR}")
        return 0

    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(BOOTSTRAP_SQL)
        applied = {
            row["filename"]: row["checksum"]
            for row in await conn.fetch("SELECT filename, checksum FROM vos._migrations")
        }

        for path in files:
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)
            name = path.name

            if name in applied:
                if applied[name] != checksum:
                    print(
                        f"ERROR: {name} was already applied but its content CHANGED. "
                        "Migrations are immutable — create a new file.",
                        file=sys.stderr,
                    )
                    return 2
                print(f"skip  {name} (already applied)")
                continue

            print(f"apply {name}...")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO vos._migrations (filename, checksum) VALUES ($1, $2)",
                    name,
                    checksum,
                )
            print(f"ok    {name}")

        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'vos' ORDER BY tablename"
        )
        print("\nvos tables:", ", ".join(t["tablename"] for t in tables))
        print("Migrations applied successfully.")
        return 0
    finally:
        await conn.close()


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is not set (load .env or export it).", file=sys.stderr)
        return 1

    safe_url = database_url
    if "@" in safe_url:
        prefix, rest = safe_url.split("@", 1)
        if ":" in prefix:
            scheme_user, _ = prefix.rsplit(":", 1)
            safe_url = f"{scheme_user}:***@{rest}"
    print(f"Target: {safe_url}\n")

    return asyncio.run(apply_migrations(database_url))


if __name__ == "__main__":
    sys.exit(main())
