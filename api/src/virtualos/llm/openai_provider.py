"""OpenAI implementation of LLMProvider (text/JSON only; the agent uses Anthropic).

Adapted from orkiza-captacion openai_client.py: same contract, cached-token
accounting and temperature-retry. Only this module imports the openai SDK.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from virtualos.config.settings import get_settings
from virtualos.llm.pricing import compute_cost_usd
from virtualos.llm.provider import LLMResult, ToolCall
from virtualos.observability.usage import record_usage

logger = logging.getLogger(__name__)

_default_client: AsyncOpenAI | None = None


def _get_client(api_key: str | None) -> AsyncOpenAI:
    if api_key is not None:
        return AsyncOpenAI(api_key=api_key)
    global _default_client
    if _default_client is None:
        settings = get_settings()
        if settings.openai_api_key is None:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
        _default_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _default_client


class OpenAIProvider:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float = 1.0,
        tools: list[dict[str, Any]] | None = None,
        output_format: str = "text",
        workspace_id: str | None = None,
    ) -> LLMResult:
        client = _get_client(self._api_key)

        oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        oai_messages.extend(to_openai_messages(messages))

        extra: dict[str, Any] = {}
        if tools:
            extra["tools"] = to_openai_tools(tools)
        if output_format == "json":
            # Requires the word "json" somewhere in the prompt or OpenAI returns 400.
            extra["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        try:
            resp = await client.chat.completions.create(
                model=model,
                max_completion_tokens=max_tokens,
                temperature=temperature,
                messages=oai_messages,  # type: ignore[arg-type]
                **extra,
            )
        except BadRequestError as exc:
            # Reasoning models only accept the default temperature; retry without it.
            if "temperature" not in str(exc):
                raise
            logger.warning(
                "OpenAI rejected temperature=%s for %s; retrying default", temperature, model
            )
            resp = await client.chat.completions.create(
                model=model,
                max_completion_tokens=max_tokens,
                messages=oai_messages,  # type: ignore[arg-type]
                **extra,
            )
        latency_ms = int((time.monotonic() - started) * 1000)

        msg = resp.choices[0].message
        text = msg.content or ""
        tool_calls, raw_content = from_openai_message(text, msg.tool_calls)
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached_tokens = getattr(details, "cached_tokens", 0) or 0
        noncached_input = max(0, prompt_tokens - cached_tokens)

        cost_usd = compute_cost_usd(
            model,
            input_tokens=noncached_input,
            output_tokens=output_tokens,
            cache_read_tokens=cached_tokens,
        )

        if workspace_id is not None:
            await record_usage(
                workspace_id, "openai", units=cost_usd, unit_label="USD", cost_usd=cost_usd
            )

        return LLMResult(
            text=text,
            input_tokens=noncached_input,
            output_tokens=output_tokens,
            cache_read_tokens=cached_tokens,
            cache_creation_tokens=0,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            stop_reason="tool_use" if tool_calls else "end_turn",
            tool_calls=tool_calls,
            raw_content=raw_content,
        )


# ---------------------------------------------------------------------------
# Canonical (Anthropic-style) <-> OpenAI chat format translation.
# The agent loop speaks the canonical format; only this module knows OpenAI's.
# ---------------------------------------------------------------------------


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        blocks = list(content)
        if role == "assistant":
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})},
                }
                for b in blocks
                if b.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
        else:
            # user turn carrying tool_result blocks (and possibly text)
            for b in blocks:
                if b.get("type") == "tool_result":
                    result = b.get("content", "")
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": b["tool_use_id"],
                            "content": result if isinstance(result, str) else json.dumps(result),
                        }
                    )
                elif b.get("type") == "text":
                    out.append({"role": "user", "content": b.get("text", "")})
    return out


def from_openai_message(
    text: str, oai_tool_calls: list[Any] | None
) -> tuple[list[ToolCall], list[dict[str, Any]]]:
    """Return (tool_calls, canonical raw_content blocks)."""
    calls: list[ToolCall] = []
    raw: list[dict[str, Any]] = []
    if text:
        raw.append({"type": "text", "text": text})
    for tc in oai_tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))
        raw.append({"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args})
    return calls, raw
