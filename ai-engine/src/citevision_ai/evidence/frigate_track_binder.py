"""Proactive IA track → Frigate event binding (clip/snapshot/bbox Frigate)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from citevision_ai.config import settings
from citevision_ai.evidence.capture import bbox_valid, normalize_bbox

logger = logging.getLogger(__name__)

_VEHICLE_CLASSES = frozenset({"car", "truck", "bus", "motorcycle", "motorbike", "van", "vehicle"})


@dataclass
class FrigateTrackBinding:
    frigate_event_id: str
    align_delta: float
    iou: float
    bound_at: float


class FrigateTrackBinder:
    """Maintain live (camera, track_id) → Frigate event reservations via IoU."""

    def __init__(self, track_engine: Any) -> None:
        self._track = track_engine
        self._bindings: dict[tuple[str, int], FrigateTrackBinding] = {}
        self._frame_counter = 0

    def clear_camera(self, camera_id: str) -> None:
        if not camera_id:
            return
        drop = [k for k in self._bindings if k[0] == camera_id]
        for k in drop:
            del self._bindings[k]

    def clear_all(self) -> None:
        self._bindings.clear()

    def get(self, camera_id: str, track_id: int) -> FrigateTrackBinding | None:
        return self._bindings.get((camera_id, int(track_id)))

    def inject_event(self, camera_id: str, evt: dict[str, Any]) -> None:
        """Attach reserved Frigate event id to a violation before capture."""
        if evt.get("frigate_event_id"):
            return
        tid = evt.get("track_id")
        if tid is None:
            return
        try:
            track_id = int(tid)
        except (TypeError, ValueError):
            return
        if track_id < 0:
            return
        binding = self.get(camera_id, track_id)
        if not binding:
            return
        evt["frigate_event_id"] = binding.frigate_event_id
        meta = evt.setdefault("metadata", {})
        if isinstance(meta, dict):
            meta["frigate_event_id"] = binding.frigate_event_id
            meta["frigate_bind_iou"] = round(binding.iou, 3)
            meta["frigate_bind_delta_sec"] = round(binding.align_delta, 3)

    def update_tracks(
        self,
        camera_id: str,
        tracks: list[dict[str, Any]],
        *,
        frame_w: int,
        frame_h: int,
        wall_ts: float,
    ) -> None:
        if not settings.frigate_track_binding_enabled or not self._track.enabled():
            return
        every = max(1, int(settings.frigate_bind_every_n_frames))
        self._frame_counter += 1
        if (self._frame_counter - 1) % every != 0:
            return

        fid = self._track.frigate_camera_id(camera_id)
        events = self._track.list_events_for_camera(fid)
        if not events:
            return

        min_iou = float(settings.frigate_bind_min_iou)
        for track in tracks:
            cls = str(track.get("class_name") or "").lower()
            if cls and cls not in _VEHICLE_CLASSES:
                continue
            tid = track.get("track_id")
            if tid is None:
                continue
            try:
                track_id = int(tid)
            except (TypeError, ValueError):
                continue
            if track_id < 0:
                continue
            raw = track.get("bbox") or {}
            norm = normalize_bbox(raw, frame_w, frame_h)
            if not norm or not bbox_valid(norm, min_frac=0.02):
                continue
            matched, delta, iou = self._track.match_track_to_event(
                events,
                anchor_ts=wall_ts,
                class_name=cls,
                evt_bbox=norm,
                camera_id=camera_id,
                frame_w=frame_w,
                frame_h=frame_h,
            )
            if not matched:
                continue
            event_id = str(matched.get("id") or "")
            if not event_id or iou < min_iou:
                continue
            self._bindings[(camera_id, track_id)] = FrigateTrackBinding(
                frigate_event_id=event_id,
                align_delta=delta,
                iou=iou,
                bound_at=time.time(),
            )
            logger.debug(
                "frigate_bind cam=%s track=%s event=%s iou=%.2f delta=%.2fs",
                camera_id[:8], track_id, event_id[:20], iou, delta,
            )
