"""Lightweight ByteTrack-style multi-object tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .yolo_onnx import Detection


@dataclass
class Track:
    track_id: int
    class_id: int
    class_name: str
    bbox: tuple[float, float, float, float]
    confidence: float
    age: int = 0
    hits: int = 1
    time_since_update: int = 0

    def to_dict(self) -> dict[str, Any]:
        x1, y1, x2, y2 = self.bbox
        return {
            "track_id": self.track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "age": self.age,
            "hits": self.hits,
        }


def _iou(box_a: tuple[float, ...], box_b: tuple[float, ...]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class ByteTracker:
    """Greedy IoU association tracker (ByteTrack-inspired)."""

    def __init__(self, iou_threshold: float = 0.3, max_age: int = 30) -> None:
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self._tracks: list[Track] = []
        self._next_id = 1

    def update(self, detections: list[Detection]) -> list[Track]:
        for track in self._tracks:
            track.age += 1
            track.time_since_update += 1

        if not detections:
            self._tracks = [t for t in self._tracks if t.time_since_update <= self.max_age]
            return list(self._tracks)

        det_boxes = [d.bbox for d in detections]
        track_indices = list(range(len(self._tracks)))
        det_indices = list(range(len(detections)))
        matched: list[tuple[int, int]] = []

        while track_indices and det_indices:
            best_iou, best_t, best_d = 0.0, -1, -1
            for ti in track_indices:
                for di in det_indices:
                    iou = _iou(self._tracks[ti].bbox, det_boxes[di])
                    if iou > best_iou:
                        best_iou, best_t, best_d = iou, ti, di
            if best_iou < self.iou_threshold:
                break
            matched.append((best_t, best_d))
            track_indices.remove(best_t)
            det_indices.remove(best_d)

        matched_tracks = {t for t, _ in matched}
        for ti, di in matched:
            det = detections[di]
            track = self._tracks[ti]
            track.bbox = det.bbox
            track.confidence = det.confidence
            track.hits += 1
            track.time_since_update = 0

        for di in det_indices:
            det = detections[di]
            self._tracks.append(
                Track(
                    track_id=self._next_id,
                    class_id=det.class_id,
                    class_name=det.class_name,
                    bbox=det.bbox,
                    confidence=det.confidence,
                )
            )
            self._next_id += 1

        self._tracks = [
            t for t in self._tracks
            if t.time_since_update <= self.max_age and (t in [self._tracks[m[0]] for m in matched] or t.hits >= 1)
        ]
        return [t for t in self._tracks if t.time_since_update == 0 or t.hits >= 2]

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1
