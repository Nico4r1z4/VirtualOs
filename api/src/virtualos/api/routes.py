"""User-facing endpoints (Phase 2): outliers, trends, posts, ingestions, profiles.

Every handler runs its queries inside user_tx(auth.claims): the transaction
takes the `authenticated` role with the user's JWT claims, so RLS enforces
workspace isolation at the database — not just in application code.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from virtualos.auth.deps import Auth
from virtualos.db.client import get_pool, user_tx
from virtualos.queue.postgres import PostgresJobQueue

router = APIRouter(tags=["tools"])


def _record(row: Any) -> dict[str, Any]:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif hasattr(v, "__float__") and type(v).__name__ == "Decimal":
            d[k] = float(v)
        else:
            d[k] = str(v) if type(v).__name__ == "UUID" else v
    return d


# ---------------------------------------------------------------------------
# Outliers board
# ---------------------------------------------------------------------------


@router.get("/outliers")
async def list_outliers(
    auth: Auth,
    platform: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_multiplier: float = Query(default=1.5, ge=0),
    sort: str = Query(default="rank", pattern="^(rank|outlier|views|velocity|recent)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    order = {
        "rank": "rank_score DESC NULLS LAST",
        "outlier": "outlier_score DESC NULLS LAST",
        "views": "views DESC NULLS LAST",
        "velocity": "velocity DESC NULLS LAST",
        "recent": "published_at DESC NULLS LAST",
    }[sort]
    where = ["workspace_id = $1", "outlier_score IS NOT NULL", "outlier_score >= $2"]
    args: list[Any] = [auth.workspace_id, min_multiplier]
    if platform:
        args.append(platform)
        where.append(f"platform = ${len(args)}")
    if date_from:
        args.append(date_from)
        where.append(f"published_at >= ${len(args)}")
    if date_to:
        args.append(date_to)
        where.append(f"published_at <= ${len(args)}")

    offset = (page - 1) * page_size
    sql = f"""
        SELECT id, platform, external_id, author_handle, url, published_at,
               views, likes, comments, shares, caption, hashtags, sound_name,
               duration_s, thumbnail_url, outlier_score, velocity, rank_score
        FROM vos.posts
        WHERE {" AND ".join(where)}
        ORDER BY {order}
        LIMIT {page_size} OFFSET {offset}
    """
    count_sql = f"SELECT COUNT(*) FROM vos.posts WHERE {' AND '.join(where)}"

    async with user_tx(auth.claims) as conn:
        rows = await conn.fetch(sql, *args)
        total = await conn.fetchval(count_sql, *args)

    return {
        "items": [_record(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/posts/{post_id}")
async def get_post(post_id: str, auth: Auth) -> dict[str, Any]:
    async with user_tx(auth.claims) as conn:
        post = await conn.fetchrow(
            "SELECT * FROM vos.posts WHERE id = $1 AND workspace_id = $2",
            post_id,
            auth.workspace_id,
        )
        if post is None:
            raise HTTPException(status_code=404, detail="Post no encontrado")
        snaps = await conn.fetch(
            "SELECT captured_at, views, likes, comments, shares FROM vos.post_snapshots "
            "WHERE post_id = $1 ORDER BY captured_at",
            post_id,
        )
        hook = await conn.fetchrow(
            "SELECT hook_text, hook_type, structure, cta, language FROM vos.hooks WHERE post_id = $1",
            post_id,
        )
    out = _record(post)
    out.pop("raw", None)  # raw payload is untrusted and heavy; not for the UI
    out["snapshots"] = [_record(s) for s in snaps]
    out["hook"] = _record(hook) if hook else None
    return out


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


@router.get("/trends")
async def list_trends(
    auth: Auth,
    platform: str = "tiktok",
    country: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    where = ["workspace_id = $1", "platform = $2"]
    args: list[Any] = [auth.workspace_id, platform]
    if country:
        args.append(country.upper())
        where.append(f"country = ${len(args)}")
    sql = f"""
        SELECT DISTINCT ON (trend_type, name)
            id, platform, country, trend_type, name, rank, metrics, captured_at
        FROM vos.platform_trends
        WHERE {" AND ".join(where)}
        ORDER BY trend_type, name, captured_at DESC
    """
    async with user_tx(auth.claims) as conn:
        rows = await conn.fetch(sql, *args)
    items = sorted(
        (_record(r) for r in rows), key=lambda r: (r["rank"] is None, r["rank"] or 0)
    )[:limit]
    for it in items:
        if isinstance(it.get("metrics"), str):
            it["metrics"] = json.loads(it["metrics"])
    return {"items": items}


# ---------------------------------------------------------------------------
# Niche profiles (minimal CRUD; the mascot drives this in Phase 4)
# ---------------------------------------------------------------------------


class NicheProfileIn(BaseModel):
    name: str
    kind: str = "creator"
    platforms: list[str] = Field(default_factory=lambda: ["tiktok"])
    countries: list[str] = Field(default_factory=lambda: ["CO"])
    languages: list[str] = Field(default_factory=lambda: ["es"])
    keywords: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    seed_accounts: dict[str, list[str]] = Field(default_factory=dict)
    goals: str | None = None
    tone: str | None = None


@router.get("/niche-profiles")
async def list_profiles(auth: Auth) -> dict[str, Any]:
    async with user_tx(auth.claims) as conn:
        rows = await conn.fetch(
            "SELECT * FROM vos.niche_profiles WHERE workspace_id = $1 ORDER BY created_at DESC",
            auth.workspace_id,
        )
    items = []
    for r in rows:
        d = _record(r)
        if isinstance(d.get("seed_accounts"), str):
            d["seed_accounts"] = json.loads(d["seed_accounts"])
        items.append(d)
    return {"items": items}


@router.post("/niche-profiles", status_code=201)
async def create_profile(body: NicheProfileIn, auth: Auth) -> dict[str, Any]:
    async with user_tx(auth.claims) as conn:
        active = await conn.fetchval(
            "SELECT COUNT(*) FROM vos.niche_profiles WHERE workspace_id = $1 AND status = 'active'",
            auth.workspace_id,
        )
        limit = await conn.fetchval(
            "SELECT pl.max_active_niches FROM vos.plan_limits pl "
            "JOIN vos.workspaces w ON w.plan = pl.plan WHERE w.id = $1",
            auth.workspace_id,
        )
        if limit is not None and active >= limit:
            raise HTTPException(
                status_code=409,
                detail=f"Tu plan permite {limit} nicho(s) activo(s). Archiva uno o mejora el plan.",
            )
        row = await conn.fetchrow(
            """
            INSERT INTO vos.niche_profiles
                (workspace_id, kind, name, platforms, countries, languages, keywords, hashtags, seed_accounts, goals, tone)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11)
            RETURNING *
            """,
            auth.workspace_id,
            body.kind,
            body.name,
            body.platforms,
            body.countries,
            body.languages,
            body.keywords,
            body.hashtags,
            json.dumps(body.seed_accounts),
            body.goals,
            body.tone,
        )
    d = _record(row)
    if isinstance(d.get("seed_accounts"), str):
        d["seed_accounts"] = json.loads(d["seed_accounts"])
    return d


# ---------------------------------------------------------------------------
# Ingestions + jobs
# ---------------------------------------------------------------------------


class IngestionIn(BaseModel):
    niche_profile_id: str


@router.post("/ingestions", status_code=202)
async def start_ingestion(body: IngestionIn, auth: Auth) -> dict[str, str]:
    async with user_tx(auth.claims) as conn:
        profile = await conn.fetchrow(
            "SELECT id FROM vos.niche_profiles WHERE id = $1 AND workspace_id = $2 AND status = 'active'",
            body.niche_profile_id,
            auth.workspace_id,
        )
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil de nicho no encontrado o archivado")

    queue = PostgresJobQueue(get_pool())
    job_id = await queue.enqueue(
        workspace_id=auth.workspace_id,
        kind="ingest_niche",
        payload={"niche_profile_id": body.niche_profile_id},
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, auth: Auth) -> dict[str, Any]:
    async with user_tx(auth.claims) as conn:
        row = await conn.fetchrow(
            "SELECT id, kind, status, attempts, error, created_at, started_at, finished_at "
            "FROM vos.jobs WHERE id = $1 AND workspace_id = $2",
            job_id,
            auth.workspace_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return _record(row)
