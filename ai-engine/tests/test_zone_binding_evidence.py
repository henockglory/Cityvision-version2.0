"""Zone-containment Frigate binding for road evidence (no IA soft-accept)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from citevision_ai.evidence.frigate_track_evidence import (
    FrigateTrackEvidence,
    _frigate_in_binding_zone,
    _point_in_polygon,
    _subject_binding_zone,
)


# Square observation zone covering right half of frame.
_ZONE = [
    {"x": 0.5, "y": 0.0},
    {"x": 1.0, "y": 0.0},
    {"x": 1.0, "y": 1.0},
    {"x": 0.5, "y": 1.0},
]


def _road_evt(*, in_zone_box=True, with_zone=True):
    # IA box anywhere — identity must come from Frigate+zone, not IA IoU.
    bbox = {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}
    meta: dict = {}
    if with_zone:
        meta["subject_binding_zone"] = {
            "zone_id": "obs-1",
            "behavior": "red_light_observation",
            "polygon": _ZONE,
            "anchor": "bottom_085",
        }
    return {
        "event_type": "red_light_violation",
        "bbox_ts": 1000.0,
        "bbox": bbox,
        "class_name": "car",
        "metadata": meta,
    }


def _frigate(*, box, start=1000.2, eid="e1"):
    return {"id": eid, "label": "car", "start_time": start, "data": {"box": list(box)}}


def test_point_in_polygon_basic():
    assert _point_in_polygon(0.75, 0.5, _ZONE) is True
    assert _point_in_polygon(0.25, 0.5, _ZONE) is False


def test_point_in_polygon_trapezoid_downward_edges():
    """Regression: denom must keep sign (max(yj-yi, eps) broke real demo zones)."""
    trap = [
        {"x": 0.0116, "y": 0.3357},
        {"x": 0.9902, "y": 0.3643},
        {"x": 0.9366, "y": 0.9833},
        {"x": 0.0130, "y": 0.9833},
    ]
    assert _point_in_polygon(0.5, 0.5, trap) is True
    assert _point_in_polygon(0.711, 0.47, trap) is True
    assert _point_in_polygon(0.5, 0.2, trap) is False


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_pick_active_track_despite_old_start(mock_settings: MagicMock):
    """Frigate start_time can be minutes early; active+zone must still win."""
    mock_settings.demo_loop_guard = False
    mock_settings.frigate_road_max_end_lag_sec = 90.0
    mock_settings.frigate_road_max_start_lead_sec = 45.0
    svc = FrigateTrackEvidence()
    evt = _road_evt()
    zb = _subject_binding_zone(evt)
    # Old start, still open (no end_time), inside zone.
    active = _frigate(box=[0.7, 0.4, 0.1, 0.1], start=1000.0 - 120.0, eid="active-old")
    # Recent start but outside zone.
    near_out = _frigate(box=[0.1, 0.4, 0.1, 0.1], start=1000.1, eid="near-out")
    matched, delta = svc._pick_correlated(
        [near_out, active],
        1000.0,
        "car",
        evt["bbox"],
        12.0,
        binding_polygon=zb["polygon"],
        require_zone=True,
    )
    assert matched is not None
    assert matched["id"] == "active-old"
    assert delta <= 0.05


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_pick_sealed_track_within_end_lag(mock_settings: MagicMock):
    """Short sealed Frigate tracks must still match when end is within road lag."""
    mock_settings.demo_loop_guard = False
    mock_settings.frigate_road_max_end_lag_sec = 90.0
    mock_settings.frigate_road_max_start_lead_sec = 45.0
    svc = FrigateTrackEvidence()
    evt = _road_evt()
    zb = _subject_binding_zone(evt)
    sealed = {
        "id": "sealed-lag",
        "label": "car",
        "start_time": 1000.0 - 70.0,
        "end_time": 1000.0 - 51.0,  # sealed 51s before anchor — within 90s lag
        "data": {"box": [0.7, 0.4, 0.1, 0.1]},
    }
    newer_wrong = {
        "id": "newer-after",
        "label": "car",
        "start_time": 1000.0 + 60.0,  # beyond start_lead — not the offender
        "end_time": 1000.0 + 75.0,
        "data": {"box": [0.72, 0.42, 0.1, 0.1]},
    }
    matched, delta = svc._pick_correlated(
        [newer_wrong, sealed],
        1000.0,
        "car",
        evt["bbox"],
        12.0,
        binding_polygon=zb["polygon"],
        require_zone=True,
    )
    assert matched is not None
    assert matched["id"] == "sealed-lag"
    assert delta <= 0.05


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_demo_zone_pick_prefers_active_over_newest(mock_settings: MagicMock):
    mock_settings.frigate_road_max_end_lag_sec = 90.0
    mock_settings.frigate_road_max_start_lead_sec = 45.0
    mock_settings.frigate_demo_max_align_sec = 10.0
    svc = FrigateTrackEvidence()
    evt = _road_evt()
    active = {
        "id": "at-anchor",
        "label": "car",
        "start_time": 990.0,
        "end_time": 1005.0,
        "data": {"box": [0.7, 0.4, 0.1, 0.1]},
    }
    newer = {
        "id": "too-new",
        "label": "car",
        "start_time": 1060.0,
        "end_time": 1070.0,
        "data": {"box": [0.71, 0.41, 0.1, 0.1]},
    }
    with patch.object(svc, "_list_events", return_value=[newer, active]):
        picked = svc._demo_zone_vehicle_at_anchor("cv_cam", 1000.0, evt=evt)
    assert picked is not None
    assert picked["id"] == "at-anchor"


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_accept_active_zone_ignores_wide_start_delta(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.frigate_demo_accept_max_align_sec = 8.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12
    mock_settings.demo_red_light_loop_sec = 352.52
    svc = FrigateTrackEvidence()
    evt = _road_evt()
    matched = _frigate(box=[0.7, 0.4, 0.1, 0.1], start=1000.0 - 90.0)
    # 90s start delta would normally fail RED_LIGHT_MAX_ALIGN_SEC=8
    assert svc._accept_correlation(evt, matched, 90.0, "cam-1") is True


def test_frigate_in_binding_zone_inside_outside():
    evt = _road_evt()
    inside = _frigate(box=[0.7, 0.4, 0.1, 0.1])  # ground ~0.75, 0.485
    outside = _frigate(box=[0.1, 0.4, 0.1, 0.1])
    assert _frigate_in_binding_zone(evt, inside) is True
    assert _frigate_in_binding_zone(evt, outside) is False
    assert _frigate_in_binding_zone(_road_evt(with_zone=False), inside) is None


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_accept_low_iou_inside_zone(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = False
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.frigate_demo_accept_max_align_sec = 30.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12
    svc = FrigateTrackEvidence()
    evt = _road_evt()
    # Frigate box inside zone, disjoint from IA bbox → IoU ~0, must still accept.
    matched = _frigate(box=[0.7, 0.4, 0.1, 0.1])
    assert svc._accept_correlation(evt, matched, 0.2, "cam-1") is True


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_reject_outside_zone_even_high_time_align(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = False
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.frigate_demo_accept_max_align_sec = 30.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12
    svc = FrigateTrackEvidence()
    evt = _road_evt()
    matched = _frigate(box=[0.1, 0.4, 0.1, 0.1])
    assert svc._accept_correlation(evt, matched, 0.1, "cam-1") is False


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_pick_prefers_in_zone_over_nearest_time(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = False
    svc = FrigateTrackEvidence()
    evt = _road_evt()
    zb = _subject_binding_zone(evt)
    events = [
        _frigate(box=[0.1, 0.4, 0.1, 0.1], start=1000.05, eid="near-out"),  # closer time, outside
        _frigate(box=[0.7, 0.4, 0.1, 0.1], start=1000.8, eid="far-in"),   # farther, inside
    ]
    matched, delta = svc._pick_correlated(
        events,
        1000.0,
        "car",
        evt["bbox"],
        12.0,
        binding_polygon=zb["polygon"],
        require_zone=True,
    )
    assert matched is not None
    assert matched["id"] == "far-in"
    # Active+zone compresses reported delta (start may lag the violation instant).
    assert delta <= 0.05


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_pick_require_zone_rejects_all_outside(mock_settings: MagicMock):
    svc = FrigateTrackEvidence()
    evt = _road_evt()
    zb = _subject_binding_zone(evt)
    events = [
        _frigate(box=[0.1, 0.4, 0.1, 0.1], start=1000.1, eid="a"),
        _frigate(box=[0.2, 0.4, 0.1, 0.1], start=1000.2, eid="b"),
    ]
    matched, _ = svc._pick_correlated(
        events, 1000.0, "car", evt["bbox"], 12.0,
        binding_polygon=zb["polygon"], require_zone=True,
    )
    assert matched is None
