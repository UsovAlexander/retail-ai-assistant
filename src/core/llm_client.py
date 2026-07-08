"""LLM client with switchable backends (local Ollama / external / auto).

All model calls in the project go through :func:`chat`. Backends (config
``LLM_BACKEND``):

- ``local``    — Ollama at ``OLLAMA_BASE_URL`` (default; keeps the system fully
  local — the spec's air-gapped principle).
- ``external`` — an external OpenAI-compatible endpoint (``EXTERNAL_LLM_*``),
  e.g. to benchmark against a stronger model.
- ``auto``     — try external first, fall back to local on any error / rate
  limit / quota exhaustion (useful in prod when the external quota runs out).

Both backends use the OpenAI SDK, so any OpenAI-compatible provider works
(OpenAI, Groq, Anthropic-compat, OpenRouter, ...). See [[Architecture]].
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Iterator

from openai import OpenAI

from src.config import get_settings

logger = logging.getLogger(__name__)

# Per-request backend override (e.g. a desktop UI toggle) — takes precedence
# over LLM_BACKEND but below an explicit ``backend=`` argument to chat().
_backend_override: ContextVar[str | None] = ContextVar("llm_backend_override", default=None)


@contextmanager
def use_backend(backend: str | None) -> Iterator[None]:
    """Temporarily force a backend for all ``chat()`` calls in this context.

    Used by interfaces to let the user compare local vs external per request:
    ``with use_backend("external"): resp = core.ask(q)``. ``None`` = no override.
    """
    token = _backend_override.set(backend)
    try:
        yield
    finally:
        _backend_override.reset(token)


def resolved_backend(explicit: str | None = None) -> str:
    """Resolve the active backend: explicit arg > context override > config."""
    return (explicit or _backend_override.get() or get_settings().llm_backend).lower()


@lru_cache(maxsize=1)
def _local_client() -> OpenAI:
    s = get_settings()
    # Ollama ignores the key, but the SDK requires a non-empty value.
    return OpenAI(base_url=s.ollama_base_url, api_key="ollama")


@lru_cache(maxsize=1)
def _external_client() -> OpenAI:
    s = get_settings()
    if not s.external_configured:
        raise RuntimeError(
            "External LLM backend is not configured — set EXTERNAL_LLM_BASE_URL, "
            "EXTERNAL_LLM_API_KEY and EXTERNAL_LLM_MODEL in .env."
        )
    return OpenAI(base_url=s.external_llm_base_url, api_key=s.external_llm_api_key)


def _call(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    json_mode: bool,
) -> str:
    kwargs: dict = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        **kwargs,
    )
    return response.choices[0].message.content or ""


def active_model_label(backend: str | None = None) -> str:
    """Human-readable label of the active backend/model (for eval reports/logs)."""
    s = get_settings()
    b = resolved_backend(backend)
    if b == "local":
        return f"local:{s.ollama_model}"
    if b == "external":
        return f"external:{s.external_llm_model}"
    if s.external_configured:
        return f"auto(external:{s.external_llm_model} → local:{s.ollama_model})"
    return f"auto(local:{s.ollama_model})"


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.1,
    json_mode: bool = False,
    backend: str | None = None,
) -> str:
    """Run a chat completion via the configured (or overridden) backend.

    Args:
        messages: OpenAI-style message dicts.
        temperature: low by default (0.1) for SQL/classification determinism.
        json_mode: request a JSON object response (structured output).
        backend: override ``LLM_BACKEND`` for this call (``local``/``external``/``auto``).
    """
    s = get_settings()
    backend = resolved_backend(backend)

    if backend == "external":
        return _call(_external_client(), s.external_llm_model, messages, temperature, json_mode)

    if backend == "auto" and s.external_configured:
        try:
            return _call(_external_client(), s.external_llm_model, messages, temperature, json_mode)
        except Exception as exc:  # noqa: BLE001 - fall back to local on any failure
            logger.warning(
                "External LLM failed (%s: %s) — falling back to local Ollama.",
                type(exc).__name__, str(exc)[:160],
            )

    # local, or auto with no external configured, or auto after a fallback.
    return _call(_local_client(), s.ollama_model, messages, temperature, json_mode)
