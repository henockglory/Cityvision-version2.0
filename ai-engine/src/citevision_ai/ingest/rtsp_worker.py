from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class RTSPWorker:
    """Reads RTSP frames and feeds them into the pipeline."""

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        process_fn: Callable[[str, np.ndarray, float], Any],
        reconnect_delay: float = 5.0,
        target_fps: float = 8.0,
    ) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.process_fn = process_fn
        self.reconnect_delay = reconnect_delay
        self.target_fps = max(1.0, target_fps)
        self._min_interval = 1.0 / self.target_fps
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._frames_processed = 0
        self._last_error: str | None = None
        self._fps = 25.0
        self._last_process_ts = 0.0

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"rtsp-{self.camera_id}")
        self._thread.start()
        self._running = True
        logger.info("RTSP worker started for camera %s", self.camera_id)

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None
        logger.info("RTSP worker stopped for camera %s", self.camera_id)

    def status(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "rtsp_url": self.rtsp_url,
            "running": self.is_running,
            "frames_processed": self._frames_processed,
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
                if now - self._last_process_ts < self._min_interval:
                    continue
                self._last_process_ts = now

                self.process_fn(self.camera_id, frame, self._fps)
                self._frames_processed += 1
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("RTSP worker error for %s", self.camera_id)
                if cap:
                    cap.release()
                    cap = None
                time.sleep(self.reconnect_delay)

        if cap:
            cap.release()


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
