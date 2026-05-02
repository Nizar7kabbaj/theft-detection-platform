"""
config.py — Load environment variables
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # MongoDB
    MONGODB_URL:      str
    DATABASE_NAME:    str = "theft_detection_db"

    # API
    API_HOST:         str = "0.0.0.0"
    API_PORT:         int = 8000
    DEBUG:            bool = True

    # Security
    SECRET_KEY:       str
    ALGORITHM:        str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # File Storage
    SNAPSHOTS_DIR:    str = "ai-model/outputs/snapshots"
    ALERTS_DIR:       str = "ai-model/outputs/alerts"

    # Telegram (TDP-35) — optional, app runs fine if not set
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID:   str | None = None

    class Config:
        env_file = "backend/.env"


settings = Settings()