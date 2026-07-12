from functools import lru_cache
from typing import Annotated
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    CAMERA_ID: str
    DEVICE_PATH: str = "/dev/video0"

    FRAME_WIDTH: int = 1920
    FRAME_HEIGHT: int = 1080
    TARGET_FPS: Annotated[int, Field(ge=1, le=60)] = 15
    JPEG_QUALITY: Annotated[int, Field(ge=1, le=100)] = 80

    AI_HOST: str = "ai"
    AI_PORT: int = 50051

    BUFFER_MAX_DEPTH: Annotated[int, Field(ge=1)] = 30
    BUFFER_MAX_AGE_SECONDS: Annotated[float, Field(gt=0)] = 2.0

    DEVICE_REOPEN_BACKOFF_SECONDS: Annotated[float, Field(gt=0)] = 1.0
    DEVICE_REOPEN_BACKOFF_MAX_SECONDS: Annotated[float, Field(gt=0)] = 30.0
    HEARTBEAT_PATH: str = "/tmp/camera_heartbeat"
    HEARTBEAT_MAX_AGE_SECONDS: Annotated[float, Field(gt=0)] = 10.0
    FORWARD_RETRY_BACKOFF_SECONDS: Annotated[float, Field(gt=0)] = 0.5
    FORWARD_RETRY_BACKOFF_MAX_SECONDS: Annotated[float, Field(gt=0)] = 10.0

    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    @field_validator("CAMERA_ID")
    @classmethod
    def _camera_id_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("CAMERA_ID must not be empty")
        return v

    @property
    def ai_target(self) -> str:
        return f"{self.AI_HOST}:{self.AI_PORT}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
