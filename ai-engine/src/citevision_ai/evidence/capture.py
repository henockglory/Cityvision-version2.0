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


def normalize_bbox(bbox: dict[str, Any] | None, frame_w: int, frame_h: int) -> dict[str, Any] | None:
    """Return bbox in 0–1 normalized coords (handles pixel or norm input)."""
    if not bbox:
        return None
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    bw = float(bbox.get("width", 0))
    bh = float(bbox.get("height", 0))
    if bw <= 0 or bh <= 0:
        return None
    if x <= 1 and y <= 1 and bw <= 1 and bh <= 1:
        return {"x": x, "y": y, "width": bw, "height": bh}
    w, h = max(frame_w, 1), max(frame_h, 1)
    return {
        "x": max(0.0, min(1.0, x / w)),
        "y": max(0.0, min(1.0, y / h)),
        "width": max(0.0, min(1.0, bw / w)),
        "height": max(0.0, min(1.0, bh / h)),
    }


def bbox_rear_plate_region(bbox: dict[str, Any]) -> dict[str, Any]:
    """Lower-rear band of a vehicle bbox (typical plate location)."""
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    bw = float(bbox.get("width", 0.1))
    bh = float(bbox.get("height", 0.1))
    plate_h = bh * 0.42
    plate_w = bw * 0.72
    cx = x + bw / 2
    cy = y + bh * 0.82
    return {
        "x": cx - plate_w / 2,
        "y": cy - plate_h / 2,
        "width": plate_w,
        "height": plate_h,
    }


def bbox_area_norm(bbox: dict[str, Any] | None, frame_w: int, frame_h: int) -> float:
    bb = normalize_bbox(bbox, frame_w, frame_h)
    if not bb:
        return 0.0
    return float(bb["width"]) * float(bb["height"])


def pick_best_bbox(
    candidates: list[dict[str, Any] | None],
    frame_w: int,
    frame_h: int,
    *,
    min_frac: float = 0.02,
) -> dict[str, Any] | None:
    """Largest valid normalized bbox — avoids 1px ByteTrack glitches on zone exit."""
    best: dict[str, Any] | None = None
    best_area = 0.0
    for raw in candidates:
        if not raw:
            continue
        bb = normalize_bbox(raw, frame_w, frame_h)
        if not bb or not bbox_valid(bb, min_frac=min_frac):
            continue
        area = float(bb["width"]) * float(bb["height"])
        if area > best_area:
            best_area = area
            best = bb
    return best


def pick_best_bbox_with_ts(
    candidates: list[tuple[dict[str, Any] | None, float | None]],
    frame_w: int,
    frame_h: int,
    *,
    min_frac: float = 0.02,
) -> tuple[dict[str, Any] | None, float | None]:
    """Like ``pick_best_bbox`` but each candidate carries the wall-clock timestamp
    of the frame it was observed in, and the timestamp of the winning bbox is
    returned alongside it.

    This lets evidence capture fetch the *exact* frame that produced the chosen
    bbox (from the ring buffer or the live frame) instead of a frame captured at
    event-emission time, which can be hundreds of ms later than the bbox itself
    (vehicle has moved on) — the root cause of crops landing on empty road.
    """
    best: dict[str, Any] | None = None
    best_ts: float | None = None
    best_area = 0.0
    for raw, ts in candidates:
        if not raw:
            continue
        bb = normalize_bbox(raw, frame_w, frame_h)
        if not bb or not bbox_valid(bb, min_frac=min_frac):
            continue
        area = float(bb["width"]) * float(bb["height"])
        if area > best_area:
            best_area = area
            best = bb
            best_ts = ts
    return best, best_ts


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
    fallback_full: bool = True,
) -> bytes | None:
    if crop == "full" or not bbox:
        return encode_scene_jpeg(frame, quality) if fallback_full or crop == "full" else None
    h, w = frame.shape[:2]
    bbox = normalize_bbox(bbox, w, h)
    if not bbox_valid(bbox):
        return encode_scene_jpeg(frame, quality) if fallback_full else None
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    bw = float(bbox.get("width", 0.1))
    bh = float(bbox.get("height", 0.1))
    pad = padding_pct / 100.0
    cx = x + bw / 2
    cy = y + bh / 2
    zoom = min(max(zoom, 0.5), 3.5)
    bw_z = bw / zoom
    bh_z = bh / zoom
    x = cx - bw_z / 2
    y = cy - bh_z / 2
    x1 = int(max(0, (x - bw_z * pad) * w))
    y1 = int(max(0, (y - bh_z * pad) * h))
    x2 = int(min(w, (x + bw_z * (1 + pad)) * w))
    y2 = int(min(h, (y + bh_z * (1 + pad)) * h))
    if x2 <= x1 or y2 <= y1:
        return encode_scene_jpeg(frame, quality) if fallback_full else None
    if (x2 - x1) < 32 or (y2 - y1) < 32:
        return encode_scene_jpeg(frame, quality) if fallback_full else None
    crop_img = frame[y1:y2, x1:x2]
    ok, buf = cv2.imencode(".jpg", crop_img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def bbox_from_event(evt: dict[str, Any]) -> dict[str, Any] | None:
    bb = evt.get("bbox")
    if isinstance(bb, dict) and bbox_valid(bb, min_frac=0.02):
        return bb
    meta = evt.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("bbox"), dict):
        bb = meta["bbox"]
        if bbox_valid(bb, min_frac=0.02):
            return bb
    return None


def draw_bbox_on_frame(
    frame: np.ndarray,
    bbox: dict[str, Any] | None,
    *,
    color: tuple[int, int, int] = (255, 180, 0),
    thickness: int = 3,
    min_luminance: float = 12.0,
) -> np.ndarray:
    h, w = frame.shape[:2]
    norm = normalize_bbox(bbox, w, h) if bbox else None
    if not norm or not bbox_valid(norm, min_frac=0.02):
        return frame
    bbox = norm
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
    h, w = frame.shape[:2]
    norm_bbox = normalize_bbox(bbox, w, h) if bbox else None
    for spec in images_spec:
        role = spec.get("role", "scene")
        crop = spec.get("crop", "full" if role == "scene" else "bbox")
        padding = float(spec.get("padding_pct") or 10)
        zoom = float(spec.get("zoom") or (2.2 if role == "subject" else 1.0))
        crop_bbox = norm_bbox

        if role == "scene":
            scene = encode_scene_jpeg(frame, quality)
            continue

        if role == "subject":
            use_bbox = norm_bbox if norm_bbox and bbox_valid(norm_bbox, min_frac=0.02) else None
            if crop == "full" and use_bbox:
                crop = "bbox"
            if crop == "bbox" and use_bbox:
                subject = encode_subject_jpeg(
                    frame, use_bbox, quality,
                    padding_pct=max(padding, 12.0), zoom=zoom, crop="bbox", fallback_full=False,
                )
            elif crop == "full" or not use_bbox:
                src = draw_bbox_on_frame(frame, use_bbox) if draw_bbox and use_bbox else frame
                subject = encode_scene_jpeg(src, quality)
            else:
                src = draw_bbox_on_frame(frame, use_bbox) if draw_bbox else frame
                subject = encode_subject_jpeg(
                    src, use_bbox, quality,
                    padding_pct=padding, zoom=zoom, crop="bbox", fallback_full=False,
                )
            if subject is None and use_bbox:
                subject = encode_subject_jpeg(
                    frame, use_bbox, quality,
                    padding_pct=15.0, zoom=1.0, crop="bbox", fallback_full=False,
                )
            if subject is None:
                subject = encode_scene_jpeg(frame, quality)
            continue

        if role == "plate" or crop in ("plate_rear", "rear_plate"):
            zoom_plate = float(spec.get("zoom") or 1.8)
            padding_plate = float(spec.get("padding_pct") or 6)
            plate_bbox = bbox_rear_plate_region(norm_bbox) if norm_bbox else None
            jpeg = encode_subject_jpeg(
                frame, plate_bbox, quality,
                padding_pct=padding_plate, zoom=zoom_plate, crop="bbox", fallback_full=False,
            )
            if jpeg is None and norm_bbox:
                jpeg = encode_subject_jpeg(
                    frame, norm_bbox, quality,
                    padding_pct=4, zoom=4.0, crop="bbox", fallback_full=False,
                )
            if jpeg is None and norm_bbox:
                jpeg = encode_subject_jpeg(
                    frame, norm_bbox, quality,
                    padding_pct=0, zoom=2.5, crop="bbox", fallback_full=True,
                )
            if jpeg:
                extras.append(jpeg)
            continue

        src = frame
        if draw_bbox and crop_bbox and role == "subject":
            src = draw_bbox_on_frame(frame, crop_bbox)
        jpeg = encode_subject_jpeg(
            src, crop_bbox, quality, padding_pct=padding, zoom=zoom, crop=crop,
        )
        extras.append(jpeg)
    if scene is None and images_spec:
        scene = encode_scene_jpeg(frame, quality)
    if subject is None and any(s.get("role") == "subject" for s in images_spec):
        subject = encode_scene_jpeg(frame, quality)
    return scene, subject, extras
