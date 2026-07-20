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

import logging
import uuid
from collections import deque
from typing import Any

import cv2
import numpy as np

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

logger = logging.getLogger(__name__)

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
    # Minimum illuminated ratio for any colour to count.
    min_ratio = 0.008
    state = max(ratios, key=ratios.get)
    if ratios[state] < min_ratio:
        return "unknown", ratios
    # No "prefer red" bias: if green/amber truly dominate the ROI, trust them.
    # Only reject a max==red when another colour is strictly stronger.
    if state == "red":
        if ratios["green"] > ratios["red"]:
            return ("green" if ratios["green"] >= ratios["amber"] else "amber"), ratios
        if ratios["amber"] > ratios["red"]:
            return "amber", ratios
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
        # Consecutive frames a track spent inside an observation zone (motion gate).
        self._obs_streak: dict[tuple[str, int], int] = {}
        self._frame_counter = 0
        self._cooldown_frames = 45

    def reset_camera(self, camera_id: str) -> None:
        """Clear smoothed state when spatial config is hot-reloaded."""
        self._state_history.pop(camera_id, None)
        self._stable_state.pop(camera_id, None)
        drop = [k for k in self._prev_centroid if k[0] == camera_id]
        for k in drop:
            self._prev_centroid.pop(k, None)
            self._cooldown.pop(k, None)
            self._obs_streak.pop(k, None)

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
        cooldown = self._cooldown_frames
        new_state = self._stable_state.get(camera_id, "unknown")
        raw_state = "unknown"
        hsv_ratios: dict[str, float] = {}
        light_polygon: list[dict] = []
        for lz in light_zones:
            cfg = lz.get("behavior_config") or {}
            try:
                stable_window = max(1, int(cfg.get("stable_frames", 3)))
            except (TypeError, ValueError):
                stable_window = 3
            cooldown = 8 if stable_window <= 1 else self._cooldown_frames
            light_polygon = list(lz.get("polygon") or [])
            box = _polygon_pixel_bbox(light_polygon, w, h)
            if not box:
                continue
            x1, y1, x2, y2 = box
            raw_state, hsv_ratios = classify_light_color(frame[y1:y2, x1:x2])
            hist = self._state_history.setdefault(camera_id, deque(maxlen=max(stable_window, 1)))
            hist.append(raw_state)
            if len(hist) >= hist.maxlen:
                # Majority vote — more tolerant of brief HSV flicker in live video.
                counts: dict[str, int] = {}
                for s in hist:
                    counts[s] = counts.get(s, 0) + 1
                new_state = max(counts, key=counts.get)
            else:
                new_state = raw_state
            break  # one traffic-light zone per camera is the supported case

        prev_stable = self._stable_state.get(camera_id)
        if new_state != prev_stable:
            self._stable_state[camera_id] = new_state
            events.append(
                self._make_state_event(camera_id, new_state, timestamp)
            )

        # 2) Red-light synergy: moving vehicle in observation zone while red.
        # Require BOTH stable history and current-frame raw classification as red
        # so sticky "red" after the lamp turned green cannot keep firing.
        tracks_in_obs: set[tuple[str, int]] = set()
        light_is_red = (
            self._stable_state.get(camera_id) == "red"
            and raw_state == "red"
        )
        if light_is_red and obs_zones:
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
                    # Use a point near the bottom of the bbox (wheels / road contact).
                    cy = float(bbox.get("y", 0)) + float(bbox.get("height", 0)) * 0.85
                    ncx, ncy = cx / max(w, 1), cy / max(h, 1)
                    if poly and not _point_in_polygon(ncx, ncy, poly):
                        continue
                    tid = int(track.get("track_id", -1))
                    key = (camera_id, tid)
                    tracks_in_obs.add(key)
                    streak = self._obs_streak.get(key, 0) + 1
                    self._obs_streak[key] = streak
                    motion = self._motion_px(camera_id, tid, cx, cy)
                    # First frame in zone has motion=0; allow after 2 consecutive frames.
                    if motion < min_motion and streak < 2:
                        continue
                    if not self._allow_emit(camera_id, tid, cooldown):
                        continue
                    events.append(
                        self._make_violation_event(
                            camera_id, track, timestamp, motion,
                            hsv_ratios=hsv_ratios,
                            light_state=raw_state,
                            light_zone_polygon=light_polygon,
                            frame_w=w,
                            frame_h=h,
                        )
                    )
        for key in list(self._obs_streak):
            if key[0] == camera_id and key not in tracks_in_obs:
                self._obs_streak.pop(key, None)

        # Always refresh centroid cache for motion estimation.
        for track in tracks:
            bbox = track.get("bbox") or {}
            cx = float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2
            cy = float(bbox.get("y", 0)) + float(bbox.get("height", 0)) / 2
            self._prev_centroid[(camera_id, int(track.get("track_id", -1)))] = (cx, cy)

        if events:
            logger.info(
                "traffic_light camera=%s events=%s",
                camera_id[:8],
                [e.get("event_type") for e in events],
            )
        return events

    def _motion_px(self, camera_id: str, track_id: int, cx: float, cy: float) -> float:
        prev = self._prev_centroid.get((camera_id, track_id))
        if not prev:
            return 0.0
        return float(((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) ** 0.5)

    def _allow_emit(self, camera_id: str, track_id: int, cooldown_frames: int | None = None) -> bool:
        key = (camera_id, track_id)
        last = self._cooldown.get(key, -9999)
        frames = self._cooldown_frames if cooldown_frames is None else cooldown_frames
        if self._frame_counter - last < frames:
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
        camera_id: str,
        track: dict,
        timestamp: str,
        motion_px: float,
        *,
        hsv_ratios: dict[str, float] | None = None,
        light_state: str = "red",
        light_zone_polygon: list[dict] | None = None,
        frame_w: int = 0,
        frame_h: int = 0,
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
            "frame_width": frame_w or None,
            "frame_height": frame_h or None,
            "metadata": {
                "red_signal_active": True,
                "light_state": light_state,
                "hsv_ratios": hsv_ratios or {},
                "light_zone_polygon": light_zone_polygon or [],
                "motion_px": round(motion_px, 2),
                "detection_method": "zone_traffic_light_synergy",
            },
        }
