"""USD rates per million tokens, by model id substring.

Longest-match wins so e.g. "gpt-5.4-mini" is checked before "gpt-5.4".
Update this table when model IDs in settings change; unknown models fall back
to the most expensive known rate so cost is never under-reported.
"""

from __future__ import annotations

# model substring -> (input_usd_per_mtok, output_usd_per_mtok)
RATES: dict[str, tuple[float, float]] = {
    # Anthropic
    "haiku-4-5": (1.00, 5.00),
    "sonnet-4-6": (3.00, 15.00),
    # OpenAI
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5.4": (2.50, 15.00),
}
DEFAULT_RATE = (3.00, 15.00)

CACHE_WRITE_MULT = 1.25  # Anthropic cache write premium over input
CACHE_READ_MULT = 0.10  # cache read discount (both providers)


def rates_for(model: str) -> tuple[float, float]:
    for key in sorted(RATES, key=len, reverse=True):
        if key in model:
            return RATES[key]
    return DEFAULT_RATE


def compute_cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """USD cost of one call. ``input_tokens`` is the NON-cached portion."""
    in_rate, out_rate = rates_for(model)
    cost = (
        input_tokens * in_rate
        + cache_creation_tokens * in_rate * CACHE_WRITE_MULT
        + cache_read_tokens * in_rate * CACHE_READ_MULT
        + output_tokens * out_rate
    ) / 1_000_000
    return round(cost, 6)
