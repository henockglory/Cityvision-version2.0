from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def encode_scene_jpeg(frame: np.ndarray, quality: int = 82) -> bytes | None:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def frame_median_luminance(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.median(gray))


def bbox_valid(bbox: dict[str, Any] | None, min_frac: float = 0.02) -> bool:
    if not bbox:
        return False
    bw = float(bbox.get("width", 0))
    bh = float(bbox.get("height", 0))
    if bw <= 1 and bh <= 1:
        return bw >= min_frac and bh >= min_frac
    return bw >= 8 and bh >= 8


def encode_subject_jpeg(
    frame: np.ndarray,
    bbox: dict[str, Any] | None,
    quality: int = 82,
    *,
    padding_pct: float = 10,
    zoom: float = 1.0,
    crop: str = "bbox",
) -> bytes | None:
    if crop == "full" or not bbox_valid(bbox):
        return encode_scene_jpeg(frame, quality)
    h, w = frame.shape[:2]
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    bw = float(bbox.get("width", 0.1))
    bh = float(bbox.get("height", 0.1))
    pad = padding_pct / 100.0
    if x <= 1 and y <= 1 and bw <= 1 and bh <= 1:
        cx = x + bw / 2
        cy = y + bh / 2
        zoom = min(max(zoom, 0.5), 3.0)
        bw_z = bw / zoom
        bh_z = bh / zoom
        x = cx - bw_z / 2
        y = cy - bh_z / 2
        bw, bh = bw_z, bh_z
        x1 = int(max(0, (x - bw * pad) * w))
        y1 = int(max(0, (y - bh * pad) * h))
        x2 = int(min(w, (x + bw * (1 + pad)) * w))
        y2 = int(min(h, (y + bh * (1 + pad)) * h))
    else:
        x1, y1, x2, y2 = int(x), int(y), int(x + bw), int(y + bh)
    if x2 <= x1 or y2 <= y1:
        return encode_scene_jpeg(frame, quality)
    if (x2 - x1) < 32 or (y2 - y1) < 32:
        return encode_scene_jpeg(frame, quality)
    crop_img = frame[y1:y2, x1:x2]
    ok, buf = cv2.imencode(".jpg", crop_img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def bbox_from_event(evt: dict[str, Any]) -> dict[str, Any] | None:
    bb = evt.get("bbox")
    if isinstance(bb, dict):
        return bb if bbox_valid(bb, min_frac=0.005) else None
    meta = evt.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("bbox"), dict):
        bb = meta["bbox"]
        return bb if bbox_valid(bb, min_frac=0.005) else None
    return None


def draw_bbox_on_frame(
    frame: np.ndarray,
    bbox: dict[str, Any] | None,
    *,
    color: tuple[int, int, int] = (255, 180, 0),
    thickness: int = 2,
    min_luminance: float = 12.0,
) -> np.ndarray:
    if not bbox or not bbox_valid(bbox, min_frac=0.005):
        return frame
    if frame_median_luminance(frame) < min_luminance:
        return frame
    out = frame.copy()
    h, w = out.shape[:2]
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    bw = float(bbox.get("width", 0.1))
    bh = float(bbox.get("height", 0.1))
    if x <= 1 and y <= 1 and bw <= 1 and bh <= 1:
        x1 = int(max(0, x * w))
        y1 = int(max(0, y * h))
        x2 = int(min(w, (x + bw) * w))
        y2 = int(min(h, (y + bh) * h))
    else:
        x1, y1, x2, y2 = int(x), int(y), int(x + bw), int(y + bh)
    if x2 > x1 and y2 > y1:
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)
    return out


def capture_images_from_policy(
    frame: np.ndarray,
    bbox: dict[str, Any] | None,
    images_spec: list[dict[str, Any]],
    quality: int,
    *,
    draw_bbox: bool = False,
) -> tuple[bytes | None, bytes | None, list[bytes | None]]:
    scene: bytes | None = None
    subject: bytes | None = None
    extras: list[bytes | None] = []
    for spec in images_spec:
        role = spec.get("role", "scene")
        crop = spec.get("crop", "full" if role == "scene" else "bbox")
        padding = float(spec.get("padding_pct") or 10)
        zoom = float(spec.get("zoom") or 1.0)
        src = frame
        if draw_bbox and bbox and role == "subject":
            src = draw_bbox_on_frame(frame, bbox)
        jpeg = encode_subject_jpeg(src, bbox, quality, padding_pct=padding, zoom=zoom, crop=crop)
        if role == "scene":
            scene = jpeg
        elif role == "subject":
            subject = jpeg
        else:
            extras.append(jpeg)
    if scene is None and images_spec:
        scene = encode_scene_jpeg(frame, quality)
    if subject is None and len(images_spec) > 1:
        subject = encode_subject_jpeg(frame, bbox, quality)
    return scene, subject, extras
