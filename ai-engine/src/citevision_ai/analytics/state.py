from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrackState:
    track_id: int
    camera_id: str
    class_name: str
    last_seen_frame: int = 0
    zone_ids: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)


class StateEngine:
    """Maintains per-track state across frames."""

    def __init__(self) -> None:
        self._tracks: dict[tuple[str, int], TrackState] = {}

    def update(self, camera_id: str, frame_id: int, tracks: list[dict]) -> list[TrackState]:
        seen: set[int] = set()
        active: list[TrackState] = []

        for t in tracks:
            tid = t["track_id"]
            seen.add(tid)
            key = (camera_id, tid)
            if key not in self._tracks:
                self._tracks[key] = TrackState(
                    track_id=tid,
                    camera_id=camera_id,
                    class_name=t.get("class_name", "unknown"),
                )
            state = self._tracks[key]
            state.last_seen_frame = frame_id
            state.class_name = t.get("class_name", state.class_name)
            active.append(state)

        stale = [k for k, s in self._tracks.items() if s.last_seen_frame < frame_id - 30]
        for k in stale:
            if self._tracks[k].track_id not in seen:
                del self._tracks[k]

        return active

    def get_track(self, camera_id: str, track_id: int) -> TrackState | None:
        return self._tracks.get((camera_id, track_id))
