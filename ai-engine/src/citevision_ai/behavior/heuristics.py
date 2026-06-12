from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BehaviorLabel(str, Enum):
    NORMAL = "normal"
    RUNNING = "running"
    CROWDING = "crowding"
    ABANDONED_OBJECT = "abandoned_object"
    TAILGATING = "tailgating"
    WRONG_WAY = "wrong_way"


@dataclass
class BehaviorSignal:
    track_id: int
    label: BehaviorLabel
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)


class BehaviorHeuristics:
    """Rule-based behavior classification from track kinematics and context."""

    def __init__(
        self,
        speed_threshold: float = 120.0,
        crowding_min_tracks: int = 5,
        crowding_radius: float = 80.0,
    ) -> None:
        self.speed_threshold = speed_threshold
        self.crowding_min_tracks = crowding_min_tracks
        self.crowding_radius = crowding_radius

    @staticmethod
    def _speed(history: list[tuple[float, float]]) -> float:
        if len(history) < 2:
            return 0.0
        x1, y1 = history[-2]
        x2, y2 = history[-1]
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    def evaluate_track(
        self,
        track_id: int,
        history: list[tuple[float, float]],
        class_name: str,
    ) -> BehaviorSignal:
        speed = self._speed(history)
        if speed >= self.speed_threshold and class_name == "person":
            return BehaviorSignal(track_id, BehaviorLabel.RUNNING, 0.7, {"speed": speed})
        return BehaviorSignal(track_id, BehaviorLabel.NORMAL, 0.9, {"speed": speed})

    def evaluate_scene(
        self,
        centroids: list[tuple[int, tuple[float, float]]],
    ) -> list[BehaviorSignal]:
        signals: list[BehaviorSignal] = []
        if len(centroids) < self.crowding_min_tracks:
            return signals
        for i, (tid, (x, y)) in enumerate(centroids):
            neighbors = 0
            for j, (_, (ox, oy)) in enumerate(centroids):
                if i == j:
                    continue
                if ((x - ox) ** 2 + (y - oy) ** 2) ** 0.5 <= self.crowding_radius:
                    neighbors += 1
            if neighbors >= self.crowding_min_tracks - 1:
                signals.append(
                    BehaviorSignal(
                        tid,
                        BehaviorLabel.CROWDING,
                        0.6,
                        {"neighbor_count": neighbors},
                    )
                )
        return signals
