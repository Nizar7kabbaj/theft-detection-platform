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
    SESSION_ID: Annotated[int, Field(ge=1)] = 1
    FRAME_SOURCE: str = "camera"
    CLIP_PATH: str = "/app/fixtures/presence.mp4"
    GATE_FPS: Annotated[int, Field(ge=1, le=60)] = 15
    MODEL_NAME: str = "yolov8n.pt"
    MODEL_DEVICE: str = "cuda"
    PERSON_CLASS_ID: Annotated[int, Field(ge=0)] = 0
    DETECTION_CONFIDENCE: Annotated[float, Field(gt=0, le=1)] = 0.5
    EXIT_DEBOUNCE_FRAMES: Annotated[int, Field(ge=1)] = 30
    AI_HOST: str = "ai"
    AI_PORT: int = 50051
    STREAM_SEND_TIMEOUT_SECONDS: Annotated[float, Field(gt=0)] = 1.0
    STREAM_RETRY_BACKOFF_SECONDS: Annotated[float, Field(gt=0)] = 0.5
    STREAM_RETRY_BACKOFF_MAX_SECONDS: Annotated[float, Field(gt=0)] = 10.0
    REDIS_HOST: str = "redis-stream"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 2
    REDIS_USER: str = "gate"
    REDIS_PASSWORD_FILE: str = "/run/secrets/gate_redis_password"
    FRAME_STREAM_PREFIX: str = "frame"
    FRAME_READ_BLOCK_MS: Annotated[int, Field(ge=100)] = 2000
    FRAME_RETRY_BACKOFF_SECONDS: Annotated[float, Field(gt=0)] = 0.5
    FRAME_RETRY_BACKOFF_MAX_SECONDS: Annotated[float, Field(gt=0)] = 10.0
    HEARTBEAT_PATH: str = "/tmp/detect_gate_heartbeat"
    HEARTBEAT_MAX_AGE_SECONDS: Annotated[float, Field(gt=0)] = 10.0
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    @field_validator("CAMERA_ID")
    @classmethod
    def _camera_id_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("CAMERA_ID must not be empty")
        return v

    @field_validator("MODEL_DEVICE")
    @classmethod
    def _device_known(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"cuda", "cpu"}:
            raise ValueError("MODEL_DEVICE must be cuda or cpu")
        return v

    @field_validator("FRAME_SOURCE")
    @classmethod
    def _source_known(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"camera", "clip"}:
            raise ValueError("FRAME_SOURCE must be camera or clip")
        return v

    @model_validator(mode="after")
    def _debounce_sane(self) -> Self:
        if self.EXIT_DEBOUNCE_FRAMES < 1:
            raise ValueError("EXIT_DEBOUNCE_FRAMES must be at least 1")
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
