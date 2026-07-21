"""Frigate-track evidence composition (ported from SingleTrackWorker)."""
from __future__ import annotations

import http.client
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import cv2
import numpy as np

from citevision_ai.config import settings
from citevision_ai.evidence import abort_stats
from citevision_ai.evidence.capture import (
    bbox_from_event,
    bbox_rear_plate_region,
    bbox_region_has_content,
    bbox_valid,
    capture_images_from_policy,
    encode_subject_jpeg,
    normalize_bbox,
    subject_jpeg_texture,
)
from citevision_ai.road_enforcement.traffic_light import (
    _polygon_pixel_bbox,
    classify_light_color,
)
from citevision_ai.evidence.config import CLIP_DURATION_SEC, JPEG_QUALITY
from citevision_ai.evidence.frigate_timeline import (
    _STREAM_CLOCK_MAX,
    aligned_anchor,
    best_frigate_ts,
    demo_loop_absolute_align_ok,
    frigate_times_look_stream_relative,
    learn_clock_offset,
    min_time_delta,
    same_demo_loop_cycle,
    wall_clock_skewed_from_frigate,
)
from citevision_ai.evidence.gate import default_evidence_policy
from citevision_ai.evidence.ocr_client import recognize_plate_jpeg

logger = logging.getLogger(__name__)

SUBJECT_MIN_TEXTURE = 50.0
# Red-light evidence must stay close to the IA emission instant — wide demo skew
# produces scenes where the lamp has already turned green.
RED_LIGHT_MAX_ALIGN_SEC = 8.0
RED_LIGHT_MIN_IOU = 0.08
# Sprint 1 — deferred compose: wait for Frigate end_time before clip API (I4).
RED_LIGHT_END_TIME_WAIT_SEC = 30.0
RED_LIGHT_END_TIME_BACKOFF_INITIAL = 2.0
RED_LIGHT_END_TIME_BACKOFF_MAX = 8.0
_VEHICLE_LABELS = frozenset({
    "car", "motorcycle", "motorbike", "truck", "bus", "vehicle", "van",
})


def _frigate_box_to_norm(box: list[float] | tuple[float, ...]) -> dict[str, float] | None:
    if not box or len(box) < 4:
        return None
    x, y, w, h = float(box[0]), float(box[1]), float(box[2]), float(box[3])
    bb = {"x": x, "y": y, "width": w, "height": h}
    return bb if bbox_valid(bb, min_frac=0.02) else None


def _frigate_box_from_event(ev: dict[str, Any]) -> dict[str, float] | None:
    """Latest normalized bbox from a Frigate event (prefers data.box)."""
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    box = data.get("box")
    if isinstance(box, (list, tuple)):
        return _frigate_box_to_norm(box)
    return None


def _bbox_iou(a: dict[str, float] | None, b: dict[str, float] | None) -> float:
    if not a or not b:
        return 0.0
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / max(union, 1e-9)


class FrigateTrackEvidence:
    """Build evidence from a single correlated Frigate event (clip + snapshot + OCR)."""

    def __init__(self) -> None:
        self._base = settings.frigate_url.rstrip("/")
        self._demo_clock_offset: dict[str, float] = {}

    def reset_demo_offset(self, camera_id: str) -> None:
        """Drop learned IA↔Frigate skew after demo video switch or failed correlate."""
        if camera_id:
            self._demo_clock_offset.pop(camera_id, None)

    def _demo_loop_guard_active(self) -> bool:
        """Demo-only stale-loop guard (H1). Off for live production cameras.

        Uses strict ``is True`` checks so unit-test MagicMocks do not accidentally
        activate the guard (MagicMock is truthy).
        """
        if getattr(settings, "demo_loop_guard", True) is False:
            return False
        if getattr(settings, "demo_mode", False) is True:
            return True
        fn = getattr(settings, "demo_relaxed_evidence", None)
        if callable(fn):
            try:
                return fn() is True
            except Exception:
                return False
        return False

    def _hard_align_max_sec(self, event_type: str = "") -> float:
        accept_max = float(settings.frigate_demo_accept_max_align_sec)
        if str(event_type or "") == "red_light_violation":
            accept_max = min(accept_max, RED_LIGHT_MAX_ALIGN_SEC)
        return accept_max

    def _demo_loop_pair_ok(
        self,
        anchor: float,
        matched: dict[str, Any] | None,
        align_delta: float,
        event_type: str = "",
    ) -> bool:
        """Absolute align + same loop cycle — never widened by soft-accept."""
        if not self._demo_loop_guard_active():
            return True
        max_sec = self._hard_align_max_sec(event_type)
        if not demo_loop_absolute_align_ok(align_delta, max_sec):
            return False
        frig_ts = best_frigate_ts(matched or {})
        if frig_ts is None:
            return True
        loop_sec = float(getattr(settings, "demo_red_light_loop_sec", 352.52) or 352.52)
        return same_demo_loop_cycle(float(anchor), float(frig_ts), loop_sec)

    def enabled(self) -> bool:
        return settings.frigate_enabled and settings.frigate_evidence

    def frigate_camera_id(self, camera_id: str) -> str:
        return f"cv_{camera_id}"

    def _missing(
        self,
        reason: str,
        *,
        camera_id: str,
        evt: dict[str, Any],
        event_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Structured missing package — never fabricate proof assets (Décision 2 / R.2)."""
        et = str(evt.get("event_type") or evt.get("event") or "")
        abort_stats.record_abort(
            reason,
            camera_id=camera_id,
            event_type=et,
            event_id=event_id,
            extra=extra,
        )
        meta: dict[str, Any] = {
            "evidence_status": "missing",
            "abort_reason": reason,
            "capture_source": "frigate_track",
            "event_type": et,
            "frigate_event_id": event_id or None,
            "bbox_ts": evt.get("bbox_ts"),
            "track_id": evt.get("track_id"),
            "zone_id": evt.get("zone_id"),
        }
        if extra:
            meta.update({k: v for k, v in extra.items() if k not in meta})
        return {
            "status": "missing",
            "scene": None,
            "subject": None,
            "clip_bytes": None,
            "plate_jpeg": None,
            "extra_images": [],
            "meta": meta,
        }

    def _wait_until_end_time(self, event_id: str) -> dict[str, Any] | None:
        """Poll Frigate until event has end_time (clip seal signal) or timeout.

        Sprint 1: never call clip.mp4 before end_time — eliminates I4 HTTP 400 thrash.
        Exponential backoff 2s → 4s → 8s (capped).
        """
        wait_sec = float(
            getattr(settings, "frigate_red_light_end_time_wait_sec", RED_LIGHT_END_TIME_WAIT_SEC)
        )
        backoff = float(
            getattr(
                settings,
                "frigate_red_light_end_time_backoff_initial",
                RED_LIGHT_END_TIME_BACKOFF_INITIAL,
            )
        )
        backoff_max = float(
            getattr(
                settings,
                "frigate_red_light_end_time_backoff_max",
                RED_LIGHT_END_TIME_BACKOFF_MAX,
            )
        )
        deadline = time.time() + max(1.0, wait_sec)
        last: dict[str, Any] = {}
        while time.time() < deadline:
            meta = self._event_meta(event_id)
            if meta:
                last = meta
                end = meta.get("end_time")
                if end is not None and end != "" and end is not False:
                    logger.info(
                        "frigate_track: end_time ready event=%s end=%s",
                        event_id[:24], end,
                    )
                    return meta
            time.sleep(backoff)
            backoff = min(backoff * 2.0, backoff_max)
        return last if last else None

    def list_events_for_camera(self, frigate_id: str) -> list[dict[str, Any]]:
        return self._list_events(frigate_id)

    def match_track_to_event(
        self,
        events: list[dict[str, Any]],
        *,
        anchor_ts: float,
        class_name: str,
        evt_bbox: dict[str, float],
        camera_id: str,
        frame_w: int = 1920,
        frame_h: int = 720,
    ) -> tuple[dict[str, Any] | None, float, float]:
        """IoU-first match for proactive track binding (ignores large time skew)."""
        if not events:
            return None, 1e18, 0.0
        want = str(class_name or "").lower()
        min_iou = max(0.05, float(settings.frigate_bind_min_iou) * 0.5)
        matched, delta = self._pick_correlated(
            events[: int(settings.frigate_demo_events_limit)],
            float(anchor_ts),
            want,
            evt_bbox,
            float(settings.frigate_demo_bootstrap_max_sec),
            label_iou_only=True,
            min_iou=min_iou,
            ignore_time_filter=True,
        )
        if matched is None:
            return None, delta, 0.0
        frigate_bbox = _frigate_box_from_event(matched)
        norm_evt = normalize_bbox(evt_bbox, frame_w, frame_h)
        iou = _bbox_iou(norm_evt, frigate_bbox) if norm_evt and frigate_bbox else 0.0
        if matched is not None:
            self._maybe_learn_offset(camera_id, float(anchor_ts), matched)
        return matched, delta, iou

    def fetch_event(self, event_id: str) -> dict[str, Any]:
        meta = self._event_meta(event_id)
        return meta if meta else {"id": event_id}

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
        et = str(evt.get("event_type") or evt.get("event") or "")
        abort_stats.record_attempt(camera_id=camera_id, event_type=et)
        result = self._capture_impl(policy, evt, org_id=org_id, camera_id=camera_id)
        if result is None:
            # Terminal failure without structured _missing (non-red paths historically).
            abort_stats.record_abort(
                abort_stats.ABORT_NO_CORRELATION,
                camera_id=camera_id,
                event_type=et,
                extra={"via": "capture_return_none"},
            )
            return None
        meta = result.get("meta") if isinstance(result, dict) else None
        status = result.get("status") if isinstance(result, dict) else None
        if status == "missing" or (
            isinstance(meta, dict) and meta.get("evidence_status") == "missing"
        ):
            # Terminal abort already recorded in _missing.
            return result
        abort_stats.record_complete(
            camera_id=camera_id,
            event_type=et,
            event_id=str(
                (meta or {}).get("frigate_event_id")
                or evt.get("frigate_event_id")
                or evt.get("event_id")
                or ""
            ),
        )
        return result

    def _capture_impl(
        self,
        policy: dict[str, Any],
        evt: dict[str, Any],
        *,
        org_id: str,
        camera_id: str,
    ) -> dict[str, Any] | None:
        fid = self.frigate_camera_id(camera_id)
        anchor = evt.get("bbox_ts")
        if not isinstance(anchor, (int, float)):
            anchor = time.time()
        anchor = float(anchor)

        bound_id = str(evt.get("frigate_event_id") or "").strip()
        # Never trust a proactive binder id for red_light / speeding — it often freezes
        # an early track box while the car has already moved (empty subject on snapshot).
        event_type0 = str(evt.get("event_type") or "")
        if bound_id and event_type0 in ("red_light_violation", "speeding"):
            logger.info(
                "frigate_track: ignore stale bind for %s cam=%s id=%s — re-correlate",
                event_type0, camera_id[:8], bound_id[:24],
            )
            bound_id = ""
            evt.pop("frigate_event_id", None)
            meta = evt.get("metadata")
            if isinstance(meta, dict):
                meta.pop("frigate_event_id", None)
                meta.pop("frigate_bind_iou", None)
        if bound_id:
            bound_ev = self.fetch_event(bound_id)
            align_delta = min_time_delta(anchor, bound_ev) if bound_ev else 0.0
            if self._accept_correlation(evt, bound_ev, align_delta, camera_id):
                composed = self._compose_from_matched(
                    bound_ev, align_delta, policy, evt, camera_id, org_id,
                )
                if composed is not None:
                    logger.info(
                        "frigate_track: bound capture cam=%s event=%s delta=%.2fs",
                        camera_id[:8], bound_id[:24], align_delta,
                    )
                    return composed
            logger.info(
                "frigate_track: bound event rejected cam=%s id=%s — retry correlate",
                camera_id[:8], bound_id[:24],
            )

        matched, align_delta = None, 1e18
        deadline = time.time() + settings.frigate_correlate_wait_sec
        poll = max(0.2, settings.frigate_event_media_poll_sec)
        max_align = float(settings.frigate_demo_max_align_sec)
        self._wait_for_live_frigate(fid, anchor, max_align, min(15.0, settings.frigate_correlate_wait_sec * 0.5))
        while True:
            matched, align_delta = self._correlate_event(
                fid, anchor, evt, camera_id=camera_id,
            )
            soft_meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
            soft_red = soft_meta.get("frigate_red_light_soft_iou") is not None
            # demo_loop_guard: soft-accept may relax IoU only — never the align window.
            if matched is not None and align_delta <= max_align:
                if self._accept_correlation(evt, matched, align_delta, camera_id):
                    break
                matched = None
            elif matched is not None:
                logger.warning(
                    "frigate_track: reject stale match cam=%s anchor=%.3f delta=%.2fs max=%.1fs soft_red=%s",
                    camera_id[:8], anchor, align_delta, max_align, soft_red,
                )
                abort_stats.record_probe_reject(
                    abort_stats.ABORT_STALE_MATCH,
                    camera_id=camera_id,
                    event_type=str(evt.get("event_type") or ""),
                    extra={"align_delta_sec": round(float(align_delta), 3)},
                )
                matched = None
            if time.time() >= deadline:
                break
            time.sleep(poll)

        if not matched:
            if camera_id in self._demo_clock_offset:
                logger.info(
                    "frigate_track: reset demo offset cam=%s after failed correlate",
                    camera_id[:8],
                )
                self.reset_demo_offset(camera_id)
            fallback = self._demo_latest_vehicle_event(fid)
            if fallback is None:
                # Frigate may still be spinning up after restart — brief wait for any vehicle.
                for _ in range(8):
                    time.sleep(1.0)
                    fallback = self._demo_latest_vehicle_event(fid)
                    if fallback is not None:
                        break
            if fallback is not None:
                # Demo: allow identity-agnostic Frigate media for road rules when
                # compose overlays the IA offender bbox (soft IoU / scene gates).
                et = str(evt.get("event_type") or "")
                if et in ("red_light_violation", "speeding"):
                    if not settings.demo_relaxed_evidence():
                        logger.warning(
                            "frigate_track: skip demo vehicle fallback for %s cam=%s "
                            "(DEMO_MODE=%s source=%s)",
                            et, camera_id[:8], settings.demo_mode, settings.demo_mode_source,
                        )
                        fallback = None
                    else:
                        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else None
                        if meta is None:
                            evt["metadata"] = {}
                            meta = evt["metadata"]
                        if et == "red_light_violation":
                            meta["frigate_red_light_soft_iou"] = -1.0
                        else:
                            meta["frigate_speed_soft_iou"] = -1.0
                        logger.warning(
                            "frigate_track: %s demo vehicle fallback cam=%s "
                            "(IA bbox on Frigate media) DEMO_MODE=%s source=%s",
                            et, camera_id[:8], settings.demo_mode, settings.demo_mode_source,
                        )
            if fallback is not None:
                matched = fallback
                align_delta = min_time_delta(anchor, fallback)
                # demo_loop_guard: never compose time-agnostic media with a wide delta
                # (speeding previously reused one Frigate event across ~720s).
                if not self._demo_loop_pair_ok(
                    anchor, matched, align_delta, str(evt.get("event_type") or ""),
                ):
                    logger.warning(
                        "frigate_track: demo_loop_guard reject fallback cam=%s event=%s delta=%.1fs",
                        camera_id[:8], str(fallback.get("id", ""))[:24], align_delta,
                    )
                    abort_stats.record_probe_reject(
                        abort_stats.ABORT_ALIGN_REJECT,
                        camera_id=camera_id,
                        event_type=str(evt.get("event_type") or ""),
                        extra={
                            "align_delta_sec": round(float(align_delta), 3),
                            "via": "demo_loop_guard_fallback",
                        },
                    )
                    matched = None
                else:
                    logger.warning(
                        "frigate_track: demo vehicle fallback cam=%s event=%s delta=%.1fs",
                        camera_id[:8], str(fallback.get("id", ""))[:24], align_delta,
                    )
            if matched is None:
                logger.warning(
                    "frigate_track: no correlated event cam=%s anchor=%.3f offset=%s",
                    camera_id[:8], anchor,
                    round(self._demo_clock_offset.get(camera_id, 0.0), 2)
                    if camera_id in self._demo_clock_offset else "none",
                )
                if str(evt.get("event_type") or "") == "red_light_violation":
                    return self._missing(
                        abort_stats.ABORT_NO_CORRELATION,
                        camera_id=camera_id,
                        evt=evt,
                        extra={"anchor_ts": anchor},
                    )
                return None
        event_id = str(matched.get("id") or "")
        if not event_id:
            if str(evt.get("event_type") or "") == "red_light_violation":
                return self._missing(
                    abort_stats.ABORT_NO_CORRELATION,
                    camera_id=camera_id,
                    evt=evt,
                )
            return None
        return self._compose_from_matched(matched, align_delta, policy, evt, camera_id, org_id)

    def _demo_latest_vehicle_event(self, frigate_id: str) -> dict[str, Any] | None:
        """Demo go2rtc: pick newest Frigate vehicle event with a bbox (time-agnostic)."""
        best_clip: dict[str, Any] | None = None
        for ev in self._list_events(frigate_id):
            label = str(ev.get("label") or "").lower()
            if label and label not in _VEHICLE_LABELS:
                continue
            if _frigate_box_from_event(ev) is not None:
                return ev
            # Tiny boxes fail min_frac — still usable if Frigate retained a clip.
            if best_clip is None and ev.get("has_clip"):
                best_clip = ev
        return best_clip

    def _compose_from_matched(
        self,
        matched: dict[str, Any],
        align_delta: float,
        policy: dict[str, Any],
        evt: dict[str, Any],
        camera_id: str,
        org_id: str,
    ) -> dict[str, Any] | None:
        event_id = str(matched.get("id") or "")
        if not event_id:
            return None

        event_type = str(evt.get("event_type") or "")
        is_red = event_type == "red_light_violation"
        is_speed = event_type == "speeding"
        require_subject = is_red or is_speed
        hard_max = self._hard_align_max_sec(event_type)
        anchor = evt.get("bbox_ts")
        if not isinstance(anchor, (int, float)):
            anchor = time.time()
        # §3.1 demo_loop_guard — absolute align for every demo rule (not only red_light).
        # Soft-accept must never widen this window. Live cameras skip this block.
        if self._demo_loop_guard_active() and (
            float(align_delta) > hard_max
            or not self._demo_loop_pair_ok(float(anchor), matched, float(align_delta), event_type)
        ):
            return self._missing(
                abort_stats.ABORT_ALIGN_TOO_WIDE,
                camera_id=camera_id,
                evt=evt,
                event_id=event_id,
                extra={
                    "align_delta_sec": round(float(align_delta), 3),
                    "max_align_sec": hard_max,
                    "via": "demo_loop_guard_compose",
                },
            )

        if is_red and float(align_delta) > RED_LIGHT_MAX_ALIGN_SEC:
            return self._missing(
                abort_stats.ABORT_ALIGN_TOO_WIDE,
                camera_id=camera_id,
                evt=evt,
                event_id=event_id,
                extra={
                    "align_delta_sec": round(float(align_delta), 3),
                    "max_align_sec": RED_LIGHT_MAX_ALIGN_SEC,
                },
            )

        fresh = self._event_meta(event_id)
        if fresh:
            matched = {
                **matched,
                **{k: fresh.get(k) for k in ("data", "start_time", "end_time", "frame_time", "label") if k in fresh},
            }

        anchor = evt.get("bbox_ts")
        if not isinstance(anchor, (int, float)):
            anchor = time.time()
        anchor = float(anchor)
        fid = self.frigate_camera_id(camera_id)

        # Sprint 1 — deferred: wait for end_time before any clip download (red_light).
        if is_red:
            sealed = self._wait_until_end_time(event_id)
            if not sealed or sealed.get("end_time") in (None, "", False):
                return self._missing(
                    abort_stats.ABORT_CLIP_NOT_READY_TIMEOUT,
                    camera_id=camera_id,
                    evt=evt,
                    event_id=event_id,
                    extra={"waited_sec": RED_LIGHT_END_TIME_WAIT_SEC},
                )
            matched = {
                **matched,
                **{k: sealed.get(k) for k in ("data", "start_time", "end_time", "frame_time", "label", "has_clip", "has_snapshot") if k in sealed},
            }
            meta = sealed
        else:
            meta = self._wait_for_event_media(event_id)

        clip_bytes = self._download_event_clip(event_id, meta)
        if is_red and not clip_bytes:
            return self._missing(
                abort_stats.ABORT_NO_CLIP,
                camera_id=camera_id,
                evt=evt,
                event_id=event_id,
            )

        target_clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
        if clip_bytes and target_clip_sec > 0:
            clip_bytes = self._trim_clip_bytes(clip_bytes, target_clip_sec)

        # Sprint 1 — red_light: clip red-frame is PRIMARY scene strategy (not fallback).
        scene_bytes = None
        subject_bytes = None
        ocr_frames: list[bytes] = []
        norm_bbox = None
        plate_crop = None
        clean_bytes = None
        scene_light = None
        frigate_bbox_embedded = False
        bbox_quality_ok = False

        if is_red and clip_bytes:
            red_scene = self._red_frame_jpeg_from_clip(clip_bytes, evt)
            if red_scene is not None:
                scene_bytes = red_scene
                scene_light = "red"
                logger.info(
                    "frigate_track: red_light scene from clip (primary) cam=%s event=%s delta=%.2fs",
                    camera_id[:8], event_id[:24], align_delta,
                )
            # Still build subject/plate from Frigate assets + clip frames.
            _sc, subject_bytes, ocr_frames, norm_bbox, plate_crop, clean_bytes = (
                self._build_images(event_id, matched, policy, clip_bytes)
            )
            if scene_bytes is None:
                scene_bytes = _sc
            scene_bytes, norm_bbox, frigate_bbox_embedded, bbox_quality_ok, subject_bytes = (
                self._finalize_scene_bbox(
                    scene_bytes,
                    clean_bytes,
                    norm_bbox,
                    evt,
                    subject_bytes,
                    policy,
                    camera_id,
                    event_id,
                    align_delta,
                )
            )
            if scene_light is None and scene_bytes is not None:
                scene_light = self._scene_light_state(scene_bytes, evt)
            if scene_light and scene_light != "red":
                # Last attempt: scan clip again (trim may have changed window).
                red_retry = self._red_frame_jpeg_from_clip(clip_bytes, evt)
                if red_retry is not None:
                    scene_bytes = red_retry
                    scene_light = "red"
                else:
                    return self._missing(
                        abort_stats.ABORT_SCENE_GREEN,
                        camera_id=camera_id,
                        evt=evt,
                        event_id=event_id,
                        extra={
                            "scene_light_state": scene_light,
                            "align_delta_sec": round(float(align_delta), 3),
                        },
                    )
        else:
            scene_bytes, subject_bytes, ocr_frames, norm_bbox, plate_crop, clean_bytes = (
                self._build_images(event_id, matched, policy, clip_bytes)
            )
            scene_bytes, norm_bbox, frigate_bbox_embedded, bbox_quality_ok, subject_bytes = (
                self._finalize_scene_bbox(
                    scene_bytes,
                    clean_bytes,
                    norm_bbox,
                    evt,
                    subject_bytes,
                    policy,
                    camera_id,
                    event_id,
                    align_delta,
                )
            )

        if scene_bytes is None:
            if is_red:
                return self._missing(
                    abort_stats.ABORT_NO_SCENE,
                    camera_id=camera_id,
                    evt=evt,
                    event_id=event_id,
                )
            logger.warning(
                "frigate_track: compose aborted — no scene cam=%s event=%s",
                camera_id[:8], event_id[:24],
            )
            return None

        if is_red and scene_light is None:
            scene_light = self._scene_light_state(scene_bytes, evt)

        subject_texture = subject_jpeg_texture(subject_bytes)
        subject_quality_ok = (
            subject_bytes is not None
            and subject_texture is not None
            and subject_texture >= SUBJECT_MIN_TEXTURE
        )
        if subject_bytes is not None and not subject_quality_ok:
            bbox_quality_ok = False

        # Fail-closed for red_light + speeding: empty / lagged subject must not ship as "proof".
        if require_subject:
            if not bbox_quality_ok or not subject_quality_ok:
                return self._missing(
                    abort_stats.ABORT_SUBJECT_EMPTY,
                    camera_id=camera_id,
                    evt=evt,
                    event_id=event_id,
                    extra={
                        "bbox_ok": bbox_quality_ok,
                        "subject_ok": subject_quality_ok,
                        "texture": subject_texture,
                    },
                )

        plate_jpeg, plate_number, plate_confidence = self._ocr_plate(plate_crop, evt)
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        want_plate = any(s.get("role") == "plate" for s in images_spec)
        # Sprint 4 / A.4 / R.2: never fabricate a plate from the subject crop.
        missing_roles: list[str] = []
        if want_plate and not plate_jpeg:
            missing_roles.append("plate")

        clip_duration = target_clip_sec if clip_bytes else 0.0
        complete = bool(scene_bytes and subject_bytes and clip_bytes and bbox_quality_ok)
        if want_plate and not plate_jpeg:
            complete = False
        status = "complete" if complete else "partial"

        ia_bbox = bbox_from_event(evt)
        bbox_source = "frigate_mqtt" if frigate_bbox_embedded else "emission_track"
        meta_out = {
                "bbox": norm_bbox,
                "bbox_ts": anchor,
                "bbox_source": bbox_source,
                "bbox_quality_ok": bbox_quality_ok,
                "frigate_bbox_embedded": frigate_bbox_embedded,
                "subject_texture": round(subject_texture, 1) if subject_texture is not None else None,
                "subject_quality_ok": subject_quality_ok,
                "capture_source": "frigate_track",
                "frigate_camera_id": fid,
                "frigate_event_id": event_id,
                "align_delta_ms": int(round(align_delta * 1000)),
                "plate_ocr_source": settings.ocr_url and "fast_alpr" or "none",
                "confidence": evt.get("confidence"),
                "class_name": evt.get("class_name"),
                "zone_id": evt.get("zone_id"),
                "track_id": evt.get("track_id"),
                "event_type": evt.get("event_type") or evt.get("event"),
                "clip_duration_sec": clip_duration,
                "plate_number": plate_number or evt.get("plate_number"),
                "plate_confidence": plate_confidence if plate_confidence else evt.get("plate_confidence"),
                "missing_roles": missing_roles,
                "evidence_status": status,
            }
        if want_plate and not plate_jpeg:
            meta_out["plate_status"] = "missing"
        if scene_light is not None:
            meta_out["scene_light_state"] = scene_light
        if ia_bbox and norm_bbox:
            meta_out["ia_bbox"] = ia_bbox

        if evt.get("frigate_event_id") and not frigate_bbox_embedded:
            logger.warning(
                "frigate_track: bound capture missing frigate bbox cam=%s event=%s — IA fallback",
                camera_id[:8], event_id[:24],
            )
            if ia_bbox and norm_bbox:
                # Keep real source label (do not pretend frigate_mqtt when box is IA).
                meta_out["bbox_source"] = "ia_overlay"
                frigate_bbox_embedded = True
            else:
                return None

        return {
            "scene": scene_bytes,
            "subject": subject_bytes,
            "clip_bytes": clip_bytes,
            "plate_jpeg": plate_jpeg,
            "extra_images": [],
            "meta": meta_out,
            "status": status,
        }

    @staticmethod
    def _scene_light_state(scene_bytes: bytes, evt: dict[str, Any]) -> str | None:
        """Classify traffic-light colour on an image via the IA light-zone polygon.

        Returns None when the ROI is missing / undecodable (caller may still ship).
        """
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        poly = meta.get("light_zone_polygon") or []
        if not isinstance(poly, list) or len(poly) < 3:
            return None
        try:
            arr = np.frombuffer(scene_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            return None
        if frame is None or frame.size == 0:
            return None
        return FrigateTrackEvidence._frame_light_state(frame, poly)

    @staticmethod
    def _frame_light_state(frame: np.ndarray, poly: list) -> str | None:
        h, w = frame.shape[:2]
        box = _polygon_pixel_bbox(poly, w, h)
        if not box:
            return None
        x1, y1, x2, y2 = box
        state, _ = classify_light_color(frame[y1:y2, x1:x2])
        return state

    @staticmethod
    def _red_frame_jpeg_from_clip(clip_bytes: bytes | None, evt: dict[str, Any]) -> bytes | None:
        """Return a JPEG scene from the clip where the lamp ROI classifies as red."""
        if not clip_bytes:
            return None
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        poly = meta.get("light_zone_polygon") or []
        if not isinstance(poly, list) or len(poly) < 3:
            return None
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(clip_bytes)
                tmp_path = tmp.name
            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                return None
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 10.0)
            step = max(1, int(round(fps * 0.4)))  # ~every 0.4s
            idx = 0
            best: bytes | None = None
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if idx % step == 0:
                    if FrigateTrackEvidence._frame_light_state(frame, poly) == "red":
                        ok_enc, buf = cv2.imencode(
                            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
                        )
                        if ok_enc:
                            best = buf.tobytes()
                            break
                idx += 1
            cap.release()
            return best
        except Exception:
            return None
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _events_within(
        self,
        anchor_ts: float,
        events: list[dict[str, Any]],
        max_sec: float,
    ) -> list[dict[str, Any]]:
        cap = float(max_sec)
        if cap <= 0:
            return list(events)
        return [ev for ev in events if min_time_delta(anchor_ts, ev) <= cap]

    def _is_wall_clock_frigate_time(self, ts: float) -> bool:
        return float(ts) >= _STREAM_CLOCK_MAX

    def _event_is_live_for_anchor(
        self,
        ev: dict[str, Any],
        anchor_ts: float,
        max_sec: float,
    ) -> bool:
        """Wall-clock Frigate: keep events near anchor or recently emitted."""
        now = time.time()
        for key in ("start_time", "frame_time"):
            st = ev.get(key)
            if not isinstance(st, (int, float)):
                continue
            st = float(st)
            if not self._is_wall_clock_frigate_time(st):
                return True
            if min_time_delta(anchor_ts, ev) <= max_sec:
                return True
            if (now - st) <= max_sec:
                return True
        return False

    def _live_events_for_anchor(
        self,
        events: list[dict[str, Any]],
        anchor_ts: float,
        max_sec: float,
    ) -> list[dict[str, Any]]:
        if frigate_times_look_stream_relative(events):
            return list(events)
        live = [ev for ev in events if self._event_is_live_for_anchor(ev, anchor_ts, max_sec)]
        return live

    def _wait_for_live_frigate(
        self,
        frigate_id: str,
        anchor_ts: float,
        max_sec: float,
        timeout_sec: float,
    ) -> None:
        """Poll until Frigate emits an event within the correlate window (demo go2rtc)."""
        if timeout_sec <= 0:
            return
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            events = self._list_events(frigate_id)
            if self._live_events_for_anchor(events, anchor_ts, max_sec):
                return
            time.sleep(max(0.3, settings.frigate_event_media_poll_sec))
        logger.info(
            "frigate_track: no live events yet cam=%s (waited %.0fs)",
            frigate_id[:16], timeout_sec,
        )

    def _correlate_event(
        self,
        frigate_id: str,
        anchor_ts: float,
        evt: dict[str, Any],
        *,
        camera_id: str = "",
    ) -> tuple[dict[str, Any] | None, float]:
        events = self._list_events(frigate_id)
        if not events:
            return None, 1e18
        max_align = float(settings.frigate_demo_max_align_sec)
        all_events = events
        events = self._live_events_for_anchor(all_events, anchor_ts, max_align)

        want = str(evt.get("class_name") or "").lower()
        evt_bbox = bbox_from_event(evt)

        # Pass 1: strict wall-clock match (live RTSP).
        # Red-light: prefer IoU among time-matched vehicles so we do not lock onto
        # a different lane's car that happens to share the wall clock.
        is_red = str(evt.get("event_type") or "") == "red_light_violation"
        if events:
            matched, delta = self._pick_correlated(
                events,
                anchor_ts,
                want,
                evt_bbox,
                settings.frigate_event_match_sec,
                iou_first=is_red,
                min_iou=(max(0.02, float(settings.frigate_demo_min_bbox_iou) * 0.25) if is_red else 0.0),
            )
            if matched is not None:
                self._maybe_learn_offset(camera_id, anchor_ts, matched)
                return matched, delta
            if is_red:
                # Fallback: time-only within window (soft-accept may overlay IA bbox).
                matched, delta = self._pick_correlated(
                    events, anchor_ts, want, evt_bbox, settings.frigate_event_match_sec,
                )
                if matched is not None:
                    self._maybe_learn_offset(camera_id, anchor_ts, matched)
                    return matched, delta

        if not settings.frigate_demo_timeline_align:
            return None, 1e18

        bootstrap_sec = min(float(settings.frigate_demo_bootstrap_max_sec), max_align)
        loose_sec = min(float(settings.frigate_demo_loose_match_sec), max_align)
        stream_rel = frigate_times_look_stream_relative(all_events)

        # Pass 2b: bootstrap — IoU + label; time capped except true stream-relative clocks.
        min_delta = min(min_time_delta(anchor_ts, ev) for ev in all_events[:12]) if all_events else 1e18
        demo_skew = (
            stream_rel
            or wall_clock_skewed_from_frigate(anchor_ts, all_events)
            or min_delta > settings.frigate_event_match_sec
        )
        if demo_skew and camera_id not in self._demo_clock_offset:
            iou_bootstrap = stream_rel or min_delta > settings.frigate_event_match_sec
            pool = all_events[:12] if iou_bootstrap else self._events_within(anchor_ts, all_events, bootstrap_sec)
            if pool or iou_bootstrap:
                matched, delta = self._pick_correlated(
                    pool if pool else all_events[:12],
                    anchor_ts,
                    want,
                    evt_bbox,
                    bootstrap_sec,
                    label_iou_only=True,
                    min_iou=max(0.05, settings.frigate_demo_min_bbox_iou * 0.5),
                    ignore_time_filter=iou_bootstrap,
                )
                if matched is not None:
                    self._maybe_learn_offset(camera_id, anchor_ts, matched)
                    adj = aligned_anchor(self._demo_clock_offset, camera_id, anchor_ts)
                    adj_delta = min_time_delta(adj, matched)
                    if adj_delta <= max_align:
                        logger.info(
                            "frigate_track: demo bootstrap cam=%s anchor=%.3f delta=%.2fs offset=%.2f",
                            camera_id[:8] if camera_id else frigate_id[:12],
                            anchor_ts, adj_delta,
                            self._demo_clock_offset.get(camera_id, 0.0),
                        )
                        return matched, adj_delta
                    logger.info(
                        "frigate_track: bootstrap skip stale cam=%s delta=%.2fs max=%.1fs",
                        camera_id[:8] if camera_id else frigate_id[:12], adj_delta, max_align,
                    )

        # Pass 2: strict match after learned demo loop offset.
        if camera_id and camera_id in self._demo_clock_offset:
            adj = aligned_anchor(self._demo_clock_offset, camera_id, anchor_ts)
            pool = self._events_within(adj, all_events, max_align)
            matched, delta = self._pick_correlated(
                pool, adj, want, evt_bbox, max_align,
            )
            if matched is not None:
                self._maybe_learn_offset(camera_id, anchor_ts, matched)
                return matched, delta

        # Pass 3: IoU-first within tight demo window.
        adj_anchor = anchor_ts
        if camera_id and camera_id in self._demo_clock_offset:
            adj_anchor = aligned_anchor(self._demo_clock_offset, camera_id, anchor_ts)
        pool = self._events_within(adj_anchor, all_events, loose_sec)
        if pool:
            matched, delta = self._pick_correlated(
                pool,
                adj_anchor,
                want,
                evt_bbox,
                loose_sec,
                iou_first=True,
                min_iou=settings.frigate_demo_min_bbox_iou,
            )
            if matched is not None:
                self._maybe_learn_offset(camera_id, anchor_ts, matched)
                logger.info(
                    "frigate_track: demo timeline align cam=%s anchor=%.3f delta=%.2fs offset=%.2f",
                    camera_id[:8] if camera_id else frigate_id[:12],
                    anchor_ts, delta, self._demo_clock_offset.get(camera_id, 0.0),
                )
                return matched, delta

        return None, 1e18

    def _accept_correlation(
        self,
        evt: dict[str, Any],
        matched: dict[str, Any],
        align_delta: float,
        camera_id: str,
    ) -> bool:
        """Reject weak IA↔Frigate pairings before downloading media."""
        event_type = str(evt.get("event_type") or "")
        if not isinstance(matched, dict) or not (matched.get("id") or matched):
            return False

        anchor = evt.get("bbox_ts")
        if not isinstance(anchor, (int, float)):
            anchor = time.time()
        anchor = float(anchor)
        if camera_id and camera_id in self._demo_clock_offset:
            adj = aligned_anchor(self._demo_clock_offset, camera_id, anchor)
            align_delta = min_time_delta(adj, matched)
            anchor_for_loop = adj
        else:
            anchor_for_loop = anchor

        # demo_loop_guard §3.1: absolute window before any soft-accept / bound trust.
        accept_max = self._hard_align_max_sec(event_type)
        if self._demo_loop_guard_active() and not self._demo_loop_pair_ok(
            anchor_for_loop, matched, float(align_delta), event_type,
        ):
            logger.warning(
                "frigate_track: demo_loop_guard reject cam=%s delta=%.2fs max=%.1fs",
                camera_id[:8], align_delta, accept_max,
            )
            abort_stats.record_probe_reject(
                abort_stats.ABORT_ALIGN_REJECT,
                camera_id=camera_id,
                event_type=event_type,
                extra={
                    "align_delta_sec": round(float(align_delta), 3),
                    "max_align_sec": accept_max,
                    "via": "demo_loop_guard",
                },
            )
            return False

        bound_id = str(evt.get("frigate_event_id") or "").strip()
        # Bound id still must pass the hard align gate above; then trust geometry path.
        # Speeding / red_light must not short-circuit on binder alone (stale snapshot box).
        if bound_id and event_type not in ("red_light_violation", "speeding"):
            return True
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        if meta.get("frigate_bind_iou") is not None and event_type not in ("red_light_violation", "speeding"):
            try:
                if float(meta["frigate_bind_iou"]) >= float(settings.frigate_bind_min_iou):
                    frigate_bbox = _frigate_box_from_event(matched)
                    if frigate_bbox is not None:
                        return True
            except (TypeError, ValueError):
                pass

        # Non-demo / guard-off: keep classic accept_max (soft_pre must NOT widen window).
        if not self._demo_loop_guard_active():
            if float(align_delta) > accept_max:
                logger.warning(
                    "frigate_track: reject align cam=%s delta=%.2fs max=%.1fs",
                    camera_id[:8], align_delta, accept_max,
                )
                abort_stats.record_probe_reject(
                    abort_stats.ABORT_ALIGN_REJECT,
                    camera_id=camera_id,
                    event_type=event_type,
                    extra={"align_delta_sec": round(float(align_delta), 3), "max_align_sec": accept_max},
                )
                return False

        soft_pre = False
        meta0 = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        if meta0.get("frigate_red_light_soft_iou") is not None:
            soft_pre = True
        # Demo go2rtc: time-only accept for most rules (inside hard window already).
        # Red-light + speeding keep IoU gate so the snapshot still shows the offender.
        if (
            settings.demo_relaxed_evidence()
            and settings.frigate_demo_timeline_align
            and event_type not in ("red_light_violation", "speeding")
        ):
            return True
        # Soft fallback: IoU soft-accept only — align already enforced.
        if soft_pre and event_type == "red_light_violation" and settings.demo_relaxed_evidence():
            return True
        evt_bbox = bbox_from_event(evt)
        frigate_bbox = _frigate_box_from_event(matched)
        iou = 0.0
        if evt_bbox and frigate_bbox:
            fw = int(evt.get("frame_width") or evt.get("width") or 1920)
            fh = int(evt.get("frame_height") or evt.get("height") or 1080)
            norm_evt = normalize_bbox(evt_bbox, fw, fh)
            iou = _bbox_iou(norm_evt, frigate_bbox)
            min_iou = float(settings.frigate_accept_min_bbox_iou)
            if event_type == "red_light_violation":
                min_iou = max(min_iou, RED_LIGHT_MIN_IOU)
            if iou < min_iou:
                # Demo looping streams: Frigate often tracks a different car at the
                # same wall-clock. Accept time-aligned media and let compose overlay
                # the IA offender bbox on the Frigate scene.
                if (
                    event_type in ("red_light_violation", "speeding")
                    and settings.demo_relaxed_evidence()
                    and settings.frigate_demo_timeline_align
                    and demo_loop_absolute_align_ok(align_delta, accept_max)
                    and evt_bbox
                ):
                    logger.warning(
                        "frigate_track: %s demo soft-accept iou=%.3f "
                        "delta=%.2fs — IA bbox on Frigate scene cam=%s DEMO_MODE source=%s",
                        event_type, iou, align_delta, camera_id[:8], settings.demo_mode_source,
                    )
                    meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else None
                    if meta is None:
                        evt["metadata"] = {}
                        meta = evt["metadata"]
                    if event_type == "red_light_violation":
                        meta["frigate_red_light_soft_iou"] = round(float(iou), 4)
                    else:
                        meta["frigate_speed_soft_iou"] = round(float(iou), 4)
                    return True
                logger.warning(
                    "frigate_track: reject IoU cam=%s iou=%.3f min=%.2f delta=%.2fs",
                    camera_id[:8], iou, min_iou, align_delta,
                )
                abort_stats.record_probe_reject(
                    abort_stats.ABORT_IOU_REJECT,
                    camera_id=camera_id,
                    event_type=event_type,
                    extra={"iou": round(float(iou), 4), "min_iou": min_iou},
                )
                return False
        elif event_type == "red_light_violation" and evt_bbox and not frigate_bbox:
            logger.warning(
                "frigate_track: reject red_light — Frigate event has no bbox cam=%s",
                camera_id[:8],
            )
            abort_stats.record_probe_reject(
                abort_stats.ABORT_NO_FRIGATE_BBOX,
                camera_id=camera_id,
                event_type=event_type,
            )
            return False
        return True

    def _finalize_scene_bbox(
        self,
        scene_bytes: bytes | None,
        clean_bytes: bytes | None,
        norm_bbox: dict[str, float] | None,
        evt: dict[str, Any],
        subject_bytes: bytes | None,
        policy: dict[str, Any],
        camera_id: str,
        event_id: str,
        align_delta: float,
    ) -> tuple[bytes | None, dict[str, float] | None, bool, bool, bytes | None]:
        """Validate bbox on clean frame; fall back to IA bbox overlay when Frigate box is empty."""
        clean_frame = None
        if clean_bytes:
            clean_frame = cv2.imdecode(np.frombuffer(clean_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        ia_bbox = bbox_from_event(evt)
        ia_norm = normalize_bbox(ia_bbox, 1920, 1080) if ia_bbox else None
        frigate_bbox_embedded = True
        bbox_quality_ok = norm_bbox is not None
        scene_out = scene_bytes
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        soft_red = bool(meta.get("frigate_red_light_soft_iou") is not None)
        soft_speed = bool(meta.get("frigate_speed_soft_iou") is not None)
        soft_ia = soft_red or soft_speed
        event_type = str(evt.get("event_type") or "")
        # Road rules: never ship Frigate burned-in bbox (often frozen on asphalt).
        # Prefer clean snapshot + IA offender box whenever the region has content.
        force_ia_road = event_type in ("red_light_violation", "speeding")

        # Soft-accept / road force-IA path: draw the IA offender on Frigate media.
        soft_frame = clean_frame
        soft_bytes = clean_bytes
        if (soft_ia or force_ia_road) and soft_frame is None and scene_bytes:
            soft_frame = cv2.imdecode(np.frombuffer(scene_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            soft_bytes = scene_bytes
        if (soft_ia or force_ia_road) and soft_frame is not None and ia_norm and bbox_region_has_content(soft_frame, ia_norm):
            # Prefer clean bytes (no Frigate overlay) when available.
            if clean_bytes and clean_frame is not None and bbox_region_has_content(clean_frame, ia_norm):
                scene_out = clean_bytes
                soft_frame = clean_frame
            else:
                scene_out = soft_bytes
            norm_bbox = ia_norm
            frigate_bbox_embedded = False
            bbox_quality_ok = True
            images_spec = policy.get("images") or default_evidence_policy()["images"]
            # Draw IA bbox onto scene so UI/thumbnail show the offender (not empty road).
            drawn_scene, subject_bytes, _ = capture_images_from_policy(
                soft_frame, ia_norm, images_spec, JPEG_QUALITY, draw_bbox=True,
            )
            if drawn_scene:
                scene_out = drawn_scene
            logger.info(
                "frigate_track: road IA bbox on Frigate media cam=%s event=%s force=%s soft=%s",
                camera_id[:8], event_id[:24], force_ia_road, soft_ia,
            )
            return scene_out, norm_bbox, frigate_bbox_embedded, bbox_quality_ok, subject_bytes

        if clean_frame is not None and norm_bbox:
            if not bbox_region_has_content(clean_frame, norm_bbox):
                logger.warning(
                    "frigate_track: bbox empty on clean frame cam=%s event=%s delta=%.2fs",
                    camera_id[:8], event_id[:24], align_delta,
                )
                # Prefer IA bbox on clean scene when Frigate crop is empty (same as speed path).
                if ia_norm and bbox_region_has_content(clean_frame, ia_norm):
                    scene_out = clean_bytes
                    norm_bbox = ia_norm
                    frigate_bbox_embedded = False
                    bbox_quality_ok = True
                    images_spec = policy.get("images") or default_evidence_policy()["images"]
                    _, subject_bytes, _ = capture_images_from_policy(
                        clean_frame, ia_norm, images_spec, JPEG_QUALITY, draw_bbox=False,
                    )
                    logger.info(
                        "frigate_track: IA bbox fallback on clean scene cam=%s event=%s",
                        camera_id[:8], event_id[:24],
                    )
                else:
                    return None, None, False, False, None
        elif clean_frame is not None and not norm_bbox and ia_norm:
            if bbox_region_has_content(clean_frame, ia_norm):
                scene_out = clean_bytes
                norm_bbox = ia_norm
                frigate_bbox_embedded = False
                bbox_quality_ok = True
            else:
                return None, None, False, False, None
        elif not scene_out:
            return None, None, False, False, None

        return scene_out, norm_bbox, frigate_bbox_embedded, bbox_quality_ok, subject_bytes

    def _maybe_learn_offset(
        self,
        camera_id: str,
        anchor_ts: float,
        frigate_ev: dict[str, Any],
    ) -> None:
        if not camera_id or not settings.frigate_demo_timeline_align:
            return
        start = frigate_ev.get("start_time") or frigate_ev.get("frame_time")
        if not isinstance(start, (int, float)):
            return
        start_f = float(start)
        max_align = float(settings.frigate_demo_max_align_sec)
        if self._is_wall_clock_frigate_time(start_f):
            if min_time_delta(anchor_ts, frigate_ev) > max_align:
                return
        learn_clock_offset(self._demo_clock_offset, camera_id, anchor_ts, start_f)

    def _pick_correlated(
        self,
        events: list[dict[str, Any]],
        anchor_ts: float,
        want: str,
        evt_bbox: dict[str, float] | None,
        match_sec: float,
        *,
        iou_first: bool = False,
        time_only: bool = False,
        label_iou_only: bool = False,
        min_iou: float = 0.0,
        ignore_time_filter: bool = False,
    ) -> tuple[dict[str, Any] | None, float]:
        best: dict[str, Any] | None = None
        best_score = -1e18
        best_delta = 1e18
        norm_evt = normalize_bbox(evt_bbox, 1920, 1080) if evt_bbox else None

        for ev in events:
            delta = min_time_delta(anchor_ts, ev)
            if delta > match_sec and not (label_iou_only and ignore_time_filter):
                continue
            label = str(ev.get("label") or "").lower()
            if want and label != want and label not in _VEHICLE_LABELS:
                continue
            data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
            box = data.get("box")
            frigate_bbox = _frigate_box_to_norm(box) if isinstance(box, (list, tuple)) else None
            if not frigate_bbox and not time_only and not label_iou_only:
                continue
            iou = _bbox_iou(norm_evt, frigate_bbox) if norm_evt and frigate_bbox else 0.0
            if iou_first and norm_evt and frigate_bbox and iou < min_iou:
                continue
            if label_iou_only and norm_evt and frigate_bbox and iou < min_iou:
                continue
            if time_only and min_iou > 0 and norm_evt and frigate_bbox and iou < min_iou:
                continue

            if label_iou_only:
                score = iou * 30.0 - delta * 2.0
                if want and label == want:
                    score += 10.0
                elif label in _VEHICLE_LABELS:
                    score += 4.0
            elif time_only:
                score = -delta
            elif iou_first:
                score = iou * 20.0 - delta * 1.5
            else:
                score = -delta
                if want and label == want:
                    score += 8.0
                elif label in _VEHICLE_LABELS:
                    score += 3.0
                if norm_evt:
                    score += iou * 5.0

            if score > best_score:
                best_score = score
                best = ev
                best_delta = delta
        return best, best_delta

    def _list_events(self, frigate_id: str) -> list[dict[str, Any]]:
        limit = max(10, int(settings.frigate_demo_events_limit))
        qs = urllib.parse.urlencode({"cameras": frigate_id, "limit": limit})
        url = f"{self._base}/api/events?{qs}"
        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                events = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
            return []
        if not isinstance(events, list):
            return []
        # List API may omit data.box — hydrate from event detail when missing.
        out: list[dict[str, Any]] = []
        for ev in events[:limit]:
            if not isinstance(ev, dict):
                continue
            data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
            if not data.get("box") and ev.get("id"):
                detail = self._event_meta(str(ev["id"]))
                if detail:
                    ev = {**ev, **{k: detail.get(k) for k in ("data", "start_time", "end_time", "frame_time") if k in detail}}
            out.append(ev)
        return out

    def _wait_for_event_media(self, event_id: str) -> dict[str, Any]:
        deadline = time.time() + settings.frigate_event_media_wait_sec
        poll = settings.frigate_event_media_poll_sec
        last: dict[str, Any] = {}
        while time.time() < deadline:
            meta = self._event_meta(event_id)
            if meta:
                last = meta
                # Frigate often sets has_clip=True before the mp4 is downloadable.
                # Probe the clip endpoint so we don't compose with a 400 body.
                if meta.get("has_snapshot") and meta.get("has_clip"):
                    probe = self._read_bytes(
                        f"{self._base}/api/events/{event_id}/clip.mp4",
                        timeout=8,
                    )
                    if probe and len(probe) >= settings.frigate_clip_min_bytes:
                        return meta
            time.sleep(poll)
        return last

    def _event_meta(self, event_id: str) -> dict[str, Any]:
        url = f"{self._base}/api/events/{event_id}"
        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
            return {}

    def _read_bytes_retry(
        self,
        url: str,
        *,
        attempts: int,
        delay: float,
        timeout: int,
        min_bytes: int = 1000,
    ) -> bytes | None:
        last_err = ""
        for i in range(max(1, attempts)):
            data = self._read_bytes(url, timeout)
            if data and len(data) >= min_bytes:
                return data
            last_err = f"size={len(data) if data else 0}"
            if i < attempts - 1:
                time.sleep(delay)
        logger.debug("frigate fetch failed url=%s %s", url, last_err)
        return None

    def _download_event_clip(self, event_id: str, meta: dict[str, Any]) -> bytes | None:
        if meta.get("has_clip") is False:
            time.sleep(settings.frigate_clip_wait_if_missing)
        url = f"{self._base}/api/events/{event_id}/clip.mp4"
        # Young events frequently return HTTP 400 until the segment is sealed —
        # retry longer than the generic snapshot path.
        attempts = max(12, int(settings.frigate_clip_retries) * 2)
        delay = max(1.0, float(settings.frigate_clip_retry_delay))
        data = self._read_bytes_retry(
            url,
            attempts=attempts,
            delay=delay,
            timeout=20,
            min_bytes=settings.frigate_clip_min_bytes,
        )
        if data:
            logger.info(
                "frigate_track: clip ok event=%s bytes=%d",
                event_id[:24], len(data),
            )
            return data
        cam = str(meta.get("camera") or "")
        start = meta.get("start_time")
        end = meta.get("end_time")
        if cam and isinstance(start, (int, float)):
            e = float(end) if isinstance(end, (int, float)) else float(start) + 3.0
            s = max(0.0, float(start) - settings.frigate_clip_pad_before)
            e = max(s + 1.0, e + settings.frigate_clip_pad_after)
            win = f"{self._base}/api/{cam}/start/{s:.3f}/end/{e:.3f}/clip.mp4"
            data = self._read_bytes_retry(
                win,
                attempts=6,
                delay=delay,
                timeout=20,
                min_bytes=settings.frigate_clip_min_bytes,
            )
            if data:
                logger.info(
                    "frigate_track: window clip ok cam=%s event=%s bytes=%d",
                    cam[:20], event_id[:24], len(data),
                )
                return data
        logger.warning("frigate_track: clip unavailable event=%s", event_id[:24])
        return None

    def _build_images(
        self,
        event_id: str,
        matched: dict[str, Any],
        policy: dict[str, Any],
        clip_bytes: bytes | None,
    ) -> tuple[bytes | None, bytes | None, list[bytes], dict[str, float] | None, bytes | None, bytes | None]:
        base = f"{self._base}/api/events/{event_id}"
        q = str(settings.frigate_snapshot_quality)
        # Native Frigate bbox render — do not redraw (avoids IA/Frigate double box).
        scene_data = self._read_bytes_retry(
            f"{base}/snapshot.jpg?quality={q}&bbox=1",
            attempts=settings.frigate_snapshot_retries,
            delay=settings.frigate_snapshot_retry_delay,
            timeout=20,
            min_bytes=2000,
        )
        if not scene_data:
            scene_data = self._read_bytes_retry(
                f"{base}/snapshot.jpg?bbox=1",
                attempts=settings.frigate_snapshot_retries,
                delay=settings.frigate_snapshot_retry_delay,
                timeout=20,
                min_bytes=2000,
            )
        if not scene_data:
            scene_data = self._read_bytes_retry(
                f"{base}/snapshot.jpg",
                attempts=max(2, settings.frigate_snapshot_retries),
                delay=settings.frigate_snapshot_retry_delay,
                timeout=20,
                min_bytes=1500,
            )
        if not scene_data:
            scene_data = self._read_bytes_retry(
                f"{base}/thumbnail.jpg",
                attempts=4,
                delay=0.5,
                timeout=15,
                min_bytes=500,
            )
        if not scene_data and clip_bytes:
            # Last resort: first extracted frame from the clip we already downloaded.
            frames = self._extract_clip_frames(clip_bytes)
            if frames:
                scene_data = frames[0]
                logger.warning(
                    "frigate_track: scene from clip frame event=%s",
                    event_id[:24],
                )

        clean_data = self._read_bytes_retry(
            f"{base}/snapshot-clean.webp",
            attempts=2,
            delay=settings.frigate_snapshot_retry_delay,
            timeout=20,
            min_bytes=2000,
        )
        if not clean_data and scene_data:
            clean_data = self._read_bytes_retry(
                f"{base}/snapshot.jpg",
                attempts=2,
                delay=settings.frigate_snapshot_retry_delay,
                timeout=20,
                min_bytes=2000,
            )
        if not clean_data and scene_data:
            clean_data = scene_data

        norm_bbox = _frigate_box_from_event(matched)

        crop_frame = None
        if clean_data:
            arr = np.frombuffer(clean_data, dtype=np.uint8)
            crop_frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        elif scene_data:
            arr = np.frombuffer(scene_data, dtype=np.uint8)
            crop_frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        extra_frames: list[bytes] = []
        if clip_bytes:
            extra_frames = self._extract_clip_frames(clip_bytes)

        images_spec = policy.get("images") or default_evidence_policy()["images"]
        subject_bytes: bytes | None = None
        if crop_frame is not None and norm_bbox:
            _, subject_bytes, _ = capture_images_from_policy(
                crop_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=False,
            )
            if subject_bytes is None or subject_jpeg_texture(subject_bytes) is None:
                thumb = self._read_bytes(f"{base}/thumbnail.jpg", 15)
                if thumb:
                    subject_bytes = thumb

        if subject_bytes is None and extra_frames:
            subject_bytes = extra_frames[0]

        plate_crop: bytes | None = None
        if crop_frame is not None and norm_bbox:
            plate_crop = self._plate_rear_crop_jpeg(crop_frame, norm_bbox, images_spec)

        return scene_data, subject_bytes, extra_frames, norm_bbox, plate_crop, clean_data

    def _extract_clip_frames(self, clip_bytes: bytes) -> list[bytes]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return []
        tmp = tempfile.mkdtemp(prefix="cv_ft_clip_")
        clip_path = os.path.join(tmp, "clip.mp4")
        frames: list[bytes] = []
        try:
            with open(clip_path, "wb") as f:
                f.write(clip_bytes)
            dur = self._probe_duration(clip_path) or 3.0
            count = max(2, settings.frigate_evidence_frame_count)
            qv = settings.frigate_clip_frame_jpeg_q
            for i in range(count):
                t = min(i * (dur / count), max(0.0, dur - 0.05))
                out = os.path.join(tmp, f"frame_{i}.jpg")
                cmd = [
                    ffmpeg, "-y", "-ss", f"{t:.3f}", "-i", clip_path,
                    "-frames:v", "1", "-q:v", str(qv), out,
                ]
                try:
                    subprocess.run(cmd, capture_output=True, timeout=20, check=True)
                    with open(out, "rb") as f:
                        frames.append(f.read())
                except (OSError, subprocess.SubprocessError):
                    continue
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return frames

    def _trim_clip_bytes(self, clip_bytes: bytes, target_sec: float) -> bytes:
        if target_sec <= 0:
            return clip_bytes
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return clip_bytes
        tmp = tempfile.mkdtemp(prefix="cv_ft_trim_")
        inp = os.path.join(tmp, "in.mp4")
        out = os.path.join(tmp, "out.mp4")
        try:
            with open(inp, "wb") as f:
                f.write(clip_bytes)
            dur = self._probe_duration(inp)
            if dur is None or dur <= target_sec + 0.15:
                return clip_bytes
            start = max(0.0, (dur - target_sec) / 2.0)
            cmd = [
                ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", inp,
                "-t", f"{target_sec:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-an", "-movflags", "+faststart",
                out,
            ]
            subprocess.run(cmd, capture_output=True, timeout=30, check=True)
            with open(out, "rb") as f:
                trimmed = f.read()
            if len(trimmed) >= settings.frigate_clip_min_bytes:
                return trimmed
            return clip_bytes
        except (OSError, subprocess.SubprocessError):
            return clip_bytes
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _plate_rear_crop_jpeg(
        self,
        frame: np.ndarray,
        norm_bbox: dict[str, float],
        images_spec: list[dict[str, Any]],
    ) -> bytes | None:
        """Crop rear plate band inside the vehicle bbox only (never full scene)."""
        plate_spec = next((s for s in images_spec if s.get("role") == "plate"), None)
        zoom = float(plate_spec.get("zoom") or 1.8) if plate_spec else 1.8
        padding = float(plate_spec.get("padding_pct") or 6) if plate_spec else 6.0
        plate_bbox = bbox_rear_plate_region(norm_bbox)
        if not plate_bbox:
            return None
        return encode_subject_jpeg(
            frame, plate_bbox, JPEG_QUALITY,
            padding_pct=padding, zoom=zoom, crop="bbox", fallback_full=False,
        )

    def _ocr_plate(
        self,
        plate_crop: bytes | None,
        evt: dict[str, Any],
    ) -> tuple[bytes | None, str | None, float | None]:
        """Return plate JPEG for the evidence slot.

        OCR text is best-effort. When OCR is down or low-confidence, still attach
        the crop so road-rule completeness (scene+subject+plate) can pass with a
        visual plate proof — matching « plaque si disponible ».
        """
        if not plate_crop:
            return None, evt.get("plate_number"), evt.get("plate_confidence")
        if settings.ocr_url:
            plate, conf, _src = recognize_plate_jpeg(
                plate_crop, settings.ocr_url, timeout=settings.ocr_timeout,
            )
            if plate and conf >= settings.plate_min_conf:
                return plate_crop, plate, conf
        return plate_crop, evt.get("plate_number"), evt.get("plate_confidence")

    def _probe_duration(self, path: str) -> float | None:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe or not os.path.isfile(path):
            return None
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if proc.returncode != 0:
                return None
            val = float(proc.stdout.strip())
            return val if val > 0 else None
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None

    def _read_bytes(self, url: str, timeout: int) -> bytes | None:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.read()
        except http.client.IncompleteRead as exc:
            # Drop the partial bytes immediately — holding them in the exception
            # object (exc.partial) causes multi-GB memory accumulation when Frigate
            # clips are large and many events retry concurrently.
            exc.partial = b""
            return None
        except (urllib.error.URLError, TimeoutError, OSError):
            return None
