"""Unit tests for the Telegram bot's text formatting (no network)."""

from __future__ import annotations

from src.ui_telegram.bot import _fmt_value, _format_rows

RANKED = [
    {"store": "Уфа", "plan": 32666382, "actual": 40091465.0, "execution_pct": 122.73},
    {"store": "Ростов", "plan": 46664723, "actual": 54775495.0, "execution_pct": 117.38},
    {"store": "Самара", "plan": 49335145, "actual": 57282990.0, "execution_pct": 116.11},
    {"store": "Казань", "plan": 50000000, "actual": 55000000.0, "execution_pct": 110.0},
]


def test_fmt_value_ru_numbers_and_pct() -> None:
    assert _fmt_value(40091465, "actual") == "40 091 465"
    assert _fmt_value(122.73, "execution_pct") == "122,7%"
    assert _fmt_value(110.0, "execution_pct") == "110%"
    assert _fmt_value("Уфа", "store") == "Уфа"


def test_ranked_rows_get_medals() -> None:
    out = _format_rows(RANKED)
    assert "🥇" in out and "🥈" in out and "🥉" in out
    assert out.count("▫️") == 1  # 4th row
    assert "<pre>" not in out  # no more tables


def test_unranked_rows_get_plain_bullets() -> None:
    rows = [
        {"month": "2025-01-01", "revenue": 100.0},
        {"month": "2025-02-01", "revenue": 300.0},  # ascending → not a ranking
    ]
    out = _format_rows(rows)
    assert "🥇" not in out
    assert out.count("▫️") == 2


def test_single_value_column_is_one_line() -> None:
    rows = [{"city": "Москва", "revenue": 1000.0}, {"city": "Казань", "revenue": 500.0}]
    out = _format_rows(rows)
    assert "Москва — <b>1 000</b>" in out


def test_row_limit_note() -> None:
    rows = [{"c": f"x{i}", "v": float(100 - i)} for i in range(15)]
    out = _format_rows(rows, limit=10)
    assert "ещё 5 строк" in out
