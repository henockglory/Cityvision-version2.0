"""Segment replay helpers — kept separate to avoid ingest/service circular imports."""

from __future__ import annotations

from typing import Any

import numpy as np


def segment_pts_from_frame_index(frame_index: int | None, ingest_fps: float) -> float | None:
    if frame_index is None:
        return None
    try:
        return max(0.0, float(int(frame_index)) / max(float(ingest_fps), 1.0))
    except (TypeError, ValueError):
        return None


def segment_pts_from_bbox_ts(bbox_ts: float | None, segment_start_wall: float) -> float | None:
    """Map a wall-clock bbox timestamp to seconds within the segment MP4."""
    if bbox_ts is None or not segment_start_wall:
        return None
    try:
        return max(0.0, float(bbox_ts) - float(segment_start_wall))
    except (TypeError, ValueError):
        return None


def read_segment_frame_by_index(
    segment_path: str,
    frame_index: int,
    width: int = 1920,
    height: int = 1080,
):
    """Load a BGR frame by zero-based index (matches segment replay cap.read() order)."""
    import cv2

    try:
        cap = cv2.VideoCapture(segment_path)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_index)))
            ok, frame = cap.read()
            cap.release()
            if ok and frame is not None:
                return frame
    except Exception:
        pass
    return np.zeros((height, width, 3), dtype=np.uint8)


def read_segment_frame_bgr(
    segment_path: str,
    frame_pts: float,
    width: int = 1920,
    height: int = 1080,
):
    """Load a BGR frame from a segment MP4 at the given PTS (seconds)."""
    import cv2

    try:
        cap = cv2.VideoCapture(segment_path)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(frame_pts)) * 1000.0)
            ok, frame = cap.read()
            cap.release()
            if ok and frame is not None:
                return frame
    except Exception:
        pass
    return np.zeros((height, width, 3), dtype=np.uint8)


def resolve_segment_capture_frame(
    frame,
    segment_path: str | None,
    evt: dict[str, Any],
    capture_pts: float,
    width: int = 1920,
    height: int = 1080,
    *,
    current_frame_index: int | None = None,
):
    """Pick the evidence frame aligned to segment_bbox_frame_index, not replay tick."""
    want_idx: int | None = None
    raw_idx = evt.get("segment_bbox_frame_index")
    if raw_idx is not None:
        try:
            want_idx = int(raw_idx)
        except (TypeError, ValueError):
            want_idx = None

    aligned_with_replay = (
        want_idx is None
        or current_frame_index is None
        or want_idx == int(current_frame_index)
    )
    if aligned_with_replay and frame is not None and getattr(frame, "size", 0) > 0 and frame.any():
        return frame

    if segment_path and want_idx is not None:
        by_index = read_segment_frame_by_index(segment_path, want_idx, width, height)
        if by_index is not None and by_index.any():
            return by_index

    if segment_path:
        by_pts = read_segment_frame_bgr(segment_path, capture_pts, width, height)
        if by_pts is not None and by_pts.any():
            return by_pts

    if aligned_with_replay and frame is not None:
        return frame
    if segment_path:
        return read_segment_frame_bgr(segment_path, capture_pts, width, height)
    return frame
