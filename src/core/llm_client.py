"""Ollama LLM client (OpenAI-compatible API), as a process-wide singleton.

All model calls in the project go through here. Local only — Ollama at
``OLLAMA_BASE_URL``. See spec §11. Used by text-to-SQL, chart spec, intent
routing and summarization.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from openai import OpenAI

from src.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_llm_client() -> OpenAI:
    s = get_settings()
    logger.info("Creating Ollama client at %s (model=%s)", s.ollama_base_url, s.ollama_model)
    # Ollama ignores the API key but the OpenAI SDK requires a non-empty value.
    return OpenAI(base_url=s.ollama_base_url, api_key="ollama")


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.1,
    json_mode: bool = False,
) -> str:
    """Run a chat completion and return the assistant text.

    Args:
        messages: OpenAI-style message dicts.
        temperature: low by default (0.1) for SQL/classification determinism.
        json_mode: request a JSON object response (structured output).
    """
    s = get_settings()
    client = get_llm_client()
    kwargs: dict = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(
        model=s.ollama_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        **kwargs,
    )
    return response.choices[0].message.content or ""
