"""External API usage tracking -> `vos.api_usage`, per workspace.

Every connector / LLM call records its real cost here (CLAUDE.md hard rule 7).
Fire-and-forget: tracking must never break a run — on failure it logs and moves on.

Adapted from orkiza-captacion observability/usage.py, with workspace scoping.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def record_usage(
    workspace_id: str,
    provider: str,
    *,
    calls: int = 1,
    units: float | None = None,
    unit_label: str | None = None,
    cost_usd: float | None = None,
) -> None:
    """Increment the daily per-workspace counter for a provider. Never raises.

    ``units`` is the billable dimension when it is not plain calls (Apify compute
    units, Serper credits); ``cost_usd`` is the USD cost when known.
    """
    try:
        from virtualos.db.client import get_pool

        pool = get_pool()
        await pool.execute(
            """
            INSERT INTO vos.api_usage (workspace_id, provider, day, calls, units, unit_label, cost_usd)
            VALUES ($1, $2, CURRENT_DATE, $3, COALESCE($4, 0), $5, COALESCE($6, 0))
            ON CONFLICT (workspace_id, provider, day) DO UPDATE SET
                calls      = vos.api_usage.calls + EXCLUDED.calls,
                units      = vos.api_usage.units + EXCLUDED.units,
                unit_label = COALESCE(EXCLUDED.unit_label, vos.api_usage.unit_label),
                cost_usd   = vos.api_usage.cost_usd + EXCLUDED.cost_usd
            """,
            workspace_id,
            provider,
            calls,
            units,
            unit_label,
            cost_usd,
        )
    except Exception:  # fire-and-forget by design
        logger.debug("record_usage failed (provider=%s); usage not recorded", provider)
