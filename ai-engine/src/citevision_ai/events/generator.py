from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _crosses_line(
    prev: tuple[float, float],
    curr: tuple[float, float],
    start: dict,
    end: dict,
) -> bool:
    x1, y1 = prev
    x2, y2 = curr
    x3, y3 = start["x"], start["y"]
    x4, y4 = end["x"], end["y"]

    def orient(ax, ay, bx, by, cx, cy):
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    o1 = orient(x1, y1, x2, y2, x3, y3)
    o2 = orient(x1, y1, x2, y2, x4, y4)
    o3 = orient(x3, y3, x4, y4, x1, y1)
    o4 = orient(x3, y3, x4, y4, x2, y2)
    return o1 * o2 < 0 and o3 * o4 < 0


class EventGenerator:
    """Generates zone, line, and loitering events from tracked detections."""

    def __init__(self) -> None:
        self._zone_state: dict[tuple[str, int], set[str]] = {}
        self._positions: dict[tuple[str, int], tuple[float, float]] = {}
        self._enter_times: dict[tuple[str, int, str], datetime] = {}

    def process_frame(
        self,
        camera_id: str,
        tracks: list[dict],
        rules: list[dict],
        timestamp: str | None = None,
    ) -> list[dict[str, Any]]:
        ts = timestamp or _utc_now()
        events: list[dict[str, Any]] = []

        for track in tracks:
            track_id = track["track_id"]
            bbox = track["bbox"]
            cx = bbox["x"] + bbox["width"] / 2
            cy = bbox["y"] + bbox["height"] / 2
            key = (camera_id, track_id)
            prev = self._positions.get(key)

            for rule in rules:
                if not rule.get("enabled", True):
                    continue
                if rule.get("camera_id") and rule["camera_id"] != camera_id:
                    continue

                rule_type = rule.get("rule_type")
                if rule_type == "zone" and "zone" in rule:
                    events.extend(self._check_zone(camera_id, track_id, cx, cy, rule, ts))
                elif rule_type == "line" and "line" in rule and prev:
                    events.extend(self._check_line(camera_id, track_id, prev, (cx, cy), rule, ts))
                elif rule_type == "loitering" and "loitering" in rule:
                    events.extend(self._check_loitering(camera_id, track_id, cx, cy, rule, ts))

            self._positions[key] = (cx, cy)

        return events

    def _check_zone(
        self, camera_id: str, track_id: int, cx: float, cy: float, rule: dict, ts: str
    ) -> list[dict]:
        zone = rule["zone"]
        zone_id = zone["zone_id"]
        polygon = zone["polygon"]
        inside = _point_in_polygon(cx, cy, polygon)
        key = (camera_id, track_id)
        prev_zones = self._zone_state.setdefault(key, set())
        events: list[dict] = []

        if inside and zone_id not in prev_zones:
            prev_zones.add(zone_id)
            events.append(self._make_event(camera_id, "zone_enter", ts, track_id, zone_id=zone_id))
        elif not inside and zone_id in prev_zones:
            prev_zones.discard(zone_id)
            events.append(self._make_event(camera_id, "zone_exit", ts, track_id, zone_id=zone_id))
        return events

    def _check_line(
        self,
        camera_id: str,
        track_id: int,
        prev: tuple[float, float],
        curr: tuple[float, float],
        rule: dict,
        ts: str,
    ) -> list[dict]:
        line = rule["line"]
        if not _crosses_line(prev, curr, line["start"], line["end"]):
            return []
        return [
            self._make_event(
                camera_id,
                "line_cross",
                ts,
                track_id,
                line_id=line["line_id"],
                direction=line.get("direction_filter", "unknown"),
            )
        ]

    def _check_loitering(
        self, camera_id: str, track_id: int, cx: float, cy: float, rule: dict, ts: str
    ) -> list[dict]:
        loiter = rule["loitering"]
        threshold = loiter.get("threshold_seconds", 30)
        zone_id = loiter.get("zone_id")
        if not zone_id:
            return []

        zone_rule = rule.get("zone") or {}
        polygon = zone_rule.get("polygon", [])
        if polygon and not _point_in_polygon(cx, cy, polygon):
            self._enter_times.pop((camera_id, track_id, zone_id), None)
            return []

        enter_key = (camera_id, track_id, zone_id)
        now = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if enter_key not in self._enter_times:
            self._enter_times[enter_key] = now
            return []

        duration = (now - self._enter_times[enter_key]).total_seconds()
        if duration >= threshold:
            self._enter_times.pop(enter_key, None)
            return [
                self._make_event(
                    camera_id,
                    "loitering",
                    ts,
                    track_id,
                    zone_id=zone_id,
                    duration_seconds=duration,
                    severity="warning",
                )
            ]
        return []

    @staticmethod
    def _make_event(
        camera_id: str,
        event_type: str,
        timestamp: str,
        track_id: int,
        severity: str = "info",
        **extra: Any,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "severity": severity,
            "track_id": track_id,
        }
        event.update(extra)
        return event
