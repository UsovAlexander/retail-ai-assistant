"""Environment check: verify connectivity to the three local services.

Run: ``python -m src.check_env``

This VERIFIES (does not install) that ClickHouse, Qdrant and Ollama are
reachable with the configured credentials, and that the expected Ollama model
is present. Exit code is non-zero if any required service is unreachable.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import httpx

from src.config import configure_logging, get_settings


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_clickhouse() -> CheckResult:
    from src import db  # local import: keeps failures isolated per service

    try:
        version = db.server_version()
        return CheckResult("ClickHouse", True, f"version {version}")
    except Exception as exc:  # noqa: BLE001 - report any failure to the user
        return CheckResult("ClickHouse", False, f"{type(exc).__name__}: {exc}")


def check_qdrant() -> CheckResult:
    s = get_settings()
    try:
        resp = httpx.get(f"{s.qdrant_url}/collections", timeout=5.0)
        resp.raise_for_status()
        names = [c["name"] for c in resp.json()["result"]["collections"]]
        return CheckResult("Qdrant", True, f"reachable; collections={names or '[]'}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Qdrant", False, f"{type(exc).__name__}: {exc}")


def check_ollama() -> CheckResult:
    s = get_settings()
    # base_url ends with /v1 (OpenAI-compatible); tags live on the native API.
    root = s.ollama_base_url.rsplit("/v1", 1)[0]
    try:
        resp = httpx.get(f"{root}/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        if s.ollama_model not in models:
            return CheckResult(
                "Ollama",
                False,
                f"reachable but model '{s.ollama_model}' not pulled; have {models}",
            )
        return CheckResult("Ollama", True, f"model '{s.ollama_model}' present")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Ollama", False, f"{type(exc).__name__}: {exc}")


def main() -> int:
    configure_logging()
    results = [check_clickhouse(), check_qdrant(), check_ollama()]

    print("\nEnvironment check — Retail AI Assistant")
    print("=" * 60)
    for r in results:
        mark = "OK  " if r.ok else "FAIL"
        print(f"[{mark}] {r.name:<12} {r.detail}")
    print("=" * 60)

    all_ok = all(r.ok for r in results)
    print("All services reachable." if all_ok else "Some services are UNREACHABLE.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
