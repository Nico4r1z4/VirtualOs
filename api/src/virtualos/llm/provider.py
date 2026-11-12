"""LLMProvider: the ONLY door to LLM APIs (CLAUDE.md hard rule 4).

No other module may import anthropic/openai SDKs. The provider is selected by
settings.llm_provider; an explicit api_key can be injected per call site to
support BYOK workspaces later (keys would come decrypted from KMS, never logged).

Canonical message/tool format is Anthropic's; adapters translate as needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(slots=True)
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float
    latency_ms: int
    stop_reason: str = "end_turn"
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_content: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tokens_used(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )


class LLMProvider(Protocol):
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
    ) -> LLMResult: ...


def get_provider(api_key: str | None = None) -> LLMProvider:
    """Return the configured provider. ``api_key`` overrides settings (BYOK-ready)."""
    from virtualos.config.settings import get_settings

    settings = get_settings()
    if settings.llm_provider == "openai":
        from virtualos.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=api_key)
    from virtualos.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider(api_key=api_key)
