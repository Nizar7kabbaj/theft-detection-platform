from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50052

    HTTP_HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8000

    REDIS_URL: str = "redis://theft-redis:6379/1"

    TELEGRAM_BOT_TOKEN: SecretStr | None = None
    TELEGRAM_CHAT_ID: str | None = None
    TELEGRAM_REQUEST_TIMEOUT_SEC: int = 5
    TELEGRAM_PHOTO_TIMEOUT_SEC: int = 15
    TELEGRAM_CAPTION_MAX_CHARS: int = 1024

    SNAPSHOTS_DIR: str = "/app/ai-model/outputs/snapshots"

    CELERY_TASK_MAX_RETRIES: int = 3
    CELERY_TASK_RETRY_DELAY_SEC: int = 10

    ALERTMANAGER_WEBHOOK_TOKEN_FILE: Path = Path("/run/secrets/webhook_token")

    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(extra="ignore")


settings = Settings()
