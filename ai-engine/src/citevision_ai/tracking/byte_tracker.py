from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    track_id: int | None = None


@dataclass
class TrackState:
    track_id: int
    class_id: int
    class_name: str
    bbox: tuple[float, float, float, float]
    hits: int = 1
    age: int = 0
    time_since_update: int = 0
    history: list[tuple[float, float]] = field(default_factory=list)


class ByteTracker:
    """Lightweight ByteTrack-style multi-object tracker."""

    def __init__(self, max_age: int = 30, min_hits: int = 3, iou_threshold: float = 0.3) -> None:
        self._max_age = max_age
        self._min_hits = min_hits
        self._iou_threshold = iou_threshold
        self._tracks: dict[int, TrackState] = {}
        self._next_id = 1

    @staticmethod
    def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if inter <= 0:
            return 0.0
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def update(self, detections: list[Detection]) -> list[Detection]:
        for track in self._tracks.values():
            track.age += 1
            track.time_since_update += 1

        matched: set[int] = set()
        results: list[Detection] = []

        for det in detections:
            best_id: int | None = None
            best_iou = self._iou_threshold
            for tid, track in self._tracks.items():
                if tid in matched:
                    continue
                if track.class_id != det.class_id:
                    continue
                score = self._iou(det.bbox, track.bbox)
                if score >= best_iou:
                    best_iou = score
                    best_id = tid

            if best_id is not None:
                track = self._tracks[best_id]
                track.bbox = det.bbox
                track.hits += 1
                track.time_since_update = 0
                cx = (det.bbox[0] + det.bbox[2]) / 2
                cy = (det.bbox[1] + det.bbox[3]) / 2
                track.history.append((cx, cy))
                matched.add(best_id)
                det.track_id = best_id
            else:
                tid = self._next_id
                self._next_id += 1
                cx = (det.bbox[0] + det.bbox[2]) / 2
                cy = (det.bbox[1] + det.bbox[3]) / 2
                self._tracks[tid] = TrackState(
                    track_id=tid,
                    class_id=det.class_id,
                    class_name=det.class_name,
                    bbox=det.bbox,
                    history=[(cx, cy)],
                )
                det.track_id = tid
                matched.add(tid)

            if det.track_id is not None and self._tracks[det.track_id].hits >= self._min_hits:
                results.append(det)

        stale = [tid for tid, t in self._tracks.items() if t.time_since_update > self._max_age]
        for tid in stale:
            del self._tracks[tid]

        return results

    def get_active_tracks(self) -> list[TrackState]:
        return list(self._tracks.values())
