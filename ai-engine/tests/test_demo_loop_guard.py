"""demo_loop_guard — reject stale Frigate events across demo loop iterations."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from citevision_ai.evidence.frigate_timeline import (
    demo_loop_absolute_align_ok,
    same_demo_loop_cycle,
)
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence


def test_absolute_align_ok():
    assert demo_loop_absolute_align_ok(0.4, 30.0) is True
    assert demo_loop_absolute_align_ok(720.444, 30.0) is False


def test_same_demo_loop_cycle_rejects_full_loop_gap():
    loop = 352.52
    t0 = 1_700_000_000.0
    assert same_demo_loop_cycle(t0, t0 + 5.0, loop) is True
    assert same_demo_loop_cycle(t0, t0 + loop, loop) is False
    assert same_demo_loop_cycle(t0, t0 + 2 * loop, loop) is False


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_accept_rejects_720s_delta_under_demo_loop_guard(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.demo_red_light_loop_sec = 352.52
    mock_settings.frigate_demo_accept_max_align_sec = 30.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12

    engine = FrigateTrackEvidence()
    anchor = 1_784_483_713.0 + 720.444
    evt = {
        "event_type": "speeding",
        "bbox_ts": anchor,
        "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        "frigate_event_id": "1784483713.108543-spihzy",  # bound trust must NOT bypass
        "class_name": "car",
    }
    matched = {
        "id": "1784483713.108543-spihzy",
        "label": "car",
        "start_time": 1_784_483_713.108543,
        "data": {"box": [0.2, 0.3, 0.2, 0.2]},
    }
    assert engine._accept_correlation(evt, matched, 720.444, "cam-speed") is False


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_accept_allows_tight_delta_under_demo_loop_guard(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.demo_red_light_loop_sec = 352.52
    mock_settings.frigate_demo_accept_max_align_sec = 30.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12

    engine = FrigateTrackEvidence()
    t0 = 1_784_483_713.0
    evt = {
        "event_type": "speeding",
        "bbox_ts": t0 + 0.5,
        "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        "class_name": "car",
    }
    matched = {
        "id": "fresh-ev",
        "label": "car",
        "start_time": t0,
        "data": {"box": [0.2, 0.3, 0.2, 0.2]},
    }
    assert engine._accept_correlation(evt, matched, 0.5, "cam-speed") is True


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_soft_red_does_not_widen_align_window(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.demo_red_light_loop_sec = 352.52
    mock_settings.frigate_demo_accept_max_align_sec = 30.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12
    mock_settings.demo_mode_source = "test"

    engine = FrigateTrackEvidence()
    t0 = 1_784_483_713.0
    evt = {
        "event_type": "red_light_violation",
        "bbox_ts": t0 + 90.0,
        "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        "metadata": {"frigate_red_light_soft_iou": -1.0},
        "class_name": "car",
    }
    matched = {
        "id": "stale-red",
        "label": "car",
        "start_time": t0,
        "data": {"box": [0.2, 0.3, 0.2, 0.2]},
    }
    # 90s > RED_LIGHT_MAX_ALIGN_SEC (8) and > would-be soft bypass
    assert engine._accept_correlation(evt, matched, 90.0, "cam-feux") is False
