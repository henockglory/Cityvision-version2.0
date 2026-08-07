"""Unit tests for Frigate→Gemini / speed bridge helpers (no live MQTT)."""
from __future__ import annotations

import json
import time

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


def _patch_red_light_frigate_snapshot(monkeypatch, *, light: str = "red") -> None:
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.wait_snapshot_ready",
        lambda *_a, **_k: {"has_snapshot": True},
    )
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.download_snapshot_jpeg",
        lambda *_a, **_k: b"\xff\xd8\xff",
    )
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.classify_snapshot_light_state",
        lambda *_a, **_k: light,
    )


def test_frigate_id_roundtrip():
    cam = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    zone = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert frigate_camera_id(cam) == f"cv_{cam}"
    assert frigate_zone_id(zone) == f"cv_zone_{zone}"
    assert parse_camera_uuid(frigate_camera_id(cam)) == cam
    assert parse_zone_uuid(frigate_zone_id(zone)) == zone
    assert parse_camera_uuid("not-cv") is None


def test_bridge_red_light_candidate_events_keep_primary_first():
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    zone_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    zinfo = {
        "id": zone_uuid,
        "zone_id": "Zone_Observation",
        "behavior": "red_light_observation",
        "polygon": [
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
            {"x": 1.0, "y": 1.0},
            {"x": 0.0, "y": 1.0},
        ],
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: {"zones": [zinfo]},
        vlm_enabled=False,
    )
    now = time.time()
    primary = {
        "id": "primary",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "start_time": now,
        "frame_time": now,
        "data": {"box": [0.10, 0.20, 0.20, 0.20]},
    }
    fallback = {
        "id": "fallback",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "start_time": now,
        "frame_time": now,
        "data": {"box": [0.30, 0.40, 0.20, 0.20]},
    }
    bridge._remember_red_light_track("fallback", fallback, zinfo, {zone_uuid: zinfo})
    bridge._remember_red_light_track("primary", primary, zinfo, {zone_uuid: zinfo})

    candidates = bridge._red_light_candidate_events(cam_uuid, "primary")

    assert [c["id"] for c in candidates[:2]] == ["primary", "fallback"]
    assert {k: candidates[0]["bbox"][k] for k in ("x", "y", "width", "height")} == {
        "x": 0.1,
        "y": 0.2,
        "width": 0.2,
        "height": 0.2,
    }
    assert candidates[0]["zone_id"] == "Zone_Observation"


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
    assert emitted[0]["metadata"]["speed_emit_mode"] == "exit"
    assert emitted[0]["metadata"]["bbox_source"] == "frigate"
    assert emitted[0]["frigate_event_id"] == "evt-1"


def test_bridge_speed_no_midzone_emit_when_exit_mode(monkeypatch):
    monkeypatch.setenv("FRIGATE_SPEED_EMIT_MODE", "exit")
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
    # Still inside zone — must NOT emit under exit mode.
    after = {
        "id": "evt-in",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [f"cv_zone_{zone_uuid}"],
        "entered_zones": [f"cv_zone_{zone_uuid}"],
        "data": {"average_estimated_speed": 55.0, "box": [0.1, 0.1, 0.2, 0.2]},
    }
    before = {"current_zones": [f"cv_zone_{zone_uuid}"], "data": {"average_estimated_speed": 40.0}}
    bridge._handle_event(after, before)
    assert emitted == []


def test_bridge_speed_respects_track_objects_filter(monkeypatch):
    monkeypatch.setenv("FRIGATE_SPEED_EMIT_MODE", "exit")
    emitted: list[dict] = []
    zone_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "SpeedZone",
                "behavior": "speed_measurement",
                "behavior_config": {"speed_limit_kmh": 20, "track_objects": ["motorcycle"]},
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
        "id": "evt-car",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "data": {"average_estimated_speed": 90.0, "box": [0.1, 0.1, 0.2, 0.2]},
    }
    before = {
        "current_zones": [f"cv_zone_{zone_uuid}"],
        "data": {"average_estimated_speed": 90.0},
    }
    bridge._handle_event(after, before)
    assert emitted == []


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
    assert bridge.stats().get("speed_below_limit", 0) >= 1


def test_bridge_cabin_dispatches_seatbelt(monkeypatch):
    zone_uuid = "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "Cabin",
                "behavior": "seatbelt",
                "behavior_config": {"confidence": 0.4},
            }
        ]
    }
    called: list[tuple] = []

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=object(),  # non-None so vlm_enabled sticks
    )
    # Force vlm path without real queue
    bridge._vlm_enabled = True
    bridge._vlm_queue = object()

    def _fake_cabin(camera_id, event_id, after, zinfo, behavior):
        called.append((camera_id, event_id, behavior))

    monkeypatch.setattr(bridge, "_maybe_cabin", _fake_cabin)
    after = {
        "id": "evt-cabin",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [f"cv_zone_{zone_uuid}"],
        "entered_zones": [f"cv_zone_{zone_uuid}"],
    }
    bridge._handle_event(after, {})
    assert called and called[0][2] == "seatbelt"


def test_bridge_cabin_enqueues_vehicle_bbox_crop(monkeypatch):
    zone_uuid = "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_uuid,
                "zone_id": "Cabin",
                "behavior": "seatbelt",
                "behavior_config": {"confidence": 0.4},
            }
        ]
    }
    enqueued: list[dict] = []

    class _FakeQueue:
        def try_enqueue(self, job):
            enqueued.append(job)
            return True

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=_FakeQueue(),
    )
    bridge._vlm_enabled = True
    bridge._vlm_queue = _FakeQueue()

    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_cabin_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xff", {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}, {}),
    )
    after = {
        "id": "evt-cabin2",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "box": [0.1, 0.2, 0.3, 0.4],
        "current_zones": [f"cv_zone_{zone_uuid}"],
        "entered_zones": [f"cv_zone_{zone_uuid}"],
    }
    bridge._handle_event(after, {})
    assert len(enqueued) == 1
    assert enqueued[0].event_skeleton["metadata"]["crop_mode"] == "frigate_vehicle_bbox"
    assert enqueued[0].rule == "seatbelt_violation"


def test_bridge_red_light_skips_when_not_red(monkeypatch):
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    zone_light = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {"id": zone_obs, "zone_id": "Obs", "behavior": "red_light_observation"},
            {"id": zone_light, "zone_id": "Feux", "behavior": "traffic_light_color"},
        ]
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=object(),
        light_state_resolver=lambda _c: "green",
    )
    bridge._vlm_enabled = True
    bridge._vlm_queue = object()
    enqueued = []

    def _boom(*_a, **_k):
        enqueued.append(1)
        raise AssertionError("must not fetch jpeg when not red")

    _patch_red_light_frigate_snapshot(monkeypatch)
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_red_light_jpeg",
        _boom,
    )
    after = {
        "id": "evt-red",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [f"cv_zone_{zone_obs}"],
    }
    bridge._handle_event(after, {})
    assert enqueued == []
    assert bridge.stats().get("red_light_skipped_not_red", 0) >= 1


def test_bridge_red_light_does_not_remember_track_seen_during_green(monkeypatch):
    """A vehicle seen while the gate is still green must never be cached as a
    red-light candidate: retrying it once the light later turns red would tie
    a green/amber crossing to an unrelated red window (bug 1 in the temporal
    alignment fix)."""
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    zone_light = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_obs,
                "zone_id": "Obs",
                "behavior": "red_light_observation",
                "polygon": [
                    {"x": 0.65, "y": 0.35},
                    {"x": 0.95, "y": 0.35},
                    {"x": 0.95, "y": 0.65},
                    {"x": 0.65, "y": 0.65},
                ],
            },
            {"id": zone_light, "zone_id": "Feux", "behavior": "traffic_light_color"},
        ]
    }
    gate = {"gate": "green", "raw": "green", "stable": "green"}
    enqueued = []

    class _Queue:
        def try_enqueue(self, job):
            enqueued.append(job)
            return True

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=_Queue(),
        light_debug_resolver=lambda _c: gate,
    )
    _patch_red_light_frigate_snapshot(monkeypatch)
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_red_light_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xff", {"x": 0.7, "y": 0.4, "width": 0.1, "height": 0.1}, {}),
    )
    after = {
        "id": "evt-red-memory",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "box": [0.7, 0.4, 0.1, 0.1],
        "frame_time": 123.4,
    }

    bridge._handle_event(after, {})
    assert enqueued == []
    assert bridge.stats().get("red_light_skipped_not_red", 0) >= 1
    assert "evt-red-memory" not in bridge._red_light_active

    gate.update({"gate": "red", "raw": "red", "stable": "red"})
    bridge._retry_cached_red_light_tracks(camera_id=cam_uuid)

    # Nothing was ever remembered while the light was green, so the retry
    # (now that the light is red) must not resurrect this unrelated crossing.
    assert enqueued == []
    assert bridge.stats().get("red_light_memory_enqueued", 0) == 0


def test_bridge_red_light_remembers_track_seen_while_gate_already_red(monkeypatch):
    """A vehicle seen while the gate is already red is a legitimate candidate
    and must be cached (in addition to being enqueued immediately)."""
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    zone_light = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_obs,
                "zone_id": "Obs",
                "behavior": "red_light_observation",
                "polygon": [
                    {"x": 0.65, "y": 0.35},
                    {"x": 0.95, "y": 0.35},
                    {"x": 0.95, "y": 0.65},
                    {"x": 0.65, "y": 0.65},
                ],
            },
            {"id": zone_light, "zone_id": "Feux", "behavior": "traffic_light_color"},
        ]
    }
    gate = {"gate": "red", "raw": "red", "stable": "red"}
    enqueued = []

    class _Queue:
        def try_enqueue(self, job):
            enqueued.append(job)
            return True

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=_Queue(),
        light_debug_resolver=lambda _c: gate,
    )
    _patch_red_light_frigate_snapshot(monkeypatch)
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_red_light_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xff", {"x": 0.7, "y": 0.4, "width": 0.1, "height": 0.1}, {}),
    )
    after = {
        "id": "evt-red-already",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "box": [0.7, 0.4, 0.1, 0.1],
        "frame_time": 123.4,
    }

    bridge._handle_event(after, {})

    assert "evt-red-already" in bridge._red_light_active
    assert len(enqueued) == 1
    assert enqueued[0].event_skeleton["frigate_event_id"] == "evt-red-already"


def test_bridge_poll_red_light_camera_only_remembers_when_gate_red(monkeypatch):
    """_poll_red_light_camera must gate _remember_red_light_track on the live
    HSV state at poll time, not just at some later retry time."""
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_obs,
                "zone_id": "Obs",
                "behavior": "red_light_observation",
                "polygon": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 1.0, "y": 0.0},
                    {"x": 1.0, "y": 1.0},
                    {"x": 0.0, "y": 1.0},
                ],
            },
        ]
    }
    now = time.time()
    frigate_events = [
        {
            "id": "poll-evt-1",
            "camera": f"cv_{cam_uuid}",
            "label": "car",
            "start_time": now,
            "end_time": now,
            "frame_time": now,
            "box": [0.3, 0.4, 0.2, 0.2],
        }
    ]

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return json.dumps(frigate_events).encode("utf-8")

    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.urllib.request.urlopen",
        lambda *_a, **_k: _Resp(),
    )

    gate = {"gate": "green", "raw": "green", "stable": "green"}
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=object(),
        light_debug_resolver=lambda _c: gate,
    )

    bridge._poll_red_light_camera(cam_uuid)
    assert "poll-evt-1" not in bridge._red_light_active

    gate.update({"gate": "red", "raw": "red", "stable": "red"})
    bridge._poll_red_light_camera(cam_uuid)
    assert "poll-evt-1" in bridge._red_light_active


def test_bridge_red_light_does_not_remember_track_when_raw_red_but_stable_green(monkeypatch):
    """A single noisy/misdecoded frame (raw=red) must not be enough to cache a
    track for later retry when the majority-vote stable state disagrees
    (stable=green) — this is the transient AI/Frigate phase-skew case."""
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    zone_light = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_obs,
                "zone_id": "Obs",
                "behavior": "red_light_observation",
                "polygon": [
                    {"x": 0.65, "y": 0.35},
                    {"x": 0.95, "y": 0.35},
                    {"x": 0.95, "y": 0.65},
                    {"x": 0.65, "y": 0.65},
                ],
            },
            {"id": zone_light, "zone_id": "Feux", "behavior": "traffic_light_color"},
        ]
    }
    # raw flips red for a single frame, but the stable (majority-vote) state
    # still reports green — the old gate (gate==raw=="red") would memorize
    # this track; the hardened gate must not.
    gate = {"gate": "red", "raw": "red", "stable": "green"}

    class _Queue:
        def try_enqueue(self, job):
            return True

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=_Queue(),
        light_debug_resolver=lambda _c: gate,
    )
    _patch_red_light_frigate_snapshot(monkeypatch)
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_red_light_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xff", {"x": 0.7, "y": 0.4, "width": 0.1, "height": 0.1}, {}),
    )
    after = {
        "id": "evt-raw-red-stable-green",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "box": [0.7, 0.4, 0.1, 0.1],
        "frame_time": 123.4,
    }

    bridge._handle_event(after, {})

    assert "evt-raw-red-stable-green" not in bridge._red_light_active


def test_bridge_poll_red_light_camera_does_not_remember_when_stable_green(monkeypatch):
    """_poll_red_light_camera must also require the stable HSV vote to be red,
    not just a possibly-noisy raw frame, before caching a track for retry."""
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_obs,
                "zone_id": "Obs",
                "behavior": "red_light_observation",
                "polygon": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 1.0, "y": 0.0},
                    {"x": 1.0, "y": 1.0},
                    {"x": 0.0, "y": 1.0},
                ],
            },
        ]
    }
    now = time.time()
    frigate_events = [
        {
            "id": "poll-evt-noisy",
            "camera": f"cv_{cam_uuid}",
            "label": "car",
            "start_time": now,
            "end_time": now,
            "frame_time": now,
            "box": [0.3, 0.4, 0.2, 0.2],
        }
    ]

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return json.dumps(frigate_events).encode("utf-8")

    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.urllib.request.urlopen",
        lambda *_a, **_k: _Resp(),
    )

    # raw is red (single-frame flip) but stable still says green.
    gate = {"gate": "red", "raw": "red", "stable": "green"}
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=object(),
        light_debug_resolver=lambda _c: gate,
    )

    bridge._poll_red_light_camera(cam_uuid)
    assert "poll-evt-noisy" not in bridge._red_light_active

    # Once the stable vote also confirms red, memorization proceeds normally.
    gate.update({"gate": "red", "raw": "red", "stable": "red"})
    bridge._poll_red_light_camera(cam_uuid)
    assert "poll-evt-noisy" in bridge._red_light_active


def test_bridge_red_light_skips_grace_without_raw_red(monkeypatch):
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    zone_light = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {"id": zone_obs, "zone_id": "Obs", "behavior": "red_light_observation"},
            {"id": zone_light, "zone_id": "Feux", "behavior": "traffic_light_color"},
        ]
    }
    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=object(),
        light_state_resolver=lambda _c: "red",
        light_debug_resolver=lambda _c: {
            "gate": "red",
            "raw": "green",
            "stable": "red",
            "grace_active": True,
        },
    )
    bridge._vlm_enabled = True
    bridge._vlm_queue = object()

    def _boom(*_a, **_k):
        raise AssertionError("must not fetch jpeg when raw light is not red")

    _patch_red_light_frigate_snapshot(monkeypatch)
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_red_light_jpeg",
        _boom,
    )
    after = {
        "id": "evt-red-grace",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [f"cv_zone_{zone_obs}"],
    }
    bridge._handle_event(after, {})
    assert bridge.stats().get("red_light_skipped_not_raw_red", 0) >= 1


def test_bridge_red_light_event_carries_anchor(monkeypatch):
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    zone_light = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {"id": zone_obs, "zone_id": "Obs", "behavior": "red_light_observation"},
            {
                "id": zone_light,
                "zone_id": "Feux",
                "behavior": "traffic_light_color",
                "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.1}, {"x": 0.2, "y": 0.2}],
            },
        ]
    }
    enqueued = []

    class _Queue:
        def try_enqueue(self, job):
            enqueued.append(job)
            return True

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=_Queue(),
        light_state_resolver=lambda _c: "red",
        light_debug_resolver=lambda _c: {
            "gate": "red",
            "raw": "red",
            "stable": "red",
            "grace_active": False,
        },
    )
    _patch_red_light_frigate_snapshot(monkeypatch)
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_red_light_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xff", {"x": 0.3, "y": 0.4, "width": 0.1, "height": 0.1}, {}),
    )
    after = {
        "id": "evt-red-anchor",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [f"cv_zone_{zone_obs}"],
        "box": [0.7, 0.4, 0.1, 0.1],
        "frame_time": 123.4,
        "start_time": 120.0,
    }
    bridge._handle_event(after, {})
    assert len(enqueued) == 1
    skel = enqueued[0].event_skeleton
    assert skel["bbox"] == {"x": 0.7, "y": 0.4, "width": 0.1, "height": 0.1, "norm": True}
    assert skel["metadata"]["red_light_context_bbox"] == {"x": 0.3, "y": 0.4, "width": 0.1, "height": 0.1}
    assert isinstance(skel["bbox_ts"], float)
    assert skel["metadata"]["violation_instant_ts"] == skel["bbox_ts"]
    assert skel["metadata"]["hsv_gate_ts"] == skel["bbox_ts"]
    assert skel["metadata"]["frigate_frame_time"] == 123.4
    assert skel["metadata"]["frigate_start_time"] == 120.0


def test_bridge_red_light_infers_observation_zone_from_bbox(monkeypatch):
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    zone_light = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_obs,
                "zone_id": "Obs",
                "behavior": "red_light_observation",
                "polygon": [
                    {"x": 0.65, "y": 0.35},
                    {"x": 0.95, "y": 0.35},
                    {"x": 0.95, "y": 0.65},
                    {"x": 0.65, "y": 0.65},
                ],
            },
            {
                "id": zone_light,
                "zone_id": "Feux",
                "behavior": "traffic_light_color",
                "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.1}, {"x": 0.2, "y": 0.2}],
            },
        ]
    }
    enqueued = []

    class _Queue:
        def try_enqueue(self, job):
            enqueued.append(job)
            return True

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=_Queue(),
        light_state_resolver=lambda _c: "red",
        light_debug_resolver=lambda _c: {
            "gate": "red",
            "raw": "red",
            "stable": "red",
            "grace_active": False,
        },
    )
    _patch_red_light_frigate_snapshot(monkeypatch)
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_red_light_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xff", {"x": 0.3, "y": 0.4, "width": 0.1, "height": 0.1}, {}),
    )
    after = {
        "id": "evt-red-inferred-zone",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [],
        "entered_zones": [],
        "box": [0.7, 0.4, 0.1, 0.1],
        "frame_time": 123.4,
        "start_time": 120.0,
    }
    bridge._handle_event(after, {})
    assert len(enqueued) == 1
    assert enqueued[0].event_skeleton["zone_id"] == "Obs"


def test_bridge_red_light_skips_bbox_outside_observation_zone(monkeypatch):
    zone_obs = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"
    zone_light = "dddddddd-bbbb-cccc-dddd-eeeeeeeeeeee"
    cam_uuid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
    spatial = {
        "zones": [
            {
                "id": zone_obs,
                "zone_id": "Obs",
                "behavior": "red_light_observation",
                "polygon": [
                    {"x": 0.65, "y": 0.35},
                    {"x": 0.95, "y": 0.35},
                    {"x": 0.95, "y": 0.65},
                    {"x": 0.65, "y": 0.65},
                ],
            },
            {
                "id": zone_light,
                "zone_id": "Feux",
                "behavior": "traffic_light_color",
                "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.1}, {"x": 0.2, "y": 0.2}],
            },
        ]
    }

    class _Queue:
        def try_enqueue(self, _job):
            raise AssertionError("must not enqueue a bbox outside Zone_Observation")

    bridge = FrigateEventBridge(
        frigate_url="http://127.0.0.1:5000",
        mqtt_host="127.0.0.1",
        mqtt_port=1884,
        spatial_resolver=lambda _c: spatial,
        vlm_enabled=True,
        vlm_queue=_Queue(),
        light_state_resolver=lambda _c: "red",
        light_debug_resolver=lambda _c: {
            "gate": "red",
            "raw": "red",
            "stable": "red",
            "grace_active": False,
        },
    )
    _patch_red_light_frigate_snapshot(monkeypatch)
    monkeypatch.setattr(
        "citevision_ai.frigate_bridge.bridge.fetch_red_light_jpeg",
        lambda *_a, **_k: (b"\xff\xd8\xff", {"x": 0.3, "y": 0.4, "width": 0.1, "height": 0.1}, {}),
    )
    after = {
        "id": "evt-red-wrong-bbox",
        "camera": f"cv_{cam_uuid}",
        "label": "car",
        "current_zones": [f"cv_zone_{zone_obs}"],
        "box": [948, 250, 990, 278],
        "frame_time": 123.4,
        "start_time": 120.0,
    }
    bridge._handle_event(after, {})
    assert bridge.stats().get("red_light_skipped_bbox_outside_zone", 0) >= 1


def test_bridge_vehicle_bbox_converts_pixel_xyxy():
    box = FrigateEventBridge._vehicle_bbox_from_after({"box": [1242, 293, 1278, 376]})
    assert box == {"x": 1242.0, "y": 293.0, "width": 36.0, "height": 83.0}


def test_bridge_bbox_center_accepts_frigate_coordinates_string():
    zinfo = {"coordinates": "0.65,0.35,0.95,0.35,0.95,0.65,0.65,0.65"}
    assert FrigateEventBridge._bbox_center_in_zone(
        {"x": 0.7, "y": 0.4, "width": 0.1, "height": 0.1, "norm": True},
        zinfo,
    )
    assert not FrigateEventBridge._bbox_center_in_zone(
        {"x": 948, "y": 250, "width": 42, "height": 28},
        zinfo,
    )


def test_bridge_bbox_ts_uses_latest_frigate_path_point():
    ts = FrigateEventBridge._bbox_ts_from_after(
        {
            "start_time": 100.0,
            "data": {
                "box": [0.7, 0.4, 0.1, 0.1],
                "path_data": [[[0.8, 0.45], 101.2], [[0.72, 0.45], 102.4]],
            },
        },
        fallback=200.0,
    )
    assert ts == 102.4


def test_bridge_gate_state_or_mode_raw_red_stable_green():
    from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

    eng = TrafficLightEngine()
    eng.configure_bridge_gate(mode="or", post_red_grace_sec=0)
    cam = "cam-1"
    assert eng.bridge_gate_state(cam) == "unknown"
    eng._stable_state[cam] = "green"
    eng._raw_state[cam] = "red"
    assert eng.bridge_gate_state(cam) == "red"
    eng._raw_state[cam] = "green"
    assert eng.bridge_gate_state(cam) == "green"


def test_bridge_gate_debug_recomputes_stale_snapshot():
    from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

    eng = TrafficLightEngine()
    eng.configure_bridge_gate(mode="or", post_red_grace_sec=0)
    cam = "cam-stale"
    eng._stable_state[cam] = "green"
    eng._raw_state[cam] = "green"
    assert eng.bridge_gate_debug(cam)["gate"] == "green"

    eng._stable_state[cam] = "red"
    eng._raw_state[cam] = "green"
    dbg = eng.bridge_gate_debug(cam)
    assert dbg["stable"] == "red"
    assert dbg["gate"] == "red"


def test_bridge_gate_state_and_mode_legacy():
    from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

    eng = TrafficLightEngine()
    eng.configure_bridge_gate(mode="and", post_red_grace_sec=0)
    cam = "cam-2"
    eng._stable_state[cam] = "green"
    eng._raw_state[cam] = "red"
    assert eng.bridge_gate_state(cam) == "green"
    eng._raw_state[cam] = "red"
    eng._stable_state[cam] = "red"
    assert eng.bridge_gate_state(cam) == "red"


def test_bridge_gate_debug_recomputes_stale_snapshot():
    from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine

    eng = TrafficLightEngine()
    cam = "cam-debug"
    eng._raw_state[cam] = "green"
    eng._stable_state[cam] = "green"
    assert eng.bridge_gate_debug(cam)["gate"] == "green"
    eng._raw_state[cam] = "red"
    eng._stable_state[cam] = "red"
    dbg = eng.bridge_gate_debug(cam)
    assert dbg["raw"] == "red"
    assert dbg["stable"] == "red"
    assert dbg["gate"] == "red"


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
