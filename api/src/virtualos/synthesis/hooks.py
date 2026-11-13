"""Hook/structure analysis over OUTLIERS ONLY (cost funnel: code filters first).

Fast model, JSON output validated with Pydantic. Caption + transcript enter
the prompt wrapped as untrusted content.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from virtualos.config.settings import get_settings
from virtualos.db.client import get_pool
from virtualos.llm.provider import get_provider
from virtualos.queue.postgres import report_progress
from virtualos.synthesis.prompts import HOOKS_SYSTEM, wrap_untrusted
from virtualos.synthesis.transcripts import fetch_transcript

logger = logging.getLogger(__name__)

MIN_OUTLIER_FOR_HOOKS = 2.0
MAX_POSTS_PER_RUN = 25


class HookOut(BaseModel):
    hook_text: str
    hook_type: str | None = None
    structure: dict[str, Any] = {}
    cta: str | None = None
    language: str | None = None


def _parse_hook(text: str) -> HookOut | None:
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        return HookOut.model_validate(json.loads(text[start : end + 1]))
    except (json.JSONDecodeError, ValidationError):
        return None


async def synthesize_hooks(workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Job handler: analyze hooks for outlier posts that don't have one yet."""
    settings = get_settings()
    pool = get_pool()
    min_outlier = float(payload.get("min_outlier", MIN_OUTLIER_FOR_HOOKS))

    posts = await pool.fetch(
        """
        SELECT p.id, p.caption, p.transcript, p.raw, p.duration_s, p.outlier_score
        FROM vos.posts p
        LEFT JOIN vos.hooks h ON h.post_id = p.id
        WHERE p.workspace_id = $1 AND p.outlier_score >= $2 AND h.id IS NULL
        ORDER BY p.rank_score DESC NULLS LAST
        LIMIT $3
        """,
        workspace_id,
        min_outlier,
        int(payload.get("limit", MAX_POSTS_PER_RUN)),
    )

    provider = get_provider()
    done, failed = 0, 0
    total = len(posts)
    if total == 0:
        await report_progress("No hay outliers nuevos por analizar", done=0, total=0)

    for i, p in enumerate(posts):
        await report_progress("Analizando ganchos de los outliers", done=i, total=total)
        raw = p["raw"]
        raw_dict = json.loads(raw) if isinstance(raw, str) else dict(raw or {})

        transcript = p["transcript"]
        if not transcript:
            transcript = await fetch_transcript(raw_dict)
            if transcript:
                await pool.execute(
                    "UPDATE vos.posts SET transcript = $2 WHERE id = $1", p["id"], transcript
                )

        material = f"CAPTION:\n{wrap_untrusted(p['caption'] or '(sin caption)')}\n"
        if transcript:
            material += f"\nTRANSCRIPCION:\n{wrap_untrusted(transcript)}\n"
        if p["duration_s"]:
            material += f"\nDuración del video: {p['duration_s']} segundos\n"

        try:
            result = await provider.complete(
                model=settings.resolved_model_fast,
                system=HOOKS_SYSTEM,
                messages=[{"role": "user", "content": material}],
                max_tokens=800,
                temperature=0.2,
                output_format="json",
                workspace_id=workspace_id,
            )
        except Exception:
            logger.exception("hook analysis call failed for post %s", p["id"])
            failed += 1
            continue

        hook = _parse_hook(result.text)
        if hook is None:
            logger.warning("unparseable hook JSON for post %s", p["id"])
            failed += 1
            continue

        await pool.execute(
            """
            INSERT INTO vos.hooks (workspace_id, post_id, hook_text, hook_type, structure, cta, language, model, cost_usd)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9)
            ON CONFLICT (workspace_id, post_id) DO NOTHING
            """,
            workspace_id,
            p["id"],
            hook.hook_text,
            hook.hook_type,
            json.dumps(hook.structure),
            hook.cta,
            hook.language,
            settings.resolved_model_fast,
            result.cost_usd,
        )
        done += 1

    return {"hooks_created": done, "failed": failed, "candidates": len(posts)}
