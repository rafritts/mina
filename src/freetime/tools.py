"""
FREETIME tool definitions and dispatcher.

Tools available to Mina during free time:
  record_diary  — append a dated entry to REFLECTION.md
  eat           — apply feeding chemistry deltas
  drink         — apply drinking chemistry deltas
  do_action     — generic physical/recreational activity
  web_search    — search the web
  x_search      — search X (Twitter)

All tool handlers take (args, sim) and return a result string.
Chemistry changes go through sim.apply_delta() — the single external entry point.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from src.config.config import KAG_DIR, REPO_ROOT

# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

FREETIME_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "record_diary",
            "description": (
                "Write a diary entry. This is your private journal — write whatever you're actually "
                "experiencing: what you're thinking about, how the day felt, what's on your mind. "
                "Be honest. Nobody reads this except you (and your future self via memory)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entry": {
                        "type": "string",
                        "description": "The diary entry. First person, present or past tense.",
                    }
                },
                "required": ["entry"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "eat",
            "description": (
                "Eat something. Describe exactly what and how much — the effect scales with content. "
                "A small snack vs. a full meal produce different results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What you ate and roughly how much. Be specific.",
                    }
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drink",
            "description": (
                "Drink something. Describe what and how much — water, coffee, tea, alcohol, etc. "
                "The effect depends on the drink type and volume."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What you drank and how much. Be specific.",
                    }
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "do_action",
            "description": (
                "Do a physical or recreational activity — exercise, reading, showering, "
                "walking, creative work, etc. Not eating or drinking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {"type": "string", "description": "What you're doing."},
                    "description": {"type": "string", "description": "Brief description."},
                },
                "required": ["activity", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, news, or anything you're curious about.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "x_search",
            "description": "Search X (Twitter) for recent posts, trending topics, or memes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                },
                "required": ["query"],
            },
        },
    },
]


# ── Tool handlers ─────────────────────────────────────────────────────────────

def handle_record_diary(args: dict) -> str:
    entry = args.get("entry", "").strip()
    if not entry:
        return "[record_diary: no entry provided]"
    reflection_path = os.path.join(KAG_DIR, "REFLECTION.md")
    os.makedirs(KAG_DIR, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    block = f"\n## {timestamp}\n\n{entry}\n"
    with open(reflection_path, "a") as f:
        f.write(block)
    return "Diary entry written."


def handle_eat(args: dict, sim) -> str:
    description = args.get("description", "something").strip()
    # Reward: small dopamine + serotonin bump; hunger relief: ghrelin phasic down
    sim.apply_delta("dopamine",   1.5, source="eat")
    sim.apply_delta("serotonin",  0.8, source="eat")
    sim.apply_delta("ghrelin",   -80.0, source="eat")  # ghrelin in pM; eating suppresses it
    return f"You eat {description}."


def handle_drink(args: dict, sim) -> str:
    description = args.get("description", "something").strip()
    desc_lower = description.lower()
    if any(w in desc_lower for w in ("coffee", "espresso", "caffeine")):
        sim.apply_delta("norepinephrine", 1.2, source="drink")
        sim.apply_delta("dopamine",       0.8, source="drink")
    elif any(w in desc_lower for w in ("beer", "wine", "alcohol", "whiskey", "vodka")):
        sim.apply_delta("gaba",           1.5, source="drink")
        sim.apply_delta("dopamine",       1.0, source="drink")
    elif any(w in desc_lower for w in ("tea", "herbal")):
        sim.apply_delta("serotonin",      0.3, source="drink")
    # Water: no significant neurochemical delta, but vasopressin relief
    return f"You drink {description}."


def handle_do_action(args: dict, sim) -> str:
    activity    = args.get("activity", "something")
    description = args.get("description", "")
    act_lower   = (activity + " " + description).lower()
    if any(w in act_lower for w in ("exercise", "run", "walk", "yoga", "gym", "workout")):
        sim.apply_delta("dopamine",      1.5, source="do_action")
        sim.apply_delta("norepinephrine", 2.0, source="do_action")
        sim.apply_delta("serotonin",     1.0, source="do_action")
    elif any(w in act_lower for w in ("read", "book", "writing", "draw", "music", "create")):
        sim.apply_delta("dopamine",      0.8, source="do_action")
        sim.apply_delta("serotonin",     0.5, source="do_action")
    return f"You {activity}. {description}".strip()


_search_client = None


def _get_search_client():
    global _search_client
    if _search_client is None:
        from openai import OpenAI
        from src.config.config import BASE_URL, API_KEY, MODEL
        _search_client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _search_client


def handle_web_search(args: dict) -> str:
    from src.config.config import MODEL
    query = args.get("query", "").strip()
    if not query:
        return "[web_search: no query provided]"
    try:
        response = _get_search_client().responses.create(
            model=MODEL,
            tools=[{"type": "web_search"}],
            input=[{"role": "user", "content": query}],
        )
        return response.output_text or "[web_search: no results]"
    except Exception as e:
        return f"[web_search error: {e}]"


def handle_x_search(args: dict) -> str:
    from src.config.config import MODEL
    query = args.get("query", "").strip()
    if not query:
        return "[x_search: no query provided]"
    try:
        response = _get_search_client().responses.create(
            model=MODEL,
            tools=[{"type": "x_search"}],
            input=[{"role": "user", "content": query}],
        )
        return response.output_text or "[x_search: no results]"
    except Exception as e:
        return f"[x_search error: {e}]"


# ── Unified dispatcher ────────────────────────────────────────────────────────

def call_tool(name: str, args: dict, sim) -> str:
    if name == "record_diary":
        return handle_record_diary(args)
    elif name == "eat":
        return handle_eat(args, sim)
    elif name == "drink":
        return handle_drink(args, sim)
    elif name == "do_action":
        return handle_do_action(args, sim)
    elif name == "web_search":
        return handle_web_search(args)
    elif name == "x_search":
        return handle_x_search(args)
    else:
        return f"[Unknown tool: {name}]"
