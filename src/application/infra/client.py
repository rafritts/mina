"""
LLM client — headless Grok Build CLI (same pattern as Kaiya).

All modules import chat_create() from here. Spawns `grok` with --prompt-file
(never puts large prompts on argv — Linux ARG_MAX). CLI auth only: never
passes XAI_API_KEY / OpenAI keys into the child.

Oneshots set GROK_HOME to ~/.mina/grok (override: MINA_GROK_HOME) so session
transcripts do not pollute the interactive ~/.grok tree. Auth/config are
symlinked from ~/.grok. Each completed oneshot session is deleted afterward
(Grok Build has no ephemeral flag).

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
from typing import Any

from src.application.infra.plain_text import strip_image_markup
from src.config.config import MODEL, BASE_URL, API_KEY, load_reasoning_effort

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


def oneshot_grok_home() -> Path:
    """
    Mina-only Grok data dir for headless oneshots.

    Interactive `grok` still uses ~/.grok. Only the child process env gets
    GROK_HOME pointed here so session JSONL piles up under ~/.mina, not in
    the user's main session browser.
    """
    if os.getenv("MINA_GROK_HOME"):
        d = Path(os.environ["MINA_GROK_HOME"]).expanduser().resolve()
    else:
        d = Path.home() / ".mina" / "grok"
    d.mkdir(parents=True, exist_ok=True)
    _bootstrap_mina_grok_home(d)
    return d


def _user_grok_home() -> Path:
    """Where interactive Grok keeps auth/config (not Mina's isolated home)."""
    raw = os.getenv("GROK_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".grok"


def _link_or_copy(src: Path, dst: Path) -> None:
    """Ensure dst provides src's content without clobbering a real local file."""
    if not src.is_file():
        return
    try:
        if dst.is_symlink():
            if dst.resolve() == src.resolve():
                return
            dst.unlink()
        elif dst.exists():
            return  # user-supplied file in MINA_GROK_HOME — leave it
        dst.symlink_to(src)
    except OSError:
        try:
            if dst.is_symlink() or not dst.exists():
                shutil.copy2(src, dst)
        except OSError:
            pass


def _bootstrap_mina_grok_home(mina_home: Path) -> None:
    """Share CLI login + config from the real Grok home; keep sessions local."""
    user = _user_grok_home()
    if user.resolve() == mina_home.resolve():
        return
    for name in ("auth.json", "config.toml"):
        _link_or_copy(user / name, mina_home / name)
    (mina_home / "sessions").mkdir(parents=True, exist_ok=True)


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
    # Isolate session storage to Mina only — never touch interactive ~/.grok sessions.
    env["GROK_HOME"] = str(oneshot_grok_home())
    for key in ("XAI_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    return env


def _discard_oneshot_session(session_id: str | None, grok_home: Path) -> None:
    """
    Remove a headless oneshot session directory.

    Grok Build always persists sessions; there is no ephemeral flag. Delete
    after the JSON payload is in hand so Mina does not accumulate transcripts.
    """
    if not session_id or not isinstance(session_id, str):
        return
    sid = session_id.strip()
    if not sid or ".." in sid or "/" in sid or "\\" in sid:
        return
    sessions = grok_home / "sessions"
    if not sessions.is_dir():
        return
    try:
        groups = list(sessions.iterdir())
    except OSError:
        return
    for group in groups:
        if not group.is_dir():
            continue
        target = group / sid
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            return


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return strip_image_markup(content)
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
                continue
            else:
                parts.append(str(block))
        return strip_image_markup("\n".join(p for p in parts if p))
    return strip_image_markup(str(content))


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
        "You cannot invoke Grok Build shell/file tools. Put the full reply the user "
        "reads in content in the same object as any tool_calls. The host shows that "
        "text, then runs the tools. Never leave content empty.\n\n"
        + json.dumps(specs, indent=2)
    )


_NAME_CLOTHING_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "clothing": {"type": "string"},
    },
    "required": ["name", "clothing"],
}

_NAME_POSITION_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "position": {"type": "string"},
    },
    "required": ["name", "position"],
}

_WHEN_WHAT_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "when": {"type": "string"},
        "what": {"type": "string"},
    },
    "required": ["when", "what"],
}

# Mouth reply: voice + optional host tools + live scene snapshot (Kaiya pattern).
_MOUTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content": {
            "type": ["string", "null"],
            "description": (
                "What the user reads (Mina's voice). Always the full reply, including "
                "when tool_calls is non-empty. Alias: response_in_mina_voice."
            ),
        },
        "response_in_mina_voice": {
            "type": ["string", "null"],
            "description": "Alias for content — Mina's spoken/text reply.",
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
            "description": (
                "Host tool calls for this reply, in the same object as content. "
                "Empty array when there is no tool call. There is no image tool."
            ),
        },
        "scene_time": {
            "type": "string",
            "description": "Soft fiction Now (phase/day/place). Empty only for pure logistics.",
        },
        "timeline": {
            "type": "array",
            "items": _WHEN_WHAT_ITEM,
            "description": "Past→now beats that still matter for continuity (max ~12).",
        },
        "plans": {
            "type": "array",
            "items": _WHEN_WHAT_ITEM,
            "description": "Open future commitments relative to scene_time (max 6).",
        },
        "current_clothing_scene_members": {
            "type": "array",
            "items": _NAME_CLOTHING_ITEM,
            "description": "Full clothing/presentation snapshot of people in scene.",
        },
        "current_position_in_scene": {
            "type": "array",
            "items": _NAME_POSITION_ITEM,
            "description": "Full body-placement snapshot of people in scene.",
        },
    },
    "required": ["tool_calls"],
}

# Back-compat name used by older call sites.
_TOOL_CALL_SCHEMA = _MOUTH_SCHEMA


def _build_prompt(
    messages: list[dict],
    tools: list[dict] | None,
    *,
    mouth: bool = False,
) -> str:
    if mouth or tools:
        preamble = (
            "Follow the instructions exactly. Do not use Grok Build filesystem, shell, "
            "or web tools. Reply only with the structured JSON required by the schema."
        )
        body = _format_messages_body(messages)
        parts = [preamble, ""]
        if tools:
            parts.extend([_tools_section(tools), ""])
        elif mouth:
            parts.extend([
                "## Host tools\n"
                "No host tools this turn. Set tool_calls to []. "
                "You cannot send images. Do not write image markdown or image URLs. "
                "Put the user-facing reply in content (or response_in_mina_voice). "
                "Always include scene fields on the final reply.",
                "",
            ])
        parts.append(body)
        return "\n".join(parts)
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
    __slots__ = ("content", "tool_calls", "mouth")

    def __init__(
        self,
        content: str,
        tool_calls: list[_ToolCall] | None,
        mouth: dict | None = None,
    ):
        self.content = content
        self.tool_calls = tool_calls
        self.mouth = mouth  # full structured mouth object when present


class _Choice:
    __slots__ = ("message", "finish_reason")

    def __init__(
        self,
        content: str,
        tool_calls: list[_ToolCall] | None,
        mouth: dict | None = None,
    ):
        self.message = _Message(content, tool_calls, mouth)
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
        mouth: dict | None = None,
    ):
        self.choices = [_Choice(content, tool_calls, mouth)]
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


def _voice_from_mouth(data: dict) -> str:
    """User-facing voice from mouth JSON (content or response_in_mina_voice)."""
    for key in ("content", "response_in_mina_voice"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if val is not None and not isinstance(val, str) and val != "":
            return str(val)
    return ""


def _parse_tool_envelope(payload: dict) -> tuple[str, list[_ToolCall] | None, dict | None]:
    """
    Return (content, tool_calls, raw_mouth_dict) from structured mouth/tool output.
    raw_mouth_dict is the full parsed object when available (for scene fields).
    """
    so = payload.get("structuredOutput")
    data = so if isinstance(so, dict) else None
    if data is None:
        raw_text = _extract_text(payload).strip()
        if not raw_text:
            return "", None, None
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text, None, None
    if not isinstance(data, dict):
        return _extract_text(payload), None, None

    content = _voice_from_mouth(data)

    raw_tcs = data.get("tool_calls") or []
    if not isinstance(raw_tcs, list) or not raw_tcs:
        return content, None, data

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
    return content, tool_calls or None, data


def run_grok_oneshot(
    prompt: str,
    *,
    json_schema: dict | None = None,
    model: str | None = None,
    max_turns: int = 1,
    timeout_sec: float | None = None,
) -> dict:
    """
    Spawn headless grok for a single completion. Returns parsed JSON object.
    Uses --prompt-file always (never --single argv) to avoid E2BIG.
    Child GROK_HOME is Mina-scoped; session dir is deleted after success.
    """
    cwd = oneshot_cwd()
    grok_home = oneshot_grok_home()
    bin_path = grok_bin()
    timeout = timeout_sec if timeout_sec is not None else _timeout_sec()
    child_env = _child_env()

    prompt_dir = tempfile.mkdtemp(prefix="mina-oneshot-")
    prompt_file = os.path.join(prompt_dir, "prompt.txt")
    try:
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)

        # Tool strip: `--tools ""` is a no-op (CLI treats empty as "use
        # defaults" and leaves the full Build toolset). Real empty toolset:
        # allow one dummy, then deny it plus always-on MCP meta-tools.
        # Host tools stay prompt+json-schema only (not CLI builtins).
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
            "--tools", "todo_write",
            "--disallowed-tools", "todo_write,search_tool,use_tool,Agent",
        ]
        if json_schema is not None:
            args.extend(["--json-schema", json.dumps(json_schema)])
        # One knob for every call: config.json reasoning_effort (default low).
        args.extend(["--reasoning-effort", load_reasoning_effort()])
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
                env=child_env,
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

        # Drop the persisted oneshot session (payload already parsed in memory).
        sid = payload.get("sessionId") or payload.get("session_id")
        _discard_oneshot_session(sid if isinstance(sid, str) else None, grok_home)
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

    Extra kwargs:
      mouth=True — force Mina mouth schema (voice + scene + optional tool_calls)
                   even when tools are empty.
    """
    model: str = kwargs.pop("model", MODEL)
    raw_messages: list[dict] = kwargs.pop("messages", []) or []
    tools_arg = kwargs.pop("tools", None)
    raw_tools: list[dict] = tools_arg if isinstance(tools_arg, list) else []
    mouth: bool = bool(kwargs.pop("mouth", False))
    kwargs.pop("tool_choice", None)
    kwargs.pop("temperature", None)  # CLI has no temperature
    kwargs.pop("max_tokens", None)   # CLI has no max_tokens
    response_format = kwargs.pop("response_format", None)
    kwargs.pop("reasoning_effort", None)  # config.json, not per call
    kwargs.pop("stream", None)
    # Discard remaining unknown kwargs
    kwargs.clear()

    use_mouth = mouth or bool(raw_tools)
    prompt = _build_prompt(
        raw_messages,
        raw_tools if raw_tools else None,
        mouth=use_mouth,
    )

    json_schema: dict | None = None
    if use_mouth:
        json_schema = _MOUTH_SCHEMA
    elif response_format:
        # Call sites request JSON; constrain to an object when type is json_object.
        rf_type = response_format if isinstance(response_format, str) else (
            response_format.get("type") if isinstance(response_format, dict) else None
        )
        if rf_type == "json_object":
            json_schema = {"type": "object"}

    payload = run_grok_oneshot(
        prompt,
        json_schema=json_schema,
        model=model,
        max_turns=1,
    )

    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None

    if use_mouth:
        content, tool_calls, mouth_obj = _parse_tool_envelope(payload)
        return _CompatResponse(
            content or "", tool_calls, usage, raw=payload, mouth=mouth_obj
        )

    # Prefer structuredOutput dump for json_object calls when text is empty
    text = _extract_text(payload)
    if not text and isinstance(payload.get("structuredOutput"), dict):
        text = json.dumps(payload["structuredOutput"], ensure_ascii=False)
    if not text:
        raise GrokCLIError("grok returned empty text", "empty")
    return _CompatResponse(text, None, usage, raw=payload)
