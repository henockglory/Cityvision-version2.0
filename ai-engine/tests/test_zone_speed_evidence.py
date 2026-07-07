"""Zone speed track_lost uses last known bbox."""

from __future__ import annotations

from citevision_ai.analytics.zone_speed import ZoneSpeedEngine


def test_track_lost_uses_last_bbox_not_empty():
    engine = ZoneSpeedEngine()
    camera_id = "cam-1"
    zone_id = "Zone_test"
    poly = [
        {"x": 0.1, "y": 0.1},
        {"x": 0.9, "y": 0.1},
        {"x": 0.9, "y": 0.9},
        {"x": 0.1, "y": 0.9},
    ]
    zones = [{
        "zone_id": zone_id,
        "behavior": "speed_measurement",
        "polygon": poly,
        "behavior_config": {
            "speed_limit_kmh": 5,
            "distance_m": 10,
            "cooldown_sec": 20,
            "spatial_dedup_sec": 8,
            "class_filter": "any",
            "live_traffic": True,
        },
    }]
    bbox = {"x": 300, "y": 200, "width": 120, "height": 80}
    tracks = [{"track_id": 7, "class_name": "car", "bbox": bbox}]
    engine.process_frame(camera_id, tracks, zones, 640, 480, 100.0, "2026-07-07T10:00:00Z")
    events = engine.process_frame(camera_id, [], zones, 640, 480, 101.5, "2026-07-07T10:00:01Z")
    assert len(events) == 1
    ev_bbox = events[0].get("bbox") or {}
    assert float(ev_bbox.get("width", 0)) > 0.02
    assert float(ev_bbox.get("height", 0)) > 0.02


def test_speeding_event_bbox_ts_matches_source_frame_not_finalize_time():
    """The emitted event's bbox_ts must be the wall-clock time of the frame that
    produced the chosen bbox, not the (potentially much later) moment the
    crossing is finalized — otherwise evidence capture fetches the wrong frame
    and the crop lands on empty road instead of the vehicle."""
    engine = ZoneSpeedEngine()
    camera_id = "cam-ts"
    zone_id = "Zone_test_ts"
    poly = [
        {"x": 0.1, "y": 0.1},
        {"x": 0.9, "y": 0.1},
        {"x": 0.9, "y": 0.9},
        {"x": 0.1, "y": 0.9},
    ]
    zones = [{
        "zone_id": zone_id,
        "behavior": "speed_measurement",
        "polygon": poly,
        "behavior_config": {
            "speed_limit_kmh": 5,
            "distance_m": 10,
            "cooldown_sec": 20,
            "spatial_dedup_sec": 8,
            "class_filter": "any",
            "live_traffic": True,
        },
    }]
    bbox = {"x": 300, "y": 200, "width": 200, "height": 150}
    tracks = [{"track_id": 9, "class_name": "car", "bbox": bbox}]
    # Vehicle observed at wall-clock ts=1000.0 (large, valid bbox).
    engine.process_frame(
        camera_id, tracks, zones, 640, 480, 100.0, "2026-07-07T10:00:00Z",
        frame_wall_ts=1000.0,
    )
    # Track lost; finalize happens 300ms later at ts=1000.3 — must not be used as bbox_ts.
    events = engine.process_frame(
        camera_id, [], zones, 640, 480, 101.5, "2026-07-07T10:00:01Z",
        frame_wall_ts=1000.3,
    )
    assert len(events) == 1
    assert events[0].get("bbox_ts") == 1000.0


def test_per_track_cooldown_blocks_same_track_not_different():
    engine = ZoneSpeedEngine()
    camera_id = "cam-2"
    zone_id = "Zone_cool"
    poly = [
        {"x": 0.1, "y": 0.5},
        {"x": 0.9, "y": 0.5},
        {"x": 0.9, "y": 0.9},
        {"x": 0.1, "y": 0.9},
    ]
    zones = [{
        "zone_id": zone_id,
        "behavior": "speed_measurement",
        "polygon": poly,
        "behavior_config": {
            "speed_limit_kmh": 5,
            "distance_m": 10,
            "cooldown_sec": 30,
            "spatial_dedup_sec": 2,
            "class_filter": "any",
            "live_traffic": True,
        },
    }]

    def crossing(tid: int, ts: float, x_norm: float):
        px = int(x_norm * 640 - 50)
        inside = {"track_id": tid, "class_name": "car", "bbox": {"x": px, "y": 300, "width": 100, "height": 70}}
        outside = {"track_id": tid, "class_name": "car", "bbox": {"x": px, "y": 50, "width": 100, "height": 70}}
        engine.process_frame(camera_id, [inside], zones, 640, 480, ts, f"2026-07-07T10:00:{int(ts):02d}Z")
        return engine.process_frame(camera_id, [outside], zones, 640, 480, ts + 0.8, f"2026-07-07T10:00:{int(ts+1):02d}Z")

    first = crossing(1, 200.0, 0.3)
    assert len(first) == 1
    # Same track_id again within cooldown → blocked
    second_same = crossing(1, 201.0, 0.7)
    assert len(second_same) == 0
    # Different track_id, different lane position → allowed
    third_other = crossing(2, 202.0, 0.75)
    assert len(third_other) == 1
