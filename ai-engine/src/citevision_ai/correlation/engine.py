from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class CorrelationMatch:
    correlation_id: str
    track_ids: list[int]
    camera_ids: list[str]
    score: float
    reason: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CorrelationEngine:
    """Correlates tracks across cameras using spatial-temporal heuristics."""

    def __init__(self, time_window_seconds: float = 5.0, spatial_threshold: float = 0.15) -> None:
        self.time_window_seconds = time_window_seconds
        self.spatial_threshold = spatial_threshold
        self._recent: list[dict[str, Any]] = []

    def ingest(
        self,
        camera_id: str,
        track_id: int,
        normalized_centroid: tuple[float, float],
        class_name: str,
        timestamp: float | None = None,
    ) -> list[CorrelationMatch]:
        ts = timestamp or datetime.now(timezone.utc).timestamp()
        entry = {
            "camera_id": camera_id,
            "track_id": track_id,
            "centroid": normalized_centroid,
            "class_name": class_name,
            "timestamp": ts,
        }
        self._recent.append(entry)
        cutoff = ts - self.time_window_seconds
        self._recent = [e for e in self._recent if e["timestamp"] >= cutoff]

        matches: list[CorrelationMatch] = []
        for other in self._recent:
            if other is entry or other["camera_id"] == camera_id:
                continue
            if other["class_name"] != class_name:
                continue
            dx = abs(other["centroid"][0] - normalized_centroid[0])
            dy = abs(other["centroid"][1] - normalized_centroid[1])
            dist = (dx**2 + dy**2) ** 0.5
            if dist <= self.spatial_threshold:
                score = max(0.0, 1.0 - dist / self.spatial_threshold)
                matches.append(
                    CorrelationMatch(
                        correlation_id=str(uuid4()),
                        track_ids=[track_id, other["track_id"]],
                        camera_ids=[camera_id, other["camera_id"]],
                        score=score,
                        reason="spatial_temporal_proximity",
                    )
                )
        return matches
