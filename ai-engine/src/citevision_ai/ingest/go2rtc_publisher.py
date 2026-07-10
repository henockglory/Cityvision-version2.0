from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from typing import Any

import cv2
import numpy as np

from citevision_ai.config import settings

logger = logging.getLogger(__name__)


class Go2rtcPublisher:
    """Publish BGR frames to go2rtc RTSP server (single upstream decode path)."""

    def __init__(
        self,
        stream_name: str,
        width: int,
        height: int,
        fps: float,
    ) -> None:
        self.stream_name = stream_name
        self._src_w = int(width)
        self._src_h = int(height)
        self._fps = max(5.0, min(float(fps), 30.0))
        self._out_w, self._out_h = self._scaled_size(self._src_w, self._src_h)
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._frames_written = 0
        self._last_error: str | None = None

    @staticmethod
    def _scaled_size(width: int, height: int) -> tuple[int, int]:
        max_w = max(320, int(settings.go2rtc_publish_max_width))
        if width <= max_w:
            return width, height
        scale = max_w / width
        return max_w, max(1, int(height * scale))

    def start(self) -> None:
        if self._process is not None:
            return
        if shutil.which("ffmpeg") is None:
            self._last_error = "ffmpeg not found"
            logger.error("Go2rtcPublisher: ffmpeg missing")
            return
        gop = max(1, int(self._fps))
        url = (
            f"rtsp://{settings.go2rtc_rtsp_host}:{settings.go2rtc_rtsp_port}"
            f"/{self.stream_name}"
        )
        cmd = [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{self._out_w}x{self._out_h}",
            "-r", str(self._fps),
            "-i", "pipe:0",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-profile:v", "baseline", "-pix_fmt", "yuv420p",
            "-g", str(gop), "-keyint_min", str(gop), "-bf", "0", "-sc_threshold", "0",
            "-f", "rtsp", "-rtsp_transport", "tcp",
            url,
        ]
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(
                "Go2rtcPublisher started stream=%s %dx%d@%sfps → %s",
                self.stream_name, self._out_w, self._out_h, self._fps, url,
            )
        except OSError as exc:
            self._last_error = str(exc)
            logger.exception("Go2rtcPublisher start failed for %s", self.stream_name)

    def write_frame(self, frame: np.ndarray) -> bool:
        proc = self._process
        if proc is None or proc.stdin is None:
            return False
        if proc.poll() is not None:
            self._last_error = "ffmpeg exited"
            self._process = None
            return False
        try:
            out = frame
            if frame.shape[1] != self._out_w or frame.shape[0] != self._out_h:
                out = cv2.resize(frame, (self._out_w, self._out_h))
            with self._lock:
                proc.stdin.write(out.tobytes())
                proc.stdin.flush()
            self._frames_written += 1
            return True
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._last_error = str(exc)
            return False

    def stop(self) -> None:
        proc = self._process
        self._process = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        logger.info(
            "Go2rtcPublisher stopped stream=%s frames=%d",
            self.stream_name, self._frames_written,
        )

    def status(self) -> dict[str, Any]:
        alive = self._process is not None and self._process.poll() is None
        return {
            "stream_name": self.stream_name,
            "running": alive,
            "frames_written": self._frames_written,
            "out_width": self._out_w,
            "out_height": self._out_h,
            "fps": self._fps,
            "last_error": self._last_error,
        }
