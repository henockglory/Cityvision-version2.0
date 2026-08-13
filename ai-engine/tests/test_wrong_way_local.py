"""Local EventGenerator wrong_way edge judgment (geometry bridge OFF)."""

from __future__ import annotations

from citevision_ai.events.generator import EventGenerator


def test_local_wrong_way_reverse_emits():
    gen = EventGenerator()
    poly = [
        {"x": 0.2, "y": 0.3},
        {"x": 0.8, "y": 0.3},
        {"x": 0.8, "y": 0.7},
        {"x": 0.2, "y": 0.7},
    ]
    rules = [
        {
            "camera_id": "cam",
            "rule_type": "zone",
            "enabled": True,
            "zone": {
                "zone_id": "ww",
                "polygon": poly,
                "behavior": "wrong_way",
                "behavior_config": {
                    "entry_edge_index": 3,
                    "exit_edge_index": 1,
                    "class_filter": "car",
                },
            },
        }
    ]
    # Enter near left edge (allowed entry)
    enter_track = {
        "track_id": 1,
        "class_name": "car",
        "bbox": {"x": 0.22, "y": 0.45, "width": 0.08, "height": 0.12},
    }
    e1 = gen.process_frame("cam", [enter_track], rules, "2026-01-01T00:00:00Z")
    assert any(e["event_type"] == "zone_enter" for e in e1)
    # Exit near right (allowed) — no wrong_way
    exit_ok = {
        "track_id": 1,
        "class_name": "car",
        "bbox": {"x": 0.72, "y": 0.45, "width": 0.08, "height": 0.12},
    }
    # Move outside: place center outside polygon
    outside = {
        "track_id": 1,
        "class_name": "car",
        "bbox": {"x": 0.90, "y": 0.45, "width": 0.05, "height": 0.05},
    }
    # First move to right edge inside still, then outside from right
    gen.process_frame("cam", [exit_ok], rules, "2026-01-01T00:00:01Z")
    e_ok = gen.process_frame("cam", [outside], rules, "2026-01-01T00:00:02Z")
    assert not any(e["event_type"] == "wrong_way" for e in e_ok)

    # Reverse path track 2: enter right, exit left
    enter_bad = {
        "track_id": 2,
        "class_name": "car",
        "bbox": {"x": 0.72, "y": 0.45, "width": 0.08, "height": 0.12},
    }
    gen.process_frame("cam", [enter_bad], rules, "2026-01-01T00:00:03Z")
    near_left = {
        "track_id": 2,
        "class_name": "car",
        "bbox": {"x": 0.22, "y": 0.45, "width": 0.08, "height": 0.12},
    }
    gen.process_frame("cam", [near_left], rules, "2026-01-01T00:00:04Z")
    outside_left = {
        "track_id": 2,
        "class_name": "car",
        "bbox": {"x": 0.05, "y": 0.45, "width": 0.05, "height": 0.05},
    }
    e_bad = gen.process_frame("cam", [outside_left], rules, "2026-01-01T00:00:05Z")
    assert any(e["event_type"] == "wrong_way" for e in e_bad), e_bad
