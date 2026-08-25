from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingsBackend(StrEnum):
    FASTEMBED = "fastembed"
    HASH = "hash"


class JudgeBackend(StrEnum):
    ANTHROPIC = "anthropic"
    OFFLINE = "offline"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRACEBENCH_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3105"])
    api_token: SecretStr | None = Field(
        default=None, description="When set, every /api/* mutation requires 'Authorization: Bearer <token>'."
    )
    ingest_token: SecretStr | None = Field(
        default=None, description="When set, /v1/traces requires 'Authorization: Bearer <token>'."
    )

    database_url: str = "postgresql+asyncpg://tracebench@127.0.0.1:5505/tracebench"

    clickhouse_host: str = "127.0.0.1"
    clickhouse_port: int = 27105
    clickhouse_user: str = "tracebench"
    clickhouse_password: SecretStr = SecretStr("tracebench")
    clickhouse_database: str = "tracebench"
    clickhouse_secure: bool = False
    span_ttl_days: int = Field(default=30, ge=1)

    ingest_max_batch_size: int = Field(default=5_000, ge=1)
    ingest_flush_interval_seconds: float = Field(default=1.0, gt=0)
    ingest_max_pending_spans: int = Field(default=200_000, ge=1)
    ingest_max_body_bytes: int = Field(default=16 * 1024 * 1024, ge=1024)
    price_refresh_seconds: float = Field(default=30.0, gt=0)

    embeddings_backend: EmbeddingsBackend = EmbeddingsBackend.FASTEMBED
    embeddings_model: str = "BAAI/bge-small-en-v1.5"
    embeddings_cache_dir: str | None = None

    judge_backend: JudgeBackend = JudgeBackend.OFFLINE
    judge_model: str = "claude-sonnet-5-5"
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")

    eval_concurrency: int = Field(default=8, ge=1, le=128)
    eval_target_timeout_seconds: float = Field(default=60.0, gt=0)
    eval_target_allowlist: list[str] = Field(
        default_factory=list,
        description=(
            "host or host:port entries the server may call for server-side eval runs. "
            "Empty disables server-side execution, except in development where loopback hosts are allowed."
        ),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
