"""Evidence clip export produces browser-playable H.264 MP4 when ffmpeg is available."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from citevision_ai.evidence.buffer import FrameRingBuffer, BufferedFrame


def _solid_frame(b: int, g: int, r: int) -> np.ndarray:
    img = np.zeros((48, 64, 3), dtype=np.uint8)
    img[:, :] = (b, g, r)
    return img


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_export_clip_mp4_h264(tmp_path: Path):
    buf = FrameRingBuffer(max_seconds=10, fps=5)
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (128, 128, 0), (0, 128, 128)]):
        ok, enc = cv2.imencode(".jpg", _solid_frame(*color))
        assert ok
        buf._frames.append(BufferedFrame(jpeg=enc.tobytes(), ts=float(i)))
    buf._last_push = 5.0

    clip = buf.export_clip_mp4(duration_sec=2.0, fps=5)
    assert clip is not None
    data = clip.data
    assert len(data) > 256
    assert b"ftyp" in data[:32]

    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(data)
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name", "-of", "default=nw=1",
            str(clip_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    assert "h264" in probe.stdout.lower()


def test_export_clip_min_two_unique_frames():
    """Single-frame buffers must not produce a duplicate-frame slideshow."""
    buf = FrameRingBuffer(max_seconds=10, fps=5)
    ok, enc = cv2.imencode(".jpg", _solid_frame(100, 100, 100))
    assert ok
    buf._frames.append(BufferedFrame(jpeg=enc.tobytes(), ts=1.0))
    buf._last_push = 1.0

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    assert buf.export_clip_mp4(duration_sec=6.0, fps=5) is None


def test_export_clip_centered_on_event_ts():
    buf = FrameRingBuffer(max_seconds=10, fps=5)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (128, 128, 0), (0, 128, 128), (64, 64, 64)]
    for i, color in enumerate(colors):
        ok, enc = cv2.imencode(".jpg", _solid_frame(*color))
        assert ok
        buf._frames.append(BufferedFrame(jpeg=enc.tobytes(), ts=float(i)))
    buf._last_push = 5.0

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    clip = buf.export_clip_mp4(duration_sec=2.0, fps=5, center_ts=2.0)
    assert clip is not None
    assert clip.frame_count >= 2
    assert clip.frame_count <= 6


def test_get_frame_at_ts_picks_closest():
    buf = FrameRingBuffer(max_seconds=10, fps=5)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for i, color in enumerate(colors):
        ok, enc = cv2.imencode(".jpg", _solid_frame(*color))
        assert ok
        buf._frames.append(BufferedFrame(jpeg=enc.tobytes(), ts=float(i + 1)))
    frame = buf.get_frame_at_ts(2.1)
    assert frame is not None
    assert frame.shape[0] == 48
