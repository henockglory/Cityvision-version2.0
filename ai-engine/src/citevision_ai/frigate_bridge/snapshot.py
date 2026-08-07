"""Download Frigate event snapshot and crop subject bbox."""
from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

import cv2
import numpy as np

from citevision_ai.road_enforcement.traffic_light import classify_light_color

logger = logging.getLogger(__name__)

_VEHICLE = frozenset({"car", "truck", "bus", "motorcycle", "motorbike", "van", "vehicle"})


def wait_snapshot_ready(
    frigate_url: str,
    event_id: str,
    *,
    timeout_sec: float = 25.0,
    poll_sec: float = 1.0,
) -> dict[str, Any] | None:
    """Poll Frigate event until has_snapshot (or timeout). Returns event dict or None."""
    base = frigate_url.rstrip("/")
    deadline = time.time() + max(1.0, float(timeout_sec))
    url = f"{base}/api/events/{event_id}"
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                ev = __import__("json").loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            logger.debug("frigate event poll failed id=%s: %s", event_id[:12], exc)
            time.sleep(poll_sec)
            continue
        if not isinstance(ev, dict):
            time.sleep(poll_sec)
            continue
        if ev.get("has_snapshot") or (ev.get("data") or {}).get("has_snapshot"):
            return ev
        if time.time() + poll_sec >= deadline:
            return ev
        time.sleep(poll_sec)
    return None


def download_snapshot_jpeg(frigate_url: str, event_id: str, *, quality: int = 85) -> bytes | None:
    base = frigate_url.rstrip("/")
    urls = [
        f"{base}/api/events/{event_id}/snapshot.jpg?quality={int(quality)}",
        f"{base}/api/events/{event_id}/snapshot.jpg",
        f"{base}/api/events/{event_id}/snapshot-clean.webp",
        f"{base}/api/events/{event_id}/thumbnail.jpg",
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, method="GET")
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                data = resp.read()
            if data and len(data) > 200:
                return data
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return None


def download_latest_jpeg(frigate_url: str, camera: str, *, quality: int = 85) -> bytes | None:
    base = frigate_url.rstrip("/")
    cam = str(camera or "").strip()
    if not cam:
        return None
    urls = [
        f"{base}/api/{cam}/latest.jpg?quality={int(quality)}",
        f"{base}/api/{cam}/latest.jpg",
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, method="GET")
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = resp.read()
            if data and len(data) > 200:
                return data
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return None


def _box_from_event(ev: dict[str, Any]) -> dict[str, float] | None:
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    box = data.get("box") if isinstance(data, dict) else None
    # MQTT `after` often has top-level `box` (xywh) without nesting under data.
    if not isinstance(box, (list, tuple)) or len(box) < 4:
        box = ev.get("box")
    if not isinstance(box, (list, tuple)) or len(box) < 4:
        return None
    x, y, w, h = float(box[0]), float(box[1]), float(box[2]), float(box[3])
    if max(x, y, w, h) > 1.5 and w > x and h > y:
        w, h = w - x, h - y
    if w <= 0 or h <= 0:
        return None
    if max(x, y, w, h) <= 1.5:
        return {"x": x, "y": y, "width": w, "height": h, "norm": True}
    return {"x": x, "y": y, "width": w, "height": h, "norm": False}


def bbox_cabin_driver_region(
    bbox: dict[str, Any],
    *,
    driver_side: str | None = None,
) -> dict[str, Any]:
    """Sub-ROI of a vehicle bbox targeting windshield / driver (seatbelt & phone).

    Frigate's box is the whole car; Gemini needs the cabin. Heuristic:
    - vertical: upper ~58% of the vehicle (windshield / cabin)
    - horizontal: prefer driver side (LHD = left of car from front view)

    ``driver_side``: ``left`` (default LHD), ``right`` (RHD), or ``center``.
    Override via env ``CABIN_CROP_DRIVER_SIDE``.
    """
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    bw = float(bbox.get("width", 0.1))
    bh = float(bbox.get("height", 0.1))
    side = (driver_side or os.environ.get("CABIN_CROP_DRIVER_SIDE", "left") or "left").strip().lower()
    cabin_h = bh * 0.58
    cabin_y = y + bh * 0.02
    if side in ("right", "rhd"):
        cabin_w = bw * 0.62
        cabin_x = x + bw * 0.32
    elif side in ("center", "both", "mid"):
        cabin_w = bw * 0.78
        cabin_x = x + bw * 0.11
    else:
        cabin_w = bw * 0.62
        cabin_x = x + bw * 0.06
    out: dict[str, Any] = {
        "x": cabin_x,
        "y": cabin_y,
        "width": cabin_w,
        "height": cabin_h,
    }
    if bbox.get("norm"):
        out["norm"] = True
    return out


def crop_jpeg_from_snapshot(
    jpeg_or_webp: bytes,
    box: dict[str, Any] | None,
    *,
    pad: float = 0.08,
    min_side: int = 0,
) -> bytes | None:
    """Decode snapshot, crop box (norm or px), optionally upscale, re-encode JPEG."""
    arr = np.frombuffer(jpeg_or_webp, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    h, w = img.shape[:2]
    if box:
        vals = (
            float(box.get("x", 0)),
            float(box.get("y", 0)),
            float(box.get("width", 0)),
            float(box.get("height", 0)),
        )
        if box.get("norm") or max(vals) <= 1.5:
            x1 = int(max(0, (vals[0] - pad) * w))
            y1 = int(max(0, (vals[1] - pad) * h))
            x2 = int(min(w, (vals[0] + vals[2] + pad) * w))
            y2 = int(min(h, (vals[1] + vals[3] + pad) * h))
        else:
            x1 = int(max(0, vals[0] - pad * w))
            y1 = int(max(0, vals[1] - pad * h))
            x2 = int(min(w, vals[0] + vals[2] + pad * w))
            y2 = int(min(h, vals[1] + vals[3] + pad * h))
        if x2 > x1 + 4 and y2 > y1 + 4:
            img = img[y1:y2, x1:x2]
    if min_side > 0:
        ch, cw = img.shape[:2]
        side = max(ch, cw)
        if side > 0 and side < min_side:
            scale = float(min_side) / float(side)
            img = cv2.resize(
                img,
                (max(1, int(cw * scale)), max(1, int(ch * scale))),
                interpolation=cv2.INTER_CUBIC,
            )
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    return buf.tobytes()


def fetch_subject_jpeg(
    frigate_url: str,
    event_id: str,
    event_payload: dict[str, Any] | None = None,
    *,
    wait_sec: float = 25.0,
) -> tuple[bytes | None, dict[str, float] | None, dict[str, Any] | None]:
    """Return (jpeg_crop, norm_bbox, event_dict). Fail-closed → (None, …)."""
    ev = event_payload
    if ev is None or not (ev.get("has_snapshot") or (ev.get("data") or {}).get("has_snapshot")):
        ev = wait_snapshot_ready(frigate_url, event_id, timeout_sec=wait_sec) or ev
    raw = download_snapshot_jpeg(frigate_url, event_id)
    if not raw:
        return None, None, ev
    box = _box_from_event(ev) if isinstance(ev, dict) else None
    crop = crop_jpeg_from_snapshot(raw, box)
    return crop, box, ev


def fetch_cabin_jpeg(
    frigate_url: str,
    event_id: str,
    event_payload: dict[str, Any] | None = None,
    *,
    wait_sec: float = 25.0,
    label: str = "",
) -> tuple[bytes | None, dict[str, float] | None, dict[str, Any] | None]:
    """Vehicle-in-zone → full Frigate vehicle bbox crop for Gemini seatbelt/phone.

    Cabine policy: ``vehicle_bbox`` only (never driver_roi / cabin sub-crop).
    """
    ev = event_payload
    if ev is None or not (ev.get("has_snapshot") or (ev.get("data") or {}).get("has_snapshot")):
        ev = wait_snapshot_ready(frigate_url, event_id, timeout_sec=wait_sec) or ev
    raw = download_snapshot_jpeg(frigate_url, event_id)
    if not raw:
        return None, None, ev
    vehicle_box = _box_from_event(ev) if isinstance(ev, dict) else None
    if not vehicle_box:
        return None, None, ev
    # No size gate: every tracked vehicle in the zone goes to Gemini; the
    # min_side upscale keeps small/distant crops legible for the yes/no prompt.
    crop = crop_jpeg_from_snapshot(raw, vehicle_box, pad=0.06, min_side=384)
    if crop and vehicle_box:
        logger.info(
            "vehicle_bbox_crop event=%s vehicle=(%.2f,%.2f,%.2fx%.2f)",
            (event_id or "")[:12],
            float(vehicle_box["x"]), float(vehicle_box["y"]),
            float(vehicle_box["width"]), float(vehicle_box["height"]),
        )
    return crop, vehicle_box, ev


def polygon_to_norm_bbox(polygon: list[Any]) -> dict[str, float] | None:
    """Axis-aligned bbox from zone polygon points (normalized 0–1 preferred)."""
    xs: list[float] = []
    ys: list[float] = []
    for p in polygon or []:
        if isinstance(p, dict):
            try:
                xs.append(float(p.get("x", p.get("X", 0))))
                ys.append(float(p.get("y", p.get("Y", 0))))
            except (TypeError, ValueError):
                continue
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
            except (TypeError, ValueError):
                continue
    if len(xs) < 3 or len(ys) < 3:
        return None
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return None
    return {"x": x0, "y": y0, "width": w, "height": h, "norm": max(x1, y1) <= 1.5}


def classify_snapshot_light_state(jpeg: bytes, light_polygon: list[Any] | None) -> str:
    """HSV classify the traffic-light ROI on a Frigate snapshot JPEG."""
    poly = list(light_polygon or [])
    if len(poly) < 3 or not jpeg:
        return "unknown"
    try:
        arr = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return "unknown"
    if frame is None or frame.size == 0:
        return "unknown"
    box = polygon_to_norm_bbox(poly)
    if not box:
        return "unknown"
    h, w = frame.shape[:2]
    x1 = int(max(0, min(w - 1, float(box["x"]) * w)))
    y1 = int(max(0, min(h - 1, float(box["y"]) * h)))
    x2 = int(max(x1 + 1, min(w, (float(box["x"]) + float(box["width"])) * w)))
    y2 = int(max(y1 + 1, min(h, (float(box["y"]) + float(box["height"])) * h)))
    roi = frame[y1:y2, x1:x2]
    state, _ = classify_light_color(roi)
    return str(state or "unknown").lower().strip()


def _union_norm_boxes(
    a: dict[str, Any] | None,
    b: dict[str, Any] | None,
) -> dict[str, float] | None:
    """Axis-aligned union of two boxes (norm or px). Prefer norm when either is norm."""
    if not a and not b:
        return None
    if not a:
        return dict(b) if isinstance(b, dict) else None  # type: ignore[arg-type]
    if not b:
        return dict(a)
    use_norm = bool(a.get("norm") or b.get("norm")) or max(
        float(a.get("x", 0)), float(a.get("y", 0)),
        float(a.get("width", 0)), float(a.get("height", 0)),
        float(b.get("x", 0)), float(b.get("y", 0)),
        float(b.get("width", 0)), float(b.get("height", 0)),
    ) <= 1.5
    ax0, ay0 = float(a["x"]), float(a["y"])
    ax1, ay1 = ax0 + float(a["width"]), ay0 + float(a["height"])
    bx0, by0 = float(b["x"]), float(b["y"])
    bx1, by1 = bx0 + float(b["width"]), by0 + float(b["height"])
    x0, y0 = min(ax0, bx0), min(ay0, by0)
    x1, y1 = max(ax1, bx1), max(ay1, by1)
    out: dict[str, float] = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
    if use_norm:
        out["norm"] = True  # type: ignore[assignment]
    return out


def fetch_red_light_jpeg(
    frigate_url: str,
    event_id: str,
    event_payload: dict[str, Any] | None = None,
    *,
    light_polygon: list[Any] | None = None,
    wait_sec: float = 25.0,
) -> tuple[bytes | None, dict[str, float] | None, dict[str, Any] | None]:
    """Crop for Gemini red-light judgment: lamp + vehicle (never lamp-only).

    Lamp-only crops make Gemini fail-closed (no vehicle visible). Prefer the
    union of traffic-light zone and vehicle bbox; fall back to full snapshot.
    """
    ev = event_payload
    if ev is None or not (ev.get("has_snapshot") or (ev.get("data") or {}).get("has_snapshot")):
        ev = wait_snapshot_ready(frigate_url, event_id, timeout_sec=wait_sec) or ev
    light_box = polygon_to_norm_bbox(list(light_polygon or []))
    vehicle_box = _box_from_event(ev) if isinstance(ev, dict) else None
    union = _union_norm_boxes(light_box, vehicle_box)
    raw = download_snapshot_jpeg(frigate_url, event_id)
    if not raw:
        return None, None, ev
    if union and float(union.get("width") or 0) > 0 and float(union.get("height") or 0) > 0:
        crop = crop_jpeg_from_snapshot(raw, union, pad=0.10, min_side=400)
        if crop:
            return crop, union, ev
    if vehicle_box:
        crop = crop_jpeg_from_snapshot(raw, vehicle_box, pad=0.14, min_side=400)
        if crop:
            return crop, vehicle_box, ev
    # Full snapshot: Gemini needs both signal and vehicle in one view.
    crop = crop_jpeg_from_snapshot(raw, None, pad=0.0, min_side=0)
    return crop, None, ev
