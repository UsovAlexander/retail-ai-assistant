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
    # When a follow-up was rewritten into a self-contained question, the
    # rewritten form (for transparency in the UIs and for interface history).
    resolved_question: str | None = None


# One dialogue turn as the interfaces remember it: (question, generated SQL).
HistoryTurn = tuple[str, str | None]


def ask(question: str, history: "list[HistoryTurn] | None" = None) -> "AssistantResponse":
    """Public core entry point: ``core.ask(question) -> AssistantResponse``.

    ``history`` — recent turns ``(question, sql)`` from the calling interface;
    used to rewrite follow-ups («добавь …», «а по месяцам») into self-contained
    questions. Lazy import keeps the orchestrator (which imports this module)
    free of a circular dependency. See [[Architecture]].
    """
    from src.core.orchestrator import ask as _ask

    return _ask(question, history)
