"""Evaluation harness: execution accuracy + result accuracy (spec §8 stage 7).

Run: ``python eval/run_eval.py`` (writes eval/results.md).

For each question we run the full text-to-SQL pipeline and compare its result to
the reference SQL's result by **denotation** (set of rows, invariant to row and
column order, numbers rounded). See [[Evaluation]].
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Make ``src`` importable when run as a plain script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import logging  # noqa: E402

logging.disable(logging.INFO)

from src.config import get_settings  # noqa: E402
from src.core.llm_client import active_model_label  # noqa: E402
from src.core.sql_generator import generate_sql  # noqa: E402
from src.db import get_client  # noqa: E402

QUESTIONS_PATH = ROOT / "eval" / "test_questions.json"
RESULTS_PATH = ROOT / "eval" / "results.md"


def _normalize(rows: list[dict]) -> list[tuple]:
    """Denotation form: rows as sorted tuples of rounded/str cells (order-invariant)."""
    out: list[tuple] = []
    for row in rows:
        cells: list[str] = []
        for v in row.values():
            if isinstance(v, bool):
                cells.append(str(v))
            elif isinstance(v, (int, float)):
                cells.append(f"{round(float(v), 2):.2f}")
            else:
                cells.append(str(v))
        out.append(tuple(sorted(cells)))
    return sorted(out)


def _results_match(gen: list[dict], ref: list[dict]) -> bool:
    return _normalize(gen) == _normalize(ref)


@dataclass
class Row:
    id: int
    category: str
    question: str
    exec_ok: bool
    result_match: bool
    attempts: int
    gen_sql: str | None
    note: str


def _query_dicts(ch, sql: str) -> list[dict]:
    result = ch.query(sql)
    cols = result.column_names
    return [dict(zip(cols, row)) for row in result.result_rows]


def run() -> list[Row]:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]
    ch = get_client(database=get_settings().ch_database)
    results: list[Row] = []
    try:
        for q in questions:
            ref_rows = _query_dicts(ch, q["sql"])
            res = generate_sql(q["question"])
            exec_ok = res.ok
            match = _results_match(res.rows, ref_rows) if exec_ok else False
            note = "" if exec_ok else (res.error or "generation failed")
            if exec_ok and not match:
                note = f"executed but result differs (gen {res.row_count} vs ref {len(ref_rows)} rows)"
            results.append(Row(
                id=q["id"], category=q["category"], question=q["question"],
                exec_ok=exec_ok, result_match=match, attempts=res.attempts,
                gen_sql=res.sql, note=note,
            ))
            flag = "OK " if match else ("run" if exec_ok else "ERR")
            print(f"[{flag}] Q{q['id']:2d} exec={exec_ok} match={match} attempts={res.attempts}")
    finally:
        ch.close()
    return results


def write_report(results: list[Row], elapsed: float) -> None:
    n = len(results)
    exec_acc = sum(r.exec_ok for r in results) / n
    res_acc = sum(r.result_match for r in results) / n

    # Per-category breakdown.
    cats: dict[str, list[Row]] = {}
    for r in results:
        cats.setdefault(r.category, []).append(r)

    lines: list[str] = []
    lines.append("# Evaluation results\n")
    lines.append(f"_Generated {datetime.now():%Y-%m-%d %H:%M} · backend "
                 f"`{active_model_label()}` · {n} questions · {elapsed:.0f}s._\n")
    lines.append("## Metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| **Execution accuracy** (SQL runs) | **{exec_acc:.0%}** ({sum(r.exec_ok for r in results)}/{n}) |")
    lines.append(f"| **Result accuracy** (matches reference) | **{res_acc:.0%}** ({sum(r.result_match for r in results)}/{n}) |")
    avg_attempts = sum(r.attempts for r in results) / n
    lines.append(f"| Avg attempts / question | {avg_attempts:.2f} |\n")

    lines.append("## By category\n")
    lines.append("| Category | Exec | Result | N |")
    lines.append("|---|---|---|---|")
    for cat, rs in sorted(cats.items()):
        e = sum(r.exec_ok for r in rs) / len(rs)
        m = sum(r.result_match for r in rs) / len(rs)
        lines.append(f"| {cat} | {e:.0%} | {m:.0%} | {len(rs)} |")
    lines.append("")

    lines.append("## Per-question\n")
    lines.append("| # | Category | Exec | Result | Att | Question |")
    lines.append("|---|---|:--:|:--:|:--:|---|")
    for r in results:
        lines.append(
            f"| {r.id} | {r.category} | {'✅' if r.exec_ok else '❌'} | "
            f"{'✅' if r.result_match else '❌'} | {r.attempts} | {r.question} |"
        )
    lines.append("")

    failures = [r for r in results if not r.result_match]
    if failures:
        lines.append("## Failures (for analysis)\n")
        for r in failures:
            lines.append(f"**Q{r.id}. {r.question}** — {r.note}")
            lines.append(f"```sql\n{r.gen_sql or '(no SQL produced)'}\n```\n")

    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nExecution accuracy: {exec_acc:.0%} | Result accuracy: {res_acc:.0%}")
    print(f"Report written to {RESULTS_PATH}")


def main() -> None:
    start = time.time()
    results = run()
    write_report(results, time.time() - start)


if __name__ == "__main__":
    main()
