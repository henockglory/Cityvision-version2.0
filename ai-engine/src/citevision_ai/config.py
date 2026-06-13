from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ai_engine_host: str = "0.0.0.0"
    ai_engine_port: int = 8001
    yolo_model_path: str = "models/yolov8n.onnx"
    max_cameras: int = 12
    yolo_confidence: float = 0.25
    yolo_iou: float = 0.45

    mqtt_broker: str = "localhost"
    mqtt_port: int = 1884
    mqtt_user: str = ""
    mqtt_password: str = ""

    insightface_model_path: str = ""
    paddleocr_model_dir: str = ""

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    redis_host: str = "localhost"
    redis_port: int = 6380


settings = Settings()
