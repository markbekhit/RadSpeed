"""Compatibility helpers for OpenAI-compatible chat-completion models."""

from __future__ import annotations

from typing import Any, Optional


def uses_modern_completion_contract(model: Optional[str]) -> bool:
    """Return whether *model* uses reasoning-model completion parameters."""
    normalised = (model or "").strip().lower()
    return normalised.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


def reasoning_effort_for_model(model: Optional[str]) -> Optional[str]:
    """Return the owner-selected reasoning effort for GPT-6 report routes."""
    normalised = (model or "").strip().lower()
    if normalised == "gpt-6-luna":
        return "high"
    if normalised == "gpt-6-sol":
        return "low"
    return None


def supports_chat_tool_calls(model: Optional[str]) -> bool:
    """Configured GPT-6 reasoning routes use JSON rather than chat tools."""
    return reasoning_effort_for_model(model) is None


def completion_options(
    model: Optional[str],
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
    **options: Any,
) -> dict[str, Any]:
    """Build provider-compatible keyword arguments for chat completions.

    GPT-5, GPT-6 and OpenAI reasoning models reject ``max_tokens`` in favour of
    ``max_completion_tokens`` and accept only their default temperature.
    Older OpenAI-compatible providers still commonly expect the legacy names.
    """
    result = dict(options)
    if uses_modern_completion_contract(model):
        effort = reasoning_effort or reasoning_effort_for_model(model)
        if effort:
            result["reasoning_effort"] = effort
        if max_tokens is not None:
            # The modern budget includes reasoning tokens. Small legacy limits
            # can otherwise leave no room for the visible answer.
            result["max_completion_tokens"] = max(2048 if effort == "high" else 256, max_tokens)
        return result

    if temperature is not None:
        result["temperature"] = temperature
    if max_tokens is not None:
        result["max_tokens"] = max_tokens
    return result
