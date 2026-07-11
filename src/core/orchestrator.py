"""Agent orchestrator: intent routing + the ``ask()`` entry point (spec §5.1).

Flow: classify intent (structured JSON) → for data intents run text-to-SQL,
summarize, and attach a chart or Excel artifact as requested. The core is
interface-agnostic and returns an :class:`AssistantResponse`. See [[Architecture]].
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from src.config import PROMPTS_DIR
from src.core import AssistantResponse, HistoryTurn
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


MAX_HISTORY_TURNS = 3


def condense(question: str, history: list[HistoryTurn]) -> str:
    """Resolve a follow-up into a self-contained question using recent turns.

    The model classifies the message explicitly (followup true/false, JSON;
    the prompt carries few-shot examples of both classes). There is
    deliberately NO heuristic rollback here: length/marker guards twice rolled
    back honest «добавь …»/«отдельный график …» merges in live use, and a
    rollback yields garbage (context lost) while a rare wrong merge stays
    visible to the user via «🔎 Понял как: …» and is easy to correct.
    """
    system = (PROMPTS_DIR / "condense.txt").read_text(encoding="utf-8")
    turns = history[-MAX_HISTORY_TURNS:]
    lines = []
    for i, (q, sql) in enumerate(turns, 1):
        lines.append(f"Вопрос {i}: {q}")
        if sql:
            lines.append(f"SQL {i}: {sql}")
    user = (
        "ПРЕДЫДУЩИЙ ДИАЛОГ:\n" + "\n".join(lines) +
        f"\n\nНОВОЕ СООБЩЕНИЕ: {question}\n\nJSON:"
    )
    try:
        raw = chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.1,
            json_mode=True,
        )
        data = json.loads(raw)
        followup = bool(data.get("followup"))
        rewritten = str(data.get("question") or "").strip()
    except Exception as exc:  # noqa: BLE001 - best-effort step
        logger.warning("condense failed (%s) — using the raw question", exc)
        return question

    if not followup or not rewritten:
        return question
    return rewritten


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


def ask(question: str, history: list[HistoryTurn] | None = None) -> AssistantResponse:
    """Answer a natural-language question. Never raises — errors go in the response.

    ``history`` (recent ``(question, sql)`` turns from the interface) lets
    follow-ups like «добавь выполнение плана в %» be rewritten into
    self-contained questions before the stateless pipeline runs.
    """
    logger.info("ask(): %s", question)
    try:
        resolved = question
        if history:
            resolved = condense(question, history)
            if resolved.strip().lower() != question.strip().lower():
                logger.info("condensed follow-up -> %s", resolved)

        # Intent is classified on the ORIGINAL message: presentation verbs
        # («покажи график», «выгрузи в Excel») live in the user's own phrasing
        # and may be dropped by the condense rewrite.
        intent = classify(question)
        logger.info("intent = %s", intent.intent)

        resolved_out = resolved if resolved.strip().lower() != question.strip().lower() else None

        if intent.intent == "chitchat":
            return AssistantResponse(text=intent.reply or FALLBACK_CHITCHAT)

        sql_result = generate_sql(resolved)
        if not sql_result.ok:
            return AssistantResponse(
                text=SQL_FAILURE_TEXT, sql=sql_result.sql, error=sql_result.error,
                resolved_question=resolved_out,
            )

        summary = summarize(resolved, sql_result.sql, sql_result.columns, sql_result.rows)
        response = AssistantResponse(
            text=summary,
            sql=sql_result.sql,
            table_preview=sql_result.rows[:PREVIEW_ROWS],
            resolved_question=resolved_out,
        )

        if intent.intent == "sql_with_chart":
            spec = decide_chart_spec(resolved, sql_result.columns, sql_result.rows)
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
