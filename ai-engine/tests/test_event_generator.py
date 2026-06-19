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


def test_line_cross_event():
    gen = EventGenerator()
    rules = [
        {
            "rule_id": "r-line",
            "camera_id": "cam-1",
            "rule_type": "line",
            "enabled": True,
            "line": {
                "line_id": "entry",
                "start": {"x": 50, "y": 0},
                "end": {"x": 50, "y": 100},
                "direction_filter": "in",
            },
        }
    ]
    tracks_left = [
        {
            "track_id": 1,
            "bbox": {"x": 10, "y": 40, "width": 10, "height": 10},
            "class_name": "person",
        }
    ]
    gen.process_frame("cam-1", tracks_left, rules, "2026-06-12T12:00:00+00:00")
    tracks_right = [
        {
            "track_id": 1,
            "bbox": {"x": 60, "y": 40, "width": 10, "height": 10},
            "class_name": "person",
        }
    ]
    events = gen.process_frame("cam-1", tracks_right, rules, "2026-06-12T12:00:01+00:00")
    assert any(e.get("event_type") == "line_cross" for e in events)


def test_loitering_event():
    gen = EventGenerator()
    polygon = [
        {"x": 0, "y": 0},
        {"x": 100, "y": 0},
        {"x": 100, "y": 100},
        {"x": 0, "y": 100},
    ]
    rules = [
        {
            "rule_id": "r-loiter",
            "camera_id": "cam-1",
            "rule_type": "loitering",
            "enabled": True,
            "zone": {"zone_id": "z1", "polygon": polygon},
            "loitering": {"zone_id": "z1", "threshold_seconds": 5},
        }
    ]
    tracks = [
        {
            "track_id": 1,
            "bbox": {"x": 40, "y": 40, "width": 10, "height": 10},
            "class_name": "person",
        }
    ]
    gen.process_frame("cam-1", tracks, rules, "2026-06-12T12:00:00+00:00")
    events = gen.process_frame("cam-1", tracks, rules, "2026-06-12T12:00:06+00:00")
    assert any(e.get("event_type") == "loitering" for e in events)
