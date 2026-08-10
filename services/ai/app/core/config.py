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
    LSTM_MODEL_PATH: str = "/app/ai-model/models/shoplifting_classifier.pt"
    DEVICE: str = "cuda"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    ANOMALY_THRESHOLD: float = 0.6
    YOLO_PERSON_CLASS: int = 0
    REDIS_HOST: str = "redis-stream"
    REDIS_PORT: int = 6380
    REDIS_TLS: bool = True
    REDIS_DB: int = 2
    REDIS_USER: str = "ai"
    REDIS_PASSWORD_FILE: str = "/run/secrets/ai_redis_password"
    TRACKER_TTL_SECONDS: int = 60
    TLS_CERT_FILE: Path = Path("/run/secrets/ai_tls_cert")
    TLS_KEY_FILE: Path = Path("/run/secrets/ai_tls_key")
    TLS_CA_FILE: Path = Path("/run/secrets/ai_tls_ca")
    TLS_REQUIRE_CLIENT_AUTH: bool = True
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @computed_field
    @property
    def REDIS_URL(self) -> str:
        password = quote(_read_secret(self.REDIS_PASSWORD_FILE), safe="")
        scheme = "rediss" if self.REDIS_TLS else "redis"
        return f"{scheme}://{self.REDIS_USER}:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

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
