"""SQL validation for generated queries.

Defense-in-depth (spec §5.2): the generated SQL is executed against a live
database, so before running it we guarantee it is a single, read-only ``SELECT``
that cannot touch system tables, external table functions, or other databases,
and that it carries a ``LIMIT``. See [[Text_to_SQL]].
"""

from __future__ import annotations

import re

# Default row cap forced onto queries that lack an explicit LIMIT.
DEFAULT_LIMIT = 1000

# Statement-level keywords that must never appear (DDL/DML/side effects).
_FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "attach", "detach", "rename", "grant", "revoke", "optimize", "system",
    "kill", "use", "set", "into", "replace", "exchange", "call",
]

# Table functions / schemas that read outside retail_demo.
_FORBIDDEN_SOURCES = [
    "system.", "information_schema.", "informationschema.",
    "url(", "file(", "remote(", "remotesecure(", "mysql(", "postgresql(",
    "s3(", "s3cluster(", "jdbc(", "odbc(", "hdfs(", "azureblobstorage(",
    "cluster(", "clusterallreplicas(", "executable(", "input(", "generaterandom(",
]


class SQLValidationError(ValueError):
    """Raised when generated SQL fails a safety/shape check."""


def _strip_fences(sql: str) -> str:
    """Remove markdown code fences / stray backticks the model may add."""
    text = sql.strip()
    if text.startswith("```"):
        # Drop the opening fence line (``` or ```sql) and any closing fence.
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip().strip("`").strip()


def validate_sql(sql: str, *, max_limit: int = DEFAULT_LIMIT) -> str:
    """Validate and normalize a generated SQL string.

    Returns the cleaned SQL (with a LIMIT appended if none was present).
    Raises :class:`SQLValidationError` on any violation.
    """
    cleaned = _strip_fences(sql)
    if not cleaned:
        raise SQLValidationError("empty query")

    # Single statement only (allow one optional trailing semicolon).
    body = cleaned.rstrip(";").strip()
    if ";" in body:
        raise SQLValidationError("multiple statements are not allowed")

    lowered = body.lower()

    # Must be a read-only SELECT (optionally a WITH ... SELECT CTE).
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise SQLValidationError("only SELECT/WITH queries are allowed")

    # Forbidden keywords as whole words.
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", lowered):
            raise SQLValidationError(f"forbidden keyword: {kw}")

    # Forbidden external/system sources (substring match, whitespace-insensitive).
    compact = re.sub(r"\s+", "", lowered)
    for src in _FORBIDDEN_SOURCES:
        if src in compact:
            raise SQLValidationError(f"forbidden source: {src}")

    # Force a LIMIT if the query has none.
    if not re.search(r"\blimit\b", lowered):
        body = f"{body}\nLIMIT {max_limit}"

    return body
