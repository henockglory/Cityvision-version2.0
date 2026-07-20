from __future__ import annotations

from dataclasses import dataclass, field


class _KalmanCV1D:
    """Minimal 1-D constant-velocity Kalman filter (position + velocity).

    Pure Python (no numpy) so it stays dependency-free and unit-testable.
    Four of these compose a bbox filter over (cx, cy, w, h).
    """

    __slots__ = ("x", "v", "p00", "p01", "p10", "p11", "q", "r")

    def __init__(self, pos: float, q: float = 1.0, r: float = 10.0) -> None:
        self.x = pos          # position estimate
        self.v = 0.0          # velocity estimate
        # Covariance matrix [[p00,p01],[p10,p11]]
        self.p00, self.p01, self.p10, self.p11 = 100.0, 0.0, 0.0, 100.0
        self.q = q            # process noise
        self.r = r            # measurement noise

    def predict(self, dt: float = 1.0) -> float:
        # State transition: x += v*dt
        self.x += self.v * dt
        # P = F P F^T + Q
        p00 = self.p00 + dt * (self.p10 + self.p01) + dt * dt * self.p11 + self.q
        p01 = self.p01 + dt * self.p11
        p10 = self.p10 + dt * self.p11
        p11 = self.p11 + self.q
        self.p00, self.p01, self.p10, self.p11 = p00, p01, p10, p11
        return self.x

    def update(self, z: float) -> float:
        # Innovation covariance S = H P H^T + R, with H = [1, 0]
        s = self.p00 + self.r
        if s == 0:
            return self.x
        k0 = self.p00 / s
        k1 = self.p10 / s
        y = z - self.x
        self.x += k0 * y
        self.v += k1 * y
        # P = (I - K H) P
        p00 = (1 - k0) * self.p00
        p01 = (1 - k0) * self.p01
        p10 = self.p10 - k1 * self.p00
        p11 = self.p11 - k1 * self.p01
        self.p00, self.p01, self.p10, self.p11 = p00, p01, p10, p11
        return self.x


class KalmanBox:
    """Constant-velocity Kalman filter over a bbox (top-left x/y + w/h)."""

    __slots__ = ("cx", "cy", "w", "h")

    def __init__(self, bbox: dict) -> None:
        w = bbox["width"]
        h = bbox["height"]
        self.cx = _KalmanCV1D(bbox["x"] + w / 2)
        self.cy = _KalmanCV1D(bbox["y"] + h / 2)
        self.w = _KalmanCV1D(w)
        self.h = _KalmanCV1D(h)

    def predict(self) -> dict:
        cx = self.cx.predict()
        cy = self.cy.predict()
        w = max(1.0, self.w.predict())
        h = max(1.0, self.h.predict())
        return {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h}

    def peek_predict(self, dt: float = 1.0) -> dict:
        """One-step prediction without mutating filter state (for live overlay)."""
        cx = self.cx.x + self.cx.v * dt
        cy = self.cy.x + self.cy.v * dt
        w = max(1.0, self.w.x + self.w.v * dt)
        h = max(1.0, self.h.x + self.h.v * dt)
        return {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h}

    def update(self, bbox: dict) -> dict:
        w = bbox["width"]
        h = bbox["height"]
        cx = self.cx.update(bbox["x"] + w / 2)
        cy = self.cy.update(bbox["y"] + h / 2)
        nw = max(1.0, self.w.update(w))
        nh = max(1.0, self.h.update(h))
        return {"x": cx - nw / 2, "y": cy - nh / 2, "width": nw, "height": nh}


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
    _kf: KalmanBox | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._kf is None:
            self._kf = KalmanBox(self.bbox)


@dataclass
class ByteTracker:
    """ByteTrack-style tracker: constant-velocity Kalman prediction plus a
    two-stage (high/low confidence) IoU association.

    The two-stage matching recovers occluded/low-confidence detections that a
    single-threshold tracker would drop, while the Kalman motion model keeps IDs
    stable through brief gaps. Backward compatible with the previous IoU-only
    ``update(detections) -> list[Track]`` contract.
    """

    max_age: int = 30
    min_hits: int = 3
    iou_threshold: float = 0.3
    high_thresh: float = 0.5
    low_thresh: float = 0.1
    _tracks: list[Track] = field(default_factory=list)
    _next_id: int = 1

    def update(self, detections: list[dict]) -> list[Track]:
        # 1) Advance the motion model for every existing track.
        predicted: list[dict] = []
        for track in self._tracks:
            assert track._kf is not None
            predicted.append(track._kf.predict())

        high = [d for d in detections if d["confidence"] >= self.high_thresh]
        low = [
            d for d in detections
            if self.low_thresh <= d["confidence"] < self.high_thresh
        ]

        matched_tracks: set[int] = set()

        # 2) Stage 1 — associate high-confidence detections.
        matched_high = self._associate(predicted, high, matched_tracks)
        # 3) Stage 2 — associate remaining tracks with low-confidence detections.
        self._associate(predicted, low, matched_tracks)

        # 4) Spawn new tracks only from unmatched high-confidence detections.
        for di, det in enumerate(high):
            if di in matched_high:
                continue
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

        # 5) Age unmatched tracks.
        for ti, track in enumerate(self._tracks):
            if ti not in matched_tracks and ti < len(predicted):
                track.time_since_update += 1
                track.age += 1
                track.bbox = predicted[ti]  # coast on prediction

        self._tracks = [t for t in self._tracks if t.time_since_update <= self.max_age]
        return [t for t in self._tracks if t.hits >= self.min_hits or t.age <= self.min_hits]

    def overlay_snapshot(self, max_coast: int = 2, predict_steps: float = 1.0) -> list[dict]:
        """Non-mutating bbox positions for live overlay between inference frames."""
        out: list[dict] = []
        for track in self._tracks:
            if track.time_since_update > max_coast:
                continue
            if track.hits < 1 and track.age > 1:
                continue
            if track._kf is not None and track.time_since_update == 0:
                bbox = track._kf.peek_predict(predict_steps)
            else:
                bbox = dict(track.bbox)
            out.append({
                "track_id": track.track_id,
                "class_id": track.class_id,
                "class_name": track.class_name,
                "confidence": track.confidence,
                "bbox": bbox,
                "time_since_update": track.time_since_update,
            })
        return out

    def _associate(
        self, predicted: list[dict], dets: list[dict], matched_tracks: set[int]
    ) -> set[int]:
        """Greedy IoU association against predicted track boxes. Returns the set
        of matched detection indices; mutates matched_tracks in place."""
        matched_dets: set[int] = set()
        for ti, track in enumerate(self._tracks):
            if ti in matched_tracks or ti >= len(predicted):
                continue
            best_iou = 0.0
            best_di = -1
            for di, det in enumerate(dets):
                if di in matched_dets:
                    continue
                iou = _bbox_iou(predicted[ti], det["bbox"])
                if iou > self.iou_threshold and iou > best_iou:
                    best_iou = iou
                    best_di = di
            if best_di >= 0:
                det = dets[best_di]
                assert track._kf is not None
                track.bbox = track._kf.update(det["bbox"])
                track.confidence = det["confidence"]
                track.class_id = det["class_id"]
                track.class_name = det["class_name"]
                track.hits += 1
                track.time_since_update = 0
                track.age += 1
                matched_dets.add(best_di)
                matched_tracks.add(ti)
        return matched_dets

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
