"""Unit tests for the SQL validator."""

from __future__ import annotations

import pytest

from src.core.validator import DEFAULT_LIMIT, SQLValidationError, validate_sql


def test_plain_select_gets_limit_appended() -> None:
    out = validate_sql("SELECT city FROM stores")
    assert out.startswith("SELECT city FROM stores")
    assert f"LIMIT {DEFAULT_LIMIT}" in out


def test_existing_limit_is_preserved() -> None:
    out = validate_sql("SELECT city FROM stores LIMIT 5")
    assert out.count("LIMIT") == 1
    assert out.strip().endswith("LIMIT 5")


def test_with_cte_is_allowed() -> None:
    out = validate_sql("WITH t AS (SELECT 1 AS x) SELECT x FROM t")
    assert out.lower().startswith("with")


def test_markdown_fences_are_stripped() -> None:
    out = validate_sql("```sql\nSELECT 1\n```")
    assert "`" not in out
    assert out.lower().startswith("select 1")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO stores VALUES (1)",
        "DROP TABLE stores",
        "UPDATE stores SET city = 'x'",
        "DELETE FROM stores",
        "ALTER TABLE stores ADD COLUMN c UInt8",
        "SELECT * FROM system.tables",
        "SELECT * FROM url('http://x', CSV)",
        "SELECT 1; SELECT 2",
        "TRUNCATE TABLE sales",
    ],
)
def test_dangerous_queries_are_rejected(sql: str) -> None:
    with pytest.raises(SQLValidationError):
        validate_sql(sql)


def test_empty_query_rejected() -> None:
    with pytest.raises(SQLValidationError):
        validate_sql("   ")
