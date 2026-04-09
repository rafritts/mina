"""
Search tools for Mina — web search (Brave) and X/Twitter search.

Both tools are available in all contexts (conversation and heartbeat free time).
Mina can use these to look up current events, find memes, see what's trending,
satisfy her own curiosity — anything a person with internet access would do.

Required env vars:
  BRAVE_API_KEY     — Brave Search API key (https://api.search.brave.com)
  X_BEARER_TOKEN    — X/Twitter API v2 bearer token
"""
import json
import os

import requests

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_X_SEARCH_ENDPOINT = "https://api.twitter.com/2/tweets/search/recent"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web. Use this to look up current events, news, topics you're "
                "curious about, or anything you'd normally google. Returns titles, snippets, "
                "and URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for.",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 10).",
                    },
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
                "Search X (formerly Twitter) for recent posts. Use this to find out what "
                "people are talking about, trending memes, reactions to events, hot takes. "
                "Returns recent tweet text and authors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (supports X search operators like lang:en, -is:retweet).",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of tweets to return (default 10, max 20).",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_web_search(args: dict) -> str:
    query = args.get("query", "").strip()
    count = min(int(args.get("count", 5)), 10)

    if not query:
        return "[web_search: no query provided]"
    if not BRAVE_API_KEY:
        return "[web_search: BRAVE_API_KEY not set]"

    try:
        resp = requests.get(
            _BRAVE_ENDPOINT,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
            params={"q": query, "count": count},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"[web_search error: {e}]"

    results = data.get("web", {}).get("results", [])
    if not results:
        return f"[web_search: no results for '{query}']"

    lines = [f"Web results for: {query}\n"]
    for r in results[:count]:
        title = r.get("title", "")
        desc = r.get("description", "")
        url = r.get("url", "")
        lines.append(f"**{title}**\n{desc}\n{url}\n")

    return "\n".join(lines).strip()


def handle_x_search(args: dict) -> str:
    query = args.get("query", "").strip()
    count = min(int(args.get("count", 10)), 20)

    if not query:
        return "[x_search: no query provided]"
    if not X_BEARER_TOKEN:
        return "[x_search: X_BEARER_TOKEN not set]"

    try:
        resp = requests.get(
            _X_SEARCH_ENDPOINT,
            headers={"Authorization": f"Bearer {X_BEARER_TOKEN}"},
            params={
                "query": query,
                "max_results": count,
                "tweet.fields": "created_at,author_id,public_metrics",
                "expansions": "author_id",
                "user.fields": "username,name",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"[x_search error: {e}]"

    tweets = data.get("data", [])
    if not tweets:
        return f"[x_search: no results for '{query}']"

    # Build username lookup from includes
    users = {
        u["id"]: u
        for u in data.get("includes", {}).get("users", [])
    }

    lines = [f"X results for: {query}\n"]
    for t in tweets[:count]:
        author = users.get(t.get("author_id", ""), {})
        name = author.get("name", "?")
        username = author.get("username", "?")
        text = t.get("text", "")
        metrics = t.get("public_metrics", {})
        likes = metrics.get("like_count", 0)
        lines.append(f"@{username} ({name}) ❤️{likes}\n{text}\n")

    return "\n".join(lines).strip()


def call_search_tool(name: str, args: dict) -> str:
    """Dispatcher for search tools. Returns result string."""
    if name == "web_search":
        return handle_web_search(args)
    elif name == "x_search":
        return handle_x_search(args)
    return f"[unknown search tool: {name}]"
