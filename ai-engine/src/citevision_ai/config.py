from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ai_engine_host: str = "0.0.0.0"
    ai_engine_port: int = 8000
    yolo_model_path: str = "models/yolov8n.onnx"
    max_cameras: int = 12

    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = "citevision"
    mqtt_password: str = "changeme_mqtt"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    redis_host: str = "localhost"
    redis_port: int = 6379


settings = Settings()
