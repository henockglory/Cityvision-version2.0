"""Unit tests for the 10 formerly « Bientôt » templates."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import cv2
import numpy as np
import pytest

from citevision_ai.analytics.scene import SceneAnalyzer
from citevision_ai.analytics.state import StateEngine
from citevision_ai.behavior.heuristics import BehaviorHeuristics, BehaviorLabel
from citevision_ai.events.generator import EventGenerator
from citevision_ai.road_enforcement.detector import RoadEnforcementEngine


def test_fight_detected_emitted():
    gen = EventGenerator()
    from citevision_ai.behavior.heuristics import BehaviorSignal

    sig = BehaviorSignal(1, BehaviorLabel.FIGHTING, 0.8, {"overlap_ratio": 0.4})
    events = gen.emit_behavior_signals("cam-1", [sig], "2026-06-16T12:00:00+00:00")
    types = {e["event_type"] for e in events}
    assert "fighting" in types
    assert "fight_detected" in types


def test_rapid_activity_behavior():
    bh = BehaviorHeuristics(speed_threshold=2.0)
    history = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 80.0)]
    sig = bh.evaluate_track(5, history, "person")
    assert sig.label == BehaviorLabel.RAPID_ACTIVITY
    assert sig.details.get("behavior") == "rapid_activity"


def test_crowd_panic_emitted():
    analyzer = SceneAnalyzer(emit_interval=0)
    persons_dense = [
        {"track_id": i, "class_name": "person", "bbox": {"x": 100 + i * 5, "y": 100, "width": 40, "height": 80}}
        for i in range(5)
    ]
    for _ in range(4):
        analyzer.analyze("cam1", persons_dense, 1920 * 1080)
    sparse = [
        {"track_id": 99, "class_name": "person", "bbox": {"x": 100, "y": 100, "width": 40, "height": 80}},
    ]
    events: list = []
    for _ in range(4):
        _, batch = analyzer.analyze("cam1", sparse, 1920 * 1080)
        events.extend(batch)
    assert any(e.get("event_type") == "crowd_panic" for e in events)


def test_vehicle_stopped_has_zone_and_duration():
    state = StateEngine(dwell_threshold_sec=0.1, stop_threshold_px=1000)
    state.set_fps(10)
    ts = datetime.now(timezone.utc).isoformat()
    state.set_zone("cam1", 7, "no-parking", True)
    tracks = [{"track_id": 7, "class_name": "car", "bbox": {"x": 10, "y": 10, "width": 50, "height": 30}}]
    state.update("cam1", 1, tracks, ts)
    _, events, _ = state.update("cam1", 4, tracks, ts)
    stopped = [e for e in events if e.get("event_type") == "vehicle_stopped"]
    assert stopped
    assert stopped[0].get("zone_id") == "no-parking"
    assert stopped[0].get("duration_seconds", 0) >= 0


def _synthetic_frame_with_red() -> np.ndarray:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[20:80, 500:600] = (0, 0, 255)
    return frame


def _synthetic_vehicle_track() -> dict:
    return {
        "track_id": 42,
        "class_name": "car",
        "bbox": {"x": 200, "y": 250, "width": 180, "height": 120},
        "confidence": 0.9,
    }


@pytest.fixture(autouse=True)
def e2e_mode():
    os.environ["E2E_MODE"] = "1"
    yield
    os.environ.pop("E2E_MODE", None)


def test_road_enforcement_red_light_violation():
    engine = RoadEnforcementEngine()
    frame = _synthetic_frame_with_red()
    events = engine.process_frame("cam1", frame, [_synthetic_vehicle_track()], "2026-06-16T12:00:00+00:00")
    assert any(e["event_type"] == "red_light_violation" for e in events)


def test_road_enforcement_seatbelt_violation():
    engine = RoadEnforcementEngine()
    frame = np.full((480, 640, 3), 180, dtype=np.uint8)
    events = engine.process_frame("cam1", frame, [_synthetic_vehicle_track()], "2026-06-16T12:00:00+00:00")
    assert any(e["event_type"] == "seatbelt_violation" for e in events)


def test_road_enforcement_phone_driving():
    engine = RoadEnforcementEngine()
    frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    x, y, w, h = 200, 250, 180, 120
    roi = frame[y : y + h // 3, x : x + int(w * 0.35)]
    roi[:] = (100, 150, 200)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hsv[:, :, 0] = 10
    hsv[:, :, 1] = 120
    hsv[:, :, 2] = 180
    frame[y : y + h // 3, x : x + int(w * 0.35)] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    events = engine.process_frame("cam1", frame, [_synthetic_vehicle_track()], "2026-06-16T12:00:00+00:00")
    assert any(e["event_type"] == "phone_driving" for e in events)
