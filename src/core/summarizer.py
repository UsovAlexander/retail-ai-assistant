"""Final analytical summary in Russian (spec §5.5).

Given the SQL result (first N rows), produce 2–4 sentences of conclusions —
trends, leaders, anomalies — not a row-by-row retelling.
"""

from __future__ import annotations

import json
import logging

from src.config import PROMPTS_DIR
from src.core.llm_client import chat

logger = logging.getLogger(__name__)

SUMMARY_ROWS = 50  # rows shown to the model (spec §5.5)


def summarize(question: str, sql: str, columns: list[str], rows: list[dict]) -> str:
    """Return a short Russian analytical summary of the result set."""
    if not rows:
        return "По вашему запросу данные не найдены."

    system = (PROMPTS_DIR / "summarize.txt").read_text(encoding="utf-8")
    preview = rows[:SUMMARY_ROWS]
    user = (
        f"ВОПРОС: {question}\n"
        f"SQL: {sql}\n"
        f"КОЛОНКИ: {columns}\n"
        f"РЕЗУЛЬТАТ (первые {len(preview)} строк из {len(rows)}):\n"
        f"{json.dumps(preview, ensure_ascii=False, default=str)}\n\n"
        "Вывод:"
    )
    return chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3,
    ).strip()
