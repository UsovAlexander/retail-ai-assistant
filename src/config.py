"""Central configuration. All settings come from environment / .env only.

Secrets (ClickHouse password, Telegram token) are never hard-coded — see
`.env.example`. Import the singleton ``settings`` from this module everywhere.
"""

from __future__ import annotations

import logging
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (this file lives at <root>/src/config.py).
ROOT_DIR: Path = Path(__file__).resolve().parent.parent
PROMPTS_DIR: Path = ROOT_DIR / "src" / "prompts"


class Settings(BaseSettings):
    """Typed application settings, loaded from the environment / .env."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- ClickHouse (HTTP interface) ---
    ch_host: str = Field(default="localhost", alias="CH_HOST")
    ch_port: int = Field(default=8123, alias="CH_PORT")
    ch_user: str = Field(default="default", alias="CH_USER")
    ch_password: str = Field(default="", alias="CH_PASSWORD")
    ch_database: str = Field(default="retail_demo", alias="CH_DATABASE")

    # --- Qdrant ---
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")

    # --- Ollama (OpenAI-compatible API) ---
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="qwen2.5-coder:14b", alias="OLLAMA_MODEL")

    # --- Embeddings ---
    embedding_model: str = Field(
        default="cointegrated/LaBSE-en-ru", alias="EMBEDDING_MODEL"
    )

    # --- Telegram ---
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_allowed_users: str = Field(default="", alias="TELEGRAM_ALLOWED_USERS")

    # --- Misc ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    artifacts_dir: str = Field(default="", alias="ARTIFACTS_DIR")

    # Qdrant collection names — safety rail: only these two are ever touched.
    qdrant_schema_collection: str = "retail_schema"
    qdrant_few_shot_collection: str = "retail_few_shot"

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def allowed_user_ids(self) -> set[int]:
        """Parse the Telegram whitelist into a set of ints."""
        raw = self.telegram_allowed_users.strip()
        if not raw:
            return set()
        return {int(x) for x in raw.split(",") if x.strip()}

    @property
    def artifacts_path(self) -> Path:
        """Resolved directory for generated artifacts (created on demand)."""
        base = Path(self.artifacts_dir) if self.artifacts_dir else (
            Path(tempfile.gettempdir()) / "retail_ai_artifacts"
        )
        base.mkdir(parents=True, exist_ok=True)
        return base


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once, using the configured level."""
    lvl = (level or get_settings().log_level).upper()
    logging.basicConfig(
        level=getattr(logging, lvl, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


settings: Settings = get_settings()
