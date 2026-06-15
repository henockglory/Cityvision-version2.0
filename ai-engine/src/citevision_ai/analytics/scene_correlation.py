from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class SceneCorrelationEngine:
    """Cross-entity correlation within a single scene."""

    def __init__(self, proximity_radius: float = 100.0, proximity_duration: float = 30.0) -> None:
        self.proximity_radius = proximity_radius
        self.proximity_duration = proximity_duration
        self._proximity_start: dict[tuple[str, int, int], datetime] = {}
        self._fired: set[tuple[str, int, int]] = set()

    def analyze(
        self,
        camera_id: str,
        tracks: list[dict],
        zone_dwell: dict[tuple[str, int], float],
        timestamp: str,
    ) -> list[dict[str, Any]]:
        now = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        events: list[dict[str, Any]] = []
        persons = [t for t in tracks if t.get("class_name") == "person"]
        vehicles = [
            t for t in tracks
            if t.get("class_name") in ("car", "truck", "bus", "motorcycle")
        ]

        for person in persons:
            pb = person["bbox"]
            px = pb["x"] + pb["width"] / 2
            py = pb["y"] + pb["height"] / 2
            for vehicle in vehicles:
                vb = vehicle["bbox"]
                vx = vb["x"] + vb["width"] / 2
                vy = vb["y"] + vb["height"] / 2
                dist = ((px - vx) ** 2 + (py - vy) ** 2) ** 0.5
                key = (camera_id, person["track_id"], vehicle["track_id"])
                if dist <= self.proximity_radius:
                    if key not in self._proximity_start:
                        self._proximity_start[key] = now
                    duration = (now - self._proximity_start[key]).total_seconds()
                    if duration >= self.proximity_duration and key not in self._fired:
                        self._fired.add(key)
                        events.append(self._evt(
                            camera_id, "person_vehicle_proximity", person["track_id"],
                            timestamp, {"vehicle_track_id": vehicle["track_id"], "duration_seconds": duration},
                        ))
                else:
                    self._proximity_start.pop(key, None)
                    self._fired.discard(key)

        if len(persons) >= 2 and len(vehicles) == 1:
            v = vehicles[0]
            near = 0
            vb = v["bbox"]
            vx = vb["x"] + vb["width"] / 2
            vy = vb["y"] + vb["height"] / 2
            for person in persons:
                pb = person["bbox"]
                px = pb["x"] + pb["width"] / 2
                py = pb["y"] + pb["height"] / 2
                if ((px - vx) ** 2 + (py - vy) ** 2) ** 0.5 <= self.proximity_radius * 1.5:
                    near += 1
            if near >= 2:
                events.append(self._evt(
                    camera_id, "multiple_persons_one_vehicle", v["track_id"],
                    timestamp, {"person_count": near},
                ))

        for (cam, tid), dwell in zone_dwell.items():
            if cam != camera_id or dwell < 60:
                continue
            events.append(self._evt(
                camera_id, "loitering_near_entrance", tid, timestamp,
                {"dwell_seconds": dwell},
            ))

        return events

    @staticmethod
    def _evt(
        camera_id: str,
        event_type: str,
        track_id: int,
        timestamp: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "severity": "warning",
            "track_id": track_id,
            "metadata": metadata,
        }
