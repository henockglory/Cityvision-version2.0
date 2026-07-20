from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable

import cv2
import numpy as np

from citevision_ai.evidence.service import probe_media_duration
from citevision_ai.ingest.timeline import FrameTimeline, SegmentCaptureContext

logger = logging.getLogger(__name__)


class SegmentState(str, Enum):
    RECORDING = "recording"
    PROCESSING = "processing"
    IDLE = "idle"


class RecordedSegment:
    __slots__ = (
        "path", "cycle_id", "frame_count", "duration_sec", "source_fps",
        "segment_start_mono", "segment_start_wall",
    )

    def __init__(
        self,
        path: str,
        cycle_id: str,
        frame_count: int,
        duration_sec: float,
        source_fps: float,
        segment_start_mono: float,
        segment_start_wall: float,
    ) -> None:
        self.path = path
        self.cycle_id = cycle_id
        self.frame_count = frame_count
        self.duration_sec = duration_sec
        self.source_fps = source_fps
        self.segment_start_mono = segment_start_mono
        self.segment_start_wall = segment_start_wall


class SegmentCycleWorker:
    """Record fixed-length RTSP segments, then replay offline for detection + evidence."""

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        process_fn: Callable[..., Any],
        eof_flush_fn: Callable[..., Any] | None = None,
        begin_replay_fn: Callable[[str], None] | None = None,
        record_sec: float = 10.0,
        process_budget_sec: float = 5.0,
        ingest_fps: float = 12.0,
        reconnect_delay: float = 5.0,
    ) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.process_fn = process_fn
        self.eof_flush_fn = eof_flush_fn
        self.begin_replay_fn = begin_replay_fn
        self.record_sec = record_sec
        self.process_budget_sec = process_budget_sec
        self.ingest_fps = ingest_fps
        self.reconnect_delay = reconnect_delay
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._state = SegmentState.IDLE
        self._cycle = 0
        self._last_error: str | None = None
        self._frames_recorded = 0
        self._frames_processed = 0
        self._last_record_sec = 0.0
        self._last_process_sec = 0.0
        self._lock = threading.Lock()
        self._segment_dir = os.path.join(tempfile.gettempdir(), "cv_segments", camera_id)
        os.makedirs(self._segment_dir, exist_ok=True)

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._cycle_loop, daemon=True, name=f"segment-{self.camera_id[:8]}",
        )
        self._thread.start()
        self._running = True
        logger.info("Segment cycle worker started for camera %s", self.camera_id)

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=15)
        self._thread = None
        logger.info("Segment cycle worker stopped for camera %s", self.camera_id)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "camera_id": self.camera_id,
                "rtsp_url": self.rtsp_url,
                "mode": "segment_cycle",
                "running": self.is_running,
                "segment_state": self._state.value,
                "cycle": self._cycle,
                "frames_recorded": self._frames_recorded,
                "frames_processed": self._frames_processed,
                "last_record_sec": round(self._last_record_sec, 2),
                "last_process_sec": round(self._last_process_sec, 2),
                "record_sec_target": self.record_sec,
                "process_budget_sec": self.process_budget_sec,
                "ingest_fps": self.ingest_fps,
                "last_error": self._last_error,
            }

    def _cycle_loop(self) -> None:
        while not self._stop.is_set():
            try:
                segment = self._record_segment()
                if segment is None:
                    time.sleep(self.reconnect_delay)
                    continue
                self._process_segment(segment)
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("Segment cycle error for %s", self.camera_id)
                time.sleep(self.reconnect_delay)

    def _record_segment(self) -> RecordedSegment | None:
        with self._lock:
            self._state = SegmentState.RECORDING
            self._cycle += 1
            cycle_id = f"{self._cycle}-{uuid.uuid4().hex[:8]}"
        cycle_path = os.path.join(self._segment_dir, f"{cycle_id}.mp4")
        min_interval = 1.0 / max(self.ingest_fps, 1.0)
        segment_start_mono = time.monotonic()
        segment_start_wall = time.time()
        frames: list[np.ndarray] = []
        cap: cv2.VideoCapture | None = None
        source_fps = 25.0
        try:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                self._last_error = f"cannot open {self.rtsp_url}"
                return None
            fps_val = cap.get(cv2.CAP_PROP_FPS)
            if fps_val and fps_val > 1:
                source_fps = float(fps_val)
            deadline = segment_start_mono + self.record_sec
            last_capture = 0.0
            while not self._stop.is_set() and time.monotonic() < deadline:
                ok, frame = cap.read()
                if not ok or frame is None:
                    self._last_error = "frame read failed during record"
                    break
                now = time.monotonic()
                if now - last_capture < min_interval:
                    continue
                last_capture = now
                frames.append(frame.copy())
            if len(frames) < 2:
                self._last_error = "segment too short"
                return None
            if not self._export_segment_mp4(frames, cycle_path, self.ingest_fps):
                self._last_error = "segment mp4 export failed"
                return None
            duration = len(frames) / max(self.ingest_fps, 1.0)
            probed = probe_media_duration(cycle_path)
            if probed is not None and probed > 0:
                duration = probed
            with self._lock:
                self._frames_recorded = len(frames)
                self._last_record_sec = time.monotonic() - segment_start_mono
                self._last_error = None
            return RecordedSegment(
                path=cycle_path,
                cycle_id=cycle_id,
                frame_count=len(frames),
                duration_sec=duration,
                source_fps=source_fps,
                segment_start_mono=segment_start_mono,
                segment_start_wall=segment_start_wall,
            )
        finally:
            if cap is not None:
                cap.release()

    def _export_segment_mp4(self, frames: list[np.ndarray], out_path: str, fps: float) -> bool:
        if not shutil.which("ffmpeg"):
            logger.error("ffmpeg required for segment export")
            return False
        tmp = tempfile.mkdtemp(prefix="cv_seg_frames_")
        try:
            for i, img in enumerate(frames):
                path = os.path.join(tmp, f"frame_{i:05d}.jpg")
                if not cv2.imwrite(path, img):
                    return False
            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(int(round(fps)) or 12),
                "-i", os.path.join(tmp, "frame_%05d.jpg"),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-preset", "veryfast",
                out_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            if result.returncode != 0:
                logger.warning("segment export ffmpeg: %s", result.stderr[-400:])
                return False
            return os.path.isfile(out_path) and os.path.getsize(out_path) > 256
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _prepare_evidence_copy(self, src: str) -> str:
        """Dedicated MP4 copy for ffmpeg clip cuts while OpenCV replays the original."""
        dst = f"{src}.evidence.mp4"
        try:
            src_sz = os.path.getsize(src)
        except OSError:
            return src
        for _ in range(3):
            try:
                shutil.copy2(src, dst)
                if os.path.getsize(dst) >= max(256, int(src_sz * 0.9)):
                    return dst
            except OSError:
                time.sleep(0.05)
        logger.warning("evidence copy failed for %s — sharing replay file for clips", src)
        return src

    def _process_segment(self, segment: RecordedSegment) -> None:
        with self._lock:
            self._state = SegmentState.PROCESSING
        process_start = time.monotonic()
        evidence_path = self._prepare_evidence_copy(segment.path)
        cap = cv2.VideoCapture(segment.path)
        if not cap.isOpened():
            self._last_error = f"cannot open segment {segment.path}"
            self._cleanup_segment(segment.path)
            return
        if self.begin_replay_fn is not None:
            self.begin_replay_fn(self.camera_id)
        # Local import: pipeline imports ingest at module load (circular otherwise).
        from citevision_ai.pipeline import priority_zone_skip

        skip = priority_zone_skip(segment.source_fps)
        frame_index = 0
        replay_index = 0
        try:
            while not self._stop.is_set():
                if time.monotonic() - process_start > self.process_budget_sec:
                    logger.warning(
                        "segment process budget exceeded cam=%s cycle=%s",
                        self.camera_id[:8], segment.cycle_id,
                    )
                    break
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if replay_index % skip != 0:
                    replay_index += 1
                    frame_index += 1
                    continue
                replay_index += 1
                pts = min(
                    frame_index / max(self.ingest_fps, 1.0),
                    segment.duration_sec - 0.01,
                )
                timeline = FrameTimeline.from_segment_start(
                    segment.segment_start_mono, segment.segment_start_wall, pts,
                )
                ctx = SegmentCaptureContext(
                    segment_path=evidence_path,
                    cycle_id=segment.cycle_id,
                    frame_index=frame_index,
                    frame_pts=pts,
                    segment_start_wall=segment.segment_start_wall,
                    ingest_fps=self.ingest_fps,
                )
                self.process_fn(
                    self.camera_id,
                    frame,
                    segment.source_fps,
                    timeline=timeline,
                    segment_ctx=ctx,
                )
                frame_index += 1
            cap.release()
            cap = None
            evidence_dur = probe_media_duration(evidence_path) or segment.duration_sec
            eof_pts = max(0.0, evidence_dur - 0.05)
            eof_timeline = FrameTimeline.from_segment_start(
                segment.segment_start_mono,
                segment.segment_start_wall,
                eof_pts,
            )
            eof_ctx = SegmentCaptureContext(
                segment_path=evidence_path,
                cycle_id=segment.cycle_id,
                frame_index=max(0, frame_index - 1),
                frame_pts=eof_pts,
                segment_start_wall=segment.segment_start_wall,
                ingest_fps=self.ingest_fps,
            )
            if self.eof_flush_fn is not None:
                self.eof_flush_fn(
                    self.camera_id, eof_timeline, eof_ctx, segment.source_fps,
                )
        finally:
            if cap is not None:
                cap.release()
            elapsed = time.monotonic() - process_start
            with self._lock:
                self._frames_processed = frame_index
                self._last_process_sec = elapsed
                self._state = SegmentState.IDLE
            time.sleep(2.0)
            self._cleanup_segment(segment.path)
            if evidence_path != segment.path:
                self._cleanup_segment(evidence_path)

    def _cleanup_segment(self, path: str) -> None:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            logger.warning("failed to remove segment %s", path)
