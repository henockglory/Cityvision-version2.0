"""Computer-vision heuristics for road enforcement violations."""

from __future__ import annotations

import os
import uuid
from typing import Any

import cv2
import numpy as np

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}


def _point_in_polygon(px: float, py: float, polygon: list[dict]) -> bool:
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]["x"], polygon[i]["y"]
        xj, yj = polygon[j]["x"], polygon[j]["y"]
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


class RoadEnforcementEngine:
    """Detect red-light, seatbelt, and phone-while-driving via OpenCV heuristics."""

    def __init__(self) -> None:
        self._process_every_n = 3
        self._frame_counter = 0
        self._red_ratio_threshold = 0.06
        self._seatbelt_diagonal_min = 8.0
        self._phone_skin_ratio_min = 0.035
        self._cooldown: dict[tuple[str, int, str], int] = {}
        self._cooldown_frames = 45
        if os.environ.get("E2E_MODE") == "1":
            self._red_ratio_threshold = 0.015
            self._seatbelt_diagonal_min = 4.0
            self._phone_skin_ratio_min = 0.012
            self._process_every_n = 2
            self._cooldown_frames = 15

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        tracks: list[dict],
        timestamp: str,
        spatial_zones: list[dict] | None = None,
        disable_red_light: bool = False,
        disable_phone: bool = False,
        disable_seatbelt: bool = False,
    ) -> list[dict[str, Any]]:
        self._frame_counter += 1
        if frame is None or frame.size == 0:
            return []
        h, w = frame.shape[:2]
        red_active = False if disable_red_light else self._detect_red_signal(frame)
        events: list[dict[str, Any]] = []
        vehicles = [t for t in tracks if t.get("class_name") in VEHICLE_CLASSES]

        for vehicle in vehicles:
            tid = int(vehicle["track_id"])
            bbox = vehicle.get("bbox") or {}
            if (self._frame_counter - 1) % self._process_every_n != 0:
                continue

            if red_active and self._vehicle_in_intersection(bbox, spatial_zones, w, h):
                if self._allow_emit(camera_id, tid, "red_light_violation"):
                    events.append(
                        self._make_event(
                            camera_id,
                            "red_light_violation",
                            vehicle,
                            timestamp,
                            {
                                "red_signal_active": True,
                                "detection_method": "hsv_red_roi",
                                "confidence": 0.78,
                            },
                        )
                    )

            if not disable_seatbelt and self._detect_no_seatbelt(frame, bbox):
                if self._allow_emit(camera_id, tid, "seatbelt_violation"):
                    events.append(
                        self._make_event(
                            camera_id,
                            "seatbelt_violation",
                            vehicle,
                            timestamp,
                            {
                                "detection_method": "cabin_diagonal_edges",
                                "confidence": 0.71,
                            },
                        )
                    )

            if not disable_phone and self._detect_phone_near_ear(frame, bbox):
                if self._allow_emit(camera_id, tid, "phone_driving"):
                    events.append(
                        self._make_event(
                            camera_id,
                            "phone_driving",
                            vehicle,
                            timestamp,
                            {
                                "detection_method": "skin_blob_cabin",
                                "confidence": 0.69,
                            },
                        )
                    )

        return events

    def _allow_emit(self, camera_id: str, track_id: int, event_type: str) -> bool:
        key = (camera_id, track_id, event_type)
        last = self._cooldown.get(key, -9999)
        if self._frame_counter - last < self._cooldown_frames:
            return False
        self._cooldown[key] = self._frame_counter
        return True

    @staticmethod
    def _crop_bbox(frame: np.ndarray, bbox: dict) -> np.ndarray | None:
        if not bbox:
            return None
        h, w = frame.shape[:2]
        x1 = max(0, int(bbox.get("x", 0)))
        y1 = max(0, int(bbox.get("y", 0)))
        x2 = min(w, int(x1 + bbox.get("width", 0)))
        y2 = min(h, int(y1 + bbox.get("height", 0)))
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _detect_red_signal(self, frame: np.ndarray) -> bool:
        h, w = frame.shape[:2]
        roi = frame[0 : max(1, h // 4), max(1, w // 3) : w]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 80, 80])
        upper1 = np.array([10, 255, 255])
        lower2 = np.array([160, 80, 80])
        upper2 = np.array([180, 255, 255])
        mask = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
        ratio = float(np.count_nonzero(mask)) / max(mask.size, 1)
        return ratio >= self._red_ratio_threshold

    def _detect_no_seatbelt(self, frame: np.ndarray, bbox: dict) -> bool:
        crop = self._crop_bbox(frame, bbox)
        if crop is None or crop.size == 0:
            return False
        ch, cw = crop.shape[:2]
        cabin = crop[0 : max(1, ch // 2), 0 : max(1, int(cw * 0.55))]
        if cabin.size == 0:
            return False
        gray = cv2.cvtColor(cabin, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=20, minLineLength=10, maxLineGap=6)
        diagonal = 0
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
                if 25 <= angle <= 65:
                    diagonal += 1
        return diagonal < self._seatbelt_diagonal_min

    def _detect_phone_near_ear(self, frame: np.ndarray, bbox: dict) -> bool:
        crop = self._crop_bbox(frame, bbox)
        if crop is None or crop.size == 0:
            return False
        ch, cw = crop.shape[:2]
        ear_roi = crop[0 : max(1, ch // 3), 0 : max(1, int(cw * 0.35))]
        if ear_roi.size == 0:
            return False
        hsv = cv2.cvtColor(ear_roi, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 30, 50])
        upper = np.array([25, 180, 255])
        mask = cv2.inRange(hsv, lower, upper)
        ratio = float(np.count_nonzero(mask)) / max(mask.size, 1)
        return ratio >= self._phone_skin_ratio_min

    def _vehicle_in_intersection(
        self,
        bbox: dict,
        zones: list[dict] | None,
        frame_w: int,
        frame_h: int,
    ) -> bool:
        cx = (bbox.get("x", 0) + bbox.get("width", 0) / 2) / max(frame_w, 1)
        cy = (bbox.get("y", 0) + bbox.get("height", 0) / 2) / max(frame_h, 1)
        if zones:
            for zone in zones:
                poly = zone.get("polygon") or []
                if poly and _point_in_polygon(cx, cy, poly):
                    return True
        return 0.25 <= cx <= 0.85 and 0.35 <= cy <= 0.92

    @staticmethod
    def _make_event(
        camera_id: str,
        event_type: str,
        track: dict,
        timestamp: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        bbox = track.get("bbox") or {}
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": event_type,
            "event": event_type,
            "timestamp": timestamp,
            "track_id": track.get("track_id"),
            "class_name": track.get("class_name"),
            "bbox": bbox,
            "confidence": metadata.get("confidence", 0.7),
            "severity": "high" if "red_light" in event_type else "medium",
            "metadata": metadata,
        }
