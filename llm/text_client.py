"""Text-model client factory.

RadSpeed talks to its language model through the OpenAI chat-completions
shape (``client.chat.completions.create``). Two providers are supported:

``openai``
    Any OpenAI-compatible endpoint (OpenAI, Groq, a local server). This is the
    default and is unchanged from earlier releases.

``bedrock-anthropic``
    Claude on Amazon Bedrock through the Anthropic Messages API, authenticated
    with a Bedrock API key. Used by the practice profile so report text never
    leaves the selected AWS region (``au.`` inference profiles keep data in
    Australia). ``BedrockAnthropicChatClient`` adapts the Messages API to the
    small subset of the chat-completions interface RadSpeed uses, so the rest
    of the code does not change.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from types import SimpleNamespace
from typing import Any, Iterable, Iterator, Optional

from openai import OpenAI

from config.config import config
from config import practice

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 8192
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


def bedrock_anthropic_base_url(region: str) -> str:
    return f"https://bedrock-runtime.{region}.amazonaws.com/anthropic"


def get_text_client(openai_cls: Any = None):
    """Return the configured text-model client.

    ``openai_cls`` lets a calling module pass its own ``OpenAI`` symbol so the
    existing tests that patch ``llm.format.OpenAI`` and friends keep working.
    """
    if practice.settings.text_provider == "bedrock-anthropic":
        return BedrockAnthropicChatClient(
            api_key=config.TEXT_API_KEY or os.environ.get("AWS_BEARER_TOKEN_BEDROCK", ""),
            region=practice.settings.bedrock_region,
        )
    factory = openai_cls or OpenAI
    return factory(api_key=config.TEXT_API_KEY, base_url=config.BASE_URL)


# ---------------------------------------------------------------------------
# Message and tool conversion
# ---------------------------------------------------------------------------

def _convert_content(content: Any) -> Any:
    """Convert OpenAI message content (str or parts list) to Anthropic blocks."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    blocks = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif ptype == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            match = _DATA_URL_RE.match(url)
            if match:
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": match.group("mime"),
                        "data": match.group("data"),
                    },
                })
            elif url:
                blocks.append({"type": "image", "source": {"type": "url", "url": url}})
    return blocks


def convert_messages(messages: Iterable[dict]) -> tuple[str, list[dict]]:
    """Split OpenAI messages into an Anthropic system string and message list."""
    system_parts: list[str] = []
    converted: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role in ("system", "developer"):
            if isinstance(content, str):
                system_parts.append(content)
            else:
                for block in _convert_content(content):
                    if block.get("type") == "text":
                        system_parts.append(block["text"])
            continue
        if role == "tool":
            converted.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": content if isinstance(content, str) else json.dumps(content),
                }],
            })
            continue
        if role == "assistant" and msg.get("tool_calls"):
            blocks = []
            if content:
                blocks.append({"type": "text", "text": content})
            for call in msg["tool_calls"]:
                fn = call.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": call.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args,
                })
            converted.append({"role": "assistant", "content": blocks})
            continue
        converted.append({
            "role": "assistant" if role == "assistant" else "user",
            "content": _convert_content(content),
        })
    # Anthropic requires the first message to come from the user.
    if converted and converted[0]["role"] != "user":
        converted.insert(0, {"role": "user", "content": "(no input)"})
    return "\n\n".join(p for p in system_parts if p), converted


def convert_tools(tools: Optional[list[dict]]) -> Optional[list[dict]]:
    if not tools:
        return None
    out = []
    for tool in tools:
        fn = tool.get("function", tool)
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return out


def convert_tool_choice(choice: Any) -> Optional[dict]:
    if not choice:
        return None
    if isinstance(choice, str):
        return {"auto": {"type": "auto"}, "required": {"type": "any"}}.get(choice)
    if isinstance(choice, dict):
        name = (choice.get("function") or {}).get("name")
        if name:
            return {"type": "tool", "name": name}
    return None


# ---------------------------------------------------------------------------
# OpenAI-shaped response objects
# ---------------------------------------------------------------------------

def _response_from_message(message: Any) -> SimpleNamespace:
    text_parts: list[str] = []
    tool_calls = []
    for block in getattr(message, "content", []) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(getattr(block, "text", "") or "")
        elif btype == "tool_use":
            tool_calls.append(SimpleNamespace(
                id=getattr(block, "id", ""),
                type="function",
                function=SimpleNamespace(
                    name=getattr(block, "name", ""),
                    arguments=json.dumps(getattr(block, "input", {}) or {}),
                ),
            ))
    content = "".join(text_parts) if text_parts else None
    msg = SimpleNamespace(
        role="assistant",
        content=content,
        tool_calls=tool_calls or None,
    )
    stop = getattr(message, "stop_reason", None)
    finish = "tool_calls" if stop == "tool_use" else ("length" if stop == "max_tokens" else "stop")
    usage = getattr(message, "usage", None)
    return SimpleNamespace(
        id=getattr(message, "id", ""),
        model=getattr(message, "model", ""),
        choices=[SimpleNamespace(index=0, message=msg, finish_reason=finish)],
        usage=SimpleNamespace(
            prompt_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            completion_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        ),
    )


def _chunk(text: Optional[str], finish_reason: Optional[str] = None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(
            index=0,
            delta=SimpleNamespace(content=text, role="assistant"),
            finish_reason=finish_reason,
        )]
    )


class _Completions:
    def __init__(self, owner: "BedrockAnthropicChatClient"):
        self._owner = owner

    def create(self, *, model: str, messages: list[dict], stream: bool = False,
               tools: Optional[list[dict]] = None, tool_choice: Any = None,
               temperature: Optional[float] = None, max_tokens: Optional[int] = None,
               max_completion_tokens: Optional[int] = None, **_ignored: Any):
        system, converted = convert_messages(messages)
        kwargs: dict[str, Any] = {
            "model": model or self._owner.default_model,
            "max_tokens": max_completion_tokens or max_tokens or _DEFAULT_MAX_TOKENS,
            "messages": converted,
        }
        if system:
            kwargs["system"] = system
        if temperature is not None:
            kwargs["temperature"] = temperature
        a_tools = convert_tools(tools)
        if a_tools:
            kwargs["tools"] = a_tools
            a_choice = convert_tool_choice(tool_choice)
            if a_choice:
                kwargs["tool_choice"] = a_choice
        if self._owner.thinking_disabled:
            # Claude rejects a custom temperature while adaptive thinking is
            # on, and report formatting is a low-temperature task.
            kwargs["thinking"] = {"type": "disabled"}
        client = self._owner.anthropic_client
        try:
            if stream:
                return self._stream(client, kwargs)
            return _response_from_message(client.messages.create(**kwargs))
        except Exception as exc:  # pragma: no cover - mapped below
            raise self._owner.translate_error(exc) from exc

    @staticmethod
    def _stream(client: Any, kwargs: dict) -> Iterator[SimpleNamespace]:
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                if text:
                    yield _chunk(text)
        yield _chunk(None, finish_reason="stop")


class BedrockAnthropicChatClient:
    """Chat-completions-shaped wrapper around Claude on Amazon Bedrock."""

    def __init__(self, api_key: str, region: str, *, anthropic_client: Any = None,
                 thinking_disabled: Optional[bool] = None):
        self.api_key = api_key
        self.region = region
        self.base_url = bedrock_anthropic_base_url(region)
        self.default_model = config.SELECTED_MODEL or ""
        env_thinking = os.environ.get("BEDROCK_THINKING", "disabled").strip().lower()
        self.thinking_disabled = (
            thinking_disabled if thinking_disabled is not None else env_thinking != "enabled"
        )
        self._anthropic_client = anthropic_client
        self.chat = SimpleNamespace(completions=_Completions(self))

    @property
    def anthropic_client(self):
        if self._anthropic_client is None:
            try:
                from anthropic import Anthropic
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise RuntimeError(
                    "RADSPEED_TEXT_PROVIDER=bedrock-anthropic needs the 'anthropic' package"
                ) from exc
            self._anthropic_client = Anthropic(api_key=self.api_key, base_url=self.base_url)
        return self._anthropic_client

    @staticmethod
    def translate_error(exc: Exception) -> Exception:
        """Map Anthropic auth failures onto openai.AuthenticationError.

        Callers already handle that class to surface a "key rejected" message,
        so keeping the type lets the practice profile reuse the same UI path.
        """
        try:
            import anthropic
            import httpx
            from openai import AuthenticationError
        except ImportError:  # pragma: no cover
            return exc
        if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
            request = httpx.Request("POST", "https://bedrock-runtime/anthropic/v1/messages")
            response = httpx.Response(401, request=request)
            return AuthenticationError(str(exc), response=response, body=None)
        return exc
