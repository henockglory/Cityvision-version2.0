from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from citevision_ai.budget.resource_budget import ResourceBudgetManager
from citevision_ai.config import settings
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
from citevision_ai import hardware_profile
from citevision_ai.identity.face import FaceIdentityEngine, InsightFaceRecognizer
from citevision_ai.identity.plate import PlateIdentityEngine
from citevision_ai.ingest.rtsp_worker import WorkerManager
from citevision_ai.mqtt.publisher import MqttPublisher
from citevision_ai.pipeline import PipelineService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pipeline: PipelineService | None = None
worker_manager: WorkerManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, worker_manager
    # Detect GPU tier and override settings before any model loading
    hw_tier = hardware_profile.apply(settings)
    logger.info("Hardware tier: %s — %s", hw_tier.tier, hw_tier.label)

    detector = YoloOnnxDetector(
        str(settings.resolved_yolo_path()),
        conf_threshold=settings.yolo_confidence,
        iou_threshold=settings.yolo_iou,
        device=settings.yolo_device,
    )
    detector.load()

    iface_root = str(settings.resolved_insightface_root())
    face_engine = FaceIdentityEngine(
        recognizer=InsightFaceRecognizer(model_root=iface_root),
    )
    face_engine.load()
    plate_engine = PlateIdentityEngine()
    plate_engine.load()
    if face_engine.is_loaded:
        logger.info("InsightFace loaded from %s", iface_root)
    else:
        logger.warning("InsightFace not loaded — install: pip install -e 'ai-engine/.[identity]'")
    if plate_engine.is_loaded:
        logger.info("PaddleOCR loaded for ANPR")
    else:
        logger.warning("PaddleOCR not loaded — install: pip install -e 'ai-engine/.[anpr]'")

    budget = ResourceBudgetManager(max_cameras=settings.max_cameras)
    mqtt = MqttPublisher(
        broker=settings.resolved_mqtt_host(),
        port=settings.resolved_mqtt_port(),
        username=settings.mqtt_user or None,
        password=settings.mqtt_password or None,
    )
    mqtt.connect()
    pipeline = PipelineService(detector, budget, mqtt, face_engine, plate_engine)

    def process_fn(camera_id: str, frame: np.ndarray, fps: float) -> None:
        if pipeline is None:
            return
        if camera_id not in pipeline._trackers:
            config = worker_manager.get_config(camera_id) if worker_manager else {}
            pipeline.register_camera(camera_id, config)
        pipeline.process_frame(camera_id, frame, fps)

    worker_manager = WorkerManager(process_fn)
    logger.info("AI Engine started on port %d with RTSP worker manager", settings.ai_engine_port)
    yield
    if worker_manager:
        for cam_id in list(worker_manager._workers.keys()):
            worker_manager.stop_camera(cam_id)
    mqtt.disconnect()
    pipeline = None
    worker_manager = None


app = FastAPI(
    title="Citévision AI Engine",
    version="2.0.0",
    lifespan=lifespan,
)


class CameraRegister(BaseModel):
    camera_id: str


class CameraStartRequest(BaseModel):
    rtsp_url: str | None = None
    video_file: str | None = None
    ai_fps: float = Field(default=8.0, ge=1.0, le=30.0)
    org_id: str | None = None
    spatial_rules: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)
    watchlist: list[dict[str, Any]] = Field(default_factory=list)
    plates: list[dict[str, Any]] = Field(default_factory=list)
    analytics_thresholds: dict[str, Any] = Field(default_factory=dict)
    evidence_capture_rules: list[dict[str, Any]] = Field(default_factory=list)
    capability_profiles: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceCaptureRequest(BaseModel):
    org_id: str
    event: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)


class RulePayload(BaseModel):
    rules: list[dict[str, Any]]


class ProcessRequest(BaseModel):
    camera_id: str
    width: int = 640
    height: int = 480


@app.get("/health")
def health() -> dict[str, str]:
    import shutil

    yolo_loaded = pipeline.detector.is_loaded if pipeline else False
    face_loaded = pipeline.face_engine.is_loaded if pipeline else False
    plate_loaded = pipeline.plate_engine.is_loaded if pipeline else False
    provider = pipeline.detector.active_provider if pipeline else "none"
    return {
        "status": "ok",
        "service": "citevision-ai-engine",
        "yolo_loaded": str(yolo_loaded).lower(),
        "face_loaded": str(face_loaded).lower(),
        "plate_loaded": str(plate_loaded).lower(),
        "yolo_provider": provider,
        "yolo_cuda": str(pipeline.detector.uses_cuda if pipeline else False).lower(),
        "ffmpeg_available": str(shutil.which("ffmpeg") is not None).lower(),
    }


@app.get("/hardware/profile")
def hardware_profile_endpoint() -> dict:
    return hardware_profile.get_profile_info()


@app.get("/health/gpu")
def health_gpu() -> dict[str, str | float | bool]:
    if pipeline is None or not pipeline.detector.is_loaded:
        raise HTTPException(status_code=503, detail="YOLO not loaded")
    fps = pipeline.detector.benchmark_fps(30)
    cuda = bool(pipeline.detector.uses_cuda)
    return {
        "provider": pipeline.detector.active_provider,
        "cuda": cuda,
        "benchmark_fps": round(fps, 1),
        "min_fps": settings.yolo_min_fps,
        "pass": fps >= settings.yolo_min_fps or not cuda,
    }


@app.get("/budget")
def get_budget() -> dict[str, Any]:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    profile = pipeline.budget.get_profile()
    return {
        "camera_count": pipeline.budget.camera_count,
        "width": profile.width,
        "height": profile.height,
        "target_fps": profile.target_fps,
    }


@app.get("/cameras")
def list_cameras() -> dict[str, Any]:
    if worker_manager is None:
        raise HTTPException(status_code=503, detail="Worker manager not ready")
    return {"cameras": worker_manager.list_status()}


@app.post("/cameras/{camera_id}/start")
def start_camera(camera_id: str, body: CameraStartRequest) -> dict[str, Any]:
    if pipeline is None or worker_manager is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    spatial = {**body.spatial_rules}
    if body.calibration:
        spatial["calibration"] = body.calibration
    pipeline.register_camera(camera_id, spatial)
    if body.org_id:
        pipeline.set_org_id(camera_id, body.org_id)
    if body.watchlist:
        pipeline.set_watchlist(body.watchlist)
    if body.plates:
        pipeline.set_plates(body.plates)
    if body.analytics_thresholds:
        pipeline.apply_runtime_config(camera_id, body.analytics_thresholds)
    if body.evidence_capture_rules:
        pipeline.set_evidence_capture_rules(camera_id, body.evidence_capture_rules)
    if body.capability_profiles:
        pipeline.set_capability_profiles(camera_id, body.capability_profiles)
    if not body.rtsp_url and not body.video_file:
        raise HTTPException(status_code=400, detail="rtsp_url or video_file required")
    status = worker_manager.start_camera(
        camera_id,
        rtsp_url=body.rtsp_url,
        spatial_config=spatial,
        video_file=body.video_file,
        ai_fps=body.ai_fps,
    )
    return {"status": "started", **status}


@app.post("/cameras/{camera_id}/evidence/capture")
def capture_evidence(camera_id: str, body: EvidenceCaptureRequest) -> dict[str, Any]:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    policy = body.evidence or {}
    uploaded = pipeline.evidence.capture_retroactive(
        camera_id, body.org_id, dict(body.event), policy if policy else None
    )
    if not uploaded:
        raise HTTPException(status_code=404, detail="capture unavailable")
    return uploaded


@app.post("/cameras/{camera_id}/stop")
def stop_camera(camera_id: str) -> dict[str, str]:
    if worker_manager is None or pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    worker_manager.stop_camera(camera_id)
    pipeline.unregister_camera(camera_id)
    return {"status": "stopped", "camera_id": camera_id}


@app.post("/cameras")
def register_camera(body: CameraRegister) -> dict[str, str]:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    try:
        pipeline.register_camera(body.camera_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "registered", "camera_id": body.camera_id}


@app.delete("/cameras/{camera_id}")
def unregister_camera(camera_id: str) -> dict[str, str]:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    if worker_manager:
        worker_manager.stop_camera(camera_id)
    pipeline.unregister_camera(camera_id)
    return {"status": "unregistered", "camera_id": camera_id}


@app.put("/rules")
def set_rules(body: RulePayload) -> dict[str, int]:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    pipeline.set_rules(body.rules)
    return {"rules_loaded": len(body.rules)}


@app.post("/process/test")
def process_test(body: ProcessRequest) -> dict[str, Any]:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    if body.camera_id not in pipeline._trackers:
        pipeline.register_camera(body.camera_id)
    frame = np.zeros((body.height, body.width, 3), dtype=np.uint8)
    result = pipeline.process_frame(body.camera_id, frame)
    return result.to_mqtt_payload()
