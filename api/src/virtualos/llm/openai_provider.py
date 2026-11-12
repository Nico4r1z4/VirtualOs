"""OpenAI implementation of LLMProvider (text/JSON only; the agent uses Anthropic).

Adapted from orkiza-captacion openai_client.py: same contract, cached-token
accounting and temperature-retry. Only this module imports the openai SDK.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from virtualos.config.settings import get_settings
from virtualos.llm.pricing import compute_cost_usd
from virtualos.llm.provider import LLMResult
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
        if tools:
            raise NotImplementedError(
                "Tool use is only implemented for the Anthropic provider (agent runs on it)."
            )
        client = _get_client(self._api_key)

        oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            content = m["content"]
            if not isinstance(content, str):
                raise NotImplementedError("OpenAIProvider only supports plain-text messages.")
            oai_messages.append({"role": m["role"], "content": content})

        extra: dict[str, Any] = {}
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

        text = resp.choices[0].message.content or ""
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
        )
