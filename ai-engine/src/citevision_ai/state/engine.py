from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TrackPhase(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    LOST = "lost"
    EXITED = "exited"


@dataclass
class EntityState:
    track_id: int
    camera_id: str
    class_name: str
    phase: TrackPhase = TrackPhase.NEW
    last_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    attributes: dict[str, Any] = field(default_factory=dict)


class StateEngine:
    """Maintains per-track lifecycle state across frames."""

    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self._entities: dict[int, EntityState] = {}

    def update(
        self,
        active_track_ids: set[int],
        track_meta: dict[int, dict[str, Any]],
    ) -> list[EntityState]:
        now = datetime.now(timezone.utc).isoformat()
        transitions: list[EntityState] = []

        for tid in active_track_ids:
            meta = track_meta.get(tid, {})
            if tid not in self._entities:
                state = EntityState(
                    track_id=tid,
                    camera_id=self.camera_id,
                    class_name=meta.get("class_name", "unknown"),
                    phase=TrackPhase.NEW,
                    last_seen=now,
                    attributes=meta,
                )
                self._entities[tid] = state
                transitions.append(state)
            else:
                state = self._entities[tid]
                state.phase = TrackPhase.ACTIVE
                state.last_seen = now
                state.attributes.update(meta)

        for tid, state in list(self._entities.items()):
            if tid not in active_track_ids:
                if state.phase != TrackPhase.EXITED:
                    state.phase = TrackPhase.LOST
                    state.last_seen = now
                    transitions.append(state)

        return transitions

    def get_entity(self, track_id: int) -> EntityState | None:
        return self._entities.get(track_id)

    def snapshot(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "entity_count": len(self._entities),
            "entities": [
                {
                    "track_id": e.track_id,
                    "class_name": e.class_name,
                    "phase": e.phase.value,
                    "last_seen": e.last_seen,
                }
                for e in self._entities.values()
            ],
        }
