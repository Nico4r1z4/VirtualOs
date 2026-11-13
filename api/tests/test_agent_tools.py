"""Agent tool regressions — no network, no DB."""

from __future__ import annotations

import inspect

from virtualos.agent import tools
from virtualos.agent.tools import as_text_list


def test_as_text_list_normalizes_model_inputs() -> None:
    assert as_text_list(None) is None
    assert as_text_list("es") == ["es"]
    assert as_text_list("ahorro, deudas ,inversión") == ["ahorro", "deudas", "inversión"]
    assert as_text_list(["es", "", None, " en "]) == ["es", "en"]
    assert as_text_list([]) is None
    assert as_text_list("") is None


def test_niche_profile_sql_casts_array_params() -> None:
    # Bug seen live 2026-11-13: COALESCE($6, '{es}') inferred text, not text[].
    src = inspect.getsource(tools.execute_tool)
    for param in ("$6::text[]", "$7::text[]", "$8::text[]"):
        assert src.count(param) >= 2, f"{param} must be cast in both INSERT and UPDATE"
