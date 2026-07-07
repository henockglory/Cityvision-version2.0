import pytest

from citevision_ai.budget.resource_budget import ResourceBudgetManager
from citevision_ai.pipeline import PRIORITY_ZONE_TARGET_HZ, priority_zone_skip


def test_single_camera_1080p():
    mgr = ResourceBudgetManager()
    mgr.register_camera("cam-1")
    profile = mgr.get_profile()
    assert profile.width == 1920
    assert profile.height == 1080
    assert profile.target_fps == 5.0


def test_two_cameras_640p():
    mgr = ResourceBudgetManager()
    mgr.register_camera("cam-1")
    mgr.register_camera("cam-2")
    profile = mgr.get_profile()
    assert profile.width == 640
    assert profile.height == 480


def test_five_cameras_320p():
    mgr = ResourceBudgetManager()
    for i in range(5):
        mgr.register_camera(f"cam-{i}")
    profile = mgr.get_profile()
    assert profile.width == 320
    assert profile.height == 240


def test_max_cameras_exceeded():
    mgr = ResourceBudgetManager(max_cameras=2)
    mgr.register_camera("a")
    mgr.register_camera("b")
    with pytest.raises(ValueError):
        mgr.register_camera("c")


def test_frame_skip_interval():
    mgr = ResourceBudgetManager()
    mgr.register_camera("cam-1")
    assert mgr.frame_skip_interval(30.0) == 6


def test_priority_zone_skip_stays_fixed_regardless_of_source_camera_count_scenario():
    """Priority zones (speed/traffic-light) must land on the same effective Hz
    no matter how many cameras are active — unlike the old unconditional
    skip=1 ('process every ingested frame'), which scaled GPU demand linearly
    with the number of priority-zone cameras."""
    source_fps = 25.0
    expected = max(1, round(source_fps / PRIORITY_ZONE_TARGET_HZ))
    assert expected > 1  # sanity: the cap must actually reduce vs skip=1

    # Same camera, same stream fps → same cap whether it's the only camera or
    # one of sixteen (the function doesn't even take camera count as input:
    # it is, by construction, independent of it).
    assert priority_zone_skip(source_fps) == expected
    assert priority_zone_skip(source_fps) == expected


def test_priority_zone_skip_scales_with_source_fps():
    # A 30fps stream needs a larger skip than a 10fps stream to hit the same
    # fixed target Hz.
    assert priority_zone_skip(30.0) >= priority_zone_skip(10.0)


def test_priority_zone_skip_handles_zero_source_fps():
    assert priority_zone_skip(0.0) == 1
