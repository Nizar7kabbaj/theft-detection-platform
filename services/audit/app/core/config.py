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
    grpc_max_concurrent_rpcs: int = 64
    health_probe_interval_seconds: int = 10
    health_probe_timeout_seconds: float = 3.0
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
    redis_connect_timeout_seconds: float = 2.0
    redis_socket_timeout_seconds: float = 2.0

    tls_enabled: bool = True
    tls_cert_file: Path = Path("/run/secrets/audit_tls_cert")
    tls_key_file: Path = Path("/run/secrets/audit_tls_key")
    tls_ca_file: Path = Path("/run/secrets/audit_tls_ca")
    tls_require_client_auth: bool = True

    postgres_pool_size: int = 5
    postgres_max_overflow: int = 5
    postgres_pool_timeout_seconds: int = 10
    lock_timeout_ms: int = 3000
    statement_timeout_ms: int = 10000
    idle_transaction_timeout_ms: int = 15000

    owner_lock_timeout_ms: int = 10000
    owner_statement_timeout_ms: int = 300000
    owner_idle_transaction_timeout_ms: int = 60000

    append_rate_limit: int = 2000
    append_rate_window_seconds: int = 1
    append_rate_fail_closed: bool = False

    schema_version: int = 1
    min_accepted_schema_version: int = 1
    max_clock_skew_seconds: int = 300
    max_backdate_seconds: int = 86400

    pseudonym_key_file: Path = Path("/run/secrets/audit_pseudonym_key")
    pseudonym_key_id: str = "p1"
    checkpoint_private_key_file: Path = Path(
        "/run/secrets/audit_checkpoint_private_key"
    )
    checkpoint_public_key_file: Path = Path("/run/secrets/audit_checkpoint_public_key")
    checkpoint_key_id: str = "c1"
    checkpoint_interval_events: int = 1000
    checkpoint_interval_seconds: int = 300

    retention_days: int = 365
    segment_interval_days: int = 30
    retention_max_rows_per_run: int = 50000


@lru_cache
def get_settings() -> Settings:
    return Settings()
