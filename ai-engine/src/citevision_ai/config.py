from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

_AI_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ai_engine_host: str = "0.0.0.0"
    ai_engine_port: int = 8001
    yolo_model_path: str = "models/yolov8n.onnx"
    yolo_device: str = "cuda"
    max_cameras: int = 12
    yolo_confidence: float = 0.25
    yolo_iou: float = 0.45
    yolo_min_fps: float = 10.0

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

    def resolved_yolo_path(self) -> Path:
        p = Path(self.yolo_model_path)
        if p.is_absolute():
            return p
        # .env may use repo-relative "ai-engine/models/..." while _AI_ROOT is already ai-engine/
        parts = p.parts
        if parts and parts[0] == "ai-engine":
            p = Path(*parts[1:])
        return (_AI_ROOT / p).resolve()

    def resolved_mqtt_host(self) -> str:
        broker = self.mqtt_broker.strip()
        if broker.startswith("tcp://") or broker.startswith("mqtt://"):
            parsed = urlparse(broker)
            return parsed.hostname or "localhost"
        return broker

    def resolved_mqtt_port(self) -> int:
        broker = self.mqtt_broker.strip()
        if broker.startswith("tcp://") or broker.startswith("mqtt://"):
            parsed = urlparse(broker)
            if parsed.port:
                return parsed.port
        return self.mqtt_port


settings = Settings()