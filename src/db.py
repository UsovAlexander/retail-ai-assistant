"""ClickHouse access helpers.

A thin wrapper over ``clickhouse-connect``. Safety rail: application code only
ever works inside the ``retail_demo`` database (see [[Data]] / CLAUDE.md).
"""

from __future__ import annotations

import logging
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from src.config import get_settings

logger = logging.getLogger(__name__)


def get_client(database: str | None = None) -> Client:
    """Return a ClickHouse client.

    Args:
        database: database to connect to. ``None`` connects without selecting a
            database (needed to CREATE/DROP ``retail_demo``). Pass the configured
            ``retail_demo`` for normal queries.
    """
    s = get_settings()
    return clickhouse_connect.get_client(
        host=s.ch_host,
        port=s.ch_port,
        username=s.ch_user,
        password=s.ch_password,
        database=database or "",
    )


def server_version() -> str:
    """Return the ClickHouse server version (used by check_env)."""
    client = get_client()
    try:
        return str(client.query("SELECT version()").result_rows[0][0])
    finally:
        client.close()


def ping() -> bool:
    """Return True if the server answers a trivial query."""
    client = get_client()
    try:
        return client.query("SELECT 1").result_rows[0][0] == 1
    finally:
        client.close()
