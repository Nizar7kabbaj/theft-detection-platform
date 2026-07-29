from functools import lru_cache
from pathlib import Path

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
    postgres_user: str = "auth"
    postgres_db: str = "authdb"
    postgres_password_file: Path = Path("/run/secrets/postgres_password")
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
