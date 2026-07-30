"""Unit tests for Frigate→Gemini / speed bridge helpers (no live MQTT)."""
from __future__ import annotations

import json

from citevision_ai.frigate_bridge.ids import (
    frigate_camera_id,
    frigate_zone_id,
    parse_camera_uuid,
    parse_zone_uuid,
)
from citevision_ai.frigate_bridge.bridge import FrigateEventBridge
from citevision_ai.frigate_bridge.snapshot import (
    bbox_cabin_driver_region,
    crop_jpeg_from_snapshot,
)


def test_frigate_id_roundtrip():
    cam = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    zone = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert frigate_camera_id(cam) == f"cv_{cam}"
    assert frigate_zone_id(zone) == f"cv_zone_{zone}"
    assert parse_camera_uuid(frigate_camera_id(cam)) == cam
    assert parse_zone_uuid(frigate_zone_id(zone)) == zone
    assert parse_camera_uuid("not-cv") is None


def test_bridge_indexes_zone_uuid():
    spatial = {
        "zones": [
            {
                "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "zone_id": "Zone_bbox2",
                "behavior": "seatbelt",
                "behavior_config": {"confidence": 0.4, "speed_limit_kmh": 30},
            }
        ]
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=False,
        speed_enabled=True,
    )
    indexed = bridge._index_zones(spatial["zones"])
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in indexed
    assert bridge._speed_limit(indexed["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]) == 30.0


def test_bridge_speed_emits_when_over_limit(monkeypatch):
    emitted: list[dict] = []
    zone_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "SpeedZone",
                "behavior": "speed_measurement",
                "behavior_config": {"speed_limit_kmh": 20},
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
        "id": "evt-1",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "data": {"average_estimated_speed": 45.5, "box": [0.1, 0.1, 0.2, 0.2]},
    }
    before = {
        "current_zones": [f"cv_zone_{zone_uuid}"],
        "data": {"average_estimated_speed": 45.5},
    }
    bridge._handle_event(after, before)
    assert len(emitted) == 1
    assert emitted[0]["event_type"] == "speeding"
    assert emitted[0]["speed_kmh"] == 45.5
    assert emitted[0]["metadata"]["detection_method"] == "frigate_speed"
    assert emitted[0]["frigate_event_id"] == "evt-1"


def test_bridge_speed_no_emit_under_limit():
    emitted: list[dict] = []
    zone_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "SpeedZone",
                "behavior": "speed_measurement",
                "behavior_config": {"speed_limit_kmh": 80},
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
        "id": "evt-2",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "data": {"average_estimated_speed": 40.0},
    }
    before = {"current_zones": [f"cv_zone_{zone_uuid}"], "data": {"average_estimated_speed": 40.0}}
    bridge._handle_event(after, before)
    assert emitted == []


def test_crop_jpeg_full_frame_without_box():
    import cv2
    import numpy as np

    img = np.zeros((40, 60, 3), dtype=np.uint8)
    img[:] = (0, 128, 255)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    out = crop_jpeg_from_snapshot(buf.tobytes(), None)
    assert out and len(out) > 50


def test_bbox_cabin_driver_region_is_upper_left_of_vehicle():
    vehicle = {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.5, "norm": True}
    cabin = bbox_cabin_driver_region(vehicle, driver_side="left")
    assert cabin["y"] >= vehicle["y"]
    assert cabin["y"] + cabin["height"] <= vehicle["y"] + vehicle["height"] + 1e-9
    assert cabin["height"] < vehicle["height"]
    assert cabin["width"] < vehicle["width"]
    # Driver (LHD) biased to left half of car
    assert cabin["x"] < vehicle["x"] + vehicle["width"] * 0.5
    assert cabin.get("norm") is True


def test_cabin_crop_smaller_than_full_vehicle_crop():
    import cv2
    import numpy as np

    img = np.zeros((200, 300, 3), dtype=np.uint8)
    img[60:160, 80:220] = (40, 40, 200)  # fake car blob
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    raw = buf.tobytes()
    vehicle = {"x": 80 / 300, "y": 60 / 200, "width": 140 / 300, "height": 100 / 200, "norm": True}
    full = crop_jpeg_from_snapshot(raw, vehicle, pad=0.0)
    cabin_box = bbox_cabin_driver_region(vehicle)
    cabin = crop_jpeg_from_snapshot(raw, cabin_box, pad=0.0, min_side=0)
    assert full and cabin
    # Cabin JPEG should be a different (typically smaller before upscale) crop
    arr_f = np.frombuffer(full, dtype=np.uint8)
    arr_c = np.frombuffer(cabin, dtype=np.uint8)
    im_f = cv2.imdecode(arr_f, cv2.IMREAD_COLOR)
    im_c = cv2.imdecode(arr_c, cv2.IMREAD_COLOR)
    assert im_f is not None and im_c is not None
    assert im_c.shape[0] * im_c.shape[1] < im_f.shape[0] * im_f.shape[1]
