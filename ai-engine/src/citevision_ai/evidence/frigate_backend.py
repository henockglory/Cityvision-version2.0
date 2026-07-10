"""Evidence capture via Frigate recordings + snapshots (media plane)."""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from typing import Any

import cv2
import numpy as np

from citevision_ai.config import settings
from citevision_ai.evidence.capture import (
    bbox_from_event,
    capture_images_from_policy,
    normalize_bbox,
    subject_jpeg_texture,
)
from citevision_ai.evidence.config import CLIP_DURATION_SEC, JPEG_QUALITY
from citevision_ai.evidence.gate import default_evidence_policy
from citevision_ai.identity.plate import PaddleOcrPlateBackend

logger = logging.getLogger(__name__)

SUBJECT_MIN_TEXTURE = 50.0


class FrigateEvidenceBackend:
    """Exports clip/snapshots from Frigate; plate slot uses PaddleOCR (not Frigate LPR)."""

    def __init__(self) -> None:
        self._base = settings.frigate_url.rstrip("/")
        self._plate = PaddleOcrPlateBackend()
        if settings.frigate_plate_ocr:
            try:
                self._plate.load()
            except Exception:
                logger.warning("PaddleOCR preload for Frigate evidence failed", exc_info=True)

    def enabled(self) -> bool:
        return settings.frigate_enabled and settings.frigate_evidence

    def frigate_camera_id(self, camera_id: str) -> str:
        return f"cv_{camera_id}"

    def capture(
        self,
        policy: dict[str, Any],
        evt: dict[str, Any],
        *,
        org_id: str,
        camera_id: str,
    ) -> dict[str, Any] | None:
        if not self.enabled():
            return None
        fid = self.frigate_camera_id(camera_id)
        clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
        anchor = evt.get("bbox_ts")
        if not isinstance(anchor, (int, float)):
            anchor = time.time()
        anchor = float(anchor)

        frame = self._fetch_snapshot(fid)
        if frame is None:
            return None

        raw_bbox = bbox_from_event(evt)
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        draw_bbox = policy.get("draw_bbox", True) is not False
        fh, fw = frame.shape[:2]
        norm_bbox = normalize_bbox(raw_bbox, fw, fh) if raw_bbox else None
        scene, subject, extras = capture_images_from_policy(
            frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=draw_bbox,
        )
        subject_texture = subject_jpeg_texture(subject)
        subject_quality_ok = (
            subject is not None
            and subject_texture is not None
            and subject_texture >= SUBJECT_MIN_TEXTURE
        )
        bbox_quality_ok = norm_bbox is not None
        if subject is not None and not subject_quality_ok:
            bbox_quality_ok = False

        plate_jpeg = extras[0] if extras else None
        plate_number = evt.get("plate_number")
        plate_confidence = evt.get("plate_confidence")
        want_plate = any(s.get("role") == "plate" for s in images_spec)
        if want_plate and plate_jpeg and self._plate.is_loaded:
            arr = np.frombuffer(plate_jpeg, dtype=np.uint8)
            crop = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if crop is not None:
                results = self._plate.recognize(crop)
                if results:
                    best = max(results, key=lambda r: r.confidence)
                    plate_number = best.text
                    plate_confidence = best.confidence

        clip_bytes = self._export_clip(fid, anchor, clip_sec)
        clip_duration = clip_sec if clip_bytes else 0.0

        missing_roles: list[str] = []
        if want_plate and not plate_jpeg:
            missing_roles.append("plate")
        complete = bool(scene and subject and clip_bytes)
        if want_plate and not plate_jpeg:
            complete = False
        if not bbox_quality_ok:
            complete = False
        status = "complete" if complete else "partial"

        return {
            "scene": scene,
            "subject": subject,
            "clip_bytes": clip_bytes,
            "plate_jpeg": plate_jpeg,
            "meta": {
                "bbox": norm_bbox,
                "bbox_ts": evt.get("bbox_ts"),
                "bbox_source": evt.get("bbox_source"),
                "bbox_quality_ok": bbox_quality_ok,
                "subject_texture": round(subject_texture, 1) if subject_texture is not None else None,
                "subject_quality_ok": subject_quality_ok,
                "capture_source": "frigate",
                "frigate_camera_id": fid,
                "align_delta_ms": 0,
                "confidence": evt.get("confidence"),
                "class_name": evt.get("class_name"),
                "zone_id": evt.get("zone_id"),
                "track_id": evt.get("track_id"),
                "event_type": evt.get("event_type") or evt.get("event"),
                "clip_duration_sec": clip_duration,
                "plate_number": plate_number,
                "plate_confidence": plate_confidence,
                "missing_roles": missing_roles,
                "evidence_status": status,
            },
            "status": status,
        }

    def _fetch_snapshot(self, frigate_id: str) -> np.ndarray | None:
        url = f"{self._base}/api/{frigate_id}/latest.jpg"
        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                data = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("frigate snapshot failed", extra={"camera": frigate_id, "error": str(exc)})
            return None
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame

    def _export_clip(self, frigate_id: str, center_ts: float, duration_sec: float) -> bytes | None:
        half = duration_sec / 2.0
        start = max(0.0, center_ts - half)
        end = center_ts + half
        url = f"{self._base}/api/{frigate_id}/start/{start:.3f}/end/{end:.3f}/clip.mp4"
        try:
            with urllib.request.urlopen(url, timeout=45) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("frigate clip export failed", extra={"camera": frigate_id, "error": str(exc)})
            return None
