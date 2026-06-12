import pytest

from citevision_ai.events.generator import EventGenerator, _point_in_polygon


def test_point_in_polygon():
    square = [
        {"x": 0, "y": 0},
        {"x": 10, "y": 0},
        {"x": 10, "y": 10},
        {"x": 0, "y": 10},
    ]
    assert _point_in_polygon(5, 5, square) is True
    assert _point_in_polygon(15, 5, square) is False


def test_zone_enter_event():
    gen = EventGenerator()
    rules = [
        {
            "rule_id": "r1",
            "camera_id": "cam-1",
            "rule_type": "zone",
            "enabled": True,
            "zone": {
                "zone_id": "zone-a",
                "polygon": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 100},
                    {"x": 0, "y": 100},
                ],
            },
        }
    ]
    tracks = [
        {
            "track_id": 1,
            "bbox": {"x": 40, "y": 40, "width": 10, "height": 10},
        }
    ]
    events = gen.process_frame("cam-1", tracks, rules, "2026-06-12T12:00:00+00:00")
    assert len(events) == 1
    assert events[0]["event_type"] == "zone_enter"
    assert events[0]["zone_id"] == "zone-a"
