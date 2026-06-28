"""Zone-based speed measurement (Frigate-style real-distance calibration).

A zone with behavior ``speed_measurement`` declares the *real* ground distance
(in metres) that the zone spans along the direction of travel, plus a speed
limit. We time how long a vehicle's centroid stays inside the polygon
(entry → exit) and compute:

    speed_kmh = distance_m / elapsed_seconds * 3.6

When the measured speed exceeds the configured limit we emit a ``speeding``
event for that vehicle, carrying the measured speed so evidence/email/plate
linking can use it. This avoids relying on a global homography calibration.
"""

from __future__ import annotations

import uuid
from typing import Any

SPEED_BEHAVIOR = "speed_measurement"
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}


def _point_in_polygon(px: float, py: float, polygon: list[dict]) -> bool:
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(polygon[i].get("x", 0)), float(polygon[i].get("y", 0))
        xj, yj = float(polygon[j].get("x", 0)), float(polygon[j].get("y", 0))
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


class ZoneSpeedEngine:
    """Measures vehicle speed from zone entry/exit timing and a real distance."""

    def __init__(self) -> None:
        # (camera, zone_id, track_id) -> entry monotonic time
        self._entry_time: dict[tuple[str, str, int], float] = {}
        # remember last-known inside state to detect the exit edge
        self._inside: dict[tuple[str, str, int], bool] = {}
        self._cooldown: dict[tuple[str, str, int], float] = {}

    def camera_has_behavior(self, zones: list[dict] | None) -> bool:
        if not zones:
            return False
        return any(str(z.get("behavior", "")) == SPEED_BEHAVIOR for z in zones)

    def process_frame(
        self,
        camera_id: str,
        tracks: list[dict],
        zones: list[dict] | None,
        frame_w: int,
        frame_h: int,
        now_ts: float,
        iso_ts: str,
    ) -> list[dict[str, Any]]:
        if not zones:
            return []
        speed_zones = [z for z in zones if str(z.get("behavior", "")) == SPEED_BEHAVIOR]
        if not speed_zones:
            return []

        events: list[dict[str, Any]] = []
        for sz in speed_zones:
            cfg = sz.get("behavior_config") or {}
            try:
                distance_m = float(cfg.get("distance_m", 0) or 0)
            except (TypeError, ValueError):
                distance_m = 0.0
            try:
                limit = float(cfg.get("speed_limit_kmh", 0) or 0)
            except (TypeError, ValueError):
                limit = 0.0
            class_filter = str(cfg.get("class_filter", "car"))
            zone_id = str(sz.get("zone_id", sz.get("name", "zone")))
            poly = sz.get("polygon") or []
            if distance_m <= 0 or not poly:
                # No real distance configured → cannot measure honestly; skip.
                continue

            present_tracks: set[int] = set()
            for track in tracks:
                cls = str(track.get("class_name", ""))
                if class_filter not in ("any", "") and cls != class_filter and cls not in VEHICLE_CLASSES:
                    continue
                tid = int(track.get("track_id", -1))
                if tid < 0:
                    continue
                bbox = track.get("bbox") or {}
                cx = (float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2) / max(frame_w, 1)
                cy = (float(bbox.get("y", 0)) + float(bbox.get("height", 0)) / 2) / max(frame_h, 1)
                inside = _point_in_polygon(cx, cy, poly)
                key = (camera_id, zone_id, tid)
                if inside:
                    present_tracks.add(tid)
                    if key not in self._entry_time:
                        self._entry_time[key] = now_ts
                    self._inside[key] = True
                elif self._inside.get(key):
                    # Exit edge → compute speed.
                    self._inside[key] = False
                    entry = self._entry_time.pop(key, None)
                    if entry is None:
                        continue
                    elapsed = max(now_ts - entry, 1e-3)
                    speed_kmh = distance_m / elapsed * 3.6
                    last = self._cooldown.get(key, -9999.0)
                    if speed_kmh > limit and (now_ts - last) > 2.0:
                        self._cooldown[key] = now_ts
                        events.append(
                            self._make_speeding_event(
                                camera_id, track, zone_id, speed_kmh, limit, distance_m, elapsed, iso_ts
                            )
                        )
        return events

    @staticmethod
    def _make_speeding_event(
        camera_id: str,
        track: dict,
        zone_id: str,
        speed_kmh: float,
        limit: float,
        distance_m: float,
        elapsed_s: float,
        iso_ts: str,
    ) -> dict[str, Any]:
        bbox = track.get("bbox") or {}
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": "speeding",
            "event": "speeding",
            "timestamp": iso_ts,
            "track_id": track.get("track_id"),
            "class_name": track.get("class_name"),
            "zone_id": zone_id,
            "bbox": bbox,
            "speed_kmh": round(speed_kmh, 1),
            "confidence": 0.85,
            "severity": "high",
            "metadata": {
                "speed_kmh": round(speed_kmh, 1),
                "speed_limit_kmh": limit,
                "distance_m": distance_m,
                "elapsed_s": round(elapsed_s, 2),
                "detection_method": "zone_distance_timing",
            },
        }
