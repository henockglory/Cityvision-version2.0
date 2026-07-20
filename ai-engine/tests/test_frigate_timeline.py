"""Tests for Frigate demo timeline alignment helpers."""

from citevision_ai.evidence.frigate_timeline import (
    aligned_anchor,
    demo_loop_absolute_align_ok,
    frigate_times_look_stream_relative,
    learn_clock_offset,
    min_time_delta,
    same_demo_loop_cycle,
    wall_clock_skewed_from_frigate,
)


def test_aligned_anchor_applies_learned_offset():
    offsets = {"cam": 1500.0}
    assert aligned_anchor(offsets, "cam", 1_700_000_000.0) == 1_699_998_500.0


def test_min_time_delta_picks_closest_candidate():
    ev = {
        "start_time": 100.0,
        "frame_time": 99.0,
        "end_time": 108.0,
        "data": {"path_data": [[(0.1, 0.2), 102.0]]},
    }
    assert min_time_delta(101.5, ev) == 0.5


def test_wall_clock_skewed_from_frigate():
    events = [{"start_time": 120.5, "end_time": 125.0}]
    assert wall_clock_skewed_from_frigate(1_700_000_000.0, events) is True
    assert wall_clock_skewed_from_frigate(125.0, events) is False


def test_frigate_times_look_stream_relative():
    assert frigate_times_look_stream_relative([{"start_time": 45.0}]) is True
    assert frigate_times_look_stream_relative([{"start_time": 1_700_000_000.0}]) is False


def test_demo_loop_absolute_align_ok():
    assert demo_loop_absolute_align_ok(12.0, 30.0) is True
    assert demo_loop_absolute_align_ok(720.0, 30.0) is False


def test_same_demo_loop_cycle():
    loop = 352.52
    base = 1_700_000_100.0
    assert same_demo_loop_cycle(base, base + 10.0, loop) is True
    assert same_demo_loop_cycle(base, base + loop, loop) is False
    # Straddle floor(ts/loop) with tiny wall delta — must still accept.
    boundary = (int(base // loop) + 1) * loop
    assert same_demo_loop_cycle(boundary - 0.4, boundary + 0.4, loop) is True
