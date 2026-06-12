"""Loitering detection based on dwell time in a region."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoiteringDetector:
    dwell_seconds: float = 30.0
    radius: float = 0.05  # normalized distance threshold
    _positions: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    _triggered: set[int] = field(default_factory=set)

    def _dist(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def update(self, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = time.monotonic()
        events: list[dict[str, Any]] = []
        active: set[int] = set()

        for track in tracks:
            track_id = int(track["track_id"])
            bbox = track.get("bbox", {})
            if not bbox:
                continue
            active.add(track_id)
            cx = (bbox["x1"] + bbox["x2"]) / 2
            cy = (bbox["y1"] + bbox["y2"]) / 2

            if track_id not in self._positions:
                self._positions[track_id] = (cx, cy, now)
                continue

            ox, oy, start = self._positions[track_id]
            if self._dist((cx, cy), (ox, oy)) > self.radius:
                self._positions[track_id] = (cx, cy, now)
                self._triggered.discard(track_id)
                continue

            dwell = now - start
            if dwell >= self.dwell_seconds and track_id not in self._triggered:
                self._triggered.add(track_id)
                events.append({
                    "track_id": track_id,
                    "dwell_seconds": round(dwell, 1),
                })

        stale = set(self._positions) - active
        for tid in stale:
            self._positions.pop(tid, None)
            self._triggered.discard(tid)

        return events
