from functools import cached_property, lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "auth"
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    grpc_max_workers: int = 8
    log_level: str = "info"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "authdb"
    postgres_app_user: str = "auth_app"
    postgres_app_password_file: Path = Path("/run/secrets/postgres_password")
    postgres_owner_user: str = "auth_owner"
    postgres_owner_password_file: Path = Path("/run/secrets/auth_owner_postgres_password")

    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 1

    jwt_private_key_file: Path = Path("/run/secrets/jwt_private_key")
    jwt_public_key_file: Path = Path("/run/secrets/jwt_public_key")
    jwt_issuer: str = "auth"
    jwt_audience: str = "theft-detection-platform"

    redis_host: str = "redis"
    redis_port: int = 6380
    redis_tls: bool = True
    redis_user: str = "auth"
    redis_db: int = 0
    redis_password_file: Path = Path("/run/secrets/auth_redis_password")

    tls_cert_file: Path = Path("/run/secrets/auth_tls_cert")
    tls_key_file: Path = Path("/run/secrets/auth_tls_key")
    tls_ca_file: Path = Path("/run/secrets/auth_tls_ca")
    tls_require_client_auth: bool = True

    audit_target: str = "audit:50054"
    audit_append_timeout_seconds: float = 2.0
    audit_max_inflight_appends: int = 256
    audit_drain_timeout_seconds: float = 3.0

    pseudonym_key_file: Path = Path("/run/secrets/auth_pseudonym_key")

    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1209600
    refresh_rotation_grace_seconds: int = 30
    session_idle_timeout_seconds: int = 43200
    session_sweep_interval_seconds: int = 300
    access_cookie_name: str = "__Host-access_token"
    refresh_cookie_name: str = "__Host-refresh_token"
    csrf_cookie_name: str = "__Host-csrf"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_samesite: str = "lax"

    login_max_attempts: int = 5
    login_window_seconds: int = 900
    login_block_seconds: int = 900

    trusted_proxies: list[str] = [
        "127.0.0.0/8",
        "::1/128",
        "172.16.0.0/12",
    ]

    @field_validator("trusted_proxies")
    @classmethod
    def _validate_proxies(cls, value: list[str]) -> list[str]:
        for entry in value:
            ip_network(entry, strict=False)
        return value

    @cached_property
    def trusted_proxy_networks(self) -> list[IPv4Network | IPv6Network]:
        return [ip_network(entry, strict=False) for entry in self.trusted_proxies]


@lru_cache
def get_settings() -> Settings:
    return Settings()
