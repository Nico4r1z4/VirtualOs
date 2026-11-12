"""Mascot tools. Hard rules (CLAUDE.md):

- workspace_id/user_id come ONLY from the authenticated context, never from
  the model.
- No tool fetches arbitrary URLs.
- Every number the mascot says must come from a tool result.
"""

from __future__ import annotations

import json
from typing import Any

from virtualos.db.client import get_pool
from virtualos.queue.postgres import PostgresJobQueue

# ---------------------------------------------------------------------------
# Anthropic tool schemas
# ---------------------------------------------------------------------------

TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "upsert_niche_profile",
        "description": (
            "Crea o actualiza el perfil de nicho del workspace. Úsalo al final del "
            "onboarding cuando ya tengas nombre, plataformas, país, keywords y cuentas semilla."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre corto del nicho"},
                "kind": {"type": "string", "enum": ["creator", "company", "agency"]},
                "platforms": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["tiktok", "instagram", "facebook"]},
                },
                "countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Códigos ISO, ej. CO",
                },
                "languages": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "hashtags": {"type": "array", "items": {"type": "string"}},
                "seed_accounts": {
                    "type": "object",
                    "description": 'Cuentas semilla por plataforma, ej. {"tiktok": ["cuenta1"], "instagram": ["cuenta2"]}',
                },
                "goals": {"type": "string"},
                "tone": {"type": "string"},
            },
            "required": ["name", "platforms", "countries"],
        },
    },
    {
        "name": "start_ingestion",
        "description": "Lanza la ingesta de datos del perfil de nicho activo (posts, tendencias, noticias). Devuelve el job_id.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_job_status",
        "description": "Consulta el estado de un job (ingesta, análisis de ganchos, brief).",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "get_outliers",
        "description": "Posts sobre-rindiendo del nicho (multiplicador sobre la mediana del autor). Única fuente válida de métricas de posts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_multiplier": {"type": "number", "default": 2},
                "platform": {"type": "string", "enum": ["tiktok", "instagram"]},
                "limit": {"type": "integer", "default": 5, "maximum": 15},
            },
        },
    },
    {
        "name": "get_platform_trends",
        "description": "Hashtags/sonidos trending capturados para el nicho, por país.",
        "input_schema": {
            "type": "object",
            "properties": {
                "country": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "get_hooks",
        "description": "Ganchos analizados de los posts ganadores del nicho.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 5, "maximum": 15}},
        },
    },
    {
        "name": "build_weekly_brief",
        "description": "Encola la generación del brief semanal (ideas con evidencia). Devuelve el job_id.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "explain_feature",
        "description": "Explica una vista de VirtualOS al usuario, en contexto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "feature": {
                    "type": "string",
                    "enum": ["outliers", "tendencias", "ganchos", "brief"],
                }
            },
            "required": ["feature"],
        },
    },
]

FEATURE_DOCS = {
    "outliers": (
        "El tablero de Outliers muestra los posts del nicho que están sobre-rindiendo: "
        "el multiplicador compara las vistas de cada post con la mediana de los últimos 20 "
        "posts de su autor (mínimo 5). Filtros: plataforma, multiplicador mínimo, fechas y orden. "
        "Clic en una fila abre el detalle con snapshots y gancho."
    ),
    "tendencias": (
        "Tendencias muestra hashtags y sonidos trending de TikTok por país, capturados en cada "
        "ingesta del nicho. Sirve para subirse a olas mientras están creciendo."
    ),
    "ganchos": (
        "La Biblioteca de ganchos extrae de cada post ganador su gancho (primeras palabras), "
        "tipo, estructura por beats y CTA. Solo se analizan outliers: la IA no gasta en posts promedio."
    ),
    "brief": (
        "El Brief semanal convierte todo (outliers + ganchos + tendencias + noticias) en un plan "
        "de grabación: 5-7 ideas con gancho sugerido y guion, cada una enlazada a su evidencia. "
        "Exporta a PDF y marca 'Lo grabé' para alimentar el loop de feedback."
    ),
}


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


async def execute_tool(
    name: str, args: dict[str, Any], *, workspace_id: str, user_id: str
) -> dict[str, Any]:
    """Run one tool. Returns a JSON-serializable result for the model."""
    pool = get_pool()

    if name == "upsert_niche_profile":
        active = await pool.fetchrow(
            "SELECT id FROM vos.niche_profiles WHERE workspace_id = $1 AND status = 'active' "
            "ORDER BY created_at DESC LIMIT 1",
            workspace_id,
        )
        if active:
            row = await pool.fetchrow(
                """
                UPDATE vos.niche_profiles SET
                    name = $2, kind = COALESCE($3, kind), platforms = $4, countries = $5,
                    languages = COALESCE($6, languages), keywords = COALESCE($7, keywords),
                    hashtags = COALESCE($8, hashtags), seed_accounts = COALESCE($9::jsonb, seed_accounts),
                    goals = COALESCE($10, goals), tone = COALESCE($11, tone), updated_at = NOW()
                WHERE id = $1 RETURNING id, name
                """,
                active["id"],
                args.get("name"),
                args.get("kind"),
                args.get("platforms") or ["tiktok"],
                args.get("countries") or ["CO"],
                args.get("languages"),
                args.get("keywords"),
                args.get("hashtags"),
                json.dumps(args["seed_accounts"]) if args.get("seed_accounts") else None,
                args.get("goals"),
                args.get("tone"),
            )
            assert row is not None
            return {"profile_id": str(row["id"]), "name": row["name"], "updated": True}

        limit_row = await pool.fetchrow(
            "SELECT pl.max_active_niches, (SELECT COUNT(*) FROM vos.niche_profiles np "
            " WHERE np.workspace_id = w.id AND np.status = 'active') AS active_count "
            "FROM vos.workspaces w JOIN vos.plan_limits pl ON pl.plan = w.plan WHERE w.id = $1",
            workspace_id,
        )
        if limit_row and limit_row["active_count"] >= limit_row["max_active_niches"]:
            return {
                "error": "plan_limit",
                "detail": f"El plan permite {limit_row['max_active_niches']} nicho(s) activo(s).",
            }
        row = await pool.fetchrow(
            """
            INSERT INTO vos.niche_profiles
                (workspace_id, kind, name, platforms, countries, languages, keywords, hashtags, seed_accounts, goals, tone)
            VALUES ($1, COALESCE($2, 'creator'), $3, $4, $5, COALESCE($6, '{es}'), COALESCE($7, '{}'),
                    COALESCE($8, '{}'), COALESCE($9::jsonb, '{}'), $10, $11)
            RETURNING id, name
            """,
            workspace_id,
            args.get("kind"),
            args["name"],
            args.get("platforms") or ["tiktok"],
            args.get("countries") or ["CO"],
            args.get("languages"),
            args.get("keywords"),
            args.get("hashtags"),
            json.dumps(args["seed_accounts"]) if args.get("seed_accounts") else None,
            args.get("goals"),
            args.get("tone"),
        )
        assert row is not None
        return {"profile_id": str(row["id"]), "name": row["name"], "created": True}

    if name == "start_ingestion":
        profile = await pool.fetchrow(
            "SELECT id, name FROM vos.niche_profiles WHERE workspace_id = $1 AND status = 'active' "
            "ORDER BY created_at DESC LIMIT 1",
            workspace_id,
        )
        if profile is None:
            return {"error": "no_profile", "detail": "No hay perfil de nicho activo todavía."}
        queue = PostgresJobQueue(pool)
        job_id = await queue.enqueue(
            workspace_id=workspace_id,
            kind="ingest_niche",
            payload={"niche_profile_id": str(profile["id"])},
        )
        return {"job_id": job_id, "profile": profile["name"], "status": "queued"}

    if name == "get_job_status":
        row = await pool.fetchrow(
            "SELECT id, kind, status, attempts, error FROM vos.jobs WHERE id = $1 AND workspace_id = $2",
            args["job_id"],
            workspace_id,
        )
        if row is None:
            return {"error": "not_found"}
        return {k: (str(v) if k == "id" else v) for k, v in dict(row).items()}

    if name == "get_outliers":
        rows = await pool.fetch(
            """
            SELECT id, platform, author_handle, caption, views, likes, outlier_score, velocity, url
            FROM vos.posts
            WHERE workspace_id = $1 AND outlier_score >= $2
              AND ($3::text IS NULL OR platform = $3)
            ORDER BY rank_score DESC NULLS LAST LIMIT $4
            """,
            workspace_id,
            float(args.get("min_multiplier", 2)),
            args.get("platform"),
            min(int(args.get("limit", 5)), 15),
        )
        return {
            "count": len(rows),
            "outliers": [
                {
                    "post_id": str(r["id"]),
                    "platform": r["platform"],
                    "author": r["author_handle"],
                    "caption": (r["caption"] or "")[:120],
                    "views": r["views"],
                    "multiplier": float(r["outlier_score"]) if r["outlier_score"] else None,
                    "url": r["url"],
                }
                for r in rows
            ],
        }

    if name == "get_platform_trends":
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (name) name, country, rank, trend_type
            FROM vos.platform_trends
            WHERE workspace_id = $1 AND ($2::text IS NULL OR country = UPPER($2))
            ORDER BY name, captured_at DESC
            LIMIT $3
            """,
            workspace_id,
            args.get("country"),
            min(int(args.get("limit", 10)), 30),
        )
        return {
            "count": len(rows),
            "trends": [dict(r) for r in rows],
        }

    if name == "get_hooks":
        rows = await pool.fetch(
            """
            SELECT h.hook_text, h.hook_type, h.cta, p.author_handle, p.outlier_score
            FROM vos.hooks h JOIN vos.posts p ON p.id = h.post_id
            WHERE h.workspace_id = $1
            ORDER BY p.rank_score DESC NULLS LAST LIMIT $2
            """,
            workspace_id,
            min(int(args.get("limit", 5)), 15),
        )
        return {
            "count": len(rows),
            "hooks": [
                {
                    "hook": r["hook_text"],
                    "type": r["hook_type"],
                    "cta": r["cta"],
                    "author": r["author_handle"],
                    "multiplier": float(r["outlier_score"]) if r["outlier_score"] else None,
                }
                for r in rows
            ],
        }

    if name == "build_weekly_brief":
        queue = PostgresJobQueue(pool)
        job_id = await queue.enqueue(
            workspace_id=workspace_id, kind="build_weekly_brief", payload={}
        )
        return {"job_id": job_id, "status": "queued"}

    if name == "explain_feature":
        feature = args.get("feature", "")
        return {"feature": feature, "explanation": FEATURE_DOCS.get(feature, "Vista desconocida.")}

    return {"error": "unknown_tool", "tool": name}
