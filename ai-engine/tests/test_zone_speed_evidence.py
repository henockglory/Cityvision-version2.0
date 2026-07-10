"""Zone speed evidence bbox selection."""

from __future__ import annotations

from citevision_ai.analytics.zone_speed import ZoneSpeedEngine
from citevision_ai.evidence.capture import bbox_region_has_content
import cv2
import numpy as np


def test_best_bbox_not_updated_outside_zone():
    engine = ZoneSpeedEngine()
    zones = [{
        "zone_id": "z1",
        "behavior": "speed_measurement",
        "behavior_config": {"speed_limit_kmh": 1.0, "class_filter": "any"},
        "polygon": [
            {"x": 0.4, "y": 0.4},
            {"x": 0.6, "y": 0.4},
            {"x": 0.6, "y": 0.6},
            {"x": 0.4, "y": 0.6},
        ],
    }]
    outside_bbox = {"x": 0.05, "y": 0.05, "width": 0.15, "height": 0.15}
    tracks = [{"track_id": 1, "class_name": "motorcycle", "bbox": outside_bbox}]
    engine.process_frame(
        "cam", tracks, zones, 1920, 1080, 100.0, "2026-01-01T00:00:00Z",
        frame_wall_ts=1000.0, segment_frame_index=5,
    )
    assert engine._best_bbox == {}


def test_best_bbox_updated_inside_zone():
    engine = ZoneSpeedEngine()
    zones = [{
        "zone_id": "z1",
        "behavior": "speed_measurement",
        "behavior_config": {"speed_limit_kmh": 1.0, "class_filter": "any"},
        "polygon": [
            {"x": 0.4, "y": 0.4},
            {"x": 0.6, "y": 0.4},
            {"x": 0.6, "y": 0.6},
            {"x": 0.4, "y": 0.6},
        ],
    }]
    inside_bbox = {"x": 820, "y": 430, "width": 280, "height": 220}
    tracks = [{"track_id": 2, "class_name": "motorcycle", "bbox": inside_bbox}]
    engine.process_frame(
        "cam", tracks, zones, 1920, 1080, 100.0, "2026-01-01T00:00:00Z",
        frame_wall_ts=1000.0, segment_frame_index=12,
    )
    key = ("cam", "z1", 2)
    assert key in engine._best_bbox
    assert engine._best_bbox[key]["frame_index"] == 12


def test_bbox_region_has_content_detects_vehicle_patch():
    frame = np.full((480, 640, 3), 90, dtype=np.uint8)
    cv2.rectangle(frame, (200, 150), (420, 320), (20, 20, 180), -1)
    cv2.rectangle(frame, (260, 200), (360, 280), (200, 200, 200), 2)
    bbox = {"x": 0.3125, "y": 0.3125, "width": 0.34375, "height": 0.354}
    assert bbox_region_has_content(frame, bbox)
    empty = {"x": 0.05, "y": 0.05, "width": 0.15, "height": 0.15}
    assert not bbox_region_has_content(frame, empty)
