"""Canonical <-> OpenAI translation and history trimming — no network."""

from __future__ import annotations

import json
from types import SimpleNamespace

from virtualos.agent.loop import trim_history
from virtualos.agent.tools import TOOL_DEFS
from virtualos.llm.openai_provider import (
    from_openai_message,
    to_openai_messages,
    to_openai_tools,
)


def test_tools_translation_covers_all_tools() -> None:
    out = to_openai_tools(TOOL_DEFS)
    assert len(out) == len(TOOL_DEFS)
    first = out[0]
    assert first["type"] == "function"
    assert first["function"]["name"] == TOOL_DEFS[0]["name"]
    assert first["function"]["parameters"]["type"] == "object"


def test_full_tool_roundtrip_messages() -> None:
    canonical = [
        {"role": "user", "content": "muéstrame outliers"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Consulto."},
                {"type": "tool_use", "id": "call_1", "name": "get_outliers", "input": {"limit": 3}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": '{"count": 3}'}
            ],
        },
    ]
    out = to_openai_messages(canonical)
    assert out[0] == {"role": "user", "content": "muéstrame outliers"}
    assert out[1]["role"] == "assistant"
    assert out[1]["content"] == "Consulto."
    call = out[1]["tool_calls"][0]
    assert call["id"] == "call_1"
    assert json.loads(call["function"]["arguments"]) == {"limit": 3}
    assert out[2] == {"role": "tool", "tool_call_id": "call_1", "content": '{"count": 3}'}


def test_assistant_tool_only_has_null_content() -> None:
    out = to_openai_messages(
        [
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "c", "name": "x", "input": {}}],
            }
        ]
    )
    assert out[0]["content"] is None


def test_from_openai_message_builds_canonical_blocks() -> None:
    tc = SimpleNamespace(
        id="call_9",
        function=SimpleNamespace(name="get_hooks", arguments='{"limit": 5}'),
    )
    calls, raw = from_openai_message("ok", [tc])
    assert calls[0].name == "get_hooks"
    assert calls[0].input == {"limit": 5}
    assert raw == [
        {"type": "text", "text": "ok"},
        {"type": "tool_use", "id": "call_9", "name": "get_hooks", "input": {"limit": 5}},
    ]


def test_from_openai_message_bad_json_args() -> None:
    tc = SimpleNamespace(id="c", function=SimpleNamespace(name="x", arguments="{not json"))
    calls, _ = from_openai_message("", [tc])
    assert calls[0].input == {}


def test_trim_history_drops_orphan_tool_results() -> None:
    history = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "{}"}]},
        {"role": "assistant", "content": "respuesta"},
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¡hola!"},
    ]
    trimmed = trim_history(history)
    assert trimmed[0] == {"role": "user", "content": "hola"}
    assert len(trimmed) == 2


def test_trim_history_empty_when_no_user_text() -> None:
    assert trim_history([{"role": "assistant", "content": "x"}]) == []
