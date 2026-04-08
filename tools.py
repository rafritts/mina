import json
import math
from datetime import datetime, timezone


# --- tool implementations ---

def get_current_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def calculate(expression: str) -> str:
    # eval is fine for a quick experiment; don't ship this
    try:
        result = eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi, "e": math.e})
        return str(result)
    except Exception as exc:
        return f"Error: {exc}"


def get_weather(location: str) -> str:
    # fake stub — swap for a real API if you want
    return f"The weather in {location} is sunny and 22°C."


# --- dispatch ---

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Returns the current UTC date and time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluates a mathematical expression and returns the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "A Python math expression, e.g. '2 ** 10' or 'sqrt(144)'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Returns current weather for a given location (stubbed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or region name"}
                },
                "required": ["location"],
            },
        },
    },
]

_REGISTRY = {
    "get_current_time": lambda args: get_current_time(),
    "calculate": lambda args: calculate(args["expression"]),
    "get_weather": lambda args: get_weather(args["location"]),
}


def call_tool(name: str, arguments: str) -> str:
    args = json.loads(arguments) if arguments else {}
    handler = _REGISTRY.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    return handler(args)
