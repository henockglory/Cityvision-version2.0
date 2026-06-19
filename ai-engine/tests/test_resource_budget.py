import pytest

from citevision_ai.budget.resource_budget import ResourceBudgetManager


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
