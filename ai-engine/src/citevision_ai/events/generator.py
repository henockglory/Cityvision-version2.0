from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from citevision_ai.behavior.heuristics import BEHAVIOR_EVENT_TYPES, BehaviorLabel, BehaviorSignal
from citevision_ai.detection.class_groups import matches_class_filter

PERSON_CLASSES = {"person"}
OBJECT_LIFECYCLE_CLASSES = {"backpack", "handbag", "suitcase", "sports ball", "bottle", "chair"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _point_in_polygon(px: float, py: float, polygon: list[dict]) -> bool:
    """Ray-casting point-in-polygon test."""
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
    """Check if segment prev→curr crosses line start→end."""
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
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    return False


class EventGenerator:
    """Generates zone, line, loitering, presence, and behavior events from tracked detections."""

    def __init__(
        self,
        presence_threshold_seconds: float = 5.0,
        absence_threshold_seconds: float = 30.0,
    ) -> None:
        self.presence_threshold_seconds = presence_threshold_seconds
        self.absence_threshold_seconds = absence_threshold_seconds
        self._zone_state: dict[tuple[str, int], set[str]] = {}
        self._positions: dict[tuple[str, int], tuple[float, float]] = {}
        self._enter_times: dict[tuple[str, int, str], datetime] = {}
        self._zone_presence_since: dict[tuple[str, str], datetime] = {}
        self._zone_presence_alerted: set[tuple[str, str]] = set()
        self._zone_last_occupied: dict[tuple[str, str], datetime] = {}
        self._zone_absence_alerted: set[tuple[str, str]] = set()
        self._known_tracks: dict[str, set[int]] = {}
        self._track_classes: dict[tuple[str, int], str] = {}

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
            class_name = str(track.get("class_name", "unknown"))
            self._track_classes[(camera_id, track_id)] = class_name
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
                    events.extend(
                        self._check_zone(camera_id, track_id, cx, cy, rule, ts, class_name)
                    )
                elif rule_type == "line" and "line" in rule and prev:
                    events.extend(
                        self._check_line(
                            camera_id, track_id, prev, (cx, cy), rule, ts, class_name
                        )
                    )
                elif rule_type == "loitering" and "loitering" in rule:
                    events.extend(
                        self._check_loitering(
                            camera_id, track_id, cx, cy, rule, ts, class_name
                        )
                    )
                elif rule_type == "zone_presence" and "zone" in rule:
                    events.extend(
                        self._check_zone_presence(
                            camera_id, track_id, cx, cy, rule, ts, class_name
                        )
                    )
                elif rule_type == "zone_absence" and "zone" in rule:
                    pass  # handled after track loop

            self._positions[key] = (cx, cy)

        events.extend(self._check_zone_absence(camera_id, tracks, rules, ts))
        events.extend(self._check_object_lifecycle(camera_id, tracks, ts))
        return events

    def emit_behavior_signals(
        self,
        camera_id: str,
        signals: list[BehaviorSignal],
        timestamp: str,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for signal in signals:
            if signal.label == BehaviorLabel.NORMAL:
                continue
            event_type = BEHAVIOR_EVENT_TYPES.get(signal.label, "behavior_anomaly")
            severity = "warning"
            if signal.label in {BehaviorLabel.FALLING, BehaviorLabel.FIGHTING}:
                severity = "critical"
            events.append(
                self.emit_behavior_event(
                    camera_id,
                    signal.track_id,
                    event_type,
                    signal.confidence,
                    {"behavior": signal.label.value, **signal.details},
                    timestamp,
                    severity=severity,
                )
            )
        return events

    def _track_class_name(self, camera_id: str, track_id: int, fallback: str = "unknown") -> str:
        return self._track_classes.get((camera_id, track_id), fallback)

    def _check_zone(
        self,
        camera_id: str,
        track_id: int,
        cx: float,
        cy: float,
        rule: dict,
        ts: str,
        class_name: str,
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
            events.append(
                self._make_event(
                    camera_id, "zone_enter", ts, track_id, zone_id=zone_id, class_name=class_name
                )
            )
        elif not inside and zone_id in prev_zones:
            prev_zones.discard(zone_id)
            events.append(
                self._make_event(
                    camera_id, "zone_exit", ts, track_id, zone_id=zone_id, class_name=class_name
                )
            )
        return events

    def _check_zone_presence(
        self,
        camera_id: str,
        track_id: int,
        cx: float,
        cy: float,
        rule: dict,
        ts: str,
        class_name: str,
    ) -> list[dict]:
        class_filter = rule.get("class_filter", "any")
        if not matches_class_filter(class_name, str(class_filter)):
            return []
        zone = rule["zone"]
        zone_id = zone["zone_id"]
        polygon = zone["polygon"]
        if not _point_in_polygon(cx, cy, polygon):
            return []

        now = _parse_ts(ts)
        zone_key = (camera_id, zone_id)
        self._zone_last_occupied[zone_key] = now
        self._zone_absence_alerted.discard(zone_key)

        presence_key = (camera_id, zone_id, track_id)
        if presence_key not in self._zone_presence_since:
            self._zone_presence_since[presence_key] = now
            return []

        duration = (now - self._zone_presence_since[presence_key]).total_seconds()
        threshold = rule.get("presence_seconds", self.presence_threshold_seconds)
        alert_key = (camera_id, f"{zone_id}:{track_id}")
        if duration >= threshold and alert_key not in self._zone_presence_alerted:
            self._zone_presence_alerted.add(alert_key)
            return [
                self._make_event(
                    camera_id,
                    "zone_presence",
                    ts,
                    track_id,
                    zone_id=zone_id,
                    class_name=class_name,
                    duration_seconds=duration,
                    metadata={"duration_seconds": duration, "class_name": class_name},
                )
            ]
        return []

    def _check_zone_absence(
        self,
        camera_id: str,
        tracks: list[dict],
        rules: list[dict],
        ts: str,
    ) -> list[dict]:
        now = _parse_ts(ts)
        events: list[dict] = []

        for rule in rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("camera_id") and rule["camera_id"] != camera_id:
                continue
            if rule.get("rule_type") != "zone_absence" or "zone" not in rule:
                continue

            zone = rule["zone"]
            zone_id = zone["zone_id"]
            polygon = zone["polygon"]
            occupied = False
            for track in tracks:
                bbox = track["bbox"]
                cx = bbox["x"] + bbox["width"] / 2
                cy = bbox["y"] + bbox["height"] / 2
                if _point_in_polygon(cx, cy, polygon):
                    occupied = True
                    break

            zone_key = (camera_id, zone_id)
            if occupied:
                self._zone_last_occupied[zone_key] = now
                self._zone_absence_alerted.discard(zone_key)
                continue

            if zone_key not in self._zone_last_occupied:
                self._zone_last_occupied[zone_key] = now
                continue

            absence = (now - self._zone_last_occupied[zone_key]).total_seconds()
            threshold = rule.get("absence_seconds", self.absence_threshold_seconds)
            if absence >= threshold and zone_key not in self._zone_absence_alerted:
                self._zone_absence_alerted.add(zone_key)
                events.append(
                    self._make_event(
                        camera_id,
                        "zone_absence",
                        ts,
                        -1,
                        zone_id=zone_id,
                        duration_seconds=absence,
                        severity="warning",
                        metadata={"duration_seconds": absence},
                    )
                )
        return events

    def _check_object_lifecycle(
        self,
        camera_id: str,
        tracks: list[dict],
        ts: str,
    ) -> list[dict]:
        events: list[dict] = []
        current: set[int] = set()
        known = self._known_tracks.setdefault(camera_id, set())

        for track in tracks:
            tid = track["track_id"]
            class_name = track.get("class_name", "")
            current.add(tid)
            self._track_classes[(camera_id, tid)] = class_name

            if tid not in known and class_name in OBJECT_LIFECYCLE_CLASSES:
                events.append(
                    self._make_event(
                        camera_id,
                        "object_appeared",
                        ts,
                        tid,
                        class_name=class_name,
                        metadata={"class_name": class_name},
                    )
                )

        for tid in known - current:
            class_name = self._track_classes.get((camera_id, tid), "")
            if class_name in OBJECT_LIFECYCLE_CLASSES:
                events.append(
                    self._make_event(
                        camera_id,
                        "object_disappeared",
                        ts,
                        tid,
                        class_name=class_name,
                        severity="warning",
                        metadata={"class_name": class_name},
                    )
                )
            self._track_classes.pop((camera_id, tid), None)

        self._known_tracks[camera_id] = current
        return events

    def _check_line(
        self,
        camera_id: str,
        track_id: int,
        prev: tuple[float, float],
        curr: tuple[float, float],
        rule: dict,
        ts: str,
        class_name: str,
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
                class_name=class_name,
            )
        ]

    def _check_loitering(
        self,
        camera_id: str,
        track_id: int,
        cx: float,
        cy: float,
        rule: dict,
        ts: str,
        class_name: str,
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
        now = _parse_ts(ts)
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
                    class_name=class_name,
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

    def emit_behavior_event(
        self,
        camera_id: str,
        track_id: int,
        event_type: str,
        confidence: float,
        metadata: dict[str, Any],
        timestamp: str,
        severity: str = "info",
    ) -> dict[str, Any]:
        return self._make_event(
            camera_id,
            event_type,
            timestamp,
            track_id,
            severity=severity,
            metadata={"confidence": confidence, **metadata},
        )
