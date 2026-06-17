from __future__ import annotations

import math
from typing import Any


class CalibrationEngine:
    """Pixel-to-world homography for speed estimation in km/h."""

    def __init__(self, calibration: dict[str, Any] | None = None) -> None:
        self._matrix = None
        self._world_scale = 1.0
        self._speed_limit_kmh = 50.0
        self._min_speed_kmh = 5.0
        self._sudden_stop_drop_kmh = 25.0
        self._sudden_stop_window_s = 2.0
        self._positions: dict[tuple[str, int], list[tuple[float, float, float]]] = {}
        self._last_speed: dict[tuple[str, int], float] = {}
        self._sudden_stop_fired: set[tuple[str, int]] = set()
        if calibration:
            self.set_calibration(calibration)

    def set_calibration(self, calibration: dict[str, Any]) -> None:
        points = calibration.get("calibration_points", [])
        self._world_scale = float(calibration.get("world_scale", 1.0))
        self._speed_limit_kmh = float(calibration.get("speed_limit_kmh", 50.0))
        self._min_speed_kmh = float(calibration.get("min_speed_kmh", 5.0))
        if len(points) >= 4:
            try:
                import cv2
                import numpy as np

                src = np.float32([[p["x"], p["y"]] for p in points[:4]])
                dst = np.float32([[p["wx"], p["wy"]] for p in points[:4]])
                self._matrix = cv2.getPerspectiveTransform(src, dst)
            except Exception:
                self._matrix = None

    def pixel_to_world(self, x: float, y: float) -> tuple[float, float]:
        if self._matrix is None:
            return (x * self._world_scale, y * self._world_scale)
        try:
            import cv2
            import numpy as np

            pt = np.float32([[[x, y]]])
            out = cv2.perspectiveTransform(pt, self._matrix)
            return float(out[0][0][0]), float(out[0][0][1])
        except Exception:
            return (x * self._world_scale, y * self._world_scale)

    def update_track(
        self,
        camera_id: str,
        track_id: int,
        cx: float,
        cy: float,
        timestamp: float,
        class_name: str,
    ) -> dict[str, Any]:
        wx, wy = self.pixel_to_world(cx, cy)
        key = (camera_id, track_id)
        hist = self._positions.setdefault(key, [])
        hist.append((wx, wy, timestamp))
        if len(hist) > 15:
            hist.pop(0)

        speed_kmh = 0.0
        if len(hist) >= 2:
            x1, y1, t1 = hist[-2]
            x2, y2, t2 = hist[-1]
            dt = max(t2 - t1, 1e-6)
            dist_m = math.hypot(x2 - x1, y2 - y1)
            speed_kmh = (dist_m / dt) * 3.6

        result: dict[str, Any] = {"speed_kmh": round(speed_kmh, 2)}
        track_key = (camera_id, track_id)
        prev_speed = self._last_speed.get(track_key, 0.0)
        is_vehicle = class_name in ("car", "truck", "bus", "motorcycle")
        if is_vehicle and (
            prev_speed >= self._sudden_stop_drop_kmh
            and speed_kmh < self._min_speed_kmh
            and track_key not in self._sudden_stop_fired
            and len(hist) >= 2
            and (timestamp - hist[-2][2]) <= self._sudden_stop_window_s
        ):
            result["speed_event"] = "sudden_stop"
            result["prior_speed_kmh"] = round(prev_speed, 2)
            self._sudden_stop_fired.add(track_key)
        elif is_vehicle and speed_kmh > 1:
            if speed_kmh > self._speed_limit_kmh:
                result["speed_event"] = "speeding"
            elif speed_kmh < self._min_speed_kmh:
                result["speed_event"] = "speed_below_minimum"
        if is_vehicle and speed_kmh >= self._min_speed_kmh:
            self._sudden_stop_fired.discard(track_key)
        self._last_speed[track_key] = speed_kmh
        return result
