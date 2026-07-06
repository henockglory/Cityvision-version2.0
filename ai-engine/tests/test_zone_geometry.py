"""Tests for zone edge calibration and speed distance resolution."""
from __future__ import annotations

from citevision_ai.analytics.zone_geometry import (
    edge_pair_distance_m,
    meters_per_norm_unit,
    path_distance_m,
    resolve_speed_distance_m,
)
from citevision_ai.analytics.zone_speed import ZoneSpeedEngine


def _rect_poly() -> list[dict]:
    # 0.1 x 0.05 normalised rectangle (road strip)
    return [
        {"x": 0.2, "y": 0.4, "distance_to_next_m": 10.0},
        {"x": 0.5, "y": 0.4, "distance_to_next_m": 2.0},
        {"x": 0.5, "y": 0.45, "distance_to_next_m": 10.0},
        {"x": 0.2, "y": 0.45, "distance_to_next_m": 2.0},
    ]


def test_meters_per_norm_unit_from_edges() -> None:
    scale = meters_per_norm_unit(_rect_poly())
    assert scale is not None
    assert 30 < scale < 40


def test_path_distance_uses_calibration() -> None:
    poly = _rect_poly()
    entry = (0.25, 0.42)
    exit_ = (0.45, 0.42)
    dist, method = resolve_speed_distance_m(poly, {}, entry, exit_)
    assert dist is not None
    assert dist > 0
    assert method == "edge_path_timing"


def test_edge_pair_distance_sum() -> None:
    poly = _rect_poly()
    # Clockwise from edge 0 (10m) + edge 1 (2m) to reach edge 1 midpoint path
    dist = edge_pair_distance_m(poly, 0, 1)
    assert dist is not None
    assert abs(dist - 12.0) < 0.01


def test_resolve_speed_uses_edge_pair_when_configured() -> None:
    poly = _rect_poly()
    cfg = {"entry_edge_index": 0, "exit_edge_index": 2}
    dist, method = resolve_speed_distance_m(poly, cfg, None, None)
    assert dist is not None
    assert dist > 0
    assert method == "edge_pair_timing"


def test_legacy_distance_m_fallback() -> None:
    poly = [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.1}, {"x": 0.2, "y": 0.2}]
    dist, method = resolve_speed_distance_m(poly, {"distance_m": 12.0}, None, None)
    assert dist == 12.0
    assert method == "zone_distance_timing"


def test_zone_speed_spatial_dedup_same_vehicle_new_track_id() -> None:
    engine = ZoneSpeedEngine()
    poly = _rect_poly()
    zones = [
        {
            "zone_id": "z1",
            "behavior": "speed_measurement",
            "behavior_config": {"speed_limit_kmh": 5, "class_filter": "car", "spatial_dedup_sec": 20},
            "polygon": poly,
        }
    ]

    def crossing(track_id: int, t: float, bbox: dict) -> list:
        tr = {"track_id": track_id, "class_name": "car", "bbox": bbox}
        return engine.process_frame("cam", [tr], zones, 800, 450, t, f"2026-01-01T00:00:{t}Z")

    crossing(1, 1000.0, {"x": 160, "y": 155, "width": 80, "height": 40})
    crossing(1, 1000.5, {"x": 320, "y": 155, "width": 80, "height": 40})
    first = crossing(1, 1001.0, {"x": 700, "y": 200, "width": 80, "height": 40})
    assert len(first) == 1

    # Same physical slot, new track_id (ByteTrack churn) — must not re-fire immediately.
    crossing(7, 1002.0, {"x": 165, "y": 156, "width": 80, "height": 40})
    crossing(7, 1002.5, {"x": 325, "y": 156, "width": 80, "height": 40})
    second = crossing(7, 1003.0, {"x": 705, "y": 201, "width": 80, "height": 40})
    assert len(second) == 0


def _bbox_bottom_norm(cx: float, cy: float, frame_w: int, frame_h: int, w: int = 80, h: int = 40) -> dict:
    """Pixel bbox whose bottom-centre normalises to (cx, cy)."""
    px = cx * frame_w - w / 2
    py = cy * frame_h - h
    return {"x": px, "y": py, "width": w, "height": h}


def test_zone_speed_engine_emits_with_edge_calibration() -> None:
    engine = ZoneSpeedEngine()
    poly = _rect_poly()
    zones = [
        {
            "zone_id": "z1",
            "behavior": "speed_measurement",
            "behavior_config": {"speed_limit_kmh": 5, "class_filter": "car"},
            "polygon": poly,
        }
    ]
    fw, fh = 800, 450
    track = {"track_id": 1, "class_name": "car", "bbox": _bbox_bottom_norm(0.25, 0.42, fw, fh)}
    engine.process_frame("cam", [track], zones, fw, fh, 1000.0, "2026-01-01T00:00:00Z")
    track_mid = {"track_id": 1, "class_name": "car", "bbox": _bbox_bottom_norm(0.45, 0.42, fw, fh)}
    engine.process_frame("cam", [track_mid], zones, fw, fh, 1000.5, "2026-01-01T00:00:00.5Z")
    track_out = {"track_id": 1, "class_name": "car", "bbox": _bbox_bottom_norm(0.85, 0.44, fw, fh)}
    events = engine.process_frame("cam", [track_out], zones, fw, fh, 1001.0, "2026-01-01T00:00:01Z")
    assert len(events) >= 1
    assert events[0]["event_type"] == "speeding"
    assert events[0]["metadata"]["detection_method"] in ("edge_path_timing", "edge_longest_timing")


def test_zone_speed_edge_pair_timing_emits() -> None:
    """B.18: timer starts at entry edge midpoint, finalizes at exit edge midpoint."""
    engine = ZoneSpeedEngine()
    poly = _rect_poly()
    fw, fh = 800, 450
    zones = [
        {
            "zone_id": "z1",
            "behavior": "speed_measurement",
            "behavior_config": {
                "speed_limit_kmh": 5,
                "class_filter": "car",
                "entry_edge_index": 0,
                "exit_edge_index": 2,
            },
            "polygon": poly,
        }
    ]
    # Edge 0 midpoint (0.35, 0.4) → edge 2 midpoint (0.35, 0.45); pair distance = 22 m.
    entry_track = {"track_id": 1, "class_name": "car", "bbox": _bbox_bottom_norm(0.35, 0.4, fw, fh)}
    engine.process_frame("cam", [entry_track], zones, fw, fh, 1000.0, "2026-01-01T00:00:00Z")
    exit_track = {"track_id": 1, "class_name": "car", "bbox": _bbox_bottom_norm(0.35, 0.45, fw, fh)}
    events = engine.process_frame("cam", [exit_track], zones, fw, fh, 1000.5, "2026-01-01T00:00:00.5Z")
    assert len(events) == 1
    assert events[0]["event_type"] == "speeding"
    assert events[0]["metadata"]["detection_method"] == "edge_pair_timing"
    assert events[0]["metadata"]["distance_m"] == 22.0
    assert events[0]["metadata"]["elapsed_s"] == 0.5


def test_zone_speed_edge_pair_no_emit_without_entry() -> None:
    """Exit edge alone must not finalize when entry edge was never crossed."""
    engine = ZoneSpeedEngine()
    poly = _rect_poly()
    fw, fh = 800, 450
    zones = [
        {
            "zone_id": "z1",
            "behavior": "speed_measurement",
            "behavior_config": {
                "speed_limit_kmh": 5,
                "class_filter": "car",
                "entry_edge_index": 0,
                "exit_edge_index": 2,
            },
            "polygon": poly,
        }
    ]
    exit_only = {"track_id": 1, "class_name": "car", "bbox": _bbox_bottom_norm(0.35, 0.45, fw, fh)}
    events = engine.process_frame("cam", [exit_only], zones, fw, fh, 1000.0, "2026-01-01T00:00:00Z")
    assert events == []
