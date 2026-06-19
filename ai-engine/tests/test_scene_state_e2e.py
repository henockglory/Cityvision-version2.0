from datetime import datetime, timezone

from citevision_ai.analytics.scene import SceneAnalyzer
from citevision_ai.analytics.state import StateEngine


def test_vehicle_count_threshold_event():
    analyzer = SceneAnalyzer(vehicle_threshold=1, emit_interval=0)
    tracks = [{
        "track_id": 1,
        "class_name": "car",
        "bbox": {"x": 10, "y": 10, "width": 50, "height": 30},
    }]
    _, events = analyzer.analyze("cam1", tracks, frame_area=1920 * 1080)
    assert any(e.get("event_type") == "vehicle_count_threshold" for e in events)


def test_vehicle_stopped_event():
    state = StateEngine(dwell_threshold_sec=0.1, stop_threshold_px=1000)
    state.set_fps(10)
    ts = datetime.now(timezone.utc).isoformat()
    tracks = [{
        "track_id": 7,
        "class_name": "car",
        "bbox": {"x": 10, "y": 10, "width": 50, "height": 30},
    }]
    state.update("cam1", 1, tracks, ts)
    _, events, _ = state.update("cam1", 4, tracks, ts)
    assert any(e.get("event_type") == "vehicle_stopped" for e in events)