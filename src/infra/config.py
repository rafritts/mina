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
RUN_DIR = os.path.join(REPO_ROOT, "run")

# Canonical file paths
STATE_FILE       = os.path.join(RUN_DIR, "state.json")
CONFIG_FILE      = os.path.join(REPO_ROOT, "config.json")
HISTORY_FILE         = os.path.join(RUN_DIR, "conversation.json")   # kept for migration detection
DECODER_WINDOW_FILE  = os.path.join(RUN_DIR, "decoder_window.json")
LAST_ACTIVE_FILE = os.path.join(PROJECT_ROOT, ".last_user_active")
ADMIN_FILE       = os.path.join(RUN_DIR, "ADMIN_INSTRUCTIONS.md")
PAUSED_FLAG      = os.path.join(RUN_DIR, ".paused")
INJECT_FILE      = os.path.join(RUN_DIR, "subconscious_inject.md")
OUTBOX_FILE          = os.path.join(RUN_DIR, "outbox.jsonl")
OVERDOSE_TIMER_FILE  = os.path.join(RUN_DIR, "overdose_timer.json")
FOLLOWUP_QUEUE_FILE  = os.path.join(RUN_DIR, "followup_queue.json")
# ---------------------------------------------------------------------------
# Provider selection — flip USE_OLLAMA to run locally via Ollama.
# ---------------------------------------------------------------------------
USE_OLLAMA = False

_GROK_MODEL   = "grok-4-1-fast-reasoning"
_GROK_URL     = "https://api.x.ai/v1"
_GROK_KEY     = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-placeholder"))

#_OLLAMA_MODEL = "gemma4:e4b-it-bf16"
_OLLAMA_MODEL = "gemma4:31b"
_OLLAMA_URL   = "http://localhost:11434/v1"
_OLLAMA_KEY   = "ollama"

# Extra options passed to Ollama on every request (ignored when USE_OLLAMA=False).
# num_ctx: context window size. kv_cache_type: f16 / q8_0 / q4_0. num_gpu: GPU layers.
OLLAMA_OPTIONS: dict = {
    "num_ctx": 24000,
    "num_gpu": 999,
    "kv_cache_type": "f16",
}

MODEL    = _OLLAMA_MODEL if USE_OLLAMA else os.getenv("MODEL",    _GROK_MODEL)
BASE_URL = _OLLAMA_URL   if USE_OLLAMA else os.getenv("BASE_URL", _GROK_URL)
API_KEY  = _OLLAMA_KEY   if USE_OLLAMA else _GROK_KEY

OLLAMA_BASE_URL = _OLLAMA_URL  # convenience export

# Per-role model overrides — each falls back to MODEL if not set
ENCODER_MODEL = os.getenv("ENCODER_MODEL", MODEL)
#DECODER_MODEL = os.getenv("DECODER_MODEL", "grok-4.20-0309-reasoning")
DECODER_MODEL = os.getenv("DECODER_MODEL", MODEL)
CONTEXT_MODEL = os.getenv("CONTEXT_MODEL", MODEL)


def load_config() -> dict:
    """Load config.json. Returns empty dict on missing or invalid file."""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
