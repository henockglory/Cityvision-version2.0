from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class CorrelationEngine:
    """Cross-camera track correlation by class and temporal proximity."""

    def __init__(self, default_window_seconds: float = 60.0) -> None:
        self.default_window_seconds = default_window_seconds
        self._recent_exits: list[dict[str, Any]] = []

    def record_exit(
        self,
        camera_id: str,
        track_id: int,
        class_name: str,
        timestamp: str | None = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        self._recent_exits.append(
            {
                "camera_id": camera_id,
                "track_id": track_id,
                "class_name": class_name,
                "timestamp": ts,
            }
        )
        if len(self._recent_exits) > 500:
            self._recent_exits = self._recent_exits[-500:]

    def find_matches(
        self,
        camera_id: str,
        track_id: int,
        class_name: str,
        source_camera_id: str,
        max_delta: float | None = None,
        timestamp: str | None = None,
    ) -> list[dict[str, Any]]:
        window = max_delta or self.default_window_seconds
        now = datetime.fromisoformat(
            (timestamp or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
        )
        matches: list[dict[str, Any]] = []

        for exit_evt in self._recent_exits:
            if exit_evt["camera_id"] != source_camera_id:
                continue
            if exit_evt["class_name"] != class_name:
                continue
            exit_time = datetime.fromisoformat(exit_evt["timestamp"].replace("Z", "+00:00"))
            delta = abs((now - exit_time).total_seconds())
            if delta <= window:
                matches.append(
                    {
                        "event_id": str(uuid.uuid4()),
                        "event_type": "correlation_match",
                        "camera_id": camera_id,
                        "timestamp": now.isoformat(),
                        "severity": "info",
                        "track_id": track_id,
                        "metadata": {
                            "source_camera_id": source_camera_id,
                            "source_track_id": exit_evt["track_id"],
                            "time_delta_seconds": delta,
                            "class_name": class_name,
                        },
                    }
                )
        return matches
