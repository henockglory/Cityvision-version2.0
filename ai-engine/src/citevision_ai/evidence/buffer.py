from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _downscale_frames(
    frames: list[np.ndarray],
    max_width: int = 1280,
    max_height: int = 720,
) -> list[np.ndarray]:
    """Resize frames so they fit within max_width×max_height (keeps aspect ratio).

    Dramatically speeds up ffmpeg H.264 encoding on 4K camera sources.
    """
    if not frames:
        return frames
    h, w = frames[0].shape[:2]
    if w <= max_width and h <= max_height:
        return frames
    scale = min(max_width / w, max_height / h)
    new_w = int(w * scale) & ~1   # ensure even for yuv420p
    new_h = int(h * scale) & ~1
    return [cv2.resize(f, (new_w, new_h), interpolation=cv2.INTER_AREA) for f in frames]


@dataclass
class BufferedFrame:
    jpeg: bytes
    ts: float


@dataclass
class ClipExport:
    data: bytes
    duration_sec: float
    frame_count: int


class FrameRingBuffer:
    """Rolling JPEG frame buffer per camera (~10s at 5 fps).

    Thread-safe: the main ingest loop calls ``maybe_push`` while background
    evidence threads call ``export_clip_mp4`` / ``get_frame_at_ts``.  A simple
    RLock protects all deque mutations and reads.
    """

    def __init__(self, max_seconds: float = 10.0, fps: int = 5, jpeg_quality: int = 82) -> None:
        self.max_seconds = max_seconds
        self.min_interval = 1.0 / max(fps, 1)
        self.jpeg_quality = jpeg_quality
        self.fps = fps
        self._frames: deque[BufferedFrame] = deque()
        self._last_push: float = 0.0
        self._last_bgr: np.ndarray | None = None
        self._lock = threading.RLock()

    def maybe_push(self, frame: np.ndarray) -> None:
        now = time.time()
        if now - self._last_push < self.min_interval:
            return
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if not ok:
            return
        with self._lock:
            self._frames.append(BufferedFrame(jpeg=buf.tobytes(), ts=now))
            self._last_push = now
            cutoff = now - self.max_seconds
            while self._frames and self._frames[0].ts < cutoff:
                self._frames.popleft()
            self._last_bgr = frame.copy()

    def _decode_frame(self, bf: BufferedFrame) -> np.ndarray | None:
        arr = np.frombuffer(bf.jpeg, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def get_last_frame(self) -> np.ndarray | None:
        with self._lock:
            if self._last_bgr is not None:
                return self._last_bgr.copy()
            if not self._frames:
                return None
            return self._decode_frame(self._frames[-1])

    def get_frame_at_ts(self, event_ts: float | None) -> np.ndarray | None:
        """Return frame closest to event timestamp, or last frame."""
        with self._lock:
            if not self._frames:
                return self.get_last_frame()
            if event_ts is None or event_ts <= 0:
                return self.get_last_frame()
            snapshot = list(self._frames)
        best = min(snapshot, key=lambda f: abs(f.ts - event_ts))
        img = self._decode_frame(best)
        return img if img is not None else self.get_last_frame()

    def get_frames_near_ts(
        self, target_ts: float, max_frames: int = 6,
    ) -> list[tuple[np.ndarray, float]]:
        """Frames closest to ``target_ts``, nearest first (quality-guard retries)."""
        with self._lock:
            snapshot = list(self._frames)
        if not snapshot:
            return []
        snapshot.sort(key=lambda f: abs(f.ts - target_ts))
        out: list[tuple[np.ndarray, float]] = []
        for bf in snapshot[:max_frames]:
            img = self._decode_frame(bf)
            if img is not None:
                out.append((img, bf.ts))
        return out

    def export_clip_mp4(
        self,
        duration_sec: float = 6.0,
        fps: int | None = None,
        center_ts: float | None = None,
    ) -> ClipExport | None:
        """Export an H.264 clip from the ring buffer.

        When ``center_ts`` is set (typically ``bbox_ts``), the clip is a real-time
        window centred on the violation — not the last N stale frames.  Duplicate-
        frame padding is never applied: a slideshow of 2–3 frozen JPEGs was the
        root cause of "video = combien de photos" reports.
        """
        with self._lock:
            if not self._frames:
                return None
            snapshot = list(self._frames)
        use_fps = fps or self.fps
        target_frames = max(4, int(duration_sec * use_fps))

        if center_ts is not None:
            half = duration_sec / 2.0
            selected = [bf for bf in snapshot if (center_ts - half) <= bf.ts <= (center_ts + half)]
            if len(selected) < 4:
                best_idx = min(range(len(snapshot)), key=lambda i: abs(snapshot[i].ts - center_ts))
                start = max(0, best_idx - target_frames // 2)
                end = min(len(snapshot), start + target_frames)
                start = max(0, end - target_frames)
                selected = snapshot[start:end]
        else:
            selected = snapshot[-target_frames:] if len(snapshot) > target_frames else snapshot

        # Downscale each frame immediately after decoding to avoid holding all
        # full-resolution (e.g. 4K) arrays simultaneously — prevents OOM when
        # 4+ concurrent evidence threads each decompress ~144 frames × 25 MB.
        _MAX_W, _MAX_H = 1280, 720
        frames_bgr: list[np.ndarray] = []
        timestamps: list[float] = []
        for bf in selected:
            img = self._decode_frame(bf)
            if img is not None:
                h, w = img.shape[:2]
                if w > _MAX_W or h > _MAX_H:
                    scale = min(_MAX_W / w, _MAX_H / h)
                    nw = int(w * scale) & ~1
                    nh = int(h * scale) & ~1
                    img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
                frames_bgr.append(img)
                timestamps.append(bf.ts)
        if len(frames_bgr) < 2:
            return None

        span = timestamps[-1] - timestamps[0]
        if span >= 0.08:
            out_fps = min(float(use_fps), max(4.0, (len(frames_bgr) - 1) / span))
        else:
            out_fps = float(use_fps)

        if shutil.which("ffmpeg"):
            # Frames are already downscaled above — skip redundant pass.
            pass
            data = self._export_h264_ffmpeg(frames_bgr, int(round(out_fps)) or 4)
            if data is None:
                return None
            actual_dur = (len(frames_bgr) - 1) / max(out_fps, 1) if len(frames_bgr) > 1 else 1.0 / max(out_fps, 1)
            return ClipExport(data=data, duration_sec=round(actual_dur, 2), frame_count=len(frames_bgr))

        logger.warning("ffmpeg not found — evidence clip skipped (browser requires H.264)")
        return None

    def _export_h264_ffmpeg(self, frames_bgr: list[np.ndarray], fps: int) -> bytes | None:
        tmp_dir = tempfile.mkdtemp(prefix="cv_evidence_")
        out_path = os.path.join(tmp_dir, "clip.mp4")
        try:
            for i, img in enumerate(frames_bgr):
                path = os.path.join(tmp_dir, f"frame_{i:04d}.jpg")
                if not cv2.imwrite(path, img):
                    return None
            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", os.path.join(tmp_dir, "frame_%04d.jpg"),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-preset", "veryfast",
                "-tune", "zerolatency",
                out_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                logger.warning("ffmpeg evidence clip failed: %s", result.stderr[-500:])
                return None
            with open(out_path, "rb") as f:
                data = f.read()
            if len(data) < 256:
                return None
            return data
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("ffmpeg evidence clip error: %s", exc)
            return None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
