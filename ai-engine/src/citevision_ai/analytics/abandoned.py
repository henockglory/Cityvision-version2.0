from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


ABANDONED_CLASSES = {"backpack", "handbag", "suitcase"}


class AbandonedObjectDetector:
    """Detects static unattended objects."""

    def __init__(self, static_threshold_sec: float = 45.0, owner_radius: float = 120.0) -> None:
        self.static_threshold_sec = static_threshold_sec
        self.owner_radius = owner_radius
        self._object_state: dict[tuple[str, int], dict[str, Any]] = {}
        self._alerted: set[tuple[str, int]] = set()

    def process(
        self,
        camera_id: str,
        tracks: list[dict],
        persons: list[dict],
        timestamp: str,
    ) -> list[dict[str, Any]]:
        now = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        events: list[dict[str, Any]] = []
        seen: set[int] = set()

        for track in tracks:
            if track.get("class_name") not in ABANDONED_CLASSES:
                continue
            tid = track["track_id"]
            seen.add(tid)
            bbox = track["bbox"]
            cx = bbox["x"] + bbox["width"] / 2
            cy = bbox["y"] + bbox["height"] / 2
            key = (camera_id, tid)

            state = self._object_state.setdefault(
                key,
                {"first_seen": now, "last_pos": (cx, cy), "static_since": now},
            )
            last_x, last_y = state["last_pos"]
            moved = ((cx - last_x) ** 2 + (cy - last_y) ** 2) ** 0.5
            if moved < 10:
                if "static_since" not in state:
                    state["static_since"] = now
            else:
                state["static_since"] = now
                state["last_pos"] = (cx, cy)
                self._alerted.discard(key)

            static_duration = (now - state["static_since"]).total_seconds()
            owner_nearby = self._has_owner_nearby(cx, cy, persons)

            if static_duration >= self.static_threshold_sec and not owner_nearby:
                if key not in self._alerted:
                    self._alerted.add(key)
                    events.append(self._make_event(
                        camera_id, "object_abandoned", tid, timestamp,
                        {"class_name": track["class_name"], "duration_seconds": static_duration},
                        "critical",
                    ))
            elif key in self._alerted and (owner_nearby or tid not in seen):
                self._alerted.discard(key)
                events.append(self._make_event(
                    camera_id, "object_removed", tid, timestamp,
                    {"class_name": track["class_name"]},
                    "info",
                ))

        stale = [k for k in self._object_state if k[0] == camera_id and k[1] not in seen]
        for k in stale:
            if k in self._alerted:
                events.append(self._make_event(
                    camera_id, "object_removed", k[1], timestamp, {}, "info"
                ))
                self._alerted.discard(k)
            del self._object_state[k]

        return events

    def _has_owner_nearby(self, cx: float, cy: float, persons: list[dict]) -> bool:
        for p in persons:
            pb = p["bbox"]
            px = pb["x"] + pb["width"] / 2
            py = pb["y"] + pb["height"] / 2
            if ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 <= self.owner_radius:
                return True
        return False

    @staticmethod
    def _make_event(
        camera_id: str,
        event_type: str,
        track_id: int,
        timestamp: str,
        metadata: dict[str, Any],
        severity: str,
    ) -> dict[str, Any]:
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "severity": severity,
            "track_id": track_id,
            "metadata": metadata,
        }
