"""
Per-turn file loggers.

  logs/context_window.log  — exact messages array sent to the API each turn
  logs/conversation.log    — clean user/Mina exchange only

Neither touches stdout; they write directly to their files so they stay
completely separate from mina.log.
"""
import json
import os
import re
import time

from dotenv import find_dotenv

_PROJECT_ROOT = os.path.dirname(find_dotenv(usecwd=True))
_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")

_CONTEXT_LOG = os.path.join(_LOG_DIR, "context_window.log")
_CONV_LOG     = os.path.join(_LOG_DIR, "conversation.log")

# Matches base64 image data URIs embedded in message content
_B64_RE = re.compile(r'(data:[^;]+;base64,)[A-Za-z0-9+/=]{64,}')


def _scrub_images(obj):
    """Recursively replace base64 image payloads with a short placeholder."""
    if isinstance(obj, str):
        return _B64_RE.sub(r'\1[... base64 image data omitted ...]', obj)
    if isinstance(obj, list):
        return [_scrub_images(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _scrub_images(v) for k, v in obj.items()}
    return obj


def _write(path: str, text: str) -> None:
    os.makedirs(_LOG_DIR, exist_ok=True)
    with open(path, "a", encoding="utf-8", buffering=1) as f:
        f.write(text)


def log_context_window(messages: list[dict]) -> None:
    """Dump the full API messages array exactly as sent."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 80
    lines = [f"\n{sep}", f"TURN  {ts}", sep]

    for msg in _scrub_images(messages):
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")

        # tool_call_id messages
        if "tool_call_id" in msg:
            lines.append(f"\n[TOOL RESULT  id={msg['tool_call_id']}]")
            lines.append(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2))
            continue

        lines.append(f"\n[{role}]")

        if isinstance(content, str):
            lines.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "text":
                        lines.append(block.get("text", ""))
                    elif btype == "image_url":
                        url = block.get("image_url", {}).get("url", "")
                        lines.append(_B64_RE.sub(r'\1[... base64 image data omitted ...]', url))
                    else:
                        lines.append(json.dumps(block, ensure_ascii=False))
                else:
                    lines.append(str(block))
        else:
            lines.append(json.dumps(content, ensure_ascii=False, indent=2))

        # Tool calls (assistant messages)
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            lines.append(f"  [TOOL CALL  {fn.get('name')}  id={tc.get('id')}]")
            try:
                args = json.loads(fn.get("arguments", "{}"))
                lines.append("  " + json.dumps(args, ensure_ascii=False, indent=2).replace("\n", "\n  "))
            except Exception:
                lines.append(f"  {fn.get('arguments')}")

    lines.append(f"\n{sep}\n")
    _write(_CONTEXT_LOG, "\n".join(lines))


def log_conversation(username: str, user_input: str, reply: str) -> None:
    """Append one exchange to the clean conversation log."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    _write(_CONV_LOG, f"[{ts}] {username}: {user_input}\n")
    if reply:
        _write(_CONV_LOG, f"[{ts}] Mina: {reply}\n")
    _write(_CONV_LOG, "\n")
