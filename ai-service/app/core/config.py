from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GRPC_HOST:       str = "0.0.0.0"
    GRPC_PORT:       int = 50051
    YOLO_MODEL_NAME: str = "yolov8n-pose.pt"
    LSTM_MODEL_PATH: str = "/app/ai-model/models/shoplifting_classifier.pt"
    DEVICE:          str = "cuda"
    LOG_LEVEL:       str = "INFO"
    DEBUG:           bool = False
    ANOMALY_THRESHOLD:   float = 0.6
    YOLO_PERSON_CLASS:   int = 0
    model_config = SettingsConfigDict(env_file="ai-service/.env", extra="ignore")


settings = Settings()
