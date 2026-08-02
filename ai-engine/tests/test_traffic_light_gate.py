"""Unit tests for D1/D2 red-light HSV gate (OR + post-red grace)."""
from __future__ import annotations

import time

import pytest

from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine


@pytest.fixture
def eng() -> TrafficLightEngine:
    e = TrafficLightEngine()
    e.configure_bridge_gate(mode="or", post_red_grace_sec=2.5)
    return e


def test_gate_or_raw_red_stable_green(eng: TrafficLightEngine) -> None:
    cam = "cam-or"
    eng._stable_state[cam] = "green"
    eng._raw_state[cam] = "red"
    assert eng.bridge_gate_state(cam) == "red"


def test_gate_and_requires_both(eng: TrafficLightEngine) -> None:
    cam = "cam-and"
    eng.configure_bridge_gate(mode="and")
    eng._stable_state[cam] = "green"
    eng._raw_state[cam] = "red"
    assert eng.bridge_gate_state(cam) == "green"
    eng._stable_state[cam] = "red"
    assert eng.bridge_gate_state(cam) == "red"


def test_gate_raw_only(eng: TrafficLightEngine) -> None:
    cam = "cam-raw"
    eng.configure_bridge_gate(mode="raw")
    eng._stable_state[cam] = "red"
    eng._raw_state[cam] = "green"
    assert eng.bridge_gate_state(cam) == "green"
    eng._raw_state[cam] = "red"
    assert eng.bridge_gate_state(cam) == "red"


def test_post_red_grace(eng: TrafficLightEngine) -> None:
    cam = "cam-grace"
    eng.configure_bridge_gate(mode="or", post_red_grace_sec=2.5)
    eng._raw_state[cam] = "red"
    eng._stable_state[cam] = "red"
    assert eng.bridge_gate_state(cam) == "red"
    eng._raw_state[cam] = "green"
    eng._stable_state[cam] = "green"
    assert eng.bridge_gate_state(cam) == "red"
    dbg = eng.bridge_gate_debug(cam)
    assert dbg.get("grace_active") is True
    eng._last_raw_red_mono[cam] = time.monotonic() - 5.0
    assert eng.bridge_gate_state(cam) == "green"


def test_bridge_gate_debug_fields(eng: TrafficLightEngine) -> None:
    cam = "cam-dbg"
    eng._raw_state[cam] = "red"
    eng._stable_state[cam] = "amber"
    eng.bridge_gate_state(cam)
    dbg = eng.bridge_gate_debug(cam)
    assert dbg["raw"] == "red"
    assert dbg["stable"] == "amber"
    assert dbg["gate_mode"] == "or"
    assert dbg["post_red_grace_sec"] == 2.5
