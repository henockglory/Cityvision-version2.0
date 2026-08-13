"""Geometry / slow-vehicle bridge unit tests (no live Frigate)."""

from __future__ import annotations

from citevision_ai.frigate_bridge.bridge import FrigateEventBridge


def test_bridge_geometry_enter_emits_perimeter():
    emitted: list[dict] = []
    zone_uuid = "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "Perimeter",
                "behavior": "perimeter",
            }
        ]
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        emit_event=lambda e: emitted.append(e),
        geometry_enabled=True,
    )
    after = {
        "id": "geom-1",
        "camera": f"cv_{cam_uuid}",
        "label": "person",
        "current_zones": [f"cv_zone_{zone_uuid}"],
        "entered_zones": [f"cv_zone_{zone_uuid}"],
        "data": {"box": [0.2, 0.2, 0.1, 0.3]},
    }
    bridge._handle_event(after, {})
    types = [e["event_type"] for e in emitted]
    assert "perimeter_breach" in types
    hit = next(e for e in emitted if e["event_type"] == "perimeter_breach")
    assert hit["frigate_event_id"] == "geom-1"
    assert hit["metadata"]["detection_method"] == "frigate_geometry"
    assert hit["bbox"] is not None


def test_bridge_geometry_dwell_presence(monkeypatch):
    emitted: list[dict] = []
    zone_uuid = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "Presence",
                "behavior": "presence",
                "behavior_config": {"config": {"duration_seconds": 2}},
            }
        ]
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        emit_event=lambda e: emitted.append(e),
        geometry_enabled=True,
    )
    t0 = [1000.0]
    monkeypatch.setattr("citevision_ai.frigate_bridge.bridge.time.monotonic", lambda: t0[0])
    after = {
        "id": "dwell-1",
        "camera": f"cv_{cam_uuid}",
        "label": "person",
        "current_zones": [f"cv_zone_{zone_uuid}"],
        "entered_zones": [f"cv_zone_{zone_uuid}"],
        "data": {"box": [0.1, 0.1, 0.2, 0.2]},
    }
    bridge._handle_event(after, {})
    assert not any(e["event_type"] == "zone_presence" for e in emitted)
    t0[0] = 1003.0
    after2 = dict(after)
    after2["entered_zones"] = []
    bridge._handle_event(after2, {"current_zones": [f"cv_zone_{zone_uuid}"]})
    assert any(e["event_type"] == "zone_presence" for e in emitted)


def test_bridge_geometry_exit_unauthorized():
    emitted: list[dict] = []
    zone_uuid = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "ExitCtrl",
                "behavior": "controlled_exit",
            }
        ]
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        emit_event=lambda e: emitted.append(e),
        geometry_enabled=True,
    )
    after = {
        "id": "exit-1",
        "camera": f"cv_{cam_uuid}",
        "label": "person",
        "current_zones": [],
        "data": {"box": [0.1, 0.1, 0.2, 0.2]},
    }
    before = {"current_zones": [f"cv_zone_{zone_uuid}"]}
    bridge._handle_event(after, before)
    types = [e["event_type"] for e in emitted]
    assert "unauthorized_exit" in types
    assert "zone_exit" in types


def test_bridge_slow_vehicle_exit():
    emitted: list[dict] = []
    zone_uuid = "eeeeeeee-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "SlowZone",
                "behavior": "speed_measurement",
                "behavior_config": {"config": {"min_speed_kmh": 20, "speed_limit_kmh": 90}},
            }
        ]
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        emit_event=lambda e: emitted.append(e),
        speed_enabled=True,
    )
    after = {
        "id": "slow-1",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "data": {"average_estimated_speed": 8.0, "box": [0.1, 0.1, 0.2, 0.2]},
    }
    before = {
        "current_zones": [f"cv_zone_{zone_uuid}"],
        "data": {"average_estimated_speed": 8.0},
    }
    bridge._handle_event(after, before)
    assert any(e["event_type"] == "speed_below_minimum" for e in emitted)

def test_bridge_wrong_way_reverse_emits():
    emitted: list[dict] = []
    zone_uuid = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    poly = [
        {"x": 0.2, "y": 0.3},
        {"x": 0.8, "y": 0.3},
        {"x": 0.8, "y": 0.7},
        {"x": 0.2, "y": 0.7},
    ]
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "WrongWay",
                "behavior": "wrong_way",
                "polygon": poly,
                "behavior_config": {
                    "entry_edge_index": 3,
                    "exit_edge_index": 1,
                    "class_filter": "car",
                },
            }
        ]
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        emit_event=lambda e: emitted.append(e),
        geometry_enabled=True,
    )
    fz = f"cv_zone_{zone_uuid}"
    enter = {
        "id": "ww-ok",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [fz],
        "entered_zones": [fz],
        "data": {"box": [0.22, 0.45, 0.08, 0.12]},
    }
    bridge._handle_event(enter, {})
    exit_ok = {
        "id": "ww-ok",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "data": {"box": [0.72, 0.45, 0.08, 0.12]},
    }
    bridge._handle_event(exit_ok, {"current_zones": [fz]})
    assert not any(e["event_type"] == "wrong_way" for e in emitted)

    enter_bad = {
        "id": "ww-bad",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [fz],
        "entered_zones": [fz],
        "data": {"box": [0.72, 0.45, 0.08, 0.12]},
    }
    bridge._handle_event(enter_bad, {})
    exit_bad = {
        "id": "ww-bad",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "data": {"box": [0.22, 0.45, 0.08, 0.12]},
    }
    bridge._handle_event(exit_bad, {"current_zones": [fz]})
    hits = [e for e in emitted if e["event_type"] == "wrong_way"]
    assert hits, emitted
    assert hits[0]["metadata"]["detection_method"] == "frigate_wrong_way_edges"
