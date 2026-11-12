"""Anthropic implementation of LLMProvider.

Adapted from orkiza-captacion anthropic_client.py: same cost/caching handling,
plus tool use support for the agent. Only this module imports the anthropic SDK.
"""

from __future__ import annotations

import time
from typing import Any

from anthropic import AsyncAnthropic

from virtualos.config.settings import get_settings
from virtualos.llm.pricing import compute_cost_usd
from virtualos.llm.provider import LLMResult, ToolCall
from virtualos.observability.usage import record_usage

_default_client: AsyncAnthropic | None = None


def _get_client(api_key: str | None) -> AsyncAnthropic:
    if api_key is not None:
        # BYOK path: dedicated client, never cached globally.
        return AsyncAnthropic(api_key=api_key)
    global _default_client
    if _default_client is None:
        settings = get_settings()
        if settings.anthropic_api_key is None:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        _default_client = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
    return _default_client


class AnthropicProvider:
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
        settings = get_settings()
        client = _get_client(self._api_key)

        system_param: list[dict[str, Any]] | str
        if settings.anthropic_prompt_cache_enabled:
            system_param = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        else:
            system_param = system

        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools

        started = time.monotonic()
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_param,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
            **kwargs,
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        text = "".join(b.text for b in resp.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=dict(b.input))  # type: ignore[arg-type]
            for b in resp.content
            if b.type == "tool_use"
        ]
        raw_content = [b.model_dump() for b in resp.content]

        usage = resp.usage
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

        cost_usd = compute_cost_usd(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )

        if workspace_id is not None:
            await record_usage(
                workspace_id, "anthropic", units=cost_usd, unit_label="USD", cost_usd=cost_usd
            )

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            stop_reason=resp.stop_reason or "end_turn",
            tool_calls=tool_calls,
            raw_content=raw_content,
        )
