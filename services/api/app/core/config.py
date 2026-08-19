from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGODB_HOST: str = "mongo:27017"
    MONGODB_USER: str = "api_svc"
    MONGODB_PASSWORD_FILE: Path = Path("/run/secrets/mongo_password")
    MONGODB_CA_FILE: Path = Path("/run/secrets/mongo_ca.crt")
    DATABASE_NAME: str = "theft_detection_db"
    REDIS_URL: str = ""
    REDIS_URL_LOCAL: str = ""
    REDIS_MODE: str = "local"
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6380
    REDIS_TLS: bool = True
    REDIS_DB: int = 0
    REDIS_USER: str = "api"
    REDIS_PASSWORD_FILE: Path = Path("/run/secrets/api_redis_password")
    STREAM_REDIS_HOST: str = "theft-redis-stream"
    STREAM_REDIS_PORT: int = 6380
    STREAM_REDIS_DB: int = 2
    STREAM_REDIS_USER: str = "api-health"
    STREAM_REDIS_PASSWORD_FILE: Path = Path("/run/secrets/stream_reader_redis_password")
    STREAM_FRAME_PREFIX: str = "frame"
    HEALTH_ONLINE_MAX_AGE_SECONDS: float = 5.0
    HEALTH_DEGRADED_MAX_AGE_SECONDS: float = 15.0
    HEALTH_RECONCILE_INTERVAL_SECONDS: float = 3.0
    FRAME_STREAM_INTERVAL_SECONDS: float = 0.1
    FRAME_STREAM_SEND_TIMEOUT_SECONDS: float = 5.0
    FRAME_STREAM_MAX_READ_FAILURES: int = 3
    FRAME_STREAM_MAX_VIEWERS: int = 4
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    SNAPSHOTS_DIR: str = "/app/snapshots"
    ALERTS_DIR: str = "ai-model/outputs/alerts"
    INFERENCE_TARGET: str = "ai:50051"
    NOTIFICATION_TARGET: str = "notification:50052"
    AUTH_TARGET: str = "auth:50053"
    AUTH_VERIFY_TIMEOUT_SECONDS: float = 2.0
    AUDIT_TARGET: str = "audit:50054"
    AUDIT_APPEND_TIMEOUT_SECONDS: float = 2.0
    AUDIT_OUTBOX_MAX_PENDING: int = 10000
    AUDIT_OUTBOX_POLL_SECONDS: float = 5.0
    TLS_CERT_FILE: Path = Path("/run/secrets/api_tls_cert")
    TLS_KEY_FILE: Path = Path("/run/secrets/api_tls_key")
    TLS_CA_FILE: Path = Path("/run/secrets/api_tls_ca")
    WS_MAX_CONNECTIONS: int = 100
    WS_HEARTBEAT_SECONDS: int = 30
    WS_ALLOWED_ORIGINS: str = "https://localhost"
    WS_REAUTH_SECONDS: int = 60
    WS_REAUTH_GRACE_SECONDS: int = 180
    WS_RATE_UPGRADES: int = 30
    WS_RATE_WINDOW_SECONDS: int = 60
    WS_RATE_BURST: int = 10
    ALERT_THRESHOLD: float = 0.7
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_BURST: int = 100
    ACCESS_COOKIE_NAME: str = "__Host-access_token"
    CSRF_COOKIE_NAME: str = "__Host-csrf"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )


settings = Settings()
