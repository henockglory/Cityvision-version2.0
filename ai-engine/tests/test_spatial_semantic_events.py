from citevision_ai.events.generator import EventGenerator


SQUARE = [
    {"x": 0, "y": 0},
    {"x": 10, "y": 0},
    {"x": 10, "y": 10},
    {"x": 0, "y": 10},
]


def test_perimeter_breach_on_zone_enter():
    gen = EventGenerator()
    rules = [
        {
            "enabled": True,
            "rule_type": "zone",
            "zone": {
                "zone_id": "site-perimeter",
                "zone_kind": "perimeter",
                "polygon": SQUARE,
            },
        }
    ]
    events = gen.process_frame(
        "cam-1",
        [{"track_id": 1, "class_name": "person", "bbox": {"x": 4, "y": 4, "width": 2, "height": 2}}],
        rules,
        "2026-06-16T12:00:00+00:00",
    )
    types = [e["event_type"] for e in events]
    assert "zone_enter" in types
    assert "perimeter_breach" in types


def test_unauthorized_exit_on_zone_exit():
    gen = EventGenerator()
    rules = [
        {
            "enabled": True,
            "rule_type": "zone",
            "zone": {
                "zone_id": "gate-exit",
                "zone_kind": "controlled_exit",
                "polygon": SQUARE,
            },
        }
    ]
    inside = {"track_id": 2, "class_name": "person", "bbox": {"x": 4, "y": 4, "width": 2, "height": 2}}
    outside = {"track_id": 2, "class_name": "person", "bbox": {"x": 20, "y": 20, "width": 2, "height": 2}}
    gen.process_frame("cam-1", [inside], rules, "2026-06-16T12:00:00+00:00")
    events = gen.process_frame("cam-1", [outside], rules, "2026-06-16T12:00:01+00:00")
    types = [e["event_type"] for e in events]
    assert "zone_exit" in types
    assert "unauthorized_exit" in types
