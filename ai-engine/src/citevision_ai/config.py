from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

_AI_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _AI_ROOT.parent  # citevision-v2/


def _env_files() -> list[str]:
    """
    Retourne la liste ordonnée des fichiers .env à charger.
    generated.env (produit par apply-hardware-profile.py) est chargé EN PREMIER
    pour que ses valeurs soient visibles, mais .env peut les surcharger.
    L'ordre pydantic-settings: le dernier fichier a la priorité.
    On place donc generated.env avant .env pour que .env puisse override.
    """
    files: list[str] = []
    generated = _REPO_ROOT / "generated.env"
    if generated.exists():
        files.append(str(generated))
    # .env can be repo-root or ai-engine/.env
    for candidate in (_REPO_ROOT / ".env", _AI_ROOT / ".env"):
        if candidate.exists():
            files.append(str(candidate))
    # Always include relative ".env" as fallback for backward compat
    if not files:
        files = [".env"]
    return files


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
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

    # GPU Elasticity — modifié dynamiquement par hardware_profile.apply()
    # "auto" = détection automatique au démarrage
    hardware_tier: str = "auto"
    batch_size: int = 4

    # Aliases produits par generated.env (apply-hardware-profile.py)
    # Ces variables prennent effet si generated.env est présent et .env ne les override pas.
    # pydantic-settings les lit via les noms de champ (case-insensitive).
    cv_gpu_tier: str = ""           # ex: "ultra" — copié dans hardware_tier par apply()
    cv_max_cameras: int = 0         # override de max_cameras si > 0
    cv_yolo_model: str = ""         # override de yolo_model_path si non vide
    cv_batch_size: int = 0          # override de batch_size si > 0
    cv_target_fps: float = 0.0      # info FPS cible
    cv_inference_backend: str = ""  # "cuda" ou "cpu" — override de yolo_device si non vide

    mqtt_broker: str = "localhost"
    mqtt_port: int = 1884
    mqtt_user: str = ""
    mqtt_password: str = ""

    insightface_model_path: str = ""
    paddleocr_model_dir: str = ""
    ai_require_all_models: bool = True

    # Segment cycle mode (Phase A — disabled): empty = all cameras use live RTSP.
    # Comma-separated camera UUIDs to opt-in to record→replay cycles (not recommended).
    segment_mode_camera_ids: str = ""
    segment_record_sec: float = 10.0
    segment_process_budget_sec: float = 5.0
    segment_ingest_fps: float = 12.0

    # Unified pipeline: AI reads camera RTSP for analytics. Live preview uses go2rtc pull
    # (ffmpeg RTSP publish to go2rtc :8554 is unreliable on go2rtc 1.9.x).
    unified_pipeline: bool = True
    go2rtc_publish_enabled: bool = False
    burn_in_overlay: bool = True
    go2rtc_rtsp_host: str = "127.0.0.1"
    go2rtc_rtsp_port: int = 8554
    go2rtc_publish_max_width: int = 1280
    go2rtc_publish_fps: float = 15.0

    # Frigate media plane (off by default — see docs/FRIGATE-INTEGRATION.md)
    frigate_enabled: bool = False
    frigate_live: bool = False
    frigate_evidence: bool = False
    frigate_url: str = "http://127.0.0.1:5000"
    frigate_plate_ocr: bool = True
    evidence_backend: str = "ring_buffer"  # ring_buffer | frigate | hybrid

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    redis_host: str = "localhost"
    redis_port: int = 6380

    def model_post_init(self, __context: object) -> None:
        """
        Applique les variables CV_* de generated.env si elles sont définies
        et si les valeurs correspondantes n'ont pas été explicitement surchargées
        par les variables standard dans .env.
        """
        if self.cv_gpu_tier and self.hardware_tier == "auto":
            object.__setattr__(self, "hardware_tier", self.cv_gpu_tier)
        if self.cv_max_cameras > 0:
            object.__setattr__(self, "max_cameras", self.cv_max_cameras)
        if self.cv_yolo_model:
            object.__setattr__(self, "yolo_model_path", f"models/{self.cv_yolo_model}")
        if self.cv_batch_size > 0:
            object.__setattr__(self, "batch_size", self.cv_batch_size)
        if self.cv_inference_backend:
            object.__setattr__(self, "yolo_device", self.cv_inference_backend)

    def parsed_segment_mode_camera_ids(self) -> frozenset[str]:
        raw = self.segment_mode_camera_ids.strip()
        if not raw:
            return frozenset()
        return frozenset(x.strip() for x in raw.split(",") if x.strip())

    def resolved_yolo_path(self) -> Path:
        p = Path(self.yolo_model_path)
        if p.is_absolute():
            return p
        # .env may use repo-relative "ai-engine/models/..." while _AI_ROOT is already ai-engine/
        parts = p.parts
        if parts and parts[0] == "ai-engine":
            p = Path(*parts[1:])
        return (_AI_ROOT / p).resolve()

    def resolved_insightface_root(self) -> Path:
        if self.insightface_model_path.strip():
            p = Path(self.insightface_model_path)
            if p.is_absolute():
                return p
            parts = p.parts
            if parts and parts[0] == "ai-engine":
                p = Path(*parts[1:])
            return (_AI_ROOT / p).resolve()
        return (_AI_ROOT / "models" / "insightface").resolve()

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