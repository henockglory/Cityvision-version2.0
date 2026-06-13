from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from citevision_ai.anpr.paddleocr_module import PaddleOcrModule
from citevision_ai.budget.resource_budget import ResourceBudgetManager
from citevision_ai.config import settings
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
from citevision_ai.face.insightface_module import InsightFaceModule
from citevision_ai.mqtt.publisher import MqttPublisher
from citevision_ai.pipeline import PipelineService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pipeline: PipelineService | None = None
face_module: InsightFaceModule | None = None
ocr_module: PaddleOcrModule | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, face_module, ocr_module
    detector = YoloOnnxDetector(
        settings.yolo_model_path,
        conf_threshold=settings.yolo_confidence,
        iou_threshold=settings.yolo_iou,
    )
    detector.load()
    budget = ResourceBudgetManager(max_cameras=settings.max_cameras)
    mqtt = MqttPublisher(
        broker=settings.mqtt_broker,
        port=settings.mqtt_port,
        username=settings.mqtt_user or None,
        password=settings.mqtt_password or None,
    )
    mqtt.connect()
    pipeline = PipelineService(detector, budget, mqtt)

    face_module = InsightFaceModule(settings.insightface_model_path)
    face_module.load()
    ocr_module = PaddleOcrModule(settings.paddleocr_model_dir)
    ocr_module.load()

    logger.info("AI Engine started on port %d", settings.ai_engine_port)
    yield
    mqtt.disconnect()
    pipeline = None


app = FastAPI(
    title="Citévision AI Engine",
    version="2.0.0",
    lifespan=lifespan,
)


class CameraRegister(BaseModel):
    camera_id: str


class RulePayload(BaseModel):
    rules: list[dict[str, Any]]


class ProcessRequest(BaseModel):
    camera_id: str
    width: int = 640
    height: int = 480


@app.get("/health")
def health() -> dict[str, str]:
    loaded = pipeline.detector.is_loaded if pipeline else False
    return {
        "status": "ok",
        "service": "citevision-ai-engine",
        "yolo_loaded": str(loaded).lower(),
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


@app.post("/face/detect")
def detect_faces(body: ProcessRequest) -> dict[str, Any]:
    if face_module is None:
        raise HTTPException(status_code=503, detail="Face module not ready")
    frame = np.zeros((body.height, body.width, 3), dtype=np.uint8)
    return {"faces": face_module.detect_faces(frame), "enabled": face_module.is_enabled}


@app.post("/anpr/recognize")
def recognize_plates(body: ProcessRequest) -> dict[str, Any]:
    if ocr_module is None:
        raise HTTPException(status_code=503, detail="OCR module not ready")
    frame = np.zeros((body.height, body.width, 3), dtype=np.uint8)
    return {"plates": ocr_module.recognize_plates(frame), "enabled": ocr_module.is_enabled}
