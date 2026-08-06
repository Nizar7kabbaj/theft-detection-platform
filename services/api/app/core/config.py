from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGODB_HOST:      str = "mongo:27017"
    MONGODB_USER:      str = "api_svc"
    MONGODB_PASSWORD_FILE: Path = Path("/run/secrets/mongo_password")
    MONGODB_CA_FILE:   Path = Path("/run/secrets/mongo_ca.crt")
    DATABASE_NAME:     str = "theft_detection_db"
    REDIS_URL:         str = ""
    REDIS_URL_LOCAL:   str = ""
    REDIS_MODE:        str = "local"
    REDIS_HOST:        str = "redis"
    REDIS_PORT:        int = 6379
    REDIS_DB:          int = 0
    REDIS_USER:        str = "api"
    REDIS_PASSWORD_FILE: Path = Path("/run/secrets/api_redis_password")
    API_HOST:          str = "0.0.0.0"
    API_PORT:          int = 8000
    DEBUG:             bool = True
    SNAPSHOTS_DIR:     str = "ai-model/outputs/snapshots"
    ALERTS_DIR:        str = "ai-model/outputs/alerts"
    INFERENCE_TARGET:    str = "ai:50051"
    NOTIFICATION_TARGET: str = "notification-service:50052"
    AUTH_TARGET:         str = "auth:50053"
    AUTH_VERIFY_TIMEOUT_SECONDS: float = 2.0
    AUDIT_TARGET:        str = "audit:50054"
    AUDIT_APPEND_TIMEOUT_SECONDS: float = 2.0
    AUDIT_TLS_CERT_FILE: Path = Path("/run/secrets/api_tls_cert")
    AUDIT_TLS_KEY_FILE:  Path = Path("/run/secrets/api_tls_key")
    AUDIT_TLS_CA_FILE:   Path = Path("/run/secrets/api_tls_ca")
    WS_MAX_CONNECTIONS:   int = 100
    WS_HEARTBEAT_SECONDS: int = 30
    WS_ALLOWED_ORIGINS:   str = "http://localhost:3000"
    WS_REAUTH_SECONDS:    int = 60
    ALERT_THRESHOLD:      float = 0.7
    RATE_LIMIT_ENABLED:         bool = True
    RATE_LIMIT_REQUESTS:        int = 100
    RATE_LIMIT_WINDOW_SECONDS:  int = 60
    RATE_LIMIT_BURST:           int = 100
    ACCESS_COOKIE_NAME: str = "__Host-access_token"
    CSRF_COOKIE_NAME:   str = "__Host-csrf"
    CSRF_HEADER_NAME:   str = "X-CSRF-Token"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )


settings = Settings()
