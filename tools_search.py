"""
Search tools for Mina — web and X search via xAI live search (Responses API).

Both tools make a focused sub-call to Grok with xAI's native server-side search.
No external API keys needed beyond XAI_API_KEY.
"""
import os
from openai import OpenAI

_BASE_URL = os.getenv("BASE_URL", "https://api.x.ai/v1")
_API_KEY = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
_MODEL = "grok-3-latest"

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=_API_KEY, base_url=_BASE_URL)
    return _client


# ---------------------------------------------------------------------------
# Tool definitions (offered to Mina's main LLM)
# ---------------------------------------------------------------------------

SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information, news, topics you're curious about, "
                "anything you'd normally google. Returns a synthesized summary with sources."
            ),
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
            "description": (
                "Search X (Twitter) for recent posts. Use to find what people are talking "
                "about, trending memes, reactions, hot takes. Returns recent post content."
            ),
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


# ---------------------------------------------------------------------------
# Handlers — sub-call to Grok via Responses API with native search tools
# ---------------------------------------------------------------------------

def handle_web_search(args: dict) -> str:
    query = args.get("query", "").strip()
    if not query:
        return "[web_search: no query provided]"
    try:
        response = _get_client().responses.create(
            model=_MODEL,
            tools=[{"type": "web_search"}],
            input=query,
        )
        return response.output_text or "[web_search: no results]"
    except Exception as e:
        return f"[web_search error: {e}]"


def handle_x_search(args: dict) -> str:
    query = args.get("query", "").strip()
    if not query:
        return "[x_search: no query provided]"
    try:
        response = _get_client().responses.create(
            model=_MODEL,
            tools=[{"type": "x_search"}],
            input=query,
        )
        return response.output_text or "[x_search: no results]"
    except Exception as e:
        return f"[x_search error: {e}]"


def call_search_tool(name: str, args: dict) -> str:
    if name == "web_search":
        return handle_web_search(args)
    elif name == "x_search":
        return handle_x_search(args)
    return f"[unknown search tool: {name}]"
