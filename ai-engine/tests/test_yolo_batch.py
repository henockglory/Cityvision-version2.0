import pytest

np = pytest.importorskip("numpy")

from citevision_ai.detection.yolo_onnx import YoloOnnxDetector, INPUT_SIZE


def test_detect_batch_without_model_returns_empty_per_frame():
    det = YoloOnnxDetector(model_path="does-not-exist.onnx")
    frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(3)]
    out = det.detect_batch(frames)
    assert out == [[], [], []]


def test_detect_batch_empty_input():
    det = YoloOnnxDetector(model_path="does-not-exist.onnx")
    assert det.detect_batch([]) == []


def test_preprocess_batch_shapes():
    pytest.importorskip("cv2")
    det = YoloOnnxDetector(model_path="does-not-exist.onnx")
    frames = [
        np.zeros((480, 640, 3), dtype=np.uint8),
        np.zeros((720, 1280, 3), dtype=np.uint8),
    ]
    blob, scales = det.preprocess_batch(frames)
    assert blob.shape == (2, 3, INPUT_SIZE, INPUT_SIZE)
    assert len(scales) == 2
