from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self
from urllib.parse import quote

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


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
    IDLE_FPS: Annotated[int, Field(ge=1, le=60)] = 15
    ACTIVE_FPS: Annotated[int, Field(ge=1, le=60)] = 30
    DWELL_SECONDS: Annotated[float, Field(gt=0)] = 3.0
    AI_HOST: str = "ai"
    AI_PORT: int = 50051
    BUFFER_MAX_DEPTH: Annotated[int, Field(ge=1)] = 30
    BUFFER_MAX_AGE_SECONDS: Annotated[float, Field(gt=0)] = 2.0
    DEVICE_REOPEN_BACKOFF_SECONDS: Annotated[float, Field(gt=0)] = 1.0
    DEVICE_REOPEN_BACKOFF_MAX_SECONDS: Annotated[float, Field(gt=0)] = 8.0
    HEARTBEAT_PATH: Path = Path("/app/run/camera_heartbeat")
    HEARTBEAT_MAX_AGE_SECONDS: Annotated[float, Field(gt=0)] = 10.0
    FORWARD_RETRY_BACKOFF_SECONDS: Annotated[float, Field(gt=0)] = 0.5
    FORWARD_RETRY_BACKOFF_MAX_SECONDS: Annotated[float, Field(gt=0)] = 10.0
    REDIS_HOST: str = "redis-stream"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 2
    REDIS_USER: str = "camera"
    REDIS_PASSWORD_FILE: str = "/run/secrets/camera_redis_password"
    FRAME_STREAM_PREFIX: str = "frame"
    FRAME_STREAM_MAXLEN: Annotated[int, Field(ge=1)] = 900
    PUBLISH_QUEUE_DEPTH: Annotated[int, Field(ge=1)] = 30
    PUBLISH_RETRY_BACKOFF_SECONDS: Annotated[float, Field(gt=0)] = 0.5
    PUBLISH_RETRY_BACKOFF_MAX_SECONDS: Annotated[float, Field(gt=0)] = 10.0
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    TLS_CERT_FILE: Path = Path("/run/secrets/camera_tls_cert")
    TLS_KEY_FILE: Path = Path("/run/secrets/camera_tls_key")
    TLS_CA_FILE: Path = Path("/run/secrets/camera_tls_ca")

    @field_validator("CAMERA_ID")
    @classmethod
    def _camera_id_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("CAMERA_ID must not be empty")
        return v

    @model_validator(mode="after")
    def _idle_le_active(self) -> Self:
        if self.IDLE_FPS > self.ACTIVE_FPS:
            raise ValueError("IDLE_FPS must be less than or equal to ACTIVE_FPS")
        return self

    @property
    def ai_target(self) -> str:
        return f"{self.AI_HOST}:{self.AI_PORT}"

    @computed_field
    @property
    def REDIS_URL(self) -> str:
        password = quote(_read_secret(self.REDIS_PASSWORD_FILE), safe="")
        return f"redis://{self.REDIS_USER}:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def frame_stream_key(self) -> str:
        return f"{self.FRAME_STREAM_PREFIX}:{self.CAMERA_ID}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
