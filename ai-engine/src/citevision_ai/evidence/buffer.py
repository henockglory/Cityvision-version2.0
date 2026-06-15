from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class BufferedFrame:
    jpeg: bytes
    ts: float


class FrameRingBuffer:
    """Rolling JPEG frame buffer per camera (~10s at 5 fps)."""

    def __init__(self, max_seconds: float = 10.0, fps: int = 5, jpeg_quality: int = 82) -> None:
        self.max_seconds = max_seconds
        self.min_interval = 1.0 / max(fps, 1)
        self.jpeg_quality = jpeg_quality
        self._frames: deque[BufferedFrame] = deque()
        self._last_push: float = 0.0

    def maybe_push(self, frame: np.ndarray) -> None:
        now = time.time()
        if now - self._last_push < self.min_interval:
            return
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if not ok:
            return
        self._frames.append(BufferedFrame(jpeg=buf.tobytes(), ts=now))
        self._last_push = now
        cutoff = now - self.max_seconds
        while self._frames and self._frames[0].ts < cutoff:
            self._frames.popleft()

    def export_clip_mp4(self, duration_sec: float = 6.0, fps: int = 5) -> bytes | None:
        if not self._frames:
            return None
        frames_bgr: list[np.ndarray] = []
        for bf in self._frames:
            arr = np.frombuffer(bf.jpeg, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                frames_bgr.append(img)
        if not frames_bgr:
            return None
        max_frames = int(duration_sec * fps)
        if len(frames_bgr) > max_frames:
            frames_bgr = frames_bgr[-max_frames:]
        h, w = frames_bgr[0].shape[:2]
        import tempfile
        import os

        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(tmp_path, fourcc, float(fps), (w, h))
            if not writer.isOpened():
                return None
            for img in frames_bgr:
                writer.write(img)
            writer.release()
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
