from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SceneAnalyzer:
    """Aggregates per-frame scene metrics and emits periodic events."""

    def __init__(
        self,
        density_threshold: float = 0.003,
        crowd_threshold: int = 8,
        vehicle_threshold: int = 5,
        emit_interval: float = 1.0,
    ) -> None:
        self.density_threshold = density_threshold
        self.crowd_threshold = crowd_threshold
        self.vehicle_threshold = vehicle_threshold
        self.emit_interval = emit_interval
        self._last_emit: dict[str, float] = {}
        self._crowd_history: dict[str, list[tuple[float, int, float]]] = {}
        self._panic_cooldown: dict[str, float] = {}

    def analyze(
        self,
        camera_id: str,
        tracks: list[dict],
        frame_area: float,
        avg_speed_kmh: float = 0.0,
        *,
        density_threshold: float | None = None,
        crowd_threshold: int | None = None,
        vehicle_threshold: int | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        density_limit = density_threshold if density_threshold is not None else self.density_threshold
        crowd_limit = crowd_threshold if crowd_threshold is not None else self.crowd_threshold
        vehicle_limit = vehicle_threshold if vehicle_threshold is not None else self.vehicle_threshold
        persons = [t for t in tracks if t.get("class_name") == "person"]
        vehicles = [
            t for t in tracks
            if t.get("class_name") in ("car", "truck", "bus", "motorcycle", "bicycle")
        ]
        density = len(persons) / max(frame_area, 1.0)

        metrics = {
            "person_count": len(persons),
            "vehicle_count": len(vehicles),
            "density_per_m2": round(density * 1_000_000, 4),
            "avg_speed_kmh": round(avg_speed_kmh, 2),
            "timestamp": _utc_now(),
        }

        now = time.monotonic()
        last = self._last_emit.get(camera_id, 0.0)
        events: list[dict[str, Any]] = []
        if now - last >= self.emit_interval:
            self._last_emit[camera_id] = now
            if density >= density_limit:
                events.append(self._scene_event(camera_id, "scene_density_high", metrics, "warning"))
            if len(persons) >= crowd_limit:
                events.append(self._scene_event(camera_id, "crowd_count_threshold", metrics, "warning"))
            if len(vehicles) >= vehicle_limit:
                events.append(self._scene_event(camera_id, "vehicle_count_threshold", metrics, "info"))
            events.extend(self._detect_crowd_panic(camera_id, persons, now))

        return metrics, events

    def _detect_crowd_panic(
        self,
        camera_id: str,
        persons: list[dict],
        now: float,
    ) -> list[dict[str, Any]]:
        if now - self._panic_cooldown.get(camera_id, 0.0) < 5.0:
            return []
        spread = self._centroid_spread(persons)
        hist = self._crowd_history.setdefault(camera_id, [])
        hist.append((now, len(persons), spread))
        if len(hist) > 12:
            hist.pop(0)
        if len(hist) < 3:
            return []
        _, prev_count, prev_spread = hist[-3]
        _, mid_count, mid_spread = hist[-2]
        cur_count, cur_spread = len(persons), spread
        dispersed = (
            mid_count >= 3
            and cur_count >= 2
            and cur_spread >= max(prev_spread, mid_spread) * 1.6
            and cur_spread > 0.08
        )
        sudden_drop = mid_count >= 4 and cur_count <= max(1, mid_count // 2)
        if not (dispersed or sudden_drop):
            return []
        self._panic_cooldown[camera_id] = now
        metrics = {
            "person_count": cur_count,
            "prior_person_count": mid_count,
            "centroid_spread": round(cur_spread, 4),
            "timestamp": _utc_now(),
        }
        return [self._scene_event(camera_id, "crowd_panic", metrics, "critical")]

    @staticmethod
    def _centroid_spread(persons: list[dict]) -> float:
        if len(persons) < 2:
            return 0.0
        xs = [p["bbox"]["x"] + p["bbox"]["width"] / 2 for p in persons]
        ys = [p["bbox"]["y"] + p["bbox"]["height"] / 2 for p in persons]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        dists = [((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in zip(xs, ys)]
        return sum(dists) / len(dists)

    @staticmethod
    def _scene_event(
        camera_id: str,
        event_type: str,
        metrics: dict[str, Any],
        severity: str,
    ) -> dict[str, Any]:
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": event_type,
            "timestamp": metrics["timestamp"],
            "severity": severity,
            "track_id": -1,
            "metadata": metrics,
        }
