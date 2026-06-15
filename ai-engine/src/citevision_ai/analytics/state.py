from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TrackState:
    track_id: int
    camera_id: str
    class_name: str
    last_seen_frame: int = 0
    zone_ids: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    stationary_since_frame: int = 0
    last_cx: float = 0.0
    last_cy: float = 0.0


class StateEngine:
    """Maintains per-track state and emits dwell/stop events."""

    def __init__(self, dwell_threshold_sec: float = 30.0, stop_threshold_px: float = 8.0) -> None:
        self.dwell_threshold_sec = dwell_threshold_sec
        self.stop_threshold_px = stop_threshold_px
        self._tracks: dict[tuple[str, int], TrackState] = {}
        self._enter_times: dict[tuple[str, int, str], datetime] = {}
        self._stop_frames: dict[tuple[str, int], int] = {}
        self._fps = 25.0

    def set_fps(self, fps: float) -> None:
        if fps > 1:
            self._fps = fps

    def update(
        self,
        camera_id: str,
        frame_id: int,
        tracks: list[dict],
        timestamp: str,
    ) -> tuple[list[TrackState], list[dict[str, Any]], dict[tuple[str, int], float]]:
        seen: set[int] = set()
        active: list[TrackState] = []
        events: list[dict[str, Any]] = []
        zone_dwell: dict[tuple[str, int], float] = {}
        now = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        for t in tracks:
            tid = t["track_id"]
            seen.add(tid)
            key = (camera_id, tid)
            bbox = t["bbox"]
            cx = bbox["x"] + bbox["width"] / 2
            cy = bbox["y"] + bbox["height"] / 2

            if key not in self._tracks:
                self._tracks[key] = TrackState(
                    track_id=tid,
                    camera_id=camera_id,
                    class_name=t.get("class_name", "unknown"),
                    stationary_since_frame=frame_id,
                )
            state = self._tracks[key]
            state.last_seen_frame = frame_id
            state.class_name = t.get("class_name", state.class_name)

            moved = ((cx - state.last_cx) ** 2 + (cy - state.last_cy) ** 2) ** 0.5
            if moved < self.stop_threshold_px:
                if key not in self._stop_frames:
                    self._stop_frames[key] = frame_id
                stop_frames = frame_id - self._stop_frames[key]
                stop_sec = stop_frames / self._fps
                if stop_sec >= self.dwell_threshold_sec:
                    evt_type = "person_stopped" if state.class_name == "person" else "vehicle_stopped"
                    if state.class_name in ("car", "truck", "bus", "motorcycle", "person"):
                        events.append(self._make_event(
                            camera_id, evt_type, tid, timestamp,
                            {"dwell_seconds": stop_sec, "class_name": state.class_name},
                        ))
            else:
                self._stop_frames.pop(key, None)

            for zone_id in state.zone_ids:
                enter_key = (camera_id, tid, zone_id)
                if enter_key in self._enter_times:
                    dwell = (now - self._enter_times[enter_key]).total_seconds()
                    zone_dwell[(camera_id, tid)] = dwell
                    if dwell >= self.dwell_threshold_sec:
                        events.append(self._make_event(
                            camera_id, "dwell_time_exceeded", tid, timestamp,
                            {"zone_id": zone_id, "dwell_seconds": dwell},
                            "warning",
                        ))

            state.last_cx = cx
            state.last_cy = cy
            active.append(state)

        stale = [k for k, s in self._tracks.items() if s.last_seen_frame < frame_id - 60]
        for k in stale:
            if self._tracks[k].track_id not in seen:
                del self._tracks[k]
                self._stop_frames.pop(k, None)

        return active, events, zone_dwell

    def set_zone(self, camera_id: str, track_id: int, zone_id: str, inside: bool) -> None:
        state = self._tracks.get((camera_id, track_id))
        if not state:
            return
        now = datetime.now(timezone.utc)
        key = (camera_id, track_id, zone_id)
        if inside:
            state.zone_ids.add(zone_id)
            if key not in self._enter_times:
                self._enter_times[key] = now
        else:
            state.zone_ids.discard(zone_id)
            self._enter_times.pop(key, None)

    def get_track(self, camera_id: str, track_id: int) -> TrackState | None:
        return self._tracks.get((camera_id, track_id))

    @staticmethod
    def _make_event(
        camera_id: str,
        event_type: str,
        track_id: int,
        timestamp: str,
        metadata: dict[str, Any],
        severity: str = "info",
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
