"""Unit tests for the deterministic facts block fed to the summarizer."""

from __future__ import annotations

from src.core.summarizer import compute_facts

MONTHS = [
    {"month": "2026-01-01", "num_checks": 19095},
    {"month": "2026-02-01", "num_checks": 32936},
    {"month": "2026-03-01", "num_checks": 40005},
    {"month": "2026-07-01", "num_checks": 7255},
]


def test_max_min_are_attributed_to_correct_rows() -> None:
    facts = compute_facts(["month", "num_checks"], MONTHS)
    # Date labels are humanized by column grain ('month' → «март 2026»).
    assert "МАКСИМУМ = 40 005 (март 2026)" in facts
    assert "минимум = 7 255 (июль 2026)" in facts


def test_total_and_average() -> None:
    facts = compute_facts(["month", "num_checks"], MONTHS)
    assert "сумма = 99 291" in facts
    assert "среднее = 24 823" in facts


def test_first_and_last_rows_named() -> None:
    facts = compute_facts(["month", "num_checks"], MONTHS)
    assert "Первая строка: январь 2026" in facts
    assert "последняя: июль 2026" in facts


def test_quarter_labels_humanized() -> None:
    rows = [
        {"quarter": "2024-01-01", "revenue": 100.0},
        {"quarter": "2024-10-01", "revenue": 900.0},
    ]
    facts = compute_facts(["quarter", "revenue"], rows)
    assert "МАКСИМУМ = 900 (4-й квартал 2024)" in facts


def test_multiple_numeric_columns() -> None:
    rows = [
        {"store": "A", "plan": 100, "actual": 150.0},
        {"store": "B", "plan": 200, "actual": 120.0},
    ]
    facts = compute_facts(["store", "plan", "actual"], rows)
    assert "МАКСИМУМ = 200 (B)" in facts       # plan
    assert "МАКСИМУМ = 150 (A)" in facts       # actual


def test_empty_rows() -> None:
    assert compute_facts(["a"], []) == ""
