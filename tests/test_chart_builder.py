"""Unit tests for the chart builder (no LLM — pure rendering logic)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.chart_builder import (
    MAX_CATEGORIES,
    OTHER_LABEL,
    ChartSpec,
    build_chart,
    limit_categories,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _rows(n: int) -> list[dict]:
    return [{"city": f"Город {i}", "revenue": float((n - i) * 1000)} for i in range(n)]


def _is_png(path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(8) == PNG_MAGIC


def test_limit_categories_folds_remainder_into_other() -> None:
    labels = [f"c{i}" for i in range(30)]
    values = [float(i) for i in range(30)]
    out_labels, out_values = limit_categories(labels, values)
    assert len(out_labels) == MAX_CATEGORIES
    assert out_labels[-1] == OTHER_LABEL
    # Total value is conserved after folding.
    assert sum(out_values) == pytest.approx(sum(values))


def test_limit_categories_noop_when_small() -> None:
    labels, values = ["a", "b"], [1.0, 2.0]
    assert limit_categories(labels, values) == (labels, values)


@pytest.mark.parametrize("chart_type", ["bar", "barh", "line", "pie"])
def test_build_chart_writes_png(tmp_path, chart_type: str) -> None:
    spec = ChartSpec(chart_type=chart_type, x="city", y="revenue", title="Тест")
    path = build_chart(_rows(5), spec, out_dir=tmp_path)
    assert path.exists() and path.suffix == ".png"
    assert path.stat().st_size > 0
    assert _is_png(path)


def test_build_chart_handles_many_categories(tmp_path) -> None:
    spec = ChartSpec(chart_type="barh", x="city", y="revenue", title="Много категорий")
    path = build_chart(_rows(40), spec, out_dir=tmp_path)
    assert _is_png(path)


def test_build_chart_empty_rows_raises(tmp_path) -> None:
    spec = ChartSpec(chart_type="bar", x="city", y="revenue", title="Пусто")
    with pytest.raises(ValueError):
        build_chart([], spec, out_dir=tmp_path)


def test_chartspec_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        ChartSpec(chart_type="scatter", x="a", y="b", title="x")
