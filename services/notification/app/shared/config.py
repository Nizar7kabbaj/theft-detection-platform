from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):


    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50052
    HTTP_HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8000
    REDIS_HOST: str = "theft-redis-broker"
    REDIS_PORT: int = 6379
    REDIS_USER: str = "broker"
    REDIS_PASSWORD_FILE: Path = Path("/run/secrets/broker_redis_password")
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
    model_config = SettingsConfigDict(extra="ignore")
    @property
    def _redis_password(self) -> str:
        return self.REDIS_PASSWORD_FILE.read_text().strip()
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_USER}:{self._redis_password}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    @property
    def RESULT_BACKEND_URL(self) -> str:
        return f"redis://{self.REDIS_USER}:{self._redis_password}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"


settings = Settings()
