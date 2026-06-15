from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def encode_scene_jpeg(frame: np.ndarray, quality: int = 82) -> bytes | None:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def encode_subject_jpeg(frame: np.ndarray, bbox: dict[str, Any] | None, quality: int = 82) -> bytes | None:
    if not bbox:
        return encode_scene_jpeg(frame, quality)
    h, w = frame.shape[:2]
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    bw = float(bbox.get("width", 0.1))
    bh = float(bbox.get("height", 0.1))
    # Normalized 0-1 coords
    if x <= 1 and y <= 1 and bw <= 1 and bh <= 1:
        x1 = int(max(0, (x - bw * 0.1) * w))
        y1 = int(max(0, (y - bh * 0.1) * h))
        x2 = int(min(w, (x + bw * 1.1) * w))
        y2 = int(min(h, (y + bh * 1.1) * h))
    else:
        x1, y1, x2, y2 = int(x), int(y), int(x + bw), int(y + bh)
    if x2 <= x1 or y2 <= y1:
        return encode_scene_jpeg(frame, quality)
    crop = frame[y1:y2, x1:x2]
    ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def bbox_from_event(evt: dict[str, Any]) -> dict[str, Any] | None:
    bb = evt.get("bbox")
    if isinstance(bb, dict):
        return bb
    meta = evt.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("bbox"), dict):
        return meta["bbox"]
    return None
