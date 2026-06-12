from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from citevision_ai.budget.resource_budget import ResourceBudgetManager
from citevision_ai.config import settings
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
from citevision_ai.mqtt.publisher import MqttPublisher
from citevision_ai.pipeline import PipelineService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pipeline: PipelineService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    detector = YoloOnnxDetector(settings.yolo_model_path)
    detector.load()
    budget = ResourceBudgetManager(max_cameras=settings.max_cameras)
    mqtt = MqttPublisher(
        broker=settings.mqtt_broker,
        port=settings.mqtt_port,
        username=settings.mqtt_user,
        password=settings.mqtt_password,
    )
    mqtt.connect()
    pipeline = PipelineService(detector, budget, mqtt)
    logger.info("AI Engine started")
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
    return {"status": "ok", "service": "citevision-ai-engine"}


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
    """Process a synthetic blank frame (integration test endpoint)."""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    if body.camera_id not in pipeline._trackers:
        pipeline.register_camera(body.camera_id)
    frame = np.zeros((body.height, body.width, 3), dtype=np.uint8)
    result = pipeline.process_frame(body.camera_id, frame)
    return result.to_mqtt_payload()
