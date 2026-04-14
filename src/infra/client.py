"""
LLM client singleton + chat_create() wrapper.

Use chat_create() at all call sites instead of get_client().chat.completions.create().
When USE_OLLAMA is True, chat_create() automatically injects OLLAMA_OPTIONS from
config.py as extra_body — so num_ctx, kv_cache_type, num_gpu, etc. are applied
without touching individual call sites.
"""
from typing import Optional
from openai import OpenAI
from .config import MODEL, BASE_URL, API_KEY, ENCODER_MODEL, DECODER_MODEL, CONTEXT_MODEL, USE_OLLAMA, OLLAMA_OPTIONS

__all__ = [
    "get_client", "chat_create",
    "MODEL", "BASE_URL", "API_KEY", "ENCODER_MODEL", "DECODER_MODEL", "CONTEXT_MODEL",
]

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


def chat_create(**kwargs):
    """Drop-in replacement for get_client().chat.completions.create(**kwargs).

    When USE_OLLAMA is True, merges ollama_options from config.json into
    extra_body so per-model tuning (context window, KV cache quant, GPU layers)
    is applied transparently.
    """
    if USE_OLLAMA and OLLAMA_OPTIONS:
        # Caller-supplied extra_body takes precedence over config defaults
        kwargs["extra_body"] = {**OLLAMA_OPTIONS, **kwargs.get("extra_body", {})}
    return get_client().chat.completions.create(**kwargs)
