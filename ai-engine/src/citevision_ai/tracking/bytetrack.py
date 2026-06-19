from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Track:
    track_id: int
    bbox: dict
    class_id: int
    class_name: str
    confidence: float
    age: int = 0
    hits: int = 1
    time_since_update: int = 0


@dataclass
class ByteTracker:
    """ByteTrack-inspired multi-object tracker with IoU association."""

    max_age: int = 30
    min_hits: int = 3
    iou_threshold: float = 0.3
    _tracks: list[Track] = field(default_factory=list)
    _next_id: int = 1

    def update(self, detections: list[dict]) -> list[Track]:
        matched_det_indices: set[int] = set()
        matched_track_indices: set[int] = set()

        for ti, track in enumerate(self._tracks):
            best_iou = 0.0
            best_di = -1
            for di, det in enumerate(detections):
                if di in matched_det_indices:
                    continue
                iou = _bbox_iou(track.bbox, det["bbox"])
                if iou > self.iou_threshold and iou > best_iou:
                    best_iou = iou
                    best_di = di
            if best_di >= 0:
                det = detections[best_di]
                track.bbox = det["bbox"]
                track.confidence = det["confidence"]
                track.hits += 1
                track.time_since_update = 0
                track.age += 1
                matched_det_indices.add(best_di)
                matched_track_indices.add(ti)

        for di, det in enumerate(detections):
            if di not in matched_det_indices:
                self._tracks.append(
                    Track(
                        track_id=self._next_id,
                        bbox=det["bbox"],
                        class_id=det["class_id"],
                        class_name=det["class_name"],
                        confidence=det["confidence"],
                    )
                )
                self._next_id += 1

        for ti, track in enumerate(self._tracks):
            if ti not in matched_track_indices:
                track.time_since_update += 1
                track.age += 1

        self._tracks = [t for t in self._tracks if t.time_since_update <= self.max_age]
        return [t for t in self._tracks if t.hits >= self.min_hits or t.age <= self.min_hits]

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1


def _bbox_iou(a: dict, b: dict) -> float:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["width"], ay1 + a["height"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["width"], by1 + b["height"]
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0
