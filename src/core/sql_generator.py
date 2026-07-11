"""Text-to-SQL with schema RAG + dynamic few-shot RAG.

Pipeline (spec §5.2, see [[Text_to_SQL]]):
  1. schema RAG — top-3 relevant tables from ``retail_schema``
  2. few-shot RAG — top-3 nearest ``question → SQL`` examples from ``retail_few_shot``
  3. prompt = system dialect rules + retrieved schema + examples + question
  4. Ollama → SQL
  5. validate (SELECT-only, forced LIMIT, no system tables) — see validator.py
  6. execute in ClickHouse; on error, retry with the error text (≤3 attempts)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from clickhouse_connect.driver.client import Client

from src.config import PROMPTS_DIR, get_settings
from src.core.llm_client import chat
from src.core.validator import SQLValidationError, validate_sql
from src.db import get_client
from src.vectorstore import client as vs

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
SCHEMA_TOP_K = 3
FEW_SHOT_TOP_K = 3


@dataclass
class SQLResult:
    """Outcome of the text-to-SQL pipeline for one question."""

    question: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    attempts: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.sql is not None


def _load_system_prompt() -> str:
    return (PROMPTS_DIR / "sql_system.txt").read_text(encoding="utf-8")


def _retrieve_schema(question: str) -> str:
    hits = vs.search(get_settings().qdrant_schema_collection, question, limit=SCHEMA_TOP_K)
    return "\n\n".join(h.payload["document"] for h in hits)


def _retrieve_few_shot(question: str) -> str:
    hits = vs.search(get_settings().qdrant_few_shot_collection, question, limit=FEW_SHOT_TOP_K)
    blocks = [f"Вопрос: {h.payload['question']}\nSQL: {h.payload['sql']}" for h in hits]
    return "\n\n".join(blocks)


def _build_user_content(
    question: str, schema: str, examples: str, prev_sql: str | None = None
) -> str:
    prev_block = ""
    if prev_sql:
        prev_block = (
            "PREVIOUS QUERY (the question below REFINES it):\n"
            f"{prev_sql}\n"
            "Modify the previous query: KEEP all its columns, filters, grouping "
            "and ORDER BY exactly as they are unless the question explicitly "
            "changes them; only add/change what is asked.\n\n"
        )
    return (
        f"SCHEMA (most relevant tables):\n{schema}\n\n"
        f"EXAMPLES (similar question → reference SQL):\n{examples}\n\n"
        f"{prev_block}"
        f"QUESTION: {question}\nSQL:"
    )


def _execute(client: Client, sql: str) -> tuple[list[str], list[dict]]:
    result = client.query(sql)
    columns = list(result.column_names)
    rows = [dict(zip(columns, row)) for row in result.result_rows]
    return columns, rows


def generate_sql(question: str, prev_sql: str | None = None) -> SQLResult:
    """Generate, validate and execute SQL for a question, with retry-on-error.

    ``prev_sql`` — the previous turn's query when the question is a follow-up
    refinement («добавь …», «включая …»): the model must extend that query
    (keeping columns/filters/ordering) instead of building a fresh one.
    """
    system = _load_system_prompt()
    schema = _retrieve_schema(question)
    examples = _retrieve_few_shot(question)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_user_content(question, schema, examples, prev_sql)},
    ]

    client = get_client(database=get_settings().ch_database)
    last_error: str | None = None
    last_sql: str | None = None
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            raw = chat(messages, temperature=0.1)
            logger.info("Attempt %d — raw model output: %s", attempt, raw.replace("\n", " ")[:200])

            try:
                sql = validate_sql(raw)
            except SQLValidationError as exc:
                last_error = f"validation: {exc}"
                logger.warning("Attempt %d rejected by validator: %s", attempt, exc)
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        f"That query was rejected: {exc}. "
                        "Return a corrected single read-only ClickHouse SELECT query. SQL only."
                    ),
                })
                continue

            last_sql = sql
            try:
                columns, rows = _execute(client, sql)
            except Exception as exc:  # noqa: BLE001 - surface CH error back to the model
                last_error = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                logger.warning("Attempt %d failed to execute: %s", attempt, last_error)
                messages.append({"role": "assistant", "content": sql})
                messages.append({
                    "role": "user",
                    "content": (
                        f"The query failed in ClickHouse with error: {last_error}. "
                        "Return a corrected ClickHouse SELECT query. SQL only."
                    ),
                })
                continue

            logger.info("Attempt %d succeeded (%d rows).", attempt, len(rows))
            return SQLResult(
                question=question, sql=sql, columns=columns, rows=rows,
                row_count=len(rows), attempts=attempt, error=None,
            )
    finally:
        client.close()

    return SQLResult(
        question=question, sql=last_sql, attempts=MAX_ATTEMPTS, error=last_error,
    )
