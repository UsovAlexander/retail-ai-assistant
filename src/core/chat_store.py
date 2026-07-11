"""Shared conversation history, stored in ClickHouse (`retail_demo.chat_history`).

Both interfaces log every completed exchange here, one row per Q&A turn.
The desktop UI renders past chats from this table — including Telegram ones.
The data generator preserves this table across regenerations (it recreates
only the six data tables).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.config import get_settings
from src.core import AssistantResponse
from src.db import get_client

logger = logging.getLogger(__name__)

PREVIEW_CAP = 50  # stored table_preview rows cap (matches orchestrator preview)

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS retail_demo.chat_history (
    ts DateTime DEFAULT now(),
    source LowCardinality(String),          -- 'desktop' | 'telegram'
    chat_id String,                          -- dialogue/session id within a source
    question String,
    resolved_question String,
    answer_text String,
    sql String,
    chart_path String,
    excel_path String,
    error String,
    table_preview String                     -- JSON array of preview rows
) ENGINE = MergeTree ORDER BY (source, chat_id, ts)
"""

COLUMNS = [
    "source", "chat_id", "question", "resolved_question", "answer_text",
    "sql", "chart_path", "excel_path", "error", "table_preview",
]


def ensure_table() -> None:
    client = get_client()
    try:
        client.command(TABLE_DDL)
    finally:
        client.close()


def log_turn(source: str, chat_id: str, question: str, resp: AssistantResponse) -> None:
    """Persist one completed exchange. Best-effort: never breaks the answer flow."""
    try:
        client = get_client(database=get_settings().ch_database)
        try:
            client.insert(
                "retail_demo.chat_history",
                [(
                    source, chat_id, question,
                    resp.resolved_question or "",
                    resp.text or "",
                    resp.sql or "",
                    str(resp.chart_path) if resp.chart_path else "",
                    str(resp.excel_path) if resp.excel_path else "",
                    resp.error or "",
                    json.dumps(resp.table_preview[:PREVIEW_CAP], ensure_ascii=False, default=str),
                )],
                column_names=COLUMNS,
            )
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_history insert failed: %s", exc)


def load_turns(source: str, chat_id: str) -> list[dict[str, Any]]:
    """All turns of one dialogue, chronological."""
    client = get_client(database=get_settings().ch_database)
    try:
        result = client.query(
            "SELECT ts, question, resolved_question, answer_text, sql, "
            "chart_path, excel_path, error, table_preview "
            "FROM chat_history WHERE source = %(s)s AND chat_id = %(c)s ORDER BY ts",
            parameters={"s": source, "c": chat_id},
        )
        cols = result.column_names
        return [dict(zip(cols, row)) for row in result.result_rows]
    finally:
        client.close()


def turn_to_response(turn: dict[str, Any]) -> AssistantResponse:
    """Rebuild an AssistantResponse from a stored turn (for rendering)."""
    from pathlib import Path

    try:
        preview = json.loads(turn.get("table_preview") or "[]")
    except json.JSONDecodeError:
        preview = []
    return AssistantResponse(
        text=turn.get("answer_text", ""),
        sql=turn.get("sql") or None,
        table_preview=preview,
        chart_path=Path(turn["chart_path"]) if turn.get("chart_path") else None,
        excel_path=Path(turn["excel_path"]) if turn.get("excel_path") else None,
        error=turn.get("error") or None,
        resolved_question=turn.get("resolved_question") or None,
    )


def list_chats(limit: int = 50) -> list[dict[str, Any]]:
    """All dialogues across sources: id, title (first question), last activity."""
    client = get_client(database=get_settings().ch_database)
    try:
        result = client.query(
            "SELECT source, chat_id, argMin(question, ts) AS title, "
            "max(ts) AS last_ts, count() AS turns "
            "FROM chat_history GROUP BY source, chat_id "
            f"ORDER BY last_ts DESC LIMIT {int(limit)}"
        )
        cols = result.column_names
        return [dict(zip(cols, row)) for row in result.result_rows]
    finally:
        client.close()


def delete_chat(source: str, chat_id: str) -> None:
    client = get_client(database=get_settings().ch_database)
    try:
        client.command(
            "DELETE FROM retail_demo.chat_history WHERE source = %(s)s AND chat_id = %(c)s",
            parameters={"s": source, "c": chat_id},
        )
    finally:
        client.close()


def build_history(source: str, chat_id: str, limit: int = 3) -> list[tuple[str, str | None]]:
    """Recent (question, sql) turns of a dialogue — for follow-up condensing."""
    turns = [
        t for t in load_turns(source, chat_id)
        if t.get("sql") and not t.get("error")
    ]
    return [
        (t["resolved_question"] or t["question"], t["sql"]) for t in turns[-limit:]
    ]
