"""RTSPWorker: read loop must never block on slow (GPU-bound) inference."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from citevision_ai.ingest import rtsp_worker as rtsp_worker_module
from citevision_ai.ingest.rtsp_worker import RTSPWorker


class _FakeCapture:
    """Synthetic RTSP source: returns a fresh frame instantly on every read()."""

    def __init__(self, *_a, **_kw) -> None:
        self._opened = True
        self._n = 0

    def isOpened(self) -> bool:
        return self._opened

    def set(self, *_a, **_kw) -> bool:
        return True

    def get(self, _prop) -> float:
        return 25.0

    def read(self):
        self._n += 1
        frame = np.full((10, 10, 3), self._n % 256, dtype=np.uint8)
        return True, frame

    def release(self) -> None:
        self._opened = False


def test_rtsp_worker_read_loop_not_blocked_by_slow_inference(monkeypatch):
    monkeypatch.setattr(rtsp_worker_module.cv2, "VideoCapture", lambda *a, **k: _FakeCapture())

    process_started = threading.Event()

    def slow_process(camera_id, frame, fps):
        process_started.set()
        time.sleep(0.3)  # far slower than the ~33ms read/queue cadence below

    worker = RTSPWorker("cam-x", "rtsp://fake", slow_process, target_fps=30.0, queue_size=2)
    worker.start()
    try:
        assert process_started.wait(timeout=2.0)
        time.sleep(0.5)
        status = worker.status()
        # The reader must keep advancing while a slow consumer call is in flight —
        # only possible because reading is decoupled from process_fn via the queue.
        assert status["frames_read"] > 5
        # The consumer can't keep up, so drop-oldest must kick in instead of the
        # queue (and therefore the reader) ever blocking.
        assert status["frames_dropped"] > 0
        assert status["queue_depth"] <= 2
    finally:
        worker.stop()


def test_rtsp_worker_processes_frames_when_consumer_keeps_up(monkeypatch):
    monkeypatch.setattr(rtsp_worker_module.cv2, "VideoCapture", lambda *a, **k: _FakeCapture())

    processed: list[np.ndarray] = []

    def fast_process(camera_id, frame, fps):
        processed.append(frame)

    worker = RTSPWorker("cam-y", "rtsp://fake", fast_process, target_fps=20.0, queue_size=2)
    worker.start()
    try:
        time.sleep(0.5)
        assert len(processed) > 3
        status = worker.status()
        assert status["frames_processed"] > 0
        assert status["last_error"] is None
    finally:
        worker.stop()
