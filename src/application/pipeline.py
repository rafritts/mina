"""
Minimal response pipeline. Reads conversation history, calls the LLM, returns a reply.
"""
import asyncio
import json
import os
from pathlib import Path

from src.config.config import get_conversation_file, REPO_ROOT
from src.application.infra.client import chat_create, MODEL

_HISTORY_MAX = 40

_SYSTEM_PROMPT_FILE = os.path.join(REPO_ROOT, "identity", "MINA.md")


def _load_system_prompt() -> str:
    try:
        return Path(_SYSTEM_PROMPT_FILE).read_text()
    except FileNotFoundError:
        return "You are Mina, a warm and thoughtful AI companion."


def _load_history() -> list[dict]:
    path = get_conversation_file()
    entries = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return entries


def _save_message(role: str, content) -> None:
    path = get_conversation_file()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"role": role, "content": content}) + "\n")


def _call_llm(messages: list[dict]) -> str:
    resp = chat_create(model=MODEL, messages=messages, max_tokens=2048)
    return resp.choices[0].message.content or ""


async def run_turn(
    user_input: str,
    *,
    username: str = "User",
    images: list[tuple[str, str]] | None = None,
) -> tuple[str, list[str]]:
    history = _load_history()

    if images:
        content = [{"type": "text", "text": f"{username}: {user_input}"}]
        for b64, mime in images:
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    else:
        content = f"{username}: {user_input}"

    _save_message("user", content)

    system = _load_system_prompt()
    recent = history[-(_HISTORY_MAX - 1):]
    messages = [{"role": "system", "content": system}] + recent + [{"role": "user", "content": content}]

    reply = await asyncio.to_thread(_call_llm, messages)

    _save_message("assistant", reply)

    return reply, []
