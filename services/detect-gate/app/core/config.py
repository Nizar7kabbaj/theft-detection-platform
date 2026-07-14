from functools import lru_cache
from typing import Annotated, Self
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    CAMERA_ID: str
    SESSION_ID: Annotated[int, Field(ge=1)] = 1
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
    @model_validator(mode="after")
    def _debounce_sane(self) -> Self:
        if self.EXIT_DEBOUNCE_FRAMES < 1:
            raise ValueError("EXIT_DEBOUNCE_FRAMES must be at least 1")
        return self
    @property
    def ai_target(self) -> str:
        return f"{self.AI_HOST}:{self.AI_PORT}"
@lru_cache
def get_settings() -> Settings:
    return Settings()
