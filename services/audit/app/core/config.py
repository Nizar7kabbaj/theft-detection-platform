from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUDIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "audit"
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50054
    grpc_max_workers: int = 8
    log_level: str = "info"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "auditdb"
    postgres_app_user: str = "audit_app"
    postgres_app_password_file: Path = Path("/run/secrets/audit_app_postgres_password")
    postgres_owner_user: str = "audit_owner"
    postgres_owner_password_file: Path = Path(
        "/run/secrets/audit_owner_postgres_password"
    )

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_user: str = "audit"
    redis_db: int = 0
    redis_password_file: Path = Path("/run/secrets/audit_redis_password")

    append_rate_limit: int = 2000
    append_rate_window_seconds: int = 1

    schema_version: int = 1
    min_accepted_schema_version: int = 1

    pseudonym_key_file: Path = Path("/run/secrets/audit_pseudonym_key")
    pseudonym_key_id: str = "p1"

    checkpoint_private_key_file: Path = Path("/run/secrets/audit_checkpoint_private_key")
    checkpoint_public_key_file: Path = Path("/run/secrets/audit_checkpoint_public_key")
    checkpoint_key_id: str = "c1"
    checkpoint_interval_events: int = 1000
    checkpoint_interval_seconds: int = 300

    retention_days: int = 365
    segment_interval_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
