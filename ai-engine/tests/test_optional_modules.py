import numpy as np

from citevision_ai.anpr.paddleocr_module import PaddleOcrModule
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
from citevision_ai.face.insightface_module import InsightFaceModule


def test_yolo_returns_empty_without_model(tmp_path):
    detector = YoloOnnxDetector(tmp_path / "missing.onnx")
    detector.load()
    assert not detector.is_loaded
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert detector.detect(frame) == []


def test_face_module_returns_empty_when_disabled():
    module = InsightFaceModule("")
    module.load()
    assert not module.is_enabled
    assert module.detect_faces(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_ocr_module_returns_empty_when_disabled():
    module = PaddleOcrModule("")
    module.load()
    assert not module.is_enabled
    assert module.recognize_plates(np.zeros((100, 100, 3), dtype=np.uint8)) == []
