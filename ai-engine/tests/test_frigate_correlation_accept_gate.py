"""Unit tests for Frigate correlation accept gate (align <= 5s)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_accept_correlation_rejects_large_align(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = False
    mock_settings.demo_relaxed_evidence = lambda: False
    mock_settings.frigate_demo_accept_max_align_sec = 5.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = False
    svc = FrigateTrackEvidence()
    evt = {
        "bbox_ts": 1009.0,
        "bbox": {"x1": 0.05, "y1": 0.05, "x2": 0.15, "y2": 0.15},
        "class_name": "car",
    }
    matched = {"id": "e1", "start_time": 1000.0, "data": {"box": [100, 100, 200, 200]}}
    assert svc._accept_correlation(evt, matched, 9.0, "") is False


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_accept_correlation_accepts_tight_align(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = False
    mock_settings.demo_relaxed_evidence = lambda: False
    mock_settings.frigate_demo_accept_max_align_sec = 5.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = False
    svc = FrigateTrackEvidence()
    evt = {
        "bbox_ts": 1000.4,
        "bbox": {"x": 0.05, "y": 0.05, "width": 0.1, "height": 0.1},
        "class_name": "car",
    }
    matched = {"id": "e1", "start_time": 1000.0, "data": {"box": [0.05, 0.05, 0.1, 0.1]}}
    assert svc._accept_correlation(evt, matched, 0.4, "") is True
