"""Agent orchestrator: intent routing + the ``ask()`` entry point (spec §5.1).

Flow: classify intent (structured JSON) → for data intents run text-to-SQL,
summarize, and attach a chart or Excel artifact as requested. The core is
interface-agnostic and returns an :class:`AssistantResponse`. See [[Architecture]].
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from src.config import PROMPTS_DIR
from src.core import AssistantResponse
from src.core.chart_builder import build_chart, decide_chart_spec
from src.core.excel_exporter import ROW_WARN_THRESHOLD, export_to_excel
from src.core.llm_client import chat
from src.core.sql_generator import generate_sql
from src.core.summarizer import summarize

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 50

Intent = Literal["sql_query", "sql_with_chart", "sql_with_excel", "chitchat"]

FALLBACK_CHITCHAT = (
    "Привет! Я аналитический ассистент розничной сети. Могу считать выручку, "
    "сравнивать магазины и сотрудников, показывать план и факт, строить графики "
    "и выгружать данные в Excel. Спросите, например: «выручка по городам за март»."
)
SQL_FAILURE_TEXT = (
    "Не удалось построить корректный SQL-запрос по вашему вопросу. "
    "Попробуйте переформулировать его точнее."
)
ERROR_TEXT = "Произошла внутренняя ошибка при обработке запроса."


class IntentResult(BaseModel):
    intent: Intent
    reply: str = ""


def classify(question: str) -> IntentResult:
    """Classify the question into one intent (structured JSON, temp 0.1)."""
    system = (PROMPTS_DIR / "intent_router.txt").read_text(encoding="utf-8")
    raw = chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": question}],
        temperature=0.1,
        json_mode=True,
    )
    try:
        return IntentResult.model_validate_json(raw)
    except ValidationError as exc:
        # Default to a plain data query — the safest useful behavior.
        logger.warning("Intent parse failed (%s); defaulting to sql_query. Raw: %s", exc, raw[:150])
        return IntentResult(intent="sql_query")


def ask(question: str) -> AssistantResponse:
    """Answer a natural-language question. Never raises — errors go in the response."""
    logger.info("ask(): %s", question)
    try:
        intent = classify(question)
        logger.info("intent = %s", intent.intent)

        if intent.intent == "chitchat":
            return AssistantResponse(text=intent.reply or FALLBACK_CHITCHAT)

        sql_result = generate_sql(question)
        if not sql_result.ok:
            return AssistantResponse(
                text=SQL_FAILURE_TEXT, sql=sql_result.sql, error=sql_result.error
            )

        summary = summarize(question, sql_result.sql, sql_result.columns, sql_result.rows)
        response = AssistantResponse(
            text=summary,
            sql=sql_result.sql,
            table_preview=sql_result.rows[:PREVIEW_ROWS],
        )

        if intent.intent == "sql_with_chart":
            spec = decide_chart_spec(question, sql_result.columns, sql_result.rows)
            if spec is not None:
                try:
                    response.chart_path = build_chart(sql_result.rows, spec)
                except Exception as exc:  # noqa: BLE001 - chart is best-effort
                    logger.warning("Chart build failed: %s", exc)

        elif intent.intent == "sql_with_excel":
            response.excel_path = export_to_excel(sql_result.rows, sql_result.columns)
            if len(sql_result.rows) > ROW_WARN_THRESHOLD:
                response.text += (
                    f"\n\n⚠️ В выгрузке {len(sql_result.rows):,} строк — "
                    "файл может открываться медленно."
                )

        return response

    except Exception as exc:  # noqa: BLE001 - orchestrator must not raise
        logger.exception("ask() failed")
        return AssistantResponse(text=ERROR_TEXT, error=str(exc))
