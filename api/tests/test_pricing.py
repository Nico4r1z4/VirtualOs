from virtualos.llm.pricing import DEFAULT_RATE, compute_cost_usd, rates_for


def test_known_rates() -> None:
    assert rates_for("claude-haiku-4-5") == (1.00, 5.00)
    assert rates_for("claude-sonnet-4-6") == (3.00, 15.00)
    # Longest match wins: gpt-5.4-mini must not resolve to gpt-5.4
    assert rates_for("gpt-5.4-mini") == (0.75, 4.50)
    assert rates_for("gpt-5.4") == (2.50, 15.00)


def test_unknown_model_uses_default() -> None:
    assert rates_for("some-future-model") == DEFAULT_RATE


def test_cost_simple() -> None:
    # 1M input + 1M output on haiku-4-5 = 1.00 + 5.00
    cost = compute_cost_usd("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == 6.0


def test_cost_with_cache() -> None:
    cost = compute_cost_usd(
        "claude-sonnet-4-6",
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
    )
    # read: 3.00 * 0.10 = 0.30 ; write: 3.00 * 1.25 = 3.75
    assert cost == 4.05
