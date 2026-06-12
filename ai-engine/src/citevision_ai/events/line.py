"""Line crossing detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LineCrossDetector:
    line_id: str
    p1: tuple[float, float]
    p2: tuple[float, float]
    direction: str = "both"  # "in", "out", "both"

    def __post_init__(self) -> None:
        self._prev_side: dict[int, float] = {}

    def _side(self, x: float, y: float) -> float:
        x1, y1 = self.p1
        x2, y2 = self.p2
        return (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)

    def update(self, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for track in tracks:
            track_id = int(track["track_id"])
            bbox = track.get("bbox", {})
            if not bbox:
                continue
            cx = (bbox["x1"] + bbox["x2"]) / 2
            cy = (bbox["y1"] + bbox["y2"]) / 2
            side = self._side(cx, cy)
            prev = self._prev_side.get(track_id)
            if prev is not None and prev * side < 0:
                events.append({
                    "track_id": track_id,
                    "line_id": self.line_id,
                    "direction": self.direction,
                })
            self._prev_side[track_id] = side
        return events
