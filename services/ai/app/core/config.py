from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


@lru_cache
def _read_secret(path: str) -> str:
    return Path(path).read_text().strip()


class Settings(BaseSettings):
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50051
    YOLO_MODEL_NAME: str = "yolov8n-pose.pt"
    YOLO_OBJECT_MODEL_NAME: str = "yolov8s.pt"
    LSTM_MODEL_PATH: str = "/app/ai-model/models/shoplifting_classifier.pt"
    DEVICE: str = "cuda"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    ANOMALY_THRESHOLD: float = 0.6
    YOLO_PERSON_CLASS: int = 0
    PERSON_CONFIDENCE: float = 0.7
    PRESENCE_GATING_ENABLED: bool = True
    PRESENCE_LEASE_SECONDS: float = 8.0
    PRESENCE_ABSENT_HOLDOFF_SECONDS: float = 3.0
    YOLO_OBJECT_CLASSES: str = "39,67"
    OBJECT_CONFIDENCE: float = 0.35
    CONCEALMENT_GRAB_RATIO: float = 0.6
    CONCEALMENT_MISSING_SECONDS: float = 1.0
    CONCEALMENT_KEYPOINT_CONFIDENCE: float = 0.5
    CONCEALMENT_EXPIRY_SECONDS: float = 10.0
    REDIS_HOST: str = "redis-stream"
    REDIS_PORT: int = 6380
    REDIS_TLS: bool = True
    REDIS_DB: int = 2
    REDIS_USER: str = "ai"
    REDIS_PASSWORD_FILE: str = "/run/secrets/ai_redis_password"
    TRACKER_TTL_SECONDS: int = 60
    NODE_STATS_KEY: str = "stats:node"
    NODE_STATS_INTERVAL_SECONDS: float = 2.0
    NODE_STATS_TTL_SECONDS: int = 15
    NODE_STATS_DEVICE_INDEX: int = 0
    TLS_CERT_FILE: Path = Path("/run/secrets/ai_tls_cert")
    TLS_KEY_FILE: Path = Path("/run/secrets/ai_tls_key")
    TLS_CA_FILE: Path = Path("/run/secrets/ai_tls_ca")
    TLS_REQUIRE_CLIENT_AUTH: bool = True
    API_BASE_URL: str = "http://backend:8000"
    AUTH_BASE_URL: str = "http://auth:8000"
    ALERT_USERNAME: str = "detector-ai"
    ALERT_PASSWORD_FILE: str = "/run/secrets/alert_password"
    ACCESS_COOKIE_NAME: str = "__Host-access_token"
    CSRF_COOKIE_NAME: str = "__Host-csrf"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"
    ALERT_TIMEOUT_SECONDS: float = 5.0
    SNAPSHOT_DIR: str = "/app/snapshots"
    CLIP_SECONDS: float = 6.0
    CLIP_MAX_FRAMES: int = 200
    CLIP_ENABLED: bool = True
    CLIP_WIDTH: int = 640
    CLIP_PRESET: str = "veryfast"
    CLIP_CRF: int = 28
    CLIP_MAX_BITRATE_KBPS: int = 900
    ANNOTATED_SNAPSHOT_ENABLED: bool = True
    ANNOTATED_SNAPSHOT_QUALITY: int = 80
    ANNOTATED_SNAPSHOT_SUFFIX: str = "-annotated"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @computed_field
    @property
    def REDIS_URL(self) -> str:
        password = quote(_read_secret(self.REDIS_PASSWORD_FILE), safe="")
        scheme = "rediss" if self.REDIS_TLS else "redis"
        return f"{scheme}://{self.REDIS_USER}:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def object_class_ids(self) -> list[int]:
        return [int(part) for part in self.YOLO_OBJECT_CLASSES.split(",") if part.strip()]

    @property
    def redis_tls_options(self) -> dict[str, object]:
        if not self.REDIS_TLS:
            return {}
        return {
            "ssl_ca_certs": str(self.TLS_CA_FILE),
            "ssl_certfile": str(self.TLS_CERT_FILE),
            "ssl_keyfile": str(self.TLS_KEY_FILE),
            "ssl_cert_reqs": "required",
        }


settings = Settings()
