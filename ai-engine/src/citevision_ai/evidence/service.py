from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from citevision_ai.evidence.buffer import FrameRingBuffer
from citevision_ai.evidence.capture import (
    bbox_from_event,
    capture_images_from_policy,
    normalize_bbox,
)
from citevision_ai.evidence.config import (
    CLIP_DURATION_SEC,
    FRAME_ALIGN_TOLERANCE_SEC,
    JPEG_QUALITY,
    RING_FPS,
    RING_SECONDS,
)
from citevision_ai.evidence.gate import EvidenceCaptureGate, default_evidence_policy
from citevision_ai.evidence.uploader import EvidenceUploader

logger = logging.getLogger(__name__)


def _parse_event_ts(evt: dict[str, Any]) -> float | None:
    event_ts = evt.get("timestamp") or evt.get("ts")
    if isinstance(event_ts, (int, float)):
        return float(event_ts)
    if isinstance(event_ts, str):
        try:
            return datetime.fromisoformat(event_ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            try:
                return float(event_ts)
            except ValueError:
                return None
    return None


class EvidenceCaptureService:
    def __init__(self) -> None:
        self._buffers: dict[str, FrameRingBuffer] = {}
        self._gate = EvidenceCaptureGate()
        self._uploader = EvidenceUploader()

    def set_capture_rules(self, camera_id: str, rules: list[dict[str, Any]] | None) -> None:
        self._gate.set_rules(camera_id, rules)

    def push_frame(self, camera_id: str, frame) -> None:
        buf = self._buffers.get(camera_id)
        if buf is None:
            buf = FrameRingBuffer(max_seconds=RING_SECONDS, fps=RING_FPS, jpeg_quality=JPEG_QUALITY)
            self._buffers[camera_id] = buf
        buf.maybe_push(frame)

    def attach_evidence(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        frame,
        *,
        force: bool = False,
        policy: dict[str, Any] | None = None,
        async_upload: bool = True,
        frame_ts: float | None = None,
    ) -> None:
        if not org_id:
            return
        if policy is None:
            if force:
                policy = default_evidence_policy()
            else:
                policy = self._gate.match_policy(camera_id, evt)
        if policy is None:
            return
        if async_upload:
            self.attach_evidence_async(camera_id, org_id, evt, frame, policy=policy, frame_ts=frame_ts)
            return
        self._capture_and_attach(camera_id, org_id, evt, frame, policy, frame_ts=frame_ts)

    def attach_evidence_async(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        frame,
        *,
        policy: dict[str, Any],
        frame_ts: float | None = None,
    ) -> None:
        """Capture + upload in background so ingest never blocks on backend HTTP."""

        def _run() -> None:
            try:
                self._capture_and_attach(camera_id, org_id, evt, frame, policy, frame_ts=frame_ts)
            except Exception:
                logger.exception(
                    "async evidence failed camera=%s event=%s",
                    camera_id,
                    evt.get("event_id"),
                )

        threading.Thread(
            target=_run,
            daemon=True,
            name=f"evidence-{evt.get('event_id', 'evt')}",
        ).start()

    def capture_retroactive(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        buf = self._buffers.get(camera_id)
        event_ts = _parse_event_ts(evt)
        if event_ts is None:
            event_ts = time.time()
        frame = buf.get_frame_at_ts(float(event_ts)) if buf else None
        if frame is None and buf:
            frame = buf.get_last_frame()
        if frame is None:
            logger.warning("retro capture unavailable camera=%s (no buffer frame)", camera_id)
            return None
        pol = policy or default_evidence_policy()
        return self._capture_and_attach(camera_id, org_id, evt, frame, pol, return_upload=True)

    def _resolve_capture_frame(
        self,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        frame_ts: float | None = None,
    ):
        """Pick the frame that actually matches ``evt["bbox"]`` in time.

        Priority:
        1. The live frame already in hand, when its wall-clock timestamp is close
           to the bbox's source-frame timestamp (``bbox_ts``) — perfect alignment,
           no ring-buffer lookup needed. This is the common case since the pipeline
           prefers the current frame's bbox before falling back to history.
        2. A ring-buffer frame looked up by ``bbox_ts`` (not the event-emission
           timestamp, which can be hundreds of ms later than the bbox itself and
           land on a frame where the vehicle has already moved off-crop).
        3. Legacy fallback: ring buffer by event-emission timestamp, then the
           last known frame, then the frame passed in.
        """
        bbox_ts = evt.get("bbox_ts")
        has_bbox_ts = isinstance(bbox_ts, (int, float))
        if has_bbox_ts and frame_ts is not None and abs(float(bbox_ts) - float(frame_ts)) <= FRAME_ALIGN_TOLERANCE_SEC:
            return frame
        buf = self._buffers.get(camera_id)
        if has_bbox_ts and buf:
            buffered = buf.get_frame_at_ts(float(bbox_ts))
            if buffered is not None:
                return buffered
        event_ts = _parse_event_ts(evt)
        if buf and event_ts is not None:
            buffered = buf.get_frame_at_ts(float(event_ts))
            if buffered is not None:
                return buffered
            last = buf.get_last_frame()
            if last is not None:
                return last
        return frame

    def _capture_and_attach(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        frame,
        policy: dict[str, Any],
        return_upload: bool = False,
        frame_ts: float | None = None,
    ) -> dict[str, Any] | None:
        clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
        event_id = str(evt.get("event_id", ""))
        capture_frame = self._resolve_capture_frame(camera_id, evt, frame, frame_ts)
        raw_bbox = bbox_from_event(evt)
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        draw_bbox = policy.get("draw_bbox", True) is not False
        fh, fw = capture_frame.shape[:2]
        norm_bbox = normalize_bbox(raw_bbox, fw, fh) if raw_bbox else None
        scene, subject, extras = capture_images_from_policy(
            capture_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=draw_bbox,
        )
        buf = self._buffers.get(camera_id)
        clip_bytes: bytes | None = None
        clip_duration = 0.0
        if buf:
            exported = buf.export_clip_mp4(clip_sec, RING_FPS)
            if exported:
                clip_bytes = exported.data
                clip_duration = exported.duration_sec
        plate_jpeg = extras[0] if extras else None
        image_labels: dict[str, str] = {}
        for spec in images_spec:
            role = str(spec.get("role", ""))
            label = spec.get("label")
            if role and label:
                image_labels[role] = str(label)
        want_plate = any(s.get("role") == "plate" for s in images_spec)
        missing_roles: list[str] = []
        if want_plate and not plate_jpeg:
            missing_roles.append("plate")
        complete = bool(scene and subject and clip_bytes)
        if want_plate and not plate_jpeg:
            complete = False
        status = "complete" if complete else "partial"
        meta = {
            "bbox": norm_bbox,
            "confidence": evt.get("confidence"),
            "class_name": evt.get("class_name"),
            "zone_id": evt.get("zone_id"),
            "track_id": evt.get("track_id"),
            "event_type": evt.get("event_type") or evt.get("event"),
            "clip_duration_sec": clip_duration,
            "plate_number": evt.get("plate_number"),
            "plate_confidence": evt.get("plate_confidence"),
            "image_labels": image_labels,
            "missing_roles": missing_roles,
            "evidence_status": status,
        }
        uploaded = self._uploader.upload(
            org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
            plate_jpeg=plate_jpeg,
        )
        if not uploaded:
            uploaded = self._uploader.upload(
                org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
                plate_jpeg=plate_jpeg,
            )
        if uploaded:
            evt["evidence"] = uploaded
            if pkg := uploaded.get("package"):
                evt["package"] = pkg
            evt["evidence_status"] = status
        else:
            evt["evidence_status"] = "failed"
        if return_upload:
            return uploaded
        return None

    def clear_camera(self, camera_id: str) -> None:
        self._buffers.pop(camera_id, None)
        self._gate.clear_camera(camera_id)
