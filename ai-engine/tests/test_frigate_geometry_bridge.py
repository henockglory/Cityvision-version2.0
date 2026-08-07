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
