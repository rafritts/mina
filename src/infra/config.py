"""
Project-wide constants — paths, config loader, and LLM env vars.

Single source of truth. All other modules import from here instead of
redefining _PROJECT_ROOT and _load_config() themselves.
"""
import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src/
REPO_ROOT    = os.path.dirname(PROJECT_ROOT)                                 # repo root

# Runtime directory — ephemeral files live under src/run/
RUN_DIR = os.path.join(PROJECT_ROOT, "run")

# Canonical file paths
STATE_FILE       = os.path.join(RUN_DIR, "state.json")
CONFIG_FILE      = os.path.join(REPO_ROOT, "config.json")
HISTORY_FILE     = os.path.join(RUN_DIR, "conversation.json")
LAST_ACTIVE_FILE = os.path.join(PROJECT_ROOT, ".last_user_active")
ADMIN_FILE       = os.path.join(RUN_DIR, "ADMIN_INSTRUCTIONS.md")
PAUSED_FLAG      = os.path.join(RUN_DIR, ".paused")
INJECT_FILE      = os.path.join(RUN_DIR, "subconscious_inject.md")
OUTBOX_FILE      = os.path.join(RUN_DIR, "outbox.jsonl")
OVERDOSE_TIMER_FILE = os.path.join(RUN_DIR, "overdose_timer.json")
PERSONALITY_FILE = os.path.join(REPO_ROOT, "personality.json")

# LLM configuration — read once at import time
MODEL    = os.getenv("MODEL",    "grok-4-1-fast-reasoning")
BASE_URL = os.getenv("BASE_URL", "https://api.x.ai/v1")
API_KEY  = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-placeholder"))


def load_config() -> dict:
    """Load config.json. Returns empty dict on missing or invalid file."""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
