from __future__ import annotations

from typing import Any

import cv2
import numpy as np

# BGR palette aligned with frontend detectionOverlayStyle.ts
_CLASS_BGR: dict[str, tuple[int, int, int]] = {
    "person": (36, 191, 251),
    "car": (248, 189, 56),
    "truck": (250, 165, 96),
    "bus": (248, 140, 129),
    "motorcycle": (191, 212, 45),
    "bicycle": (153, 211, 52),
}
_DEFAULT_BGR = (250, 139, 167)


def _color(class_name: str) -> tuple[int, int, int]:
    return _CLASS_BGR.get(class_name, _DEFAULT_BGR)


def draw_overlay_boxes(
    frame: np.ndarray,
    detections: list[dict[str, Any]],
    *,
    min_conf: float = 0.45,
) -> np.ndarray:
    """Draw ByteTrack boxes on a copy of frame (burn-in before go2rtc encode)."""
    if not detections:
        return frame
    out = frame.copy()
    h, w = out.shape[:2]
    for det in detections:
        conf = float(det.get("confidence", 0))
        if conf < min_conf:
            continue
        bb = det.get("bbox") or {}
        x = int(float(bb.get("x", 0)))
        y = int(float(bb.get("y", 0)))
        bw = int(float(bb.get("width", 0)))
        bh = int(float(bb.get("height", 0)))
        if bw < 4 or bh < 4:
            continue
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        bw = min(bw, w - x)
        bh = min(bh, h - y)
        cls = str(det.get("class_name", "object"))
        color = _color(cls)
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2, cv2.LINE_AA)
        label = f"{cls} {int(conf * 100)}%"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        ty = max(th + 4, y)
        cv2.rectangle(out, (x, ty - th - 6), (x + tw + 6, ty), (8, 12, 20), -1)
        cv2.putText(out, label, (x + 3, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return out
