"""Latest detection cache for live UI overlay."""

from citevision_ai.pipeline import PipelineService


def test_get_latest_detections_empty():
    from citevision_ai.budget.resource_budget import ResourceBudgetManager
    from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
    from citevision_ai.mqtt.publisher import MqttPublisher

    det = YoloOnnxDetector.__new__(YoloOnnxDetector)
    pipe = PipelineService(det, ResourceBudgetManager(), MqttPublisher())
    out = pipe.get_latest_detections("cam-x")
    assert out["camera_id"] == "cam-x"
    assert out["detections"] == []


def test_get_latest_detections_cached():
    from citevision_ai.budget.resource_budget import ResourceBudgetManager
    from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
    from citevision_ai.mqtt.publisher import MqttPublisher

    det = YoloOnnxDetector.__new__(YoloOnnxDetector)
    pipe = PipelineService(det, ResourceBudgetManager(), MqttPublisher())
    payload = {
        "camera_id": "cam-y",
        "timestamp": "2026-07-09T10:00:00Z",
        "frame_id": 42,
        "resolution": {"width": 1920, "height": 1080},
        "detections": [{"track_id": 1, "class_name": "car", "confidence": 0.9, "bbox": {"x": 10, "y": 20, "width": 100, "height": 80}}],
    }
    pipe._latest_detection_payload["cam-y"] = payload
    assert pipe.get_latest_detections("cam-y") == payload
