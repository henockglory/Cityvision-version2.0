from pathlib import Path
from urllib.parse import urlparse
import os
import logging

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_AI_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _AI_ROOT.parent  # citevision-v2/
_log = logging.getLogger("citevision_ai.config")


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


def _parse_env_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    v = raw.strip().strip('"').strip("'").lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off", ""):
        return False
    return None


def _read_key_from_env_files(key: str) -> str | None:
    """Parse KEY=value from repo .env files (last file wins). Independent of process environ."""
    found: str | None = None
    for path in _env_files():
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, val = s.partition("=")
            if k.strip() == key:
                found = val.strip()
    return found


def resolve_demo_mode() -> tuple[bool, str]:
    """
    Resolve DEMO_MODE without relying on the shell having sourced .env.

    Priority:
      1. Process environ DEMO_MODE / CITEVISION_DEMO_MODE
      2. Explicit key in repo .env / generated.env / ai-engine/.env
      3. Default False (strict / production)
    """
    for env_key in ("DEMO_MODE", "CITEVISION_DEMO_MODE"):
        parsed = _parse_env_bool(os.environ.get(env_key))
        if parsed is not None:
            return parsed, f"environ:{env_key}"
    for file_key in ("DEMO_MODE", "CITEVISION_DEMO_MODE"):
        parsed = _parse_env_bool(_read_key_from_env_files(file_key))
        if parsed is not None:
            return parsed, f"env_file:{file_key}"
    return False, "default:false"


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
    # Archived Sprint 4 — keep empty. Non-empty raises at camera start.
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
    # Resolved again in model_post_init via resolve_demo_mode() so soft-accept
    # never depends on the restart shell having sourced .env.
    demo_mode: bool = Field(default=False, validation_alias=AliasChoices("DEMO_MODE", "CITEVISION_DEMO_MODE"))
    demo_mode_source: str = "default:false"
    demo_evidence_backend: str = "strict_frigate"  # strict_frigate | frigate | hybrid | ring_buffer
    demo_resolution: str = "1080p"  # 1080p | source
    # Demo go2rtc loop length for red_light Feux video (ffprobe stream duration).
    demo_red_light_loop_sec: float = 352.52
    # Demo-only: hard |bbox_ts−Frigate| gate + same-loop-cycle check (stale capture H1).
    # Live cameras have no loop boundary — leave False outside DEMO_MODE.
    demo_loop_guard: bool = True

    # Frigate track evidence (ported from citevision_videoverbalisation)
    frigate_event_match_sec: float = 12.0
    # Demo go2rtc loops: Frigate start_time is stream-relative; IA uses wall clock.
    frigate_demo_timeline_align: bool = True
    # Demo go2rtc: max |IA anchor − Frigate event| — stale loop events rejected above this.
    # 10s tolerates binder/queue delay while still rejecting hour-old loop events.
    frigate_demo_max_align_sec: float = 10.0
    frigate_demo_loose_match_sec: float = 10.0
    frigate_demo_bootstrap_max_sec: float = 18.0
    frigate_demo_min_bbox_iou: float = 0.12
    # Evidence accept gate: reject correlated events beyond this |IA−Frigate| skew.
    # Soft-accept may relax IoU inside this window — never enlarge the window itself.
    frigate_demo_accept_max_align_sec: float = 30.0
    # Minimum IoU between IA emission bbox and Frigate event box to accept evidence.
    # Demo go2rtc skips IoU in _accept_correlation (ByteTrack vs Frigate boxes diverge).
    frigate_accept_min_bbox_iou: float = 0.15
    frigate_demo_time_only_max_sec: float = 15.0
    frigate_demo_time_only_min_iou: float = 0.12
    frigate_demo_events_limit: int = 80
    frigate_snapshot_retries: int = 8
    frigate_snapshot_retry_delay: float = 0.45
    frigate_snapshot_quality: int = 98
    frigate_clip_retries: int = 8
    frigate_clip_retry_delay: float = 0.8
    frigate_clip_wait_if_missing: float = 1.2
    frigate_clip_min_bytes: int = 512
    frigate_clip_pad_before: float = 0.4
    frigate_clip_pad_after: float = 0.8
    frigate_event_media_wait_sec: float = 25.0
    frigate_event_media_poll_sec: float = 0.5
    # Poll Frigate events until correlated (demo go2rtc often lags IA by several seconds).
    frigate_correlate_wait_sec: float = 12.0
    # Sprint 1 — red_light deferred compose: wait for end_time before clip download.
    frigate_red_light_end_time_wait_sec: float = 30.0
    frigate_red_light_end_time_backoff_initial: float = 2.0
    frigate_red_light_end_time_backoff_max: float = 8.0
    frigate_evidence_frame_count: int = 6
    frigate_clip_frame_jpeg_q: int = 2
    # Proactive track → Frigate event binding (IoU while track is live).
    frigate_track_binding_enabled: bool = True
    frigate_bind_every_n_frames: int = 2
    frigate_bind_min_iou: float = 0.12

    # Fast-ALPR OCR service (evidence plate recognition)
    ocr_url: str = Field(
        default="",
        validation_alias=AliasChoices("ocr_url", "OCR_URL", "CITEVISION_OCR_URL"),
    )
    ocr_timeout: float = 8.0
    plate_max_frames: int = 6
    plate_stop_conf: float = 0.88
    plate_min_conf: float = 0.35

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    redis_host: str = "localhost"
    redis_port: int = 6380

    def model_post_init(self, __context: object) -> None:
        """
        Applique les variables CV_* de generated.env si elles sont définies
        et si les valeurs correspondantes n'ont pas été explicitement surchargées
        par les variables standard dans .env.
        Force DEMO_MODE from environ or .env files so soft-accept gates are never silent.
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

        # Always re-resolve DEMO_MODE from environ + on-disk .env (last write wins over
        # pydantic defaults when the process was started without a sourced shell env).
        demo, source = resolve_demo_mode()
        object.__setattr__(self, "demo_mode", demo)
        object.__setattr__(self, "demo_mode_source", source)
        _log.info("DEMO_MODE=%s source=%s", demo, source)

    def demo_relaxed_evidence(self) -> bool:
        """True when demo soft-accept / timeline-relaxed Frigate paths are allowed."""
        return bool(self.demo_mode)

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