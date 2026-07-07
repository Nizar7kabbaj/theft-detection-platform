from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGODB_HOST:      str = "mongo:27017"
    MONGODB_USER:      str = "api_svc"
    MONGODB_PASSWORD_FILE: Path = Path("/run/secrets/mongo_password")
    MONGODB_CA_FILE:   Path = Path("/run/secrets/mongo_ca.crt")
    DATABASE_NAME:     str = "theft_detection_db"
    REDIS_URL:         str = ""
    REDIS_URL_LOCAL:   str
    REDIS_MODE:        str = "local"
    API_HOST:          str = "0.0.0.0"
    API_PORT:          int = 8000
    DEBUG:             bool = True
    SECRET_KEY:        str
    ALGORITHM:         str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    SNAPSHOTS_DIR:     str = "ai-model/outputs/snapshots"
    ALERTS_DIR:        str = "ai-model/outputs/alerts"
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID:   str | None = None
    INFERENCE_TARGET:   str = "ai:50051"
    NOTIFICATION_TARGET: str = "notification-service:50052"
    WS_MAX_CONNECTIONS:   int = 100
    WS_HEARTBEAT_SECONDS: int = 30
    ALERT_THRESHOLD:    float = 0.7
    model_config = SettingsConfigDict(env_file="backend/.env")
settings = Settings()
