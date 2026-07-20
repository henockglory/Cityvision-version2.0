import threading
import time

import pytest

np = pytest.importorskip("numpy")

from citevision_ai.detection.yolo_onnx import YoloOnnxDetector, INPUT_SIZE


class _FakeSession:
    """Records concurrency + per-call batch size to verify locking/microbatching."""

    def __init__(self, delay: float = 0.02) -> None:
        self.calls: list[int] = []
        self.delay = delay
        self._lock = threading.Lock()
        self._concurrent = 0
        self.max_concurrent = 0

    def get_inputs(self):
        return [type("Input", (), {"name": "images"})()]

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def run(self, output_names, feed):
        blob = feed["images"]
        batch_n = blob.shape[0]
        with self._lock:
            self._concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self._concurrent)
        try:
            self.calls.append(batch_n)
            time.sleep(self.delay)
        finally:
            with self._lock:
                self._concurrent -= 1
        # All-zero output → confidence never clears conf_threshold → no boxes,
        # keeping assertions focused on concurrency/batching, not detections.
        return [np.zeros((batch_n, 84, 32), dtype=np.float32)]


def _rigged_detector(delay: float = 0.02) -> YoloOnnxDetector:
    det = YoloOnnxDetector(model_path="does-not-exist.onnx")
    det._session = _FakeSession(delay=delay)
    det._input_name = "images"
    return det


def test_microbatch_coalesces_concurrent_detect_calls():
    det = _rigged_detector(delay=0.05)
    det._batch_window_sec = 0.15
    det._max_batch_size = 16
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    results: list[list[dict] | None] = [None] * 6

    def worker(i: int) -> None:
        results[i] = det.detect(frame)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert all(r == [] for r in results)
    # Six concurrent callers should be coalesced into far fewer than 6 session.run() calls.
    assert len(det._session.calls) < 6
    assert sum(det._session.calls) == 6
    # The run_lock must fully serialize session.run() — never two calls in flight at once.
    assert det._session.max_concurrent == 1


def test_run_lock_serializes_concurrent_detect_batch_calls():
    det = _rigged_detector(delay=0.03)
    det._microbatch_enabled = False  # exercise detect_batch() directly, not the queue
    frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(2)]

    def worker() -> None:
        det.detect_batch(frames)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(det._session.calls) == 4
    assert det._session.max_concurrent == 1


def test_max_batch_size_constructor_arg_overrides_env_default(monkeypatch):
    """Hardware tier's settings.batch_size must actually reach the detector —
    this is the wiring that makes the README's per-tier 'Batch' column true."""
    monkeypatch.setenv("YOLO_MAX_BATCH_SIZE", "16")
    det = YoloOnnxDetector(model_path="does-not-exist.onnx", max_batch_size=4)
    assert det._max_batch_size == 4


def test_max_batch_size_falls_back_to_env_when_not_passed(monkeypatch):
    monkeypatch.setenv("YOLO_MAX_BATCH_SIZE", "9")
    det = YoloOnnxDetector(model_path="does-not-exist.onnx")
    assert det._max_batch_size == 9


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
