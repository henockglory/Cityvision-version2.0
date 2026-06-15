from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class FileVideoWorker:
    """Lit un fichier MP4 directement — évite la contention RTSP avec le flux d'affichage."""

    def __init__(
        self,
        camera_id: str,
        file_path: str,
        process_fn: Callable[[str, np.ndarray, float], Any],
        target_fps: float = 8.0,
    ) -> None:
        self.camera_id = camera_id
        self.file_path = str(Path(file_path).resolve())
        self.process_fn = process_fn
        self.target_fps = max(1.0, min(target_fps, 30.0))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._frames_processed = 0
        self._last_error: str | None = None
        self._source_fps = 25.0

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        if not Path(self.file_path).is_file():
            self._last_error = f"file not found: {self.file_path}"
            logger.error("File video worker: %s", self._last_error)
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name=f"file-{self.camera_id}"
        )
        self._thread.start()
        self._running = True
        logger.info("File video worker started for %s (%s)", self.camera_id, self.file_path)

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None
        logger.info("File video worker stopped for %s", self.camera_id)

    def status(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "source": "file",
            "file_path": self.file_path,
            "running": self.is_running,
            "frames_processed": self._frames_processed,
            "fps": round(self.target_fps, 2),
            "source_fps": round(self._source_fps, 2),
            "last_error": self._last_error,
        }

    def _loop(self) -> None:
        cap = cv2.VideoCapture(self.file_path, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            self._last_error = f"cannot open {self.file_path}"
            self._running = False
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps and fps > 1:
            self._source_fps = float(fps)

        interval = 1.0 / self.target_fps
        self._last_error = None

        while not self._stop.is_set():
            t0 = time.monotonic()
            ok, frame = cap.read()
            if not ok or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            self.process_fn(self.camera_id, frame, self._source_fps)
            self._frames_processed += 1

            elapsed = time.monotonic() - t0
            wait = interval - elapsed
            if wait > 0:
                time.sleep(wait)

        cap.release()
