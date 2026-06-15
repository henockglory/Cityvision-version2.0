from __future__ import annotations

import logging
from typing import Any

import numpy as np

from citevision_ai.evidence.buffer import FrameRingBuffer
from citevision_ai.evidence.capture import bbox_from_event, encode_scene_jpeg, encode_subject_jpeg
from citevision_ai.evidence.config import CLIP_DURATION_SEC, EVIDENCE_WORTHY_TYPES, JPEG_QUALITY, RING_FPS, RING_SECONDS
from citevision_ai.evidence.uploader import EvidenceUploader

logger = logging.getLogger(__name__)


class EvidenceCaptureService:
    def __init__(self) -> None:
        self._buffers: dict[str, FrameRingBuffer] = {}
        self._uploader = EvidenceUploader()

    def push_frame(self, camera_id: str, frame: np.ndarray) -> None:
        buf = self._buffers.get(camera_id)
        if buf is None:
            buf = FrameRingBuffer(max_seconds=RING_SECONDS, fps=RING_FPS, jpeg_quality=JPEG_QUALITY)
            self._buffers[camera_id] = buf
        buf.maybe_push(frame)

    def is_worthy(self, event_type: str | None) -> bool:
        return bool(event_type and event_type in EVIDENCE_WORTHY_TYPES)

    def attach_evidence(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        frame: np.ndarray,
    ) -> None:
        et = evt.get("event_type") or evt.get("event")
        if not self.is_worthy(str(et) if et else None):
            return
        event_id = str(evt.get("event_id", ""))
        bbox = bbox_from_event(evt)
        scene = encode_scene_jpeg(frame, JPEG_QUALITY)
        subject = encode_subject_jpeg(frame, bbox, JPEG_QUALITY)
        buf = self._buffers.get(camera_id)
        clip = buf.export_clip_mp4(CLIP_DURATION_SEC, RING_FPS) if buf else None
        meta = {
            "bbox": bbox,
            "confidence": evt.get("confidence"),
            "class_name": evt.get("class_name"),
            "zone_id": evt.get("zone_id"),
            "track_id": evt.get("track_id"),
            "event_type": et,
        }
        uploaded = self._uploader.upload(org_id, camera_id, event_id, scene, subject, clip, meta)
        if uploaded:
            evt["evidence"] = uploaded
            if pkg := uploaded.get("package"):
                evt["package"] = pkg

    def clear_camera(self, camera_id: str) -> None:
        self._buffers.pop(camera_id, None)
