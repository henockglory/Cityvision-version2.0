from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class RTSPWorker:
    """Reads RTSP frames and hands them off to a dedicated inference thread.

    The read loop never calls ``process_fn`` (pipeline + GPU inference) itself —
    it only decodes frames and pushes them onto a small bounded, drop-oldest
    queue. A separate consumer thread (started alongside the reader) pulls from
    that queue and runs ``process_fn``. This means a slow/backed-up GPU never
    stalls the RTSP socket read: at 10-16 concurrent cameras, inference latency
    no longer causes stream staleness or ByteTrack fragmentation on the read side.
    """

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        process_fn: Callable[[str, np.ndarray, float], Any],
        reconnect_delay: float = 5.0,
        target_fps: float = 8.0,
        queue_size: int = 2,
    ) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.process_fn = process_fn
        self.reconnect_delay = reconnect_delay
        self.target_fps = max(1.0, target_fps)
        self._min_interval = 1.0 / self.target_fps
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._infer_thread: threading.Thread | None = None
        self._running = False
        self._frames_read = 0
        self._frames_processed = 0
        self._frames_dropped = 0
        self._last_error: str | None = None
        self._fps = 25.0
        self._last_process_ts = 0.0
        self._last_read_ts = 0.0
        self._last_infer_start_ts = 0.0
        self._infer_latency_sec = 0.0
        self._queue: queue.Queue[tuple[np.ndarray, float]] = queue.Queue(maxsize=max(1, queue_size))

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"rtsp-{self.camera_id}")
        self._thread.start()
        self._infer_thread = threading.Thread(
            target=self._infer_loop, daemon=True, name=f"infer-{self.camera_id}",
        )
        self._infer_thread.start()
        self._running = True
        logger.info("RTSP worker started for camera %s", self.camera_id)

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        if self._infer_thread and self._infer_thread.is_alive():
            self._infer_thread.join(timeout=10)
        self._thread = None
        self._infer_thread = None
        logger.info("RTSP worker stopped for camera %s", self.camera_id)

    def status(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "rtsp_url": self.rtsp_url,
            "running": self.is_running,
            "frames_processed": self._frames_processed,
            "frames_read": self._frames_read,
            "frames_dropped": self._frames_dropped,
            "queue_depth": self._queue.qsize(),
            "infer_latency_ms": round(self._infer_latency_sec * 1000, 1),
            "fps": round(self._fps, 2),
            "last_error": self._last_error,
        }

    def _loop(self) -> None:
        cap: cv2.VideoCapture | None = None
        while not self._stop.is_set():
            try:
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if not cap.isOpened():
                        self._last_error = f"cannot open {self.rtsp_url}"
                        logger.warning("RTSP open failed for %s, retry in %.1fs", self.camera_id, self.reconnect_delay)
                        time.sleep(self.reconnect_delay)
                        continue
                    self._last_error = None
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    if fps and fps > 1:
                        self._fps = float(fps)

                ok, frame = cap.read()
                if not ok or frame is None:
                    self._last_error = "frame read failed"
                    cap.release()
                    cap = None
                    time.sleep(self.reconnect_delay)
                    continue

                now = time.monotonic()
                self._last_read_ts = now
                self._frames_read += 1
                if now - self._last_process_ts < self._min_interval:
                    continue
                self._last_process_ts = now

                # Drop-oldest: never let a slow inference thread back-pressure the
                # RTSP read loop. A stale queued frame is worse than a fresh one.
                while True:
                    try:
                        self._queue.put_nowait((frame, self._fps))
                        break
                    except queue.Full:
                        try:
                            self._queue.get_nowait()
                            self._frames_dropped += 1
                        except queue.Empty:
                            pass
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("RTSP worker error for %s", self.camera_id)
                if cap:
                    cap.release()
                    cap = None
                time.sleep(self.reconnect_delay)

        if cap:
            cap.release()

    def _infer_loop(self) -> None:
        """Dedicated consumer: pulls queued frames and runs the (GPU-bound)
        pipeline, fully decoupled from the RTSP read loop above."""
        while not self._stop.is_set():
            try:
                frame, fps = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                start = time.monotonic()
                self._last_infer_start_ts = start
                self.process_fn(self.camera_id, frame, fps)
                self._infer_latency_sec = time.monotonic() - start
                self._frames_processed += 1
            except Exception:
                logger.exception("RTSP inference consumer error for %s", self.camera_id)


class WorkerManager:
    """Manages one ingest worker per camera (fichier local ou RTSP réseau)."""

    def __init__(self, process_fn: Callable[[str, np.ndarray, float], Any]) -> None:
        self._process_fn = process_fn
        self._workers: dict[str, RTSPWorker | Any] = {}
        self._configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start_camera(
        self,
        camera_id: str,
        rtsp_url: str | None = None,
        spatial_config: dict[str, Any] | None = None,
        video_file: str | None = None,
        ai_fps: float = 8.0,
    ) -> dict[str, Any]:
        from citevision_ai.ingest.file_video_worker import FileVideoWorker

        with self._lock:
            if camera_id in self._workers and self._workers[camera_id].is_running:
                self._configs[camera_id] = spatial_config or {}
                return {"hot_reload": True, **self._workers[camera_id].status()}

            if camera_id in self._workers:
                self._workers[camera_id].stop()

            if video_file:
                worker = FileVideoWorker(camera_id, video_file, self._process_fn, target_fps=ai_fps)
            else:
                if not rtsp_url:
                    raise ValueError("rtsp_url or video_file required")
                worker = RTSPWorker(camera_id, rtsp_url, self._process_fn, target_fps=ai_fps)
            self._workers[camera_id] = worker
            self._configs[camera_id] = spatial_config or {}
            worker.start()
            return worker.status()

    def stop_camera(self, camera_id: str) -> bool:
        with self._lock:
            worker = self._workers.pop(camera_id, None)
            self._configs.pop(camera_id, None)
            if worker:
                worker.stop()
                return True
            return False

    def get_config(self, camera_id: str) -> dict[str, Any]:
        return self._configs.get(camera_id, {})

    def list_status(self) -> list[dict[str, Any]]:
        with self._lock:
            return [w.status() for w in self._workers.values()]
