from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from citevision_ai.evidence.config import RING_FPS
from citevision_ai.config import settings
from citevision_ai.ingest.go2rtc_publisher import Go2rtcPublisher

logger = logging.getLogger(__name__)


class RTSPWorker:
    """Single RTSP read: burn-in preview → go2rtc + inference queue."""

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        process_fn: Callable[..., Any],
        reconnect_delay: float = 5.0,
        target_fps: float = 8.0,
        queue_size: int = 1,
        buffer_fn: Callable[[str, np.ndarray], None] | None = None,
        evidence_fps: float | None = None,
        go2rtc_stream_name: str | None = None,
        burn_in_fn: Callable[[str, np.ndarray], np.ndarray] | None = None,
    ) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.process_fn = process_fn
        self.reconnect_delay = reconnect_delay
        self.target_fps = max(1.0, target_fps)
        self._min_interval = 1.0 / self.target_fps
        self._buffer_fn = buffer_fn
        self._burn_in_fn = burn_in_fn
        ring_fps = evidence_fps if evidence_fps is not None else float(RING_FPS)
        self._evidence_min_interval = 1.0 / max(ring_fps, 1.0)
        self._last_buffer_ts = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._infer_thread: threading.Thread | None = None
        self._running = False
        self._frames_read = 0
        self._frames_processed = 0
        self._frames_dropped = 0
        self._frames_published = 0
        self._last_error: str | None = None
        self._fps = 25.0
        self._publish_fps = float(settings.go2rtc_publish_fps)
        self._publish_min_interval = 1.0 / max(self._publish_fps, 1.0)
        self._last_publish_ts = 0.0
        self._last_process_ts = 0.0
        self._infer_latency_sec = 0.0
        self._publisher: Go2rtcPublisher | None = None
        self._go2rtc_stream_name = go2rtc_stream_name
        self._queue: queue.Queue[tuple[np.ndarray, float, float, int]] = queue.Queue(
            maxsize=max(1, queue_size),
        )
        self._demo_downscale = bool(settings.demo_mode and settings.demo_resolution == "1080p")

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
        logger.info(
            "RTSP worker started camera=%s burn_in=%s stream=%s",
            self.camera_id, bool(self._burn_in_fn), self._go2rtc_stream_name,
        )

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self._publisher:
            self._publisher.stop()
            self._publisher = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        if self._infer_thread and self._infer_thread.is_alive():
            self._infer_thread.join(timeout=10)
        self._thread = None
        self._infer_thread = None

    def status(self) -> dict[str, Any]:
        pub = self._publisher.status() if self._publisher else {}
        mode = "burn_in" if self._burn_in_fn and self._go2rtc_stream_name else (
            "unified" if self._go2rtc_stream_name else "legacy"
        )
        return {
            "camera_id": self.camera_id,
            "rtsp_url": self.rtsp_url,
            "running": self.is_running,
            "frames_processed": self._frames_processed,
            "frames_read": self._frames_read,
            "frames_dropped": self._frames_dropped,
            "frames_published": self._frames_published,
            "queue_depth": self._queue.qsize(),
            "infer_latency_ms": round(self._infer_latency_sec * 1000, 1),
            "fps": round(self._fps, 2),
            "pipeline_mode": mode,
            "burn_in": bool(self._burn_in_fn),
            "go2rtc_publisher": pub,
            "last_error": self._last_error,
        }

    def _ensure_publisher(self, frame: np.ndarray) -> None:
        if not self._go2rtc_stream_name:
            return
        if self._publisher is not None and not self._publisher.status().get("running"):
            self._publisher.stop()
            self._publisher = None
        if self._publisher is not None:
            return
        h, w = frame.shape[:2]
        pub_fps = min(self._fps, self._publish_fps)
        self._publisher = Go2rtcPublisher(self._go2rtc_stream_name, w, h, pub_fps)
        self._publisher.start()

    def _frame_for_publish(self, frame: np.ndarray) -> np.ndarray:
        if self._burn_in_fn is None:
            return frame
        try:
            return self._burn_in_fn(self.camera_id, frame)
        except Exception:
            logger.exception("burn-in failed for %s", self.camera_id)
            return frame

    def _loop(self) -> None:
        cap: cv2.VideoCapture | None = None
        while not self._stop.is_set():
            try:
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if not cap.isOpened():
                        self._last_error = f"cannot open {self.rtsp_url}"
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
                capture_wall = time.time()
                self._frames_read += 1
                publish_index = self._frames_read
                if self._demo_downscale:
                    h, w = frame.shape[:2]
                    if w > 1920 or h > 1080:
                        frame = cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_AREA)

                if self._go2rtc_stream_name:
                    self._ensure_publisher(frame)
                    if self._publisher and now - self._last_publish_ts >= self._publish_min_interval:
                        published = self._frame_for_publish(frame)
                        if self._publisher.write_frame(published):
                            self._frames_published += 1
                            self._last_publish_ts = now

                if self._buffer_fn is not None:
                    if capture_wall - self._last_buffer_ts >= self._evidence_min_interval:
                        try:
                            self._buffer_fn(self.camera_id, frame)
                            self._last_buffer_ts = capture_wall
                        except Exception:
                            logger.exception("evidence buffer push failed for %s", self.camera_id)

                if now - self._last_process_ts < self._min_interval:
                    continue
                self._last_process_ts = now

                while True:
                    try:
                        self._queue.put_nowait((frame, self._fps, capture_wall, publish_index))
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
        while not self._stop.is_set():
            try:
                frame, fps, capture_wall, publish_index = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                start = time.monotonic()
                self.process_fn(
                    self.camera_id,
                    frame,
                    fps,
                    capture_wall_ts=capture_wall,
                    publish_frame_index=publish_index,
                )
                self._infer_latency_sec = time.monotonic() - start
                self._frames_processed += 1
            except Exception:
                logger.exception("RTSP inference consumer error for %s", self.camera_id)


class WorkerManager:
    """Manages one ingest worker per camera."""

    def __init__(
        self,
        process_fn: Callable[..., Any],
        buffer_fn: Callable[[str, np.ndarray], None] | None = None,
        eof_flush_fn: Callable[..., Any] | None = None,
        begin_replay_fn: Callable[[str], None] | None = None,
        burn_in_fn: Callable[[str, np.ndarray], np.ndarray] | None = None,
    ) -> None:
        self._process_fn = process_fn
        self._buffer_fn = buffer_fn
        self._eof_flush_fn = eof_flush_fn
        self._begin_replay_fn = begin_replay_fn
        self._burn_in_fn = burn_in_fn
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
            # Sprint 4: segment cycle ingest is archived — refuse opt-in.
            if camera_id in settings.parsed_segment_mode_camera_ids():
                raise RuntimeError(
                    f"SEGMENT_MODE_CAMERA_IDS includes {camera_id[:8]}… but segment mode "
                    "is archived (Sprint 4). Unset the env var; use RTSP/Frigate. "
                    "See _archive/segment_mode/README.md"
                )
            existing = self._workers.get(camera_id)
            if existing is not None and existing.is_running:
                desired = "file" if video_file else "rtsp"
                current = "file" if isinstance(existing, FileVideoWorker) else "rtsp"
                source_changed = current != desired
                if not source_changed and isinstance(existing, RTSPWorker) and rtsp_url:
                    source_changed = existing.rtsp_url != rtsp_url
                if not source_changed and isinstance(existing, FileVideoWorker) and video_file:
                    source_changed = existing.file_path != str(Path(video_file).resolve())
                if source_changed:
                    existing.stop()
                    del self._workers[camera_id]
                    existing = None
                else:
                    self._configs[camera_id] = spatial_config or {}
                    return {"hot_reload": True, **existing.status()}

            if camera_id in self._workers:
                self._workers[camera_id].stop()

            go2rtc_name = (
                f"cam-{camera_id}"
                if (
                    settings.go2rtc_publish_enabled
                    and settings.unified_pipeline
                    and not video_file
                    and not (settings.frigate_enabled and settings.frigate_live)
                )
                else None
            )
            use_burn_in = settings.burn_in_overlay and go2rtc_name is not None

            if video_file:
                worker = FileVideoWorker(
                    camera_id, video_file, self._process_fn, target_fps=ai_fps, buffer_fn=self._buffer_fn,
                )
            else:
                if not rtsp_url:
                    raise ValueError("rtsp_url or video_file required")
                worker = RTSPWorker(
                    camera_id,
                    rtsp_url,
                    self._process_fn,
                    target_fps=ai_fps,
                    buffer_fn=self._buffer_fn,
                    go2rtc_stream_name=go2rtc_name,
                    burn_in_fn=self._burn_in_fn if use_burn_in else None,
                )
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
