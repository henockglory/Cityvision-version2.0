"""Tests for segment cycle mode (timeline + clip extraction)."""

from __future__ import annotations

import os
import shutil
import tempfile

import cv2
import numpy as np
import pytest

from citevision_ai.evidence.service import extract_subclip_mp4
from citevision_ai.evidence.segment_align import segment_pts_from_bbox_ts, segment_pts_from_frame_index
from citevision_ai.ingest.timeline import FrameTimeline, SegmentCaptureContext


def test_frame_timeline_from_segment_start():
    tl = FrameTimeline.from_segment_start(1000.0, 2000.0, 3.5)
    assert tl.monotonic == 1003.5
    assert tl.wall == 2003.5
    assert tl.video_pts == 3.5
    assert tl.iso_timestamp is not None


def test_segment_capture_context_fields():
    ctx = SegmentCaptureContext(
        segment_path="/tmp/x.mp4",
        cycle_id="1-abc",
        frame_index=42,
        frame_pts=4.2,
        segment_start_wall=2000.0,
    )
    assert ctx.frame_pts == 4.2
    assert ctx.segment_start_wall == 2000.0


def test_resolve_segment_capture_frame_loads_index_when_replay_differs():
    from citevision_ai.evidence.segment_align import resolve_segment_capture_frame

    replay = np.full((48, 64, 3), 120, dtype=np.uint8)
    evt = {"segment_bbox_frame_index": 99, "segment_bbox_pts": 8.0}
    out = resolve_segment_capture_frame(
        replay, "/nonexistent.mp4", evt, 8.0, current_frame_index=50,
    )
    assert out is not replay
    assert int(out.mean()) == 0


def test_resolve_segment_capture_frame_keeps_replay_when_index_matches():
    from citevision_ai.evidence.segment_align import resolve_segment_capture_frame

    replay = np.full((48, 64, 3), 120, dtype=np.uint8)
    evt = {"segment_bbox_frame_index": 50, "segment_bbox_pts": 4.0}
    out = resolve_segment_capture_frame(
        replay, "/nonexistent.mp4", evt, 4.0, current_frame_index=50,
    )
    assert out is replay


def test_segment_pts_from_bbox_ts():
    assert segment_pts_from_bbox_ts(2003.5, 2000.0) == 3.5
    assert segment_pts_from_bbox_ts(None, 2000.0) is None
    assert segment_pts_from_bbox_ts(2003.5, 0.0) is None


def test_segment_pts_from_frame_index():
    assert segment_pts_from_frame_index(24, 12.0) == 2.0
    assert segment_pts_from_frame_index(None, 12.0) is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_extract_subclip_from_segment_mp4():
    tmp = tempfile.mkdtemp()
    seg = os.path.join(tmp, "seg.mp4")
    try:
        writer = cv2.VideoWriter(
            seg,
            cv2.VideoWriter_fourcc(*"mp4v"),
            12,
            (64, 48),
        )
        for i in range(120):
            img = np.full((48, 64, 3), (i % 256, 40, 40), dtype=np.uint8)
            writer.write(img)
        writer.release()
        if not os.path.isfile(seg) or os.path.getsize(seg) < 256:
            pytest.skip("VideoWriter mp4 not available")
        clip = extract_subclip_mp4(seg, center_pts=5.0, duration_sec=4.0)
        assert clip is not None
        assert len(clip) > 256
        assert b"ftyp" in clip[:32]
        # Clamping: center past end must still yield a valid clip.
        tail = extract_subclip_mp4(seg, center_pts=99.0, duration_sec=6.0)
        assert tail is not None
        assert len(tail) > 256
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
