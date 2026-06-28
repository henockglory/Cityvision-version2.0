"""Traffic-light color classification per zone + red-light violation synergy.

This module implements the truthful red-light pipeline described in the demo plan:

  * A zone with behavior ``traffic_light_color`` defines the ROI of the traffic
    light. Its color (red / green / amber) is classified by HSV thresholds and
    smoothed over N frames to avoid flicker. A ``traffic_light_state`` event is
    emitted whenever the stable state changes.
  * A zone with behavior ``red_light_observation`` is the intersection/stop area.
    When the camera's stable light state is ``red`` AND a vehicle is *moving*
    inside this zone, a ``red_light_violation`` event is emitted for that
    specific vehicle (so ANPR / plate linking can target the offender).

All polygons received here are expected normalized (0..1) like the rest of the
spatial config; they are scaled to frame pixels internally.
"""

from __future__ import annotations

import uuid
from collections import deque
from typing import Any

import cv2
import numpy as np

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

TRAFFIC_LIGHT_BEHAVIOR = "traffic_light_color"
OBSERVATION_BEHAVIOR = "red_light_observation"


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


def _polygon_pixel_bbox(polygon: list[dict], w: int, h: int) -> tuple[int, int, int, int] | None:
    if not polygon:
        return None
    xs = [float(p.get("x", 0)) for p in polygon]
    ys = [float(p.get("y", 0)) for p in polygon]
    normalized = all(0 <= v <= 1.0 for v in xs + ys)
    sx, sy = (w, h) if normalized else (1, 1)
    x1 = max(0, int(min(xs) * sx))
    y1 = max(0, int(min(ys) * sy))
    x2 = min(w, int(max(xs) * sx))
    y2 = min(h, int(max(ys) * sy))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def classify_light_color(roi: np.ndarray) -> tuple[str, dict[str, float]]:
    """Classify a traffic-light ROI as red / green / amber / unknown via HSV ratios."""
    if roi is None or roi.size == 0:
        return "unknown", {}
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    total = max(hsv.shape[0] * hsv.shape[1], 1)

    red = cv2.inRange(hsv, np.array([0, 90, 90]), np.array([10, 255, 255])) | cv2.inRange(
        hsv, np.array([160, 90, 90]), np.array([180, 255, 255])
    )
    amber = cv2.inRange(hsv, np.array([11, 90, 90]), np.array([28, 255, 255]))
    green = cv2.inRange(hsv, np.array([40, 70, 70]), np.array([90, 255, 255]))

    ratios = {
        "red": float(np.count_nonzero(red)) / total,
        "amber": float(np.count_nonzero(amber)) / total,
        "green": float(np.count_nonzero(green)) / total,
    }
    state = max(ratios, key=ratios.get)
    # Require a minimum illuminated ratio, otherwise the light is off / not visible.
    if ratios[state] < 0.012:
        return "unknown", ratios
    return state, ratios


class TrafficLightEngine:
    """Per-camera traffic-light state + red-light violation synergy."""

    def __init__(self) -> None:
        # Smoothed state machine per camera.
        self._state_history: dict[str, deque[str]] = {}
        self._stable_state: dict[str, str] = {}
        # Previous centroids to estimate per-track motion (pixels/frame).
        self._prev_centroid: dict[tuple[str, int], tuple[float, float]] = {}
        self._cooldown: dict[tuple[str, int], int] = {}
        self._frame_counter = 0
        self._cooldown_frames = 45

    def camera_has_behavior(self, zones: list[dict] | None) -> bool:
        if not zones:
            return False
        return any(
            str(z.get("behavior", "")) in (TRAFFIC_LIGHT_BEHAVIOR, OBSERVATION_BEHAVIOR)
            for z in zones
        )

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        tracks: list[dict],
        timestamp: str,
        zones: list[dict] | None,
    ) -> list[dict[str, Any]]:
        self._frame_counter += 1
        if frame is None or frame.size == 0 or not zones:
            return []
        light_zones = [z for z in zones if str(z.get("behavior", "")) == TRAFFIC_LIGHT_BEHAVIOR]
        obs_zones = [z for z in zones if str(z.get("behavior", "")) == OBSERVATION_BEHAVIOR]
        if not light_zones and not obs_zones:
            return []

        h, w = frame.shape[:2]
        events: list[dict[str, Any]] = []

        # 1) Classify the traffic-light color from the dedicated zone(s).
        stable_window = 3
        new_state = self._stable_state.get(camera_id, "unknown")
        for lz in light_zones:
            cfg = lz.get("behavior_config") or {}
            try:
                stable_window = max(1, int(cfg.get("stable_frames", 3)))
            except (TypeError, ValueError):
                stable_window = 3
            box = _polygon_pixel_bbox(lz.get("polygon") or [], w, h)
            if not box:
                continue
            x1, y1, x2, y2 = box
            raw_state, _ = classify_light_color(frame[y1:y2, x1:x2])
            hist = self._state_history.setdefault(camera_id, deque(maxlen=max(stable_window, 1)))
            hist.append(raw_state)
            # Stable only if the window agrees.
            if len(hist) >= hist.maxlen and len(set(hist)) == 1:
                new_state = hist[0]
            break  # one traffic-light zone per camera is the supported case

        prev_stable = self._stable_state.get(camera_id)
        if new_state != prev_stable:
            self._stable_state[camera_id] = new_state
            events.append(
                self._make_state_event(camera_id, new_state, timestamp)
            )

        # 2) Red-light synergy: moving vehicle in observation zone while red.
        if self._stable_state.get(camera_id) == "red" and obs_zones:
            for oz in obs_zones:
                cfg = oz.get("behavior_config") or {}
                class_filter = str(cfg.get("class_filter", "car"))
                try:
                    min_motion = float(cfg.get("min_speed_px", 2))
                except (TypeError, ValueError):
                    min_motion = 2.0
                poly = oz.get("polygon") or []
                for track in tracks:
                    cls = str(track.get("class_name", ""))
                    if class_filter not in ("any", "") and cls != class_filter and cls not in VEHICLE_CLASSES:
                        continue
                    bbox = track.get("bbox") or {}
                    cx = (float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2)
                    cy = (float(bbox.get("y", 0)) + float(bbox.get("height", 0)) / 2)
                    ncx, ncy = cx / max(w, 1), cy / max(h, 1)
                    if poly and not _point_in_polygon(ncx, ncy, poly):
                        continue
                    tid = int(track.get("track_id", -1))
                    motion = self._motion_px(camera_id, tid, cx, cy)
                    if motion < min_motion:
                        continue
                    if not self._allow_emit(camera_id, tid):
                        continue
                    events.append(
                        self._make_violation_event(camera_id, track, timestamp, motion)
                    )

        # Always refresh centroid cache for motion estimation.
        for track in tracks:
            bbox = track.get("bbox") or {}
            cx = float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2
            cy = float(bbox.get("y", 0)) + float(bbox.get("height", 0)) / 2
            self._prev_centroid[(camera_id, int(track.get("track_id", -1)))] = (cx, cy)

        return events

    def _motion_px(self, camera_id: str, track_id: int, cx: float, cy: float) -> float:
        prev = self._prev_centroid.get((camera_id, track_id))
        if not prev:
            return 0.0
        return float(((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) ** 0.5)

    def _allow_emit(self, camera_id: str, track_id: int) -> bool:
        key = (camera_id, track_id)
        last = self._cooldown.get(key, -9999)
        if self._frame_counter - last < self._cooldown_frames:
            return False
        self._cooldown[key] = self._frame_counter
        return True

    @staticmethod
    def _make_state_event(camera_id: str, state: str, timestamp: str) -> dict[str, Any]:
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": "traffic_light_state",
            "event": "traffic_light_state",
            "timestamp": timestamp,
            "track_id": -1,
            "severity": "info",
            "metadata": {"state": state, "detection_method": "hsv_zone_classifier"},
        }

    @staticmethod
    def _make_violation_event(
        camera_id: str, track: dict, timestamp: str, motion_px: float
    ) -> dict[str, Any]:
        bbox = track.get("bbox") or {}
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": "red_light_violation",
            "event": "red_light_violation",
            "timestamp": timestamp,
            "track_id": track.get("track_id"),
            "class_name": track.get("class_name"),
            "bbox": bbox,
            "confidence": 0.85,
            "severity": "high",
            "metadata": {
                "red_signal_active": True,
                "motion_px": round(motion_px, 2),
                "detection_method": "zone_traffic_light_synergy",
            },
        }
