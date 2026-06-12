"""Zone enter/exit detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Zone:
    zone_id: str
    polygon: list[tuple[float, float]]  # normalized 0-1 coords

    def contains(self, x: float, y: float) -> bool:
        """Ray-casting point-in-polygon test."""
        n = len(self.polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = self.polygon[i]
            xj, yj = self.polygon[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside
            j = i
        return inside


class ZoneStateTracker:
    def __init__(self, zones: list[Zone]) -> None:
        self.zones = zones
        self._inside: dict[tuple[str, int], set[str]] = {}

    def _centroid(self, bbox: dict[str, float], frame_w: float = 1.0, frame_h: float = 1.0) -> tuple[float, float]:
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        return ((x1 + x2) / 2) / frame_w, ((y1 + y2) / 2) / frame_h

    def update(self, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()

        for track in tracks:
            track_id = int(track["track_id"])
            bbox = track.get("bbox", {})
            if not bbox:
                continue
            cx, cy = self._centroid(bbox)
            for zone in self.zones:
                key = (zone.zone_id, track_id)
                seen.add(key)
                currently_inside = zone.contains(cx, cy)
                was_inside = key in self._inside

                if currently_inside and not was_inside:
                    events.append({
                        "event_type": "zone_enter",
                        "track_id": track_id,
                        "metadata": {"zone_id": zone.zone_id},
                    })
                    self._inside[key] = {zone.zone_id}
                elif not currently_inside and was_inside:
                    events.append({
                        "event_type": "zone_exit",
                        "track_id": track_id,
                        "metadata": {"zone_id": zone.zone_id},
                    })
                    self._inside.pop(key, None)

        return events
