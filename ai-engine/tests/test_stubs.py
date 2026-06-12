from citevision_ai.face.insightface_stub import InsightFaceStub
from citevision_ai.anpr.paddleocr_stub import PaddleOcrStub
import numpy as np


def test_face_stub_returns_empty():
    stub = InsightFaceStub()
    stub.load()
    assert stub.detect_faces(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_anpr_stub_returns_empty():
    stub = PaddleOcrStub()
    stub.load()
    assert stub.recognize_plates(np.zeros((100, 100, 3), dtype=np.uint8)) == []
