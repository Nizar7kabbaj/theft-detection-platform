from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50052
    HTTP_HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8000
    REDIS_HOST: str = "theft-redis-broker"
    REDIS_PORT: int = 6380
    REDIS_TLS: bool = True
    REDIS_USER: str = "broker"
    REDIS_PASSWORD_FILE: Path = Path("/run/secrets/broker_redis_password")
    NOTIFY_REDIS_USER: str = "notify"
    NOTIFY_REDIS_PASSWORD_FILE: Path = Path("/run/secrets/notify_redis_password")
    GATE_KEY: str = "notify:telegram:gate"
    GATE_TTL_SEC: int = 180
    GATE_PROBE_INTERVAL_SEC: int = 30
    GATE_DRAIN_BATCH: int = 100
    MONGODB_HOST: str = "mongo:27017"
    MONGODB_USER: str = "notification_svc"
    MONGODB_PASSWORD_FILE: Path = Path("/run/secrets/mongo_password")
    MONGODB_CA_FILE: Path = Path("/run/secrets/mongo_ca.crt")
    DATABASE_NAME: str = "theft_detection_db"
    DELIVERY_INTENT_COLLECTION: str = "delivery_intents"
    DEAD_LETTER_COLLECTION: str = "dead_letters"
    TELEGRAM_BOT_TOKEN_FILE: Path = Path("/run/secrets/telegram_bot_token")
    TELEGRAM_CHAT_ID: str | None = None
    TELEGRAM_REQUEST_TIMEOUT_SEC: int = 5
    TELEGRAM_PHOTO_TIMEOUT_SEC: int = 15
    TELEGRAM_CAPTION_MAX_CHARS: int = 1024
    SNAPSHOTS_DIR: str = "/app/ai-model/outputs/snapshots"
    CELERY_TASK_MAX_RETRIES: int = 3
    CELERY_TASK_RETRY_DELAY_SEC: int = 10
    RECONCILER_ENABLED: bool = True
    RECONCILER_INTERVAL_SEC: int = 60
    RECONCILER_MAX_REQUEUES: int = 3
    DELIVERY_INTENT_SENDING_TIMEOUT_SEC: int = 120
    DELIVERY_INTENT_PENDING_TIMEOUT_SEC: int = 300
    DLQ_ENABLED: bool = True
    ALERTMANAGER_WEBHOOK_TOKEN_FILE: Path = Path("/run/secrets/webhook_token")
    LOG_LEVEL: str = "INFO"

    TLS_CERT_FILE: Path = Path("/run/secrets/notification_tls_cert")
    TLS_KEY_FILE: Path = Path("/run/secrets/notification_tls_key")
    TLS_CA_FILE: Path = Path("/run/secrets/notification_tls_ca")
    TLS_REQUIRE_CLIENT_AUTH: bool = True

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def _redis_password(self) -> str:
        return self.REDIS_PASSWORD_FILE.read_text().strip()

    @property
    def _redis_scheme(self) -> str:
        return "rediss" if self.REDIS_TLS else "redis"

    @property
    def REDIS_URL(self) -> str:
        return f"{self._redis_scheme}://{self.REDIS_USER}:{self._redis_password}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def RESULT_BACKEND_URL(self) -> str:
        return f"{self._redis_scheme}://{self.REDIS_USER}:{self._redis_password}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def _notify_redis_password(self) -> str:
        return self.NOTIFY_REDIS_PASSWORD_FILE.read_text().strip()

    @property
    def NOTIFY_REDIS_URL(self) -> str:
        return f"{self._redis_scheme}://{self.NOTIFY_REDIS_USER}:{self._notify_redis_password}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"


settings = Settings()
