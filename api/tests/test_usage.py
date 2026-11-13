"""Regression guard for api_usage cost recording."""

from __future__ import annotations

from virtualos.observability.usage import record_usage


async def test_usage_query_casts_costs_to_numeric(fake_pool) -> None:
    # Bug seen 2026-11-13: COALESCE($4, 0) inferred integer and truncated USD to 0.
    await record_usage("ws", "openai", units=0.0015, unit_label="USD", cost_usd=0.0015)
    query, args = fake_pool.executed[-1]
    assert "$4::numeric" in query
    assert "$6::numeric" in query
    assert 0.0015 in args
