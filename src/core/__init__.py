"""Assistant core: orchestrator, text-to-SQL, artifacts, summarizer (stages 4–6).

The core is interface-agnostic. Public entry point (stage 6):
``core.ask(question) -> AssistantResponse``. See [[Architecture]].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AssistantResponse:
    """Structured result returned by the core to any interface. See [[Architecture]]."""

    text: str
    sql: str | None = None
    table_preview: list[dict] = field(default_factory=list)
    chart_path: Path | None = None
    excel_path: Path | None = None
    error: str | None = None


def ask(question: str) -> "AssistantResponse":
    """Public core entry point: ``core.ask(question) -> AssistantResponse``.

    Lazy import keeps the orchestrator (which imports this module) free of a
    circular dependency. See [[Architecture]].
    """
    from src.core.orchestrator import ask as _ask

    return _ask(question)
