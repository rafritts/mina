"""
LLM client — headless Grok Build CLI (same pattern as Kaiya).

All modules import chat_create() from here. Spawns `grok` with --prompt-file
(never puts large prompts on argv — Linux ARG_MAX). CLI auth only: never
passes XAI_API_KEY / OpenAI keys into the child.

chat_create() accepts OpenAI-style kwargs and returns an OpenAI-compatible
response object so call sites stay unchanged.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from src.config.config import MODEL, BASE_URL, API_KEY

__all__ = ["get_client", "chat_create", "MODEL", "BASE_URL", "API_KEY", "grok_bin"]

# ---------------------------------------------------------------------------
# Paths / binary (mirrors kaiya ui/src/lib/agent/paths.ts + grok-oneshot.ts)
# ---------------------------------------------------------------------------

def grok_bin() -> str:
    if os.getenv("GROK_BIN"):
        return os.environ["GROK_BIN"]
    home = Path.home() / ".grok" / "bin" / "grok"
    if home.is_file():
        return str(home)
    which = shutil.which("grok")
    if which:
        return which
    return "grok"


def oneshot_cwd() -> Path:
    """Isolated cwd outside the git tree so project AGENTS.md is never loaded."""
    if os.getenv("MINA_GROK_CWD"):
        d = Path(os.environ["MINA_GROK_CWD"]).expanduser().resolve()
    else:
        d = Path.home() / ".mina" / "oneshot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _timeout_sec() -> float:
    raw = os.getenv("MINA_GROK_TIMEOUT_MS", "180000")
    try:
        ms = int(raw)
    except ValueError:
        ms = 180_000
    return max(5.0, ms / 1000.0)


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("CI", "1")
    for key in ("XAI_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    return env


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(str(block.get("text") or ""))
            elif btype == "image_url":
                url = (block.get("image_url") or {}).get("url") or ""
                # Headless oneshot is text-only; keep a stub so the model knows an image was present.
                if url.startswith("data:"):
                    parts.append("[image: embedded data URL]")
                elif url:
                    parts.append(f"[image: {url[:200]}]")
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    return str(content)


def _format_messages_body(messages: list[dict]) -> str:
    systems: list[str] = []
    turns: list[str] = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        text = _content_to_text(m.get("content"))
        if role == "system":
            if text.strip():
                systems.append(text.strip())
            continue
        if role == "assistant":
            block = text.strip()
            tcs = m.get("tool_calls") or []
            if tcs:
                tc_lines = []
                for tc in tcs:
                    fn = tc.get("function") or {}
                    tc_lines.append(
                        f"- id={tc.get('id', '')} name={fn.get('name', '')} "
                        f"arguments={fn.get('arguments', '{}')}"
                    )
                tool_block = "tool_calls:\n" + "\n".join(tc_lines)
                block = f"{block}\n{tool_block}".strip() if block else tool_block
            if block:
                turns.append(f"ASSISTANT:\n{block}")
        elif role == "tool":
            tid = m.get("tool_call_id") or ""
            turns.append(f"TOOL_RESULT id={tid}:\n{text}")
        else:
            turns.append(f"USER:\n{text}")

    parts: list[str] = []
    if systems:
        parts.append("## Instructions")
        parts.append("\n\n".join(systems))
        parts.append("")
    parts.append("## Input")
    if turns:
        parts.append("\n\n".join(turns))
    else:
        parts.append("(empty)")
    return "\n".join(parts)


def _tools_section(tools: list[dict]) -> str:
    """Describe host-owned function tools for the model (not Grok Build builtins)."""
    specs = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") or t
        specs.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters") or {},
        })
    return (
        "## Host tools\n"
        "You cannot invoke Grok Build shell/file tools. To use a host tool, return "
        "structured JSON with tool_calls (and content null or a short note). "
        "When finished answering the user, return content with text and tool_calls [].\n\n"
        + json.dumps(specs, indent=2)
    )


_TOOL_CALL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content": {
            "type": ["string", "null"],
            "description": "Final reply text when done; null or empty if calling tools.",
        },
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {
                        "type": "object",
                        "description": "Tool arguments as a JSON object (not a string).",
                    },
                },
                "required": ["name", "arguments"],
            },
            "description": "Host tools to run this round; empty array if content is final.",
        },
    },
    "required": ["content", "tool_calls"],
}


def _build_prompt(messages: list[dict], tools: list[dict] | None) -> str:
    if tools:
        preamble = (
            "Follow the instructions exactly. Do not use Grok Build filesystem, shell, "
            "or web tools. Reply only with the structured JSON required by the schema."
        )
        body = _format_messages_body(messages)
        return "\n".join([preamble, "", _tools_section(tools), "", body])
    preamble = (
        "Follow the instructions exactly. Do not use tools. "
        "Reply with only the requested output — no preamble."
    )
    return "\n".join([preamble, "", _format_messages_body(messages)])


# ---------------------------------------------------------------------------
# OpenAI-compatible response wrappers
# ---------------------------------------------------------------------------

class _FunctionCall:
    __slots__ = ("name", "arguments")

    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    __slots__ = ("id", "type", "function")

    def __init__(self, id_: str, name: str, arguments: str):
        self.id = id_
        self.type = "function"
        self.function = _FunctionCall(name, arguments)


class _Message:
    __slots__ = ("content", "tool_calls")

    def __init__(self, content: str, tool_calls: list[_ToolCall] | None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    __slots__ = ("message", "finish_reason")

    def __init__(self, content: str, tool_calls: list[_ToolCall] | None):
        self.message = _Message(content, tool_calls)
        self.finish_reason = "tool_calls" if tool_calls else "stop"


class _Usage:
    __slots__ = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_prompt_text_tokens",
    )

    def __init__(self, usage: dict | None):
        u = usage or {}
        self.prompt_tokens = int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
        self.completion_tokens = int(u.get("output_tokens") or u.get("completion_tokens") or 0)
        self.total_tokens = int(u.get("total_tokens") or (self.prompt_tokens + self.completion_tokens))
        self.reasoning_tokens = int(u.get("reasoning_tokens") or 0)
        self.cached_prompt_text_tokens = int(
            u.get("cache_read_input_tokens")
            or u.get("cached_prompt_text_tokens")
            or 0
        )


class _CompatResponse:
    """OpenAI ChatCompletion-shaped response from a headless grok run."""

    __slots__ = ("choices", "usage", "raw")

    def __init__(
        self,
        content: str,
        tool_calls: list[_ToolCall] | None,
        usage: dict | None,
        raw: dict | None = None,
    ):
        self.choices = [_Choice(content, tool_calls)]
        self.usage = _Usage(usage)
        self.raw = raw


# ---------------------------------------------------------------------------
# Spawn + parse (kaiya grok-oneshot)
# ---------------------------------------------------------------------------

class GrokCLIError(RuntimeError):
    def __init__(self, message: str, code: str = "exit"):
        super().__init__(message)
        self.code = code


def parse_grok_json_output(stdout: str) -> dict:
    """
    Parse `grok --output-format json` stdout.
    Prefers last JSON object line; falls back to full stdout parse.
    """
    trimmed = stdout.strip()
    if not trimmed:
        return {}
    lines = trimmed.split("\n")
    for line in reversed(lines):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    try:
        obj = json.loads(trimmed)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return {"text": trimmed}


def _extract_text(payload: dict) -> str:
    if isinstance(payload.get("structuredOutput"), (dict, list)):
        # Prefer structured object when present; still keep string form for callers.
        so = payload["structuredOutput"]
        if isinstance(so, (dict, list)):
            # If tool-call envelope, handle separately.
            if isinstance(so, dict) and "tool_calls" in so:
                return ""
            return json.dumps(so, ensure_ascii=False)
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text
    result = payload.get("result")
    if isinstance(result, str) and result.strip():
        return result
    return ""


def _parse_tool_envelope(payload: dict) -> tuple[str, list[_ToolCall] | None]:
    """Return (content, tool_calls) from structured tool-call schema output."""
    so = payload.get("structuredOutput")
    data = so if isinstance(so, dict) else None
    if data is None:
        raw_text = _extract_text(payload).strip()
        if not raw_text:
            return "", None
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text, None
    if not isinstance(data, dict):
        return _extract_text(payload), None

    content = data.get("content")
    if content is None:
        content = ""
    elif not isinstance(content, str):
        content = str(content)

    raw_tcs = data.get("tool_calls") or []
    if not isinstance(raw_tcs, list) or not raw_tcs:
        return content, None

    tool_calls: list[_ToolCall] = []
    for tc in raw_tcs:
        if not isinstance(tc, dict):
            continue
        name = str(tc.get("name") or "")
        if not name:
            continue
        args = tc.get("arguments", {})
        if isinstance(args, str):
            args_str = args
        else:
            args_str = json.dumps(args if args is not None else {}, ensure_ascii=False)
        tool_calls.append(
            _ToolCall(id_=f"call_{uuid.uuid4().hex[:12]}", name=name, arguments=args_str)
        )
    return content, tool_calls or None


def run_grok_oneshot(
    prompt: str,
    *,
    json_schema: dict | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
    max_turns: int = 1,
    timeout_sec: float | None = None,
) -> dict:
    """
    Spawn headless grok for a single completion. Returns parsed JSON object.
    Uses --prompt-file always (never --single argv) to avoid E2BIG.
    """
    cwd = oneshot_cwd()
    bin_path = grok_bin()
    timeout = timeout_sec if timeout_sec is not None else _timeout_sec()

    prompt_dir = tempfile.mkdtemp(prefix="mina-oneshot-")
    prompt_file = os.path.join(prompt_dir, "prompt.txt")
    try:
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)

        args = [
            bin_path,
            "--prompt-file", prompt_file,
            "--cwd", str(cwd),
            "--output-format", "json",
            "--permission-mode", "bypassPermissions",
            "--max-turns", str(max(1, max_turns)),
            "--verbatim",
            "--no-subagents",
            "--disable-web-search",
            # Empty allow-list: no Build builtins (bash/read/…). Host tools are
            # described in the prompt and returned via --json-schema instead.
            "--tools", "",
        ]
        if json_schema is not None:
            args.extend(["--json-schema", json.dumps(json_schema)])
        if reasoning_effort:
            # Map "none" → low-ish: CLI may not accept "none"
            effort = reasoning_effort
            if effort == "none":
                effort = "low"
            args.extend(["--reasoning-effort", effort])
        # Only pass model when explicitly overridden via GROK_MODEL or a non-placeholder.
        grok_model = os.getenv("GROK_MODEL") or None
        if grok_model:
            args.extend(["--model", grok_model])
        elif model and model not in ("grok-4.3", "grok-4-1-fast-reasoning", "sk-placeholder"):
            # Allow call-site model if it looks like a CLI-capable id the user set.
            pass  # CLI default is preferred; API model names often fail on Build CLI

        try:
            proc = subprocess.run(
                args,
                cwd=str(cwd),
                env=_child_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as e:
            raise GrokCLIError(
                f"grok binary not found ({bin_path}). Install Grok Build CLI and log in.",
                "spawn",
            ) from e
        except subprocess.TimeoutExpired as e:
            raise GrokCLIError(f"grok timed out after {timeout:.0f}s", "timeout") from e

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        payload = parse_grok_json_output(stdout)

        # Prefer a usable payload even on non-zero exit (e.g. max-turns with JSON).
        has_body = bool(_extract_text(payload).strip()) or isinstance(
            payload.get("structuredOutput"), (dict, list)
        )
        if proc.returncode != 0 and not has_body:
            tail = (stderr.strip() or stdout.strip())[-500:]
            raise GrokCLIError(
                f"grok exited {proc.returncode}{(': ' + tail) if tail else ''}",
                "exit",
            )
        if not has_body:
            raise GrokCLIError("grok returned empty output", "empty")
        return payload
    finally:
        try:
            shutil.rmtree(prompt_dir, ignore_errors=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_client():
    """
    Legacy no-op. Previously returned xAI SDK Client.
    Kept so old imports do not crash; prefer chat_create().
    """
    raise RuntimeError(
        "get_client() removed — Mina uses headless Grok Build CLI via chat_create(). "
        "See src/application/infra/client.py."
    )


def chat_create(**kwargs) -> _CompatResponse:
    """
    OpenAI-compatible chat completion via headless `grok` (Kaiya oneshot pattern).

    Accepts the same kwargs as openai.chat.completions.create() and returns
    an object with choices[0].message.content / .tool_calls and .usage.
    """
    model: str = kwargs.pop("model", MODEL)
    raw_messages: list[dict] = kwargs.pop("messages", []) or []
    raw_tools: list[dict] = kwargs.pop("tools", None) or []
    kwargs.pop("tool_choice", None)
    kwargs.pop("temperature", None)  # CLI has no temperature
    kwargs.pop("max_tokens", None)   # CLI has no max_tokens
    response_format = kwargs.pop("response_format", None)
    reasoning_effort: Optional[str] = kwargs.pop("reasoning_effort", None)
    kwargs.pop("stream", None)
    # Discard remaining unknown kwargs
    kwargs.clear()

    want_tools = bool(raw_tools)
    prompt = _build_prompt(raw_messages, raw_tools if want_tools else None)

    json_schema: dict | None = None
    if want_tools:
        json_schema = _TOOL_CALL_SCHEMA
    elif response_format:
        # Call sites request JSON; constrain to an object when type is json_object.
        # (Some sites expect a top-level array — they parse freeform text themselves,
        # so only force a schema for the common object case and leave arrays freeform.)
        rf_type = response_format if isinstance(response_format, str) else (
            response_format.get("type") if isinstance(response_format, dict) else None
        )
        if rf_type == "json_object":
            # Soft constraint: object. Nested shape is guided by the system prompt.
            json_schema = {"type": "object"}

    payload = run_grok_oneshot(
        prompt,
        json_schema=json_schema,
        reasoning_effort=reasoning_effort,
        model=model,
        max_turns=1,
    )

    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None

    if want_tools:
        content, tool_calls = _parse_tool_envelope(payload)
        return _CompatResponse(content or "", tool_calls, usage, raw=payload)

    # Prefer structuredOutput dump for json_object calls when text is empty
    text = _extract_text(payload)
    if not text and isinstance(payload.get("structuredOutput"), dict):
        text = json.dumps(payload["structuredOutput"], ensure_ascii=False)
    if not text:
        raise GrokCLIError("grok returned empty text", "empty")
    return _CompatResponse(text, None, usage, raw=payload)
