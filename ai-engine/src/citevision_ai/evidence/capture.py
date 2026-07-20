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


def bbox_evidence_score(
    bbox: dict[str, Any] | None,
    frame_w: int,
    frame_h: int,
    *,
    min_frac: float = 0.02,
) -> float:
    """Score a bbox for evidence crops — rejects exit glitches (oversized / off-screen)."""
    bb = normalize_bbox(bbox, frame_w, frame_h)
    if not bb or not bbox_valid(bb, min_frac=min_frac):
        return 0.0
    w, h = float(bb["width"]), float(bb["height"])
    area = w * h
    if area > 0.28:
        return 0.0
    aspect = w / max(h, 1e-9)
    if aspect > 3.2 or aspect < 0.28:
        return 0.0
    x, y = float(bb["x"]), float(bb["y"])
    if x < 0.01 and w > 0.30:
        return 0.0
    if y < 0.01 and h > 0.35:
        return 0.0
    if y + h > 0.99 and h > 0.38:
        return 0.0
    score = area
    if area > 0.18:
        score *= 0.55
    return score


def pick_best_bbox(
    candidates: list[dict[str, Any] | None],
    frame_w: int,
    frame_h: int,
    *,
    min_frac: float = 0.02,
) -> dict[str, Any] | None:
    """Best evidence bbox — scored for vehicle-like size, not raw largest area."""
    best: dict[str, Any] | None = None
    best_score = 0.0
    for raw in candidates:
        if not raw:
            continue
        bb = normalize_bbox(raw, frame_w, frame_h)
        if not bb:
            continue
        score = bbox_evidence_score(bb, frame_w, frame_h, min_frac=min_frac)
        if score > best_score:
            best_score = score
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
    best_score = 0.0
    for raw, ts in candidates:
        if not raw:
            continue
        bb = normalize_bbox(raw, frame_w, frame_h)
        if not bb:
            continue
        score = bbox_evidence_score(bb, frame_w, frame_h, min_frac=min_frac)
        if score > best_score:
            best_score = score
            best = bb
            best_ts = ts
    return best, best_ts


def select_live_event_bbox(
    evt: dict[str, Any],
    track_dicts: list[dict[str, Any]],
    history: list[dict],
    frame_w: int,
    frame_h: int,
    frame_wall_ts: float,
) -> tuple[dict[str, Any] | None, float | None]:
    """Legacy helper — prefer ``resolve_emission_track_bbox`` for live evidence."""
    bb, ts, _src = resolve_emission_track_bbox(
        evt,
        track_dicts,
        frame_w,
        frame_h,
        frame_wall_ts,
        last_bbox_fallback=history[-1] if history else None,
    )
    return bb, ts


def resolve_emission_track_bbox(
    evt: dict[str, Any],
    track_dicts: list[dict[str, Any]],
    frame_w: int,
    frame_h: int,
    frame_wall_ts: float,
    last_bbox_fallback: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, float | None, str]:
    """BBox for evidence on the emission frame — YOLO/ByteTrack track on this tick.

    Priority:
    1. Current ``track_dicts`` entry for ``evt.track_id`` (co-emitted with frame).
    2. ``last_bbox_fallback`` (track_lost / track absent on finalize frame).
    3. ``evt.bbox`` if still valid.

    Returns ``(bbox_norm, bbox_ts, bbox_source)`` where ``bbox_source`` is one of
    ``emission_track``, ``last_known``, ``event_fallback``, or ``none``.
    """
    tid = evt.get("track_id")
    tid_str = str(tid) if tid is not None else None
    if tid is not None:
        for t in track_dicts:
            t_id = t.get("track_id")
            if t_id == tid or (tid_str is not None and str(t_id) == tid_str):
                if t.get("bbox"):
                    bb = normalize_bbox(t["bbox"], frame_w, frame_h)
                    if bb and bbox_valid(bb, min_frac=0.02):
                        return bb, frame_wall_ts, "emission_track"
    if last_bbox_fallback:
        fb_bbox = last_bbox_fallback.get("bbox")
        bb = normalize_bbox(fb_bbox, frame_w, frame_h) if fb_bbox else None
        if bb and bbox_valid(bb, min_frac=0.02):
            return bb, frame_wall_ts, "last_known"
    bb = evt.get("bbox")
    if isinstance(bb, dict) and bb:
        norm = normalize_bbox(bb, frame_w, frame_h)
        if norm and bbox_valid(norm, min_frac=0.02):
            return norm, frame_wall_ts, "event_fallback"
    return None, None, "none"


def subject_jpeg_texture(jpeg: bytes | None, *, min_size: int = 32) -> float | None:
    """Laplacian variance of a subject crop JPEG — None if decode fails."""
    if not jpeg or len(jpeg) < min_size:
        return None
    gray = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None or gray.size == 0:
        return None
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def bbox_region_has_content(
    frame: np.ndarray,
    bbox: dict[str, Any] | None,
    *,
    min_laplacian: float = 12.0,
    min_frac: float = 0.02,
) -> bool:
    """True when the bbox ROI has enough texture to be a real target (not empty road)."""
    h, w = frame.shape[:2]
    norm = normalize_bbox(bbox, w, h)
    if not norm or not bbox_valid(norm, min_frac=min_frac):
        return False
    x1 = int(max(0, norm["x"] * w))
    y1 = int(max(0, norm["y"] * h))
    x2 = int(min(w, (norm["x"] + norm["width"]) * w))
    y2 = int(min(h, (norm["y"] + norm["height"]) * h))
    if x2 - x1 < 20 or y2 - y1 < 20:
        return False
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    std = float(gray.std())
    # Truly uniform/empty region (e.g. sky, blank frame).
    if std < 3.0:
        return False
    # For large enough bboxes (≥60×60 px) YOLO detection confidence is high
    # enough to trust the geometry even when the vehicle roof appears smooth
    # (low Laplacian). Overhead shots of cars typically fall into this case.
    if (x2 - x1) >= 60 and (y2 - y1) >= 60 and std >= 5.0:
        return True
    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    global_std = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).std())
    if std < global_std * 0.9 and lap < min_laplacian:
        return False
    return lap >= min_laplacian or std >= max(10.0, global_std * 1.15)


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
            src = draw_bbox_on_frame(frame, norm_bbox) if draw_bbox and norm_bbox else frame
            scene = encode_scene_jpeg(src, quality)
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
                subject = encode_scene_jpeg(frame, quality)
            else:
                subject = encode_subject_jpeg(
                    frame, use_bbox, quality,
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
        jpeg = encode_subject_jpeg(
            src, crop_bbox, quality, padding_pct=padding, zoom=zoom, crop=crop,
        )
        extras.append(jpeg)
    if scene is None and images_spec:
        src = draw_bbox_on_frame(frame, norm_bbox) if draw_bbox and norm_bbox else frame
        scene = encode_scene_jpeg(src, quality)
    if subject is None and any(s.get("role") == "subject" for s in images_spec):
        subject = encode_scene_jpeg(frame, quality)
    return scene, subject, extras
