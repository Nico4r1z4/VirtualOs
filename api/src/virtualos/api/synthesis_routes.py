"""Phase 3 endpoints: hooks library, weekly briefs, idea feedback."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from virtualos.api.routes import _record
from virtualos.auth.deps import Auth
from virtualos.db.client import get_pool, user_tx
from virtualos.queue.postgres import PostgresJobQueue
from virtualos.services.pdf import render_brief_pdf

router = APIRouter(tags=["synthesis"])


# ---------------------------------------------------------------------------
# Hooks library
# ---------------------------------------------------------------------------


@router.get("/hooks")
async def list_hooks(
    auth: Auth,
    hook_type: str | None = None,
    platform: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    where = ["h.workspace_id = $1"]
    args: list[Any] = [auth.workspace_id]
    if hook_type:
        args.append(hook_type)
        where.append(f"h.hook_type = ${len(args)}")
    if platform:
        args.append(platform)
        where.append(f"p.platform = ${len(args)}")
    args.append(limit)
    sql = f"""
        SELECT h.id, h.post_id, h.hook_text, h.hook_type, h.structure, h.cta, h.language,
               h.created_at, p.platform, p.author_handle, p.caption, p.views,
               p.outlier_score, p.thumbnail_url, p.url
        FROM vos.hooks h JOIN vos.posts p ON p.id = h.post_id
        WHERE {" AND ".join(where)}
        ORDER BY p.rank_score DESC NULLS LAST
        LIMIT ${len(args)}
    """
    async with user_tx(auth.claims) as conn:
        rows = await conn.fetch(sql, *args)
    items = []
    for r in rows:
        d = _record(r)
        if isinstance(d.get("structure"), str):
            d["structure"] = json.loads(d["structure"])
        items.append(d)
    return {"items": items}


class SynthesizeIn(BaseModel):
    min_outlier: float = 2.0
    limit: int = 25


@router.post("/hooks/synthesize", status_code=202)
async def synthesize(body: SynthesizeIn, auth: Auth) -> dict[str, str]:
    queue = PostgresJobQueue(get_pool())
    job_id, created = await queue.enqueue_or_get(
        workspace_id=auth.workspace_id,
        kind="synthesize_hooks",
        payload={"min_outlier": body.min_outlier, "limit": body.limit},
    )
    return {"job_id": job_id, "status": "queued" if created else "already_running"}


# ---------------------------------------------------------------------------
# Weekly briefs
# ---------------------------------------------------------------------------


class BriefIn(BaseModel):
    niche_profile_id: str | None = None


@router.post("/briefs/generate", status_code=202)
async def generate_brief(body: BriefIn, auth: Auth) -> dict[str, str]:
    queue = PostgresJobQueue(get_pool())
    job_id, created = await queue.enqueue_or_get(
        workspace_id=auth.workspace_id,
        kind="build_weekly_brief",
        payload={"niche_profile_id": body.niche_profile_id},
    )
    return {"job_id": job_id, "status": "queued" if created else "already_running"}


@router.get("/briefs")
async def list_briefs(auth: Auth) -> dict[str, Any]:
    async with user_tx(auth.claims) as conn:
        rows = await conn.fetch(
            """
            SELECT b.id, b.week_start, b.summary, b.created_at, b.model,
                   np.name AS niche_name,
                   (SELECT COUNT(*) FROM vos.content_ideas ci WHERE ci.weekly_brief_id = b.id) AS idea_count
            FROM vos.weekly_briefs b
            LEFT JOIN vos.niche_profiles np ON np.id = b.niche_profile_id
            WHERE b.workspace_id = $1
            ORDER BY b.created_at DESC
            """,
            auth.workspace_id,
        )
    return {"items": [_record(r) for r in rows]}


async def _load_brief(auth: Auth, brief_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    async with user_tx(auth.claims) as conn:
        brief = await conn.fetchrow(
            """
            SELECT b.*, np.name AS niche_name
            FROM vos.weekly_briefs b
            LEFT JOIN vos.niche_profiles np ON np.id = b.niche_profile_id
            WHERE b.id = $1 AND b.workspace_id = $2
            """,
            brief_id,
            auth.workspace_id,
        )
        if brief is None:
            raise HTTPException(status_code=404, detail="Brief no encontrado")
        ideas = await conn.fetch(
            """
            SELECT ci.*,
                   (SELECT COUNT(*) FROM vos.idea_feedback f WHERE f.idea_id = ci.id) AS feedback_count
            FROM vos.content_ideas ci
            WHERE ci.weekly_brief_id = $1
            ORDER BY ci.created_at
            """,
            brief_id,
        )
    b = _record(brief)
    if isinstance(b.get("content"), str):
        b["content"] = json.loads(b["content"])
    idea_list = [_record(i) for i in ideas]
    return b, idea_list


@router.get("/briefs/{brief_id}")
async def get_brief(brief_id: str, auth: Auth) -> dict[str, Any]:
    b, ideas = await _load_brief(auth, brief_id)

    # Resolve evidence summaries so the UI can link idea -> proof.
    post_ids = {pid for i in ideas for pid in (i.get("evidence_post_ids") or [])}
    trend_ids = {tid for i in ideas for tid in (i.get("evidence_trend_ids") or [])}
    news_ids = {nid for i in ideas for nid in (i.get("evidence_news_ids") or [])}

    async with user_tx(auth.claims) as conn:
        ev_posts = (
            await conn.fetch(
                "SELECT id, platform, author_handle, caption, views, outlier_score, url, thumbnail_url "
                "FROM vos.posts WHERE id = ANY($1::uuid[])",
                list(post_ids),
            )
            if post_ids
            else []
        )
        ev_trends = (
            await conn.fetch(
                "SELECT id, name, country, rank FROM vos.platform_trends WHERE id = ANY($1::uuid[])",
                list(trend_ids),
            )
            if trend_ids
            else []
        )
        ev_news = (
            await conn.fetch(
                "SELECT id, title, url, source FROM vos.news_items WHERE id = ANY($1::uuid[])",
                list(news_ids),
            )
            if news_ids
            else []
        )

    b["ideas"] = ideas
    b["evidence"] = {
        "posts": {str(r["id"]): _record(r) for r in ev_posts},
        "trends": {str(r["id"]): _record(r) for r in ev_trends},
        "news": {str(r["id"]): _record(r) for r in ev_news},
    }
    return b


@router.get("/briefs/{brief_id}/pdf")
async def brief_pdf(brief_id: str, auth: Auth) -> StreamingResponse:
    b, ideas = await _load_brief(auth, brief_id)
    plan = {p["idea_id"]: p["day"] for p in (b.get("content") or {}).get("plan", [])}
    pdf_ideas = [
        {
            "title": i["title"],
            "angle": i["angle"],
            "hook_suggestion": i["hook_suggestion"],
            "script_outline": i["script_outline"],
            "day": plan.get(i["id"], ""),
            "evidence_count": len(i.get("evidence_post_ids") or [])
            + len(i.get("evidence_trend_ids") or [])
            + len(i.get("evidence_news_ids") or []),
        }
        for i in ideas
    ]
    buf = render_brief_pdf(
        niche_name=b.get("niche_name") or "Nicho",
        week_start=str(b["week_start"]),
        summary=b.get("summary"),
        ideas=pdf_ideas,
    )
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="brief-{b["week_start"]}.pdf"'},
    )


# ---------------------------------------------------------------------------
# Idea feedback ("lo grabé")
# ---------------------------------------------------------------------------


class FeedbackIn(BaseModel):
    recorded: bool = True
    posted_url: str | None = None
    result_views: int | None = None
    notes: str | None = None


@router.post("/ideas/{idea_id}/feedback", status_code=201)
async def record_feedback(idea_id: str, body: FeedbackIn, auth: Auth) -> dict[str, Any]:
    async with user_tx(auth.claims) as conn:
        idea = await conn.fetchrow(
            "SELECT id FROM vos.content_ideas WHERE id = $1 AND workspace_id = $2",
            idea_id,
            auth.workspace_id,
        )
        if idea is None:
            raise HTTPException(status_code=404, detail="Idea no encontrada")
        row = await conn.fetchrow(
            """
            INSERT INTO vos.idea_feedback (workspace_id, idea_id, recorded, posted_url, result_views, notes)
            VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
            """,
            auth.workspace_id,
            idea_id,
            body.recorded,
            body.posted_url,
            body.result_views,
            body.notes,
        )
        if body.recorded:
            await conn.execute(
                "UPDATE vos.content_ideas SET status = 'recorded' WHERE id = $1",
                idea_id,
            )
    return _record(row)
