"""Weekly brief: strong model proposes ideas with MANDATORY evidence.

Ideas citing non-existent evidence ids are discarded (hard rule: the mascot
and the engine never invent data). The brief document itself is assembled in
code from validated ideas.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from virtualos.config.settings import get_settings
from virtualos.db.client import get_pool
from virtualos.llm.provider import get_provider
from virtualos.queue.postgres import report_progress
from virtualos.synthesis.hooks import synthesize_hooks
from virtualos.synthesis.prompts import IDEAS_SYSTEM, wrap_untrusted

logger = logging.getLogger(__name__)

MAX_EVIDENCE_POSTS = 12
MAX_TRENDS = 15
MAX_NEWS = 8


class IdeaOut(BaseModel):
    title: str
    angle: str | None = None
    hook_suggestion: str | None = None
    script_outline: str | None = None
    evidence: list[str] = Field(default_factory=list)


class IdeasResponse(BaseModel):
    summary: str
    ideas: list[IdeaOut]


def parse_evidence(
    evidence: list[str],
    *,
    valid_posts: set[str],
    valid_trends: set[str],
    valid_news: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """Split and validate 'post:<id>' style references against real ids."""
    posts, trends, news = [], [], []
    for ref in evidence:
        kind, _, ref_id = str(ref).partition(":")
        ref_id = ref_id.strip()
        if kind == "post" and ref_id in valid_posts:
            posts.append(ref_id)
        elif kind == "trend" and ref_id in valid_trends:
            trends.append(ref_id)
        elif kind == "news" and ref_id in valid_news:
            news.append(ref_id)
    return posts, trends, news


def _parse_ideas(text: str) -> IdeasResponse | None:
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        return IdeasResponse.model_validate(json.loads(text[start : end + 1]))
    except (json.JSONDecodeError, ValidationError):
        return None


async def build_weekly_brief(workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Job handler: gather evidence -> strong model -> validated ideas -> brief."""
    settings = get_settings()
    pool = get_pool()
    profile_id = payload.get("niche_profile_id")

    profile = await pool.fetchrow(
        "SELECT * FROM vos.niche_profiles WHERE workspace_id = $1 AND ($2::uuid IS NULL OR id = $2) "
        "AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        workspace_id,
        profile_id,
    )
    if profile is None:
        raise ValueError("no active niche profile for workspace")

    # Analyze any outlier still missing its hook first, so the brief never
    # depends on which button the user pressed first (seen live 2026-11-13:
    # the brief job ran before the hooks job and got 0 hooks). Only outliers
    # without a hook are processed, so this is a no-op when hooks exist.
    hooks_stats = await synthesize_hooks(workspace_id, {"min_outlier": 2.0, "limit": 30})
    if hooks_stats.get("hooks_created"):
        logger.info("brief: created %s missing hooks first", hooks_stats["hooks_created"])

    # --- Evidence: outliers (with hooks when available), trends, news ---
    posts = await pool.fetch(
        """
        SELECT p.id, p.platform, p.author_handle, p.caption, p.views, p.outlier_score,
               p.hashtags, p.sound_name, h.hook_text, h.hook_type, h.cta
        FROM vos.posts p LEFT JOIN vos.hooks h ON h.post_id = p.id
        WHERE p.workspace_id = $1 AND p.outlier_score >= 2.0
        ORDER BY p.rank_score DESC NULLS LAST LIMIT $2
        """,
        workspace_id,
        MAX_EVIDENCE_POSTS,
    )
    trends = await pool.fetch(
        """
        SELECT DISTINCT ON (name) id, name, country, rank, metrics
        FROM vos.platform_trends WHERE workspace_id = $1
        ORDER BY name, captured_at DESC LIMIT $2
        """,
        workspace_id,
        MAX_TRENDS,
    )
    news = await pool.fetch(
        # Freshest real publication date first: timely ideas are the point.
        "SELECT id, title, source, snippet FROM vos.news_items WHERE workspace_id = $1 "
        "ORDER BY published_at DESC NULLS LAST, created_at DESC LIMIT $2",
        workspace_id,
        MAX_NEWS,
    )
    if not posts:
        raise ValueError("no outlier posts yet; run an ingestion first")

    # --- Build the evidence block ---
    lines: list[str] = ["PERFIL DEL NICHO:"]
    lines.append(f"- Nombre: {profile['name']} · Tipo: {profile['kind']}")
    lines.append(f"- Plataformas: {', '.join(profile['platforms'] or [])}")
    lines.append(f"- Países: {', '.join(profile['countries'] or [])}")
    if profile["keywords"]:
        lines.append(f"- Keywords: {', '.join(profile['keywords'])}")
    if profile["tone"]:
        lines.append(f"- Tono: {profile['tone']}")
    if profile["goals"]:
        lines.append(f"- Objetivos: {profile['goals']}")

    lines.append("\nPOSTS OUTLIERS (evidencia 'post:<id>'):")
    for p in posts:
        hook_part = f" · gancho: {p['hook_text']} ({p['hook_type']})" if p["hook_text"] else ""
        caption = (p["caption"] or "")[:200]
        lines.append(
            f"[post:{p['id']}] {p['platform']} @{p['author_handle']} · "
            f"{p['views'] or '?'} vistas · {p['outlier_score']}x{hook_part}\n"
            f"  caption: {wrap_untrusted(caption)}"
        )

    lines.append("\nTENDENCIAS (evidencia 'trend:<id>'):")
    for t in trends:
        lines.append(f"[trend:{t['id']}] #{t['name']} ({t['country']}, rank {t['rank']})")

    if news:
        lines.append("\nNOTICIAS (evidencia 'news:<id>'):")
        for n in news:
            snippet = (n["snippet"] or "")[:150]
            lines.append(
                f"[news:{n['id']}] {wrap_untrusted(str(n['title']))} ({n['source'] or '?'})\n"
                f"  {wrap_untrusted(snippet)}"
            )

    lines.append(
        "\nPropón de 5 a 7 ideas para la semana, cada una citando evidencia por id exacto."
    )
    user_msg = "\n".join(lines)

    await report_progress(f"Generando ideas con IA a partir de {len(posts)} outliers")
    provider = get_provider()
    result = await provider.complete(
        model=settings.resolved_model_strong,
        system=IDEAS_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=4000,
        temperature=0.7,
        output_format="json",
        workspace_id=workspace_id,
    )

    parsed = _parse_ideas(result.text)
    if parsed is None:
        raise ValueError("strong model returned unparseable ideas JSON")

    await report_progress("Validando evidencia y guardando el brief")
    valid_posts = {str(p["id"]) for p in posts}
    valid_trends = {str(t["id"]) for t in trends}
    valid_news = {str(n["id"]) for n in news}

    today = datetime.now(UTC).date()
    week_start = today - timedelta(days=today.weekday())

    brief_row = await pool.fetchrow(
        """
        INSERT INTO vos.weekly_briefs (workspace_id, niche_profile_id, week_start, summary, content, model, cost_usd)
        VALUES ($1, $2, $3, $4, '{}'::jsonb, $5, $6) RETURNING id
        """,
        workspace_id,
        profile["id"],
        week_start,
        parsed.summary,
        settings.resolved_model_strong,
        result.cost_usd,
    )
    assert brief_row is not None
    brief_id = str(brief_row["id"])

    kept, discarded = 0, 0
    idea_ids: list[str] = []
    for idea in parsed.ideas:
        ev_posts, ev_trends, ev_news = parse_evidence(
            idea.evidence,
            valid_posts=valid_posts,
            valid_trends=valid_trends,
            valid_news=valid_news,
        )
        if not (ev_posts or ev_trends or ev_news):
            discarded += 1
            logger.warning("idea without valid evidence discarded: %s", idea.title[:60])
            continue
        row = await pool.fetchrow(
            """
            INSERT INTO vos.content_ideas
                (workspace_id, niche_profile_id, weekly_brief_id, title, angle, hook_suggestion,
                 script_outline, evidence_post_ids, evidence_trend_ids, evidence_news_ids, model, cost_usd)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::uuid[], $9::uuid[], $10::uuid[], $11, 0)
            RETURNING id
            """,
            workspace_id,
            profile["id"],
            brief_id,
            idea.title,
            idea.angle,
            idea.hook_suggestion,
            idea.script_outline,
            ev_posts,
            ev_trends,
            ev_news,
            settings.resolved_model_strong,
        )
        assert row is not None
        idea_ids.append(str(row["id"]))
        kept += 1

    # Assemble the week plan in code (no extra LLM call).
    days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    plan = [{"day": days[i % 7], "idea_id": idea_id} for i, idea_id in enumerate(idea_ids)]
    await pool.execute(
        "UPDATE vos.weekly_briefs SET content = $2::jsonb WHERE id = $1",
        brief_id,
        json.dumps({"plan": plan, "week_start": str(week_start)}),
    )

    return {
        "brief_id": brief_id,
        "ideas_kept": kept,
        "ideas_discarded": discarded,
        "cost_usd": result.cost_usd,
    }


def week_start_for(d: date) -> date:
    return d - timedelta(days=d.weekday())
