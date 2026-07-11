"""Final analytical summary in Russian (spec §5.5).

Given the SQL result (first N rows), produce 2–4 sentences of conclusions —
trends, leaders, anomalies — not a row-by-row retelling.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re

from src.config import PROMPTS_DIR
from src.core.llm_client import chat

logger = logging.getLogger(__name__)

SUMMARY_ROWS = 50   # rows shown to the model (spec §5.5)
MAX_FACT_COLS = 3   # numeric columns covered by the verified-facts block


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_RU_MONTHS = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _humanize_label(value: object, col: str) -> str:
    """Turn a date label into a human period name based on the column grain.

    «2024-10-01» in a `quarter` column → «4-й квартал 2024»; in `month` →
    «октябрь 2024». Deterministic — the LLM repeatedly mislabeled period
    ordinals when given raw dates (called Q4 'второй квартал')."""
    d: dt.date | None = None
    if isinstance(value, (dt.date, dt.datetime)):
        d = value.date() if isinstance(value, dt.datetime) else value
    elif isinstance(value, str) and _DATE_RE.match(value):
        try:
            d = dt.date.fromisoformat(value[:10])
        except ValueError:
            d = None
    if d is None:
        return str(value)
    c = col.lower()
    if "quarter" in c or "кварт" in c:
        return f"{(d.month - 1) // 3 + 1}-й квартал {d.year}"
    if "month" in c or "месяц" in c:
        return f"{_RU_MONTHS[d.month - 1]} {d.year}"
    if "week" in c or "недел" in c:
        return f"неделя с {d:%d.%m.%Y}"
    if "year" in c or "год" in c:
        return str(d.year)
    return str(value)


def compute_facts(columns: list[str], rows: list[dict]) -> str:
    """Deterministically computed facts the model must rely on.

    LLMs verbalize well but scan tables unreliably (e.g. calling February the
    maximum when March is larger). Max/min/totals are computed here in Python
    and handed to the summarizer as ground truth.
    """
    if not rows:
        return ""
    first = rows[0]
    label_col = next((c for c in columns if not _is_num(first.get(c))), None)
    num_cols = [c for c in columns if _is_num(first.get(c))][:MAX_FACT_COLS]

    def label(row: dict) -> str:
        if label_col is None:
            return f"строка {rows.index(row) + 1}"
        return _humanize_label(row.get(label_col), label_col)

    lines = [f"Всего строк: {len(rows)}."]
    if label_col and len(rows) > 1:
        lines.append(f"Первая строка: {label(rows[0])}; последняя: {label(rows[-1])}.")
    for col in num_cols:
        vals = [(r, r.get(col)) for r in rows if _is_num(r.get(col))]
        if not vals:
            continue
        mx_row, mx = max(vals, key=lambda p: p[1])
        mn_row, mn = min(vals, key=lambda p: p[1])
        total = sum(v for _, v in vals)
        avg = total / len(vals)
        lines.append(
            f"Колонка «{col}»: МАКСИМУМ = {mx:,.0f} ({label(mx_row)}); "
            f"минимум = {mn:,.0f} ({label(mn_row)}); "
            f"сумма = {total:,.0f}; среднее = {avg:,.0f}."
        )
    return "\n".join(lines).replace(",", " ")


def summarize(question: str, sql: str, columns: list[str], rows: list[dict]) -> str:
    """Return a short Russian analytical summary of the result set."""
    if not rows:
        return "По вашему запросу данные не найдены."

    system = (PROMPTS_DIR / "summarize.txt").read_text(encoding="utf-8")
    preview = rows[:SUMMARY_ROWS]
    facts = compute_facts(columns, preview)
    user = (
        f"ВОПРОС: {question}\n"
        f"SQL: {sql}\n"
        f"КОЛОНКИ: {columns}\n"
        f"ПРОВЕРЕННЫЕ ФАКТЫ (вычислены точно, опирайся ТОЛЬКО на них в утверждениях "
        f"о максимуме/минимуме/сумме/среднем):\n{facts}\n\n"
        f"РЕЗУЛЬТАТ (первые {len(preview)} строк из {len(rows)}):\n"
        f"{json.dumps(preview, ensure_ascii=False, default=str)}\n\n"
        "Вывод:"
    )
    return chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3,
    ).strip()
