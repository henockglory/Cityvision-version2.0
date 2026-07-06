"""Video quality incident events (blur / darkness)."""
from __future__ import annotations

import numpy as np

from citevision_ai.pipeline import PipelineService


def _pipe() -> PipelineService:
    pipe = PipelineService.__new__(PipelineService)
    pipe._blur_streak = {}
    return pipe


def _run_quality_sequence(pipe: PipelineService, camera_id: str, frames: list[np.ndarray]) -> list[dict]:
    """Feed a multi-frame sequence through the video quality chain."""
    events: list[dict] = []
    for i, frame in enumerate(frames):
        events.extend(pipe._check_video_quality(camera_id, frame, f"2026-01-01T00:00:0{i}Z"))
    return events


def test_video_darkness_emitted_on_black_frame() -> None:
    pipe = _pipe()
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    events = pipe._check_video_quality("cam1", black, "2026-01-01T00:00:00Z")
    types = {e["event_type"] for e in events}
    assert "video_darkness" in types


def test_video_blur_emitted_on_uniform_frame() -> None:
    pipe = _pipe()
    uniform = np.full((240, 320, 3), 128, dtype=np.uint8)
    events = _run_quality_sequence(pipe, "cam1", [uniform, uniform])
    types = {e["event_type"] for e in events}
    assert "video_blur" in types


def test_video_quality_ok_on_sharp_frame() -> None:
    pipe = _pipe()
    sharp = np.full((240, 320, 3), 160, dtype=np.uint8)
    sharp[::3, ::3] = 255
    sharp[1::3, 2::3] = 80
    events = pipe._check_video_quality("cam1", sharp, "2026-01-01T00:00:00Z")
    types = {e["event_type"] for e in events}
    assert "video_blur" not in types
    assert "video_darkness" not in types


def test_video_blur_j86_multi_frame_sequence_stub() -> None:
    """J.86: blur detection requires 2+ consecutive blurry frames."""
    pipe = _pipe()
    uniform = np.full((240, 320, 3), 128, dtype=np.uint8)
    sharp = np.full((240, 320, 3), 160, dtype=np.uint8)
    sharp[::3, ::3] = 255
    sharp[1::3, 2::3] = 80

    first_only = _run_quality_sequence(pipe, "cam-one", [uniform])
    assert "video_blur" not in {e["event_type"] for e in first_only}

    two_blurry = _run_quality_sequence(pipe, "cam-two", [uniform, uniform])
    blur_events = [e for e in two_blurry if e["event_type"] == "video_blur"]
    assert len(blur_events) == 1
    assert blur_events[0]["metadata"]["frame_streak"] == 2

    reset = _run_quality_sequence(pipe, "cam-reset", [uniform, sharp, uniform])
    assert sum(1 for e in reset if e["event_type"] == "video_blur") == 0

    after_reset = _run_quality_sequence(pipe, "cam-after", [uniform, uniform])
    assert any(e["event_type"] == "video_blur" for e in after_reset)
