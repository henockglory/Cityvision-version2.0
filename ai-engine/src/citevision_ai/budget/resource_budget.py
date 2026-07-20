from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetProfile:
    width: int
    height: int
    target_fps: float


PROFILES = {
    "single": BudgetProfile(width=1920, height=1080, target_fps=5.0),
    "multi_small": BudgetProfile(width=640, height=480, target_fps=5.0),
    "multi_large": BudgetProfile(width=320, height=240, target_fps=5.0),
}


class ResourceBudgetManager:
    """Adaptive resource allocation based on active camera count."""

    def __init__(self, max_cameras: int = 12) -> None:
        self.max_cameras = max_cameras
        self._active_cameras: set[str] = set()

    def register_camera(self, camera_id: str) -> None:
        if len(self._active_cameras) >= self.max_cameras:
            raise ValueError(f"Maximum camera count ({self.max_cameras}) exceeded")
        self._active_cameras.add(camera_id)

    def unregister_camera(self, camera_id: str) -> None:
        self._active_cameras.discard(camera_id)

    @property
    def camera_count(self) -> int:
        return len(self._active_cameras)

    def get_profile(self) -> BudgetProfile:
        count = self.camera_count
        if count <= 1:
            return PROFILES["single"]
        if count <= 4:
            return PROFILES["multi_small"]
        return PROFILES["multi_large"]

    def frame_skip_interval(self, source_fps: float = 30.0) -> int:
        profile = self.get_profile()
        if profile.target_fps <= 0:
            return 1
        return max(1, int(round(source_fps / profile.target_fps)))
