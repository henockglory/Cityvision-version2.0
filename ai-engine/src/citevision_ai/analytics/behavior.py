from __future__ import annotations

from typing import Any


class BehaviorHeuristics:
    """Rule-of-thumb behavior classifiers from track history."""

    def __init__(self, speed_threshold: float = 200.0) -> None:
        self.speed_threshold = speed_threshold
        self._history: dict[tuple[str, int], list[tuple[float, float]]] = {}

    def update(
        self, camera_id: str, track_id: int, cx: float, cy: float
    ) -> dict[str, Any] | None:
        key = (camera_id, track_id)
        hist = self._history.setdefault(key, [])
        hist.append((cx, cy))
        if len(hist) > 10:
            hist.pop(0)
        if len(hist) < 2:
            return None

        dx = hist[-1][0] - hist[0][0]
        dy = hist[-1][1] - hist[0][1]
        speed = (dx**2 + dy**2) ** 0.5

        if speed > self.speed_threshold:
            return {"heuristic": "running", "speed_px": speed}
        if len(hist) >= 5 and speed < 5.0:
            return {"heuristic": "stationary", "speed_px": speed}
        return None

    def crowd_density(self, detections: list[dict], area_px: float) -> dict[str, Any]:
        count = len(detections)
        density = count / max(area_px, 1.0)
        level = "normal"
        if density > 0.001:
            level = "elevated"
        if density > 0.005:
            level = "critical"
        return {"count": count, "density": density, "level": level}
