"""Compatibility helpers for OpenAI-compatible chat-completion models."""

from __future__ import annotations

from typing import Any, Optional


def uses_modern_completion_contract(model: Optional[str]) -> bool:
    """Return whether *model* uses GPT-5/reasoning completion parameters."""
    normalised = (model or "").strip().lower()
    return normalised.startswith(("gpt-5", "o1", "o3", "o4"))


def completion_options(
    model: Optional[str],
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **options: Any,
) -> dict[str, Any]:
    """Build provider-compatible keyword arguments for chat completions.

    GPT-5 and OpenAI reasoning models reject ``max_tokens`` in favour of
    ``max_completion_tokens`` and accept only their default temperature.
    Older OpenAI-compatible providers still commonly expect the legacy names.
    """
    result = dict(options)
    if uses_modern_completion_contract(model):
        if max_tokens is not None:
            # The modern budget includes reasoning tokens. Small legacy limits
            # can otherwise leave no room for the visible answer.
            result["max_completion_tokens"] = max(256, max_tokens)
        return result

    if temperature is not None:
        result["temperature"] = temperature
    if max_tokens is not None:
        result["max_tokens"] = max_tokens
    return result
