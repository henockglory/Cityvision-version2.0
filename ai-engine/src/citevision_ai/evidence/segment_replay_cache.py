"""In-memory JPEG cache for segment replay frames (exact index, no MP4 seek)."""

from __future__ import annotations

import cv2
import numpy as np


class SegmentReplayCache:
    """Stores replay frames keyed by (camera_id, cycle_id, frame_index)."""

    def __init__(self, max_frames_per_cycle: int = 120, jpeg_quality: int = 85) -> None:
        self._jpeg: dict[tuple[str, str], dict[int, bytes]] = {}
        self._max_frames = max_frames_per_cycle
        self._quality = jpeg_quality

    def clear_camera(self, camera_id: str) -> None:
        drop = [k for k in self._jpeg if k[0] == camera_id]
        for k in drop:
            self._jpeg.pop(k, None)

    def clear_cycle(self, camera_id: str, cycle_id: str) -> None:
        self._jpeg.pop((camera_id, cycle_id), None)

    def store(self, camera_id: str, cycle_id: str, frame_index: int, frame: np.ndarray) -> None:
        key = (camera_id, cycle_id)
        bucket = self._jpeg.setdefault(key, {})
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality])
        if not ok:
            return
        bucket[int(frame_index)] = buf.tobytes()
        if len(bucket) > self._max_frames:
            for old in sorted(bucket.keys())[:-self._max_frames]:
                bucket.pop(old, None)

    def get_bgr(self, camera_id: str, cycle_id: str, frame_index: int) -> np.ndarray | None:
        data = self._jpeg.get((camera_id, cycle_id), {}).get(int(frame_index))
        if not data:
            return None
        decoded = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        return decoded if decoded is not None and decoded.size > 0 else None
