"""Co-emission bbox: track YOLO/ByteTrack on the inference frame wins."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from citevision_ai.evidence.capture import (
    resolve_emission_track_bbox,
    subject_jpeg_texture,
)


def test_emission_track_wins_over_event_bbox():
    evt = {
        "track_id": 7,
        "bbox": {"x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1},
        "bbox_ts": 1000.0,
    }
    tracks = [{"track_id": 7, "bbox": {"x": 0.7, "y": 0.7, "width": 0.2, "height": 0.2}}]
    bb, ts, src = resolve_emission_track_bbox(evt, tracks, 1920, 1080, 1003.0)
    assert src == "emission_track"
    assert abs(bb["x"] - 0.7) < 1e-6
    assert ts == 1003.0


def test_last_known_fallback_when_track_absent():
    evt = {"track_id": 5, "bbox": {"x": 0.1, "y": 0.1, "width": 0.05, "height": 0.05}}
    last_fb = {"bbox": {"x": 0.4, "y": 0.4, "width": 0.15, "height": 0.15}, "ts": 999.0}
    bb, ts, src = resolve_emission_track_bbox(
        evt, [], 1920, 1080, 1001.0, last_bbox_fallback=last_fb,
    )
    assert src == "last_known"
    assert abs(bb["x"] - 0.4) < 1e-6
    assert ts == 1001.0


def test_event_fallback_when_no_track_or_last():
    evt = {"track_id": 9, "bbox": {"x": 0.5, "y": 0.5, "width": 0.12, "height": 0.12}}
    bb, ts, src = resolve_emission_track_bbox(evt, [], 1920, 1080, 888.0)
    assert src == "event_fallback"
    assert bb is not None
    assert ts == 888.0


def test_none_when_no_valid_bbox():
    evt = {"track_id": 1}
    bb, ts, src = resolve_emission_track_bbox(evt, [], 1920, 1080, 1.0)
    assert src == "none"
    assert bb is None
    assert ts is None


def test_subject_jpeg_texture_on_textured_crop():
    img = np.full((120, 160, 3), 128, dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (140, 100), (30, 30, 190), -1)
    ok, enc = cv2.imencode(".jpg", img)
    assert ok
    tex = subject_jpeg_texture(enc.tobytes())
    assert tex is not None and tex >= 50.0


def test_subject_jpeg_texture_on_uniform_crop():
    img = np.full((120, 160, 3), 128, dtype=np.uint8)
    ok, enc = cv2.imencode(".jpg", img)
    assert ok
    tex = subject_jpeg_texture(enc.tobytes())
    assert tex is not None and tex < 50.0
