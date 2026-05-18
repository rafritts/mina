"""
LLM client singleton — xAI gRPC SDK.

One place to swap the model or provider. All modules import get_client() or
chat_create() from here instead of constructing their own client instances.

chat_create() accepts OpenAI-style kwargs and returns an OpenAI-compatible
response object so no call sites need to change.
"""
import json
from typing import Optional, Sequence

from xai_sdk import Client
from xai_sdk.proto import chat_pb2
from xai_sdk.chat import text, image as _xai_image

from src.config.config import MODEL, BASE_URL, API_KEY

__all__ = ["get_client", "chat_create", "MODEL", "BASE_URL", "API_KEY"]

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(api_key=API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Message conversion — OpenAI dict format → xAI protobuf
# ---------------------------------------------------------------------------

def _dict_to_xai_message(m: dict) -> chat_pb2.Message:
    role = m.get("role", "user")
    content = m.get("content") or ""

    if role == "system":
        return chat_pb2.Message(
            role=chat_pb2.MessageRole.ROLE_SYSTEM,
            content=[text(content)],
        )

    if role == "user":
        if isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append(text(block.get("text", "")))
                elif block.get("type") == "image_url":
                    url = (block.get("image_url") or {}).get("url", "")
                    if url:
                        parts.append(_xai_image(url))
            return chat_pb2.Message(role=chat_pb2.MessageRole.ROLE_USER, content=parts or [text("")])
        return chat_pb2.Message(role=chat_pb2.MessageRole.ROLE_USER, content=[text(content)])

    if role == "assistant":
        raw_tcs = m.get("tool_calls") or []
        xai_tcs = [
            chat_pb2.ToolCall(
                id=tc.get("id", ""),
                function=chat_pb2.FunctionCall(
                    name=(tc.get("function") or {}).get("name", ""),
                    arguments=(tc.get("function") or {}).get("arguments", "{}"),
                ),
            )
            for tc in raw_tcs
        ]
        return chat_pb2.Message(
            role=chat_pb2.MessageRole.ROLE_ASSISTANT,
            content=[text(content)],
            tool_calls=xai_tcs,
        )

    if role == "tool":
        return chat_pb2.Message(
            role=chat_pb2.MessageRole.ROLE_TOOL,
            content=[text(content)],
            tool_call_id=m.get("tool_call_id") or None,
        )

    # Fallback
    return chat_pb2.Message(role=chat_pb2.MessageRole.ROLE_USER, content=[text(str(content))])


def _dict_to_xai_tool(t: dict) -> chat_pb2.Tool:
    fn = t.get("function") or {}
    return chat_pb2.Tool(
        function=chat_pb2.Function(
            name=fn.get("name", ""),
            description=fn.get("description", ""),
            parameters=json.dumps(fn.get("parameters") or {}),
        )
    )


# ---------------------------------------------------------------------------
# OpenAI-compatible response wrapper
# ---------------------------------------------------------------------------

class _FunctionCall:
    __slots__ = ("name", "arguments")

    def __init__(self, tc: chat_pb2.ToolCall):
        self.name = tc.function.name
        self.arguments = tc.function.arguments


class _ToolCall:
    __slots__ = ("id", "type", "function")

    def __init__(self, tc: chat_pb2.ToolCall):
        self.id = tc.id
        self.type = "function"
        self.function = _FunctionCall(tc)


class _Message:
    __slots__ = ("content", "tool_calls")

    def __init__(self, response):
        self.content = response.content or ""
        tcs = response.tool_calls
        self.tool_calls = [_ToolCall(tc) for tc in tcs] if tcs else None


class _Choice:
    __slots__ = ("message", "finish_reason")

    def __init__(self, response):
        self.message = _Message(response)
        raw_finish = response.finish_reason  # e.g. "REASON_STOP", "REASON_MAX_LEN"
        self.finish_reason = "tool_calls" if "TOOL_CALL" in raw_finish else raw_finish


class _CompatResponse:
    """Wraps an xAI SDK Response to look like an OpenAI ChatCompletion."""

    __slots__ = ("choices", "usage")

    def __init__(self, response):
        self.choices = [_Choice(response)]
        self.usage = response.usage  # has .prompt_tokens, .completion_tokens, .total_tokens


# ---------------------------------------------------------------------------
# response_format normalizer
# ---------------------------------------------------------------------------

def _normalize_response_format(rf):
    """Accept {"type": "json_object"} dict or plain string; return string for xAI SDK."""
    if rf is None:
        return None
    if isinstance(rf, str):
        return rf
    if isinstance(rf, dict):
        return rf.get("type")
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat_create(**kwargs) -> _CompatResponse:
    """
    OpenAI-compatible chat completion call using the xAI gRPC SDK.

    Accepts the same kwargs as openai.chat.completions.create() and returns
    an object with the same interface (choices[0].message.content, usage, etc.).

    reasoning_effort: "none" | "low" | "medium" | "high" (default "low" per xAI docs).
      Controls how many reasoning tokens grok-4.3 spends before answering.
      Pass "none" for pure generation tasks where reasoning adds no value.
    """
    model: str = kwargs.pop("model", MODEL)
    raw_messages: list[dict] = kwargs.pop("messages", [])
    raw_tools: list[dict] = kwargs.pop("tools", None) or []
    tool_choice = kwargs.pop("tool_choice", None)
    temperature: Optional[float] = kwargs.pop("temperature", None)
    max_tokens: Optional[int] = kwargs.pop("max_tokens", None)
    response_format = _normalize_response_format(kwargs.pop("response_format", None))
    reasoning_effort: Optional[str] = kwargs.pop("reasoning_effort", None)
    # Discard any remaining unknown kwargs gracefully
    kwargs.pop("stream", None)

    xai_messages: Sequence[chat_pb2.Message] = [_dict_to_xai_message(m) for m in raw_messages]
    xai_tools: Optional[Sequence[chat_pb2.Tool]] = [_dict_to_xai_tool(t) for t in raw_tools] if raw_tools else None

    create_kwargs: dict = dict(
        model=model,
        messages=xai_messages,
        tools=xai_tools,
        tool_choice=tool_choice,
        max_tokens=max_tokens,
        response_format=response_format,
    )
    # Reasoning models reject temperature; only pass when explicitly set.
    if temperature is not None:
        create_kwargs["temperature"] = temperature
    if reasoning_effort is not None:
        create_kwargs["reasoning_effort"] = reasoning_effort

    chat = get_client().chat.create(**create_kwargs)

    response = chat.sample()
    return _CompatResponse(response)
