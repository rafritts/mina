"""
Project-wide constants — paths and LLM env vars.
"""
import os
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src/
REPO_ROOT    = os.path.dirname(PROJECT_ROOT)                                 # repo root

RUN_DIR = os.path.join(REPO_ROOT, "run")

# LLM configuration
MODEL    = os.getenv("MODEL",    "grok-4-1-fast-reasoning")
BASE_URL = os.getenv("BASE_URL", "https://api.x.ai/v1")
API_KEY  = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-placeholder"))


def get_conversation_file() -> str:
    date_str = time.strftime("%Y-%m-%d")
    return os.path.join(RUN_DIR, f"conversation-{date_str}.jsonl")
