"""
LLM client singleton.

One place to swap the model or provider. All modules import get_client() or
chat_create() from here instead of constructing their own OpenAI instances.
"""
from typing import Optional
from openai import OpenAI
from .config import MODEL, BASE_URL, API_KEY, ENCODER_MODEL, DECODER_MODEL, CONTEXT_MODEL

__all__ = ["get_client", "chat_create", "MODEL", "BASE_URL", "API_KEY", "ENCODER_MODEL", "DECODER_MODEL", "CONTEXT_MODEL"]

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


def chat_create(**kwargs):
    """Thin wrapper around get_client().chat.completions.create()."""
    return get_client().chat.completions.create(**kwargs)
