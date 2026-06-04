"""
Project-wide paths and configuration.
"""
import json
import os
import time

# ── Directory roots ──────────────────────────────────────────────────────────

_SRC_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src/
REPO_ROOT  = os.path.dirname(_SRC_ROOT)                                   # repo root

IDENTITY_DIR      = os.path.join(REPO_ROOT, "identity")
MEMORY_DIR        = os.path.join(REPO_ROOT, "memory")
KAG_DIR           = os.path.join(MEMORY_DIR, "kag")
RAG_DIR           = os.path.join(MEMORY_DIR, "rag")
RELATIONSHIP_DIR  = os.path.join(MEMORY_DIR, "relationships")
RUN_DIR           = os.path.join(REPO_ROOT, "run")

CONSOLIDATION_STATE_FILE = os.path.join(RUN_DIR, "consolidation_state.json")
SIM_STATE_FILE           = os.path.join(RUN_DIR, "sim_state.json")
SLIDING_SEQ_FILE         = os.path.join(RUN_DIR, "sliding_seq.json")


def get_conversation_file() -> str:
    date_str = time.strftime("%Y-%m-%d")
    return os.path.join(RUN_DIR, f"conversation-{date_str}.jsonl")


# ── LLM configuration ────────────────────────────────────────────────────────

MODEL         = os.getenv("MODEL",         "grok-4.3")
CONTEXT_MODEL = os.getenv("CONTEXT_MODEL", "grok-4.3")  # cheaper pillar calls
BASE_URL      = os.getenv("BASE_URL",      "https://api.x.ai/v1")
API_KEY       = os.getenv("XAI_API_KEY",   os.getenv("OPENAI_API_KEY", "sk-placeholder"))


# ── Runtime config (config.json) ─────────────────────────────────────────────

_CONFIG_FILE = os.path.join(REPO_ROOT, "config.json")


def load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_big5() -> dict[str, float]:
    """Return Big 5 trait values (0–100 scale) from config.json. Defaults to Mina's canonical vector."""
    cfg = load_config()
    defaults = {
        "openness":          72.0,
        "conscientiousness": 55.0,
        "extraversion":      48.0,
        "agreeableness":     68.0,
        "neuroticism":       65.0,
    }
    user = cfg.get("big5", {})
    return {k: float(user.get(k, defaults[k])) for k in defaults}
