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
RED_LIGHT_SUBJECT_MIN_TEXTURE = float(os.environ.get("RED_LIGHT_SUBJECT_MIN_TEXTURE", "50") or 50)
# Red-light evidence must stay close to the IA emission instant — wide demo skew
# produces scenes where the lamp has already turned green.
# Demo go2rtc loops often skew IA↔Frigate by 10–30s; 8s was too tight and
# suppressed every red-light alert (incomplete_evidence). Keep below accept_max.
RED_LIGHT_MAX_ALIGN_SEC = 30.0
RED_LIGHT_MIN_IOU = 0.08
RED_LIGHT_FRAME_WINDOW_SEC = 0.8
RED_LIGHT_FRAME_STEP_SEC = 0.2
# Max age of the nearest Frigate path_data point for a bbox to be trusted at a
# given wall timestamp — beyond this, drawing the box would place it beside the
# vehicle (stale track), so callers must skip the frame instead.
RED_LIGHT_PATH_BBOX_MAX_GAP_SEC = float(
    os.environ.get("RED_LIGHT_PATH_BBOX_MAX_GAP_SEC", "1.5") or 1.5
)
# Sprint 1 — deferred compose: wait for Frigate end_time before clip API (I4).
RED_LIGHT_END_TIME_WAIT_SEC = 30.0
RED_LIGHT_END_TIME_BACKOFF_INITIAL = 2.0
RED_LIGHT_END_TIME_BACKOFF_MAX = 8.0


def _feu_strict_red(event_type: str) -> bool:
    """Isolated 1-hit feu: no ia_overlay / soft-accept paths."""
    return event_type == "red_light_violation" and bool(getattr(settings, "feu_1hit_strict", False))
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
        self._last_red_light_frame_debug: dict[str, Any] = {}

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

    def _red_light_align_abort_extra(
        self,
        matched: dict[str, Any],
        evt: dict[str, Any],
        *,
        anchor: float,
        align_delta: float,
    ) -> dict[str, Any]:
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        path_times = self._event_path_times(matched)
        return {
            "bbox_ts": evt.get("bbox_ts"),
            "violation_instant_ts": meta.get("violation_instant_ts"),
            "frigate_event_id": matched.get("id") or evt.get("frigate_event_id"),
            "frigate_start_time": matched.get("start_time") or meta.get("frigate_start_time"),
            "frigate_end_time": matched.get("end_time"),
            "frigate_frame_time": matched.get("frame_time") or meta.get("frigate_frame_time"),
            "path_time_min": min(path_times) if path_times else None,
            "path_time_max": max(path_times) if path_times else None,
            "path_time_count": len(path_times),
            "anchor_ts": anchor,
            "align_delta_sec": round(float(align_delta), 3),
        }

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

    @staticmethod
    def _red_light_candidate_sequence(evt: dict[str, Any], bound_id: str) -> list[dict[str, Any]]:
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        raw = meta.get("frigate_candidate_events")
        candidates = raw if isinstance(raw, list) else []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(candidate: dict[str, Any]) -> None:
            cid = str(candidate.get("id") or "").strip()
            if not cid or cid in seen:
                return
            seen.add(cid)
            out.append(dict(candidate))

        primary: dict[str, Any] = {
            "id": bound_id,
            "bbox": evt.get("bbox"),
            "bbox_ts": evt.get("bbox_ts"),
            "start_time": meta.get("frigate_start_time"),
            "frame_time": meta.get("frigate_frame_time"),
            "label": meta.get("frigate_label") or evt.get("class_name"),
            "zone_id": evt.get("zone_id"),
            "score": None,
        }
        if bound_id:
            add(primary)
        for item in candidates:
            if isinstance(item, dict):
                add(item)
        return out

    @staticmethod
    def _event_for_red_light_candidate(
        evt: dict[str, Any],
        candidate: dict[str, Any],
        *,
        rank: int,
    ) -> dict[str, Any]:
        out = dict(evt)
        meta = dict(evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {})
        cid = str(candidate.get("id") or "").strip()
        if cid:
            out["frigate_event_id"] = cid
            meta["frigate_event_id"] = cid
        bbox = candidate.get("bbox")
        if bbox:
            out["bbox"] = bbox
        bbox_ts = candidate.get("bbox_ts")
        if isinstance(bbox_ts, (int, float)):
            out["bbox_ts"] = float(bbox_ts)
            meta["violation_instant_ts"] = float(bbox_ts)
            meta["hsv_gate_ts"] = float(bbox_ts)
        if candidate.get("frame_time") is not None:
            meta["frigate_frame_time"] = candidate.get("frame_time")
        if candidate.get("start_time") is not None:
            meta["frigate_start_time"] = candidate.get("start_time")
        if candidate.get("label") is not None:
            meta["frigate_label"] = candidate.get("label")
        meta["frigate_candidate_rank"] = rank
        meta["frigate_candidate_score"] = candidate.get("score")
        out["metadata"] = meta
        return out

    @staticmethod
    def _red_light_candidate_success(result: dict[str, Any] | None) -> bool:
        if not isinstance(result, dict) or result.get("status") == "missing":
            return False
        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        return (
            str(meta.get("scene_light_state") or "").lower() == "red"
            and meta.get("bbox_source") == "frigate_mqtt"
            and bool(meta.get("subject_vehicle_ok"))
        )

    @staticmethod
    def _candidate_attempt_summary(
        *,
        rank: int,
        candidate: dict[str, Any],
        event_id: str,
        align_delta: float | None,
        result: dict[str, Any] | None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        meta = result.get("meta") if isinstance(result, dict) and isinstance(result.get("meta"), dict) else {}
        return {
            "rank": rank,
            "id": event_id,
            "bbox": candidate.get("bbox"),
            "bbox_ts": candidate.get("bbox_ts"),
            "score": candidate.get("score"),
            "label": candidate.get("label"),
            "zone_id": candidate.get("zone_id"),
            "align_delta_sec": round(float(align_delta), 3) if isinstance(align_delta, (int, float)) else None,
            "reason": reason or meta.get("abort_reason") or meta.get("reason") or "not_strict_candidate",
            "red_frames": meta.get("red_frames"),
            "content_frames": meta.get("content_frames"),
            "best_texture": meta.get("best_texture"),
            "target_pts": meta.get("target_pts"),
            "subject_vehicle_ok": meta.get("subject_vehicle_ok"),
            "scene_light_state": meta.get("scene_light_state"),
            "bbox_source": meta.get("bbox_source"),
        }

    def _compose_bridge_red_light_candidates(
        self,
        *,
        bound_id: str,
        policy: dict[str, Any],
        evt: dict[str, Any],
        camera_id: str,
        org_id: str,
    ) -> dict[str, Any] | None:
        attempts: list[dict[str, Any]] = []
        candidates = self._red_light_candidate_sequence(evt, bound_id)
        if not candidates:
            return None
        for rank, candidate in enumerate(candidates):
            candidate_id = str(candidate.get("id") or "").strip()
            if not candidate_id:
                continue
            candidate_evt = self._event_for_red_light_candidate(evt, candidate, rank=rank)
            try:
                candidate_anchor = float(candidate_evt.get("bbox_ts") or time.time())
            except (TypeError, ValueError):
                candidate_anchor = time.time()
            bound_ev = self.fetch_event(candidate_id)
            if not bound_ev:
                attempts.append(self._candidate_attempt_summary(
                    rank=rank,
                    candidate=candidate,
                    event_id=candidate_id,
                    align_delta=None,
                    result=None,
                    reason="fetch_event_missing",
                ))
                continue
            align_delta = min_time_delta(candidate_anchor, bound_ev)
            composed = self._compose_from_matched(
                bound_ev, align_delta, policy, candidate_evt, camera_id, org_id,
            )
            if self._red_light_candidate_success(composed):
                meta = composed.get("meta") if isinstance(composed.get("meta"), dict) else {}
                meta["frigate_candidate_attempts"] = attempts + [
                    self._candidate_attempt_summary(
                        rank=rank,
                        candidate=candidate,
                        event_id=candidate_id,
                        align_delta=align_delta,
                        result=composed,
                        reason="accepted",
                    )
                ]
                meta["frigate_candidate_selected"] = candidate_id
                meta["frigate_candidate_rank"] = rank
                composed["meta"] = meta
                logger.info(
                    "frigate_track: bridge-bound red_light candidate accepted cam=%s event=%s rank=%s",
                    camera_id[:8], candidate_id[:24], rank,
                )
                return composed
            attempts.append(self._candidate_attempt_summary(
                rank=rank,
                candidate=candidate,
                event_id=candidate_id,
                align_delta=align_delta,
                result=composed,
            ))
        return self._missing(
            "no_candidate_with_red_frame",
            camera_id=camera_id,
            evt=evt,
            event_id=bound_id,
            extra={
                "frigate_candidate_attempts": attempts,
                "frigate_candidate_count": len(candidates),
            },
        )

    def _wait_until_end_time(
        self, event_id: str, wait_sec: float | None = None,
    ) -> dict[str, Any] | None:
        """Poll Frigate until event has end_time (clip seal signal) or timeout.

        Sprint 1: never call clip.mp4 before end_time — eliminates I4 HTTP 400 thrash.
        Exponential backoff 2s → 4s → 8s (capped).
        """
        if wait_sec is None:
            wait_sec = float(
                getattr(settings, "frigate_red_light_end_time_wait_sec", RED_LIGHT_END_TIME_WAIT_SEC)
            )
        else:
            wait_sec = float(wait_sec)
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
        meta0 = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        bridge_sourced = str(meta0.get("bridge_source") or "").lower() == "frigate"
        event_type0 = str(evt.get("event_type") or "")
        # Recover Frigate-native anchor when emit forgot bbox_ts (wall clock breaks
        # demo_loop_guard for bridge speeding / red_light).
        if not isinstance(evt.get("bbox_ts"), (int, float)):
            for key in ("frigate_frame_time", "frigate_end_time", "frigate_start_time"):
                raw = meta0.get(key) if isinstance(meta0, dict) else None
                try:
                    if raw is not None:
                        evt["bbox_ts"] = float(raw)
                        anchor = float(raw)
                        break
                except (TypeError, ValueError):
                    continue
        # Trust Frigate-bridge event ids (Gemini/speed path). Only strip proactive
        # YOLO binder ids which often freeze an early box while the car moved.
        if (
            bound_id
            and event_type0 in ("red_light_violation", "speeding")
            and not bridge_sourced
        ):
            logger.info(
                "frigate_track: ignore stale binder for %s cam=%s id=%s — re-correlate",
                event_type0, camera_id[:8], bound_id[:24],
            )
            try:
                from citevision_ai.observability.rule_blockers import blockers
                blockers.inc("bound_id_stripped")
            except Exception:
                pass
            bound_id = ""
            evt.pop("frigate_event_id", None)
            if isinstance(meta0, dict):
                meta0.pop("frigate_event_id", None)
                meta0.pop("frigate_bind_iou", None)
        elif bound_id and bridge_sourced:
            try:
                from citevision_ai.observability.rule_blockers import blockers
                blockers.inc("bound_id_trusted")
            except Exception:
                pass
        if bound_id:
            if bridge_sourced and event_type0 == "red_light_violation":
                composed = self._compose_bridge_red_light_candidates(
                    bound_id=bound_id,
                    policy=policy,
                    evt=evt,
                    camera_id=camera_id,
                    org_id=org_id,
                )
                if composed is not None:
                    logger.info(
                        "frigate_track: bridge-bound red_light candidate capture cam=%s event=%s",
                        camera_id[:8], bound_id[:24],
                    )
                    return composed
                logger.info(
                    "frigate_track: bridge-bound red_light compose missing cam=%s id=%s",
                    camera_id[:8], bound_id[:24],
                )
                return None
            # Bridge speeding: compose from the trusted Frigate track id. Skip the
            # wall-clock demo_loop_guard accept gate (same policy as compose path).
            if bridge_sourced and event_type0 == "speeding":
                bound_ev = self.fetch_event(bound_id)
                if bound_ev:
                    if not isinstance(evt.get("bbox_ts"), (int, float)):
                        frig_ts = best_frigate_ts(bound_ev)
                        if frig_ts is not None:
                            evt["bbox_ts"] = float(frig_ts)
                            anchor = float(frig_ts)
                    align_delta = min_time_delta(anchor, bound_ev)
                    composed = self._compose_from_matched(
                        bound_ev, align_delta, policy, evt, camera_id, org_id,
                    )
                    if composed is not None:
                        logger.info(
                            "frigate_track: bridge-bound speeding capture cam=%s event=%s delta=%.2fs",
                            camera_id[:8], bound_id[:24], align_delta,
                        )
                        return composed
                    logger.info(
                        "frigate_track: bridge-bound speeding compose missing cam=%s id=%s",
                        camera_id[:8], bound_id[:24],
                    )
                else:
                    logger.info(
                        "frigate_track: bridge-bound speeding fetch missing cam=%s id=%s",
                        camera_id[:8], bound_id[:24],
                    )
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
                # Demo speeding: enrichment retries lose frigate_event_id and the
                # anchor ages past the align window, so the guard rejected every
                # retry → alert stuck pending (run14/15 FAIL_EVIDENCE missing_clip).
                # The demo video loops — the latest sealed vehicle event's clip is
                # visually equivalent, so anchor on the fallback's own timestamp.
                if (
                    self._demo_mode()
                    and str(evt.get("event_type") or "") == "speeding"
                    and align_delta > self._hard_align_max_sec("speeding")
                ):
                    frig_ts = best_frigate_ts(fallback)
                    if frig_ts is not None:
                        evt["bbox_ts"] = float(frig_ts)
                        anchor = float(frig_ts)
                        align_delta = min_time_delta(anchor, fallback)
                        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else None
                        if meta is None:
                            evt["metadata"] = {}
                            meta = evt["metadata"]
                        meta["demo_speed_fallback_reanchored"] = True
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
        anchor = float(anchor)
        fid = self.frigate_camera_id(camera_id)
        meta_evt = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        bridge_sourced = str(meta_evt.get("bridge_source") or "").lower() == "frigate"

        # Wait for Frigate end_time BEFORE align gates or clip download.
        # Active events often lack path_data/end_time; min_time_delta() then returns
        # 1e18 and demo_loop_guard aborts with align_too_wide instead of deferring.
        # Speeding: do NOT fail-closed on missing end_time — demo tracks stay open for
        # minutes and a 30s wait saturates the retro semaphore. Prefer a short wait,
        # then snapshot + window clip (synthetic end) so alerts get proof.
        speed_unsealed = False
        evidence_strict = bool(getattr(settings, "frigate_evidence_strict", False))
        if is_red or is_speed:
            # Speeding: short end_time wait (default 8s) so retro slots are not
            # blocked 30s×N under a demo flood; then unsealed snapshot/window —
            # unless FRIGATE_EVIDENCE_STRICT=1 (protocole 3 complete proof).
            speed_wait = float(getattr(settings, "frigate_speed_end_time_wait_sec", 8.0))
            # Keep short wait even under strict — open demo tracks + go2rtc clip
            # provide complete packs without a 30s seal stall.
            sealed = self._wait_until_end_time(
                event_id,
                wait_sec=speed_wait if is_speed else None,
            )
            if not sealed or sealed.get("end_time") in (None, "", False):
                if is_red:
                    return self._missing(
                        abort_stats.ABORT_CLIP_NOT_READY_TIMEOUT,
                        camera_id=camera_id,
                        evt=evt,
                        event_id=event_id,
                        extra={
                            "waited_sec": RED_LIGHT_END_TIME_WAIT_SEC,
                            "reason": "red_wait_end_time",
                            "frigate_evidence_strict": evidence_strict,
                        },
                    )
                # Speeding under strict: demo tracks often stay open (max_in_zone).
                # Do not fail-closed here — synthesize end and continue to go2rtc clip.
                speed_unsealed = True
                meta = sealed or self._event_meta(event_id) or dict(matched or {})
                if sealed:
                    matched = {
                        **matched,
                        **{
                            k: sealed.get(k)
                            for k in (
                                "data", "start_time", "end_time", "frame_time",
                                "label", "has_clip", "has_snapshot",
                            )
                            if k in sealed
                        },
                    }
                # Synthetic end so window-clip fallback can run.
                st = (
                    meta.get("start_time")
                    or matched.get("start_time")
                    or meta_evt.get("frigate_start_time")
                    or evt.get("bbox_ts")
                )
                try:
                    st_f = float(st) if st is not None else None
                except (TypeError, ValueError):
                    st_f = None
                if st_f is not None and meta.get("end_time") in (None, "", False):
                    end_f = st_f + max(3.0, float(policy.get("clip_seconds") or CLIP_DURATION_SEC))
                    meta = {**meta, "start_time": st_f, "end_time": end_f}
                    matched = {**matched, "start_time": st_f, "end_time": end_f}
                logger.warning(
                    "frigate_track: speed unsealed fallback event=%s cam=%s "
                    "(snapshot/window clip — end_time not ready; strict=%s)",
                    event_id[:24], camera_id[:8], evidence_strict,
                )
                align_delta = min_time_delta(anchor, matched)
            else:
                matched = {
                    **matched,
                    **{
                        k: sealed.get(k)
                        for k in (
                            "data", "start_time", "end_time", "frame_time",
                            "label", "has_clip", "has_snapshot",
                        )
                        if k in sealed
                    },
                }
                meta = sealed
                align_delta = min_time_delta(anchor, matched)
        else:
            fresh = self._event_meta(event_id)
            if fresh:
                matched = {
                    **matched,
                    **{
                        k: fresh.get(k)
                        for k in ("data", "start_time", "end_time", "frame_time", "label")
                        if k in fresh
                    },
                }
            meta = self._wait_for_event_media(event_id)
            align_delta = min_time_delta(anchor, matched)

        # §3.1 demo_loop_guard — absolute align for every demo rule (not only red_light).
        # Bridge-sourced events already carry Frigate-native bbox_ts; skip loop guard.
        if self._demo_loop_guard_active() and not bridge_sourced and (
            float(align_delta) > hard_max
            or not self._demo_loop_pair_ok(float(anchor), matched, float(align_delta), event_type)
        ):
            extra = self._red_light_align_abort_extra(
                matched,
                evt,
                anchor=float(anchor),
                align_delta=float(align_delta),
            )
            extra.update({
                "max_align_sec": hard_max,
                "via": "demo_loop_guard_compose",
            })
            return self._missing(
                abort_stats.ABORT_ALIGN_TOO_WIDE,
                camera_id=camera_id,
                evt=evt,
                event_id=event_id,
                extra=extra,
            )

        if is_red and float(align_delta) > RED_LIGHT_MAX_ALIGN_SEC:
            extra = self._red_light_align_abort_extra(
                matched,
                evt,
                anchor=float(anchor),
                align_delta=float(align_delta),
            )
            extra["max_align_sec"] = RED_LIGHT_MAX_ALIGN_SEC
            return self._missing(
                abort_stats.ABORT_ALIGN_TOO_WIDE,
                camera_id=camera_id,
                evt=evt,
                event_id=event_id,
                extra=extra,
            )

        # Ensure window-clip path has a Frigate camera id when event meta is sparse.
        if isinstance(meta, dict) and not meta.get("camera"):
            meta = {**meta, "camera": fid}

        clip_bytes = self._download_event_clip(event_id, meta)
        raw_clip_bytes = clip_bytes
        if not clip_bytes and float(policy.get("clip_seconds") or 0) > 0:
            # Frigate often reports has_clip=true while segments were discarded
            # (maintainer saturation). Pull a short MP4 from go2rtc as last resort.
            clip_bytes = self._download_go2rtc_clip(
                camera_id=camera_id,
                meta=meta if isinstance(meta, dict) else {},
                seconds=float(policy.get("clip_seconds") or CLIP_DURATION_SEC),
            )
            raw_clip_bytes = clip_bytes
        if is_red and not clip_bytes:
            return self._missing(
                abort_stats.ABORT_NO_CLIP,
                camera_id=camera_id,
                evt=evt,
                event_id=event_id,
                extra={"reason": "red_needs_clip"},
            )
        if is_speed and not clip_bytes:
            if evidence_strict:
                return self._missing(
                    abort_stats.ABORT_NO_CLIP,
                    camera_id=camera_id,
                    evt=evt,
                    event_id=event_id,
                    extra={
                        "reason": "speed_strict_needs_clip",
                        "frigate_evidence_strict": True,
                        "unsealed": speed_unsealed,
                    },
                )
            # Snapshot-only partial is acceptable for unsealed/demo tracks —
            # better than leaving the alert without any proof.
            logger.warning(
                "frigate_track: speed snapshot-only (no clip) event=%s cam=%s unsealed=%s",
                event_id[:24], camera_id[:8], speed_unsealed,
            )
        # Geometry / road packs with clip_seconds>0 under strict: never ship partial
        # without a clip (credibility — same as protocole 3 complete).
        if (
            evidence_strict
            and not is_red
            and not is_speed
            and float(policy.get("clip_seconds") or 0) > 0
            and not clip_bytes
        ):
            return self._missing(
                abort_stats.ABORT_NO_CLIP,
                camera_id=camera_id,
                evt=evt,
                event_id=event_id,
                extra={
                    "reason": "strict_needs_clip",
                    "frigate_evidence_strict": True,
                    "event_type": event_type,
                },
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
        capture_frame_ts = None
        capture_frame_pts = None

        if is_red and raw_clip_bytes:
            # Red-light proof must use the Frigate MQTT box captured at T, not a
            # later/representative Frigate event bbox that may point to another frame.
            mqtt_bbox = bbox_from_event(evt)
            norm_bbox = normalize_bbox(mqtt_bbox, 1920, 1080) if mqtt_bbox else None
            if norm_bbox is None:
                norm_bbox = _frigate_box_from_event(matched)
            if norm_bbox is None:
                return self._missing(
                    abort_stats.ABORT_NO_FRIGATE_BBOX,
                    camera_id=camera_id,
                    evt=evt,
                    event_id=event_id,
                    extra={"via": "red_light_anchor_frame"},
                )
            selected = None
            if self._bridge_snapshot_confirmed_red(evt):
                selected = self._red_light_proof_from_snapshot(
                    event_id, matched, evt, norm_bbox, policy,
                )
            if selected is None:
                selected = self._red_light_frame_from_clip_at_anchor(
                    raw_clip_bytes,
                    matched,
                    evt,
                    camera_id,
                    anchor,
                    norm_bbox,
                    policy,
                )
            if selected is None:
                selected = self._red_light_proof_from_snapshot(
                    event_id, matched, evt, norm_bbox, policy,
                )
            if selected is None:
                emission_light = self._emission_light_state(evt) or "unknown"
                abort_reason = (
                    abort_stats.ABORT_SUBJECT_EMPTY
                    if emission_light == "red"
                    else abort_stats.ABORT_SCENE_GREEN
                )
                extra = self._red_light_align_abort_extra(
                    matched,
                    evt,
                    anchor=float(anchor),
                    align_delta=float(align_delta),
                )
                extra.update(self._last_red_light_frame_debug)
                extra.update({
                    "scene_light_state": emission_light,
                    "reason": "no_red_subject_frame_at_anchor" if emission_light == "red" else "no_red_frame_at_anchor",
                    "bbox_ok": True,
                    "subject_ok": False,
                })
                return self._missing(
                    abort_reason,
                    camera_id=camera_id,
                    evt=evt,
                    event_id=event_id,
                    extra=extra,
                )
            (
                scene_bytes,
                subject_bytes,
                plate_crop,
                norm_bbox,
                capture_frame_ts,
                capture_frame_pts,
            ) = selected
            clean_bytes = scene_bytes
            scene_light = "red"
            frigate_bbox_embedded = True
            bbox_quality_ok = True
            ocr_frames = [scene_bytes] if scene_bytes else []
            logger.info(
                "frigate_track: red_light anchored frame cam=%s event=%s delta=%.2fs pts=%s",
                camera_id[:8], event_id[:24], align_delta,
                round(float(capture_frame_pts), 3) if capture_frame_pts is not None else None,
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

        if is_red:
            scene_light = self._resolve_scene_light(
                scene_bytes, clip_bytes, evt, current=scene_light,
            )
            # Strict = rejeter uniquement si la PREUVE montre du vert (pas re-auditer l'émission).
            if _feu_strict_red(str(evt.get("event_type") or "")) and scene_light == "green":
                return self._missing(
                    abort_stats.ABORT_SCENE_GREEN,
                    camera_id=camera_id,
                    evt=evt,
                    event_id=event_id,
                    extra={
                        "scene_light_state": "green",
                        "align_delta_sec": round(float(align_delta), 3),
                        "feu_1hit_strict": True,
                    },
                )

        subject_texture = subject_jpeg_texture(subject_bytes)
        subject_min_texture = RED_LIGHT_SUBJECT_MIN_TEXTURE if is_red else SUBJECT_MIN_TEXTURE
        subject_quality_ok = (
            subject_bytes is not None
            and subject_texture is not None
            and subject_texture >= subject_min_texture
        )
        if subject_bytes is not None and not subject_quality_ok:
            bbox_quality_ok = False

        # Fail-closed for red_light + speeding: empty / lagged subject must not ship as "proof".
        # Speeding exception: if we at least have a Frigate scene, ship partial rather than
        # leaving the alert with zero media (demo unsealed tracks often crop poorly).
        if require_subject:
            if not bbox_quality_ok or not subject_quality_ok:
                if not (is_speed and scene_bytes is not None):
                    return self._missing(
                        abort_stats.ABORT_SUBJECT_EMPTY,
                        camera_id=camera_id,
                        evt=evt,
                        event_id=event_id,
                        extra={
                            "bbox_ok": bbox_quality_ok,
                            "subject_ok": subject_quality_ok,
                            "texture": subject_texture,
                            "min_texture": subject_min_texture,
                        },
                    )
                logger.warning(
                    "frigate_track: speed scene-only partial event=%s cam=%s "
                    "bbox_ok=%s subject_ok=%s",
                    event_id[:24], camera_id[:8], bbox_quality_ok, subject_quality_ok,
                )

        plate_jpeg, plate_number, plate_confidence, plate_source = self._ocr_plate(plate_crop, evt)
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        want_plate = any(s.get("role") == "plate" for s in images_spec)
        # Sprint 4 / A.4 / R.2: never fabricate a plate from the subject crop.
        # Demo exception: the rear-band crop from the vehicle subject IS the
        # visual plate proof — a partial package for a missing crop kills the
        # demo (run12 Lecture plaque: missing_images:plate status=partial).
        if want_plate and not plate_jpeg and self._demo_mode():
            fallback = subject_bytes or scene_bytes
            if fallback:
                plate_jpeg = bytes(fallback)
                plate_source = plate_source if plate_source != "none" else "demo_subject_band"
        missing_roles: list[str] = []
        if want_plate and not plate_jpeg:
            missing_roles.append("plate")

        clip_duration = target_clip_sec if clip_bytes else 0.0
        complete = bool(scene_bytes and subject_bytes and clip_bytes and bbox_quality_ok)
        if is_red and scene_light != "red":
            complete = False
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
                "subject_vehicle_ok": subject_quality_ok,
                "subject_min_texture": subject_min_texture,
                "capture_source": "frigate_track",
                "frigate_camera_id": fid,
                "frigate_event_id": event_id,
                "align_delta_ms": int(round(align_delta * 1000)),
                "capture_frame_ts": capture_frame_ts,
                "capture_frame_pts": capture_frame_pts,
                "plate_ocr_source": plate_source,
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
            }
        meta_in = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        if is_speed:
            meta_out["detection_method"] = str(meta_in.get("detection_method") or "frigate_speed")
            meta_out["speed_kmh"] = evt.get("speed_kmh") or meta_in.get("speed_est_kmh")
            meta_out["speed_limit_kmh"] = evt.get("speed_limit_kmh") or meta_in.get("speed_limit_kmh")
            meta_out["speed_emit_mode"] = meta_in.get("speed_emit_mode") or "exit"
            meta_out["zone_entry_exit"] = meta_in.get("zone_entry_exit") or "exit"
            meta_out["frigate_start_time"] = matched.get("start_time") or meta_in.get("frigate_start_time")
            meta_out["frigate_end_time"] = matched.get("end_time") or meta_in.get("frigate_end_time")
            if speed_unsealed:
                meta_out["speed_unsealed"] = True
            if bridge_sourced:
                meta_out["bbox_source"] = "frigate_mqtt"
        light_poly = meta_in.get("light_zone_polygon")
        if isinstance(light_poly, list) and light_poly:
            meta_out["light_zone_polygon"] = light_poly
        if want_plate and not plate_jpeg:
            meta_out["plate_status"] = "missing"
        if scene_light is not None:
            meta_out["scene_light_state"] = scene_light
        if ia_bbox and norm_bbox:
            meta_out["ia_bbox"] = ia_bbox

        if evt.get("frigate_event_id") and not frigate_bbox_embedded:
            bridge_sourced = str(
                (evt.get("metadata") or {}).get("bridge_source") or ""
            ).lower() == "frigate" if isinstance(evt.get("metadata"), dict) else False
            if bridge_sourced and norm_bbox:
                # MQTT box already on the CiteVision event — honest frigate_mqtt label.
                meta_out["bbox_source"] = "frigate_mqtt"
                meta_out["frigate_bbox_embedded"] = True
            else:
                logger.warning(
                    "frigate_track: bound capture missing frigate bbox cam=%s event=%s — IA fallback",
                    camera_id[:8], event_id[:24],
                )
                if ia_bbox and norm_bbox:
                    if _feu_strict_red(str(evt.get("event_type") or "")):
                        logger.warning(
                            "frigate_track: reject ia_overlay — FEU_1HIT_STRICT cam=%s event=%s",
                            camera_id[:8], event_id[:24],
                        )
                        return None
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
    def _path_nearest_gap_sec(matched: dict[str, Any], wall_ts: float) -> float | None:
        """Age (s) of the nearest Frigate path_data point vs wall_ts. None = no path."""
        data = matched.get("data") if isinstance(matched.get("data"), dict) else {}
        path = data.get("path_data")
        if not isinstance(path, list) or not path:
            return None
        best: float | None = None
        for pt in path:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            try:
                ts = float(pt[1])
            except (TypeError, ValueError):
                continue
            delta = abs(ts - float(wall_ts))
            if best is None or delta < best:
                best = delta
        return best

    @staticmethod
    def _bbox_from_path_at_time(
        matched: dict[str, Any],
        wall_ts: float,
    ) -> dict[str, float] | None:
        """Interpolate vehicle bbox at a wall timestamp using Frigate path_data.

        Fail-closed: returns None when no path point exists within
        RED_LIGHT_PATH_BBOX_MAX_GAP_SEC of ``wall_ts`` — a stale nearest point
        (or the event-level box) would draw the bbox beside the vehicle.
        """
        base = _frigate_box_from_event(matched)
        if not base:
            return None
        data = matched.get("data") if isinstance(matched.get("data"), dict) else {}
        path = data.get("path_data")
        if not isinstance(path, list) or not path:
            return None
        best_coords: list[float] | None = None
        best_delta = 1e18
        for pt in path:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            coords_raw, ts_raw = pt[0], pt[1]
            try:
                ts = float(ts_raw)
            except (TypeError, ValueError):
                continue
            delta = abs(ts - float(wall_ts))
            if delta < best_delta and isinstance(coords_raw, (list, tuple)) and len(coords_raw) >= 2:
                best_delta = delta
                best_coords = [float(coords_raw[0]), float(coords_raw[1])]
        if not best_coords or best_delta > RED_LIGHT_PATH_BBOX_MAX_GAP_SEC:
            return None
        w = float(base.get("width") or 0)
        h = float(base.get("height") or 0)
        if w <= 0 or h <= 0:
            return base
        cx, cy = best_coords[0], best_coords[1]
        # Frigate path_data stores bottom-centre of the tracked box.
        x = max(0.0, min(1.0 - w, cx - w / 2.0))
        y = max(0.0, min(1.0 - h, cy - h))
        return {"x": x, "y": y, "width": w, "height": h, "norm": True}

    @staticmethod
    def _bridge_snapshot_confirmed_red(evt: dict[str, Any]) -> bool:
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        return str(meta.get("frigate_snapshot_light_state") or "").lower().strip() == "red"

    def _red_light_proof_from_snapshot(
        self,
        event_id: str,
        matched: dict[str, Any],
        evt: dict[str, Any],
        norm_bbox: dict[str, float],
        policy: dict[str, Any],
    ) -> tuple[bytes, bytes, bytes | None, dict[str, float], float | None, float | None] | None:
        """Use Frigate snapshot.jpg when clip scan finds no red+subject frame."""
        from citevision_ai.frigate_bridge.snapshot import download_snapshot_jpeg

        raw = download_snapshot_jpeg(self._base, event_id)
        if not raw:
            return None
        # Frigate may replace snapshot.jpg after the bridge classified it at
        # emission time — always re-verify the bytes actually shipped as proof,
        # even when metadata.frigate_snapshot_light_state said red.
        if self._scene_light_state(raw, evt) != "red":
            return None
        try:
            arr = np.frombuffer(raw, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            return None
        if frame is None or frame.size == 0:
            return None
        # Frigate keeps event data.box in sync with snapshot.jpg (same frame),
        # so it is the only bbox aligned with this image by construction. The
        # MQTT anchor bbox / path interpolation belong to another instant and
        # land beside the vehicle (visible retard/avance on the drawn box).
        anchor_ts = evt.get("bbox_ts")
        frame_bbox = _frigate_box_from_event(matched)
        if not frame_bbox:
            return None
        if not bbox_region_has_content(frame, frame_bbox):
            return None
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        scene_jpeg, subject_jpeg, _ = capture_images_from_policy(
            frame, frame_bbox, images_spec, JPEG_QUALITY, draw_bbox=True,
        )
        texture = subject_jpeg_texture(subject_jpeg)
        if not scene_jpeg or not subject_jpeg or texture is None:
            return None
        if texture < RED_LIGHT_SUBJECT_MIN_TEXTURE:
            return None
        plate_crop = self._plate_rear_crop_jpeg(frame, frame_bbox, images_spec)
        capture_ts = float(anchor_ts) if isinstance(anchor_ts, (int, float)) else None
        return scene_jpeg, subject_jpeg, plate_crop, frame_bbox, capture_ts, None

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
    def _emission_light_state(evt: dict[str, Any]) -> str | None:
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        for key in ("light_state", "hsv_light_state"):
            v = str(meta.get(key) or "").lower().strip()
            if v in ("red", "green", "yellow"):
                return v
        return None

    @staticmethod
    def _event_path_times(ev: dict[str, Any]) -> list[float]:
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        out: list[float] = []
        for pt in data.get("path_data") or []:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            try:
                out.append(float(pt[1]))
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    def _event_time_bounds(ev: dict[str, Any]) -> tuple[float | None, float | None]:
        starts: list[float] = []
        ends: list[float] = []
        for key in ("start_time", "frame_time"):
            try:
                raw = ev.get(key)
                if isinstance(raw, (int, float)):
                    starts.append(float(raw))
            except (TypeError, ValueError):
                continue
        path_times = FrigateTrackEvidence._event_path_times(ev)
        starts.extend(path_times)
        ends.extend(path_times)
        try:
            raw_end = ev.get("end_time")
            if isinstance(raw_end, (int, float)):
                ends.append(float(raw_end))
        except (TypeError, ValueError):
            pass
        return (min(starts) if starts else None, max(ends) if ends else None)

    @staticmethod
    def _nearest_time(target: float, times: list[float]) -> float | None:
        if not times:
            return None
        return min(times, key=lambda t: abs(float(t) - float(target)))

    def _red_light_anchor_pts(
        self,
        clip_path: str,
        matched: dict[str, Any],
        evt: dict[str, Any],
        camera_id: str,
        anchor: float,
    ) -> tuple[float | None, float | None, float | None, dict[str, Any]]:
        """Map the red-light violation wall/stream timestamp to a PTS in the Frigate clip."""
        duration = self._probe_duration(clip_path)
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        anchor_ts = meta.get("violation_instant_ts") or evt.get("bbox_ts") or anchor
        try:
            anchor_f = float(anchor_ts)
        except (TypeError, ValueError):
            anchor_f = float(anchor)
        original_anchor = anchor_f
        # Frigate-bridge sourced events already carry a Frigate-native bbox_ts
        # (see _bbox_ts_from_after: frame_time/path_data/start_time). Re-applying
        # the learned wall-clock<->Frigate offset here would double-correct it and
        # push the anchor outside the track's [start_time, end_time] window.
        bridge_sourced = str(meta.get("bridge_source") or "").lower() == "frigate"
        if settings.frigate_demo_timeline_align and not bridge_sourced:
            anchor_f = aligned_anchor(self._demo_clock_offset, camera_id, anchor_f)

        start = matched.get("start_time")
        if start is None:
            start = meta.get("frigate_start_time")
        end = matched.get("end_time")
        frame_time = matched.get("frame_time")
        if frame_time is None:
            frame_time = meta.get("frigate_frame_time")
        start_f: float | None = None
        end_f: float | None = None
        try:
            if isinstance(start, (int, float)):
                start_f = float(start)
            elif isinstance(frame_time, (int, float)):
                start_f = float(frame_time)
        except (TypeError, ValueError):
            start_f = None
        try:
            if isinstance(end, (int, float)):
                end_f = float(end)
        except (TypeError, ValueError):
            end_f = None

        if start_f is None:
            start_f, end_from_bounds = self._event_time_bounds(matched)
            if end_f is None:
                end_f = end_from_bounds
        path_times = self._event_path_times(matched)
        candidate_times = list(path_times)
        for raw in (start_f, end_f, frame_time):
            if isinstance(raw, (int, float)):
                candidate_times.append(float(raw))

        anchor_used = anchor_f
        recentered = False
        if start_f is not None and end_f is not None and candidate_times:
            if not (start_f - 0.5 <= anchor_used <= end_f + 0.5):
                nearest = self._nearest_time(anchor_used, candidate_times)
                if nearest is not None:
                    anchor_used = nearest
                    recentered = True

        if start_f is None:
            debug = {
                "anchor_original": original_anchor,
                "anchor_aligned": anchor_f,
                "anchor_used": anchor_used,
                "duration": duration,
                "start_time": start,
                "end_time": end,
                "frame_time": frame_time,
                "path_time_min": min(path_times) if path_times else None,
                "path_time_max": max(path_times) if path_times else None,
                "anchor_recentered": recentered,
                "reason": "missing_start_time",
            }
            return None, duration, None, debug

        pre_pad = 0.0
        if duration is not None and end_f is not None and end_f > start_f:
            event_span = max(0.0, end_f - start_f)
            if duration > event_span + 0.05:
                pre_pad = min(max(0.0, duration - event_span), float(settings.frigate_clip_pad_before))
        pts_raw = anchor_used - start_f + pre_pad
        if duration is not None and candidate_times and (pts_raw < -0.25 or pts_raw > duration + 0.25):
            nearest = self._nearest_time(anchor_used, candidate_times)
            if nearest is not None:
                anchor_used = nearest
                recentered = True
                pts_raw = anchor_used - start_f + pre_pad
        pts = pts_raw
        if duration is not None:
            pts = min(max(0.0, pts), max(0.0, duration - 0.001))
        debug = {
            "anchor_original": original_anchor,
            "anchor_aligned": anchor_f,
            "anchor_used": anchor_used,
            "target_pts_raw": pts_raw,
            "target_pts": pts,
            "duration": duration,
            "clip_start_ts": start_f - pre_pad,
            "start_time": start_f,
            "end_time": end_f,
            "frame_time": frame_time,
            "path_time_min": min(path_times) if path_times else None,
            "path_time_max": max(path_times) if path_times else None,
            "path_time_count": len(path_times),
            "anchor_recentered": recentered,
            "pre_pad": pre_pad,
        }
        return pts, duration, (start_f - pre_pad), debug

    def _red_light_frame_from_clip_at_anchor(
        self,
        clip_bytes: bytes,
        matched: dict[str, Any],
        evt: dict[str, Any],
        camera_id: str,
        anchor: float,
        norm_bbox: dict[str, float],
        policy: dict[str, Any],
    ) -> tuple[bytes, bytes, bytes | None, dict[str, float], float | None, float | None] | None:
        """Select a proof frame close to the violation instant: red lamp + Frigate subject."""
        meta = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        poly = meta.get("light_zone_polygon") or []
        if not isinstance(poly, list) or len(poly) < 3:
            return None

        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(clip_bytes)
                tmp_path = tmp.name

            target_pts, duration, clip_start_ts, align_debug = self._red_light_anchor_pts(
                tmp_path, matched, evt, camera_id, anchor,
            )
            self._last_red_light_frame_debug = dict(align_debug)
            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                return None
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 10.0)
            duration = duration or (float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0) / max(fps, 1.0))
            if duration <= 0:
                duration = 3.0

            step = max(1, int(round(fps * RED_LIGHT_FRAME_STEP_SEC)))
            images_spec = policy.get("images") or default_evidence_policy()["images"]
            best: tuple[tuple[int, float, float], bytes, bytes, bytes | None, float, float | None, dict[str, float]] | None = None
            stats = {
                "frames_checked": 0,
                "red_frames": 0,
                "content_frames": 0,
                "best_texture": None,
                "searched_ranges": [],
            }

            def scan_range(start_pts: float, end_pts: float) -> None:
                nonlocal best
                start_pts = max(0.0, min(float(start_pts), duration))
                end_pts = max(0.0, min(float(end_pts), duration))
                if end_pts < start_pts:
                    return
                stats["searched_ranges"].append([round(start_pts, 3), round(end_pts, 3)])
                cap.set(cv2.CAP_PROP_POS_MSEC, start_pts * 1000.0)
                frame_idx = int(round(start_pts * fps))
                end_frame = int(round(end_pts * fps))
                while frame_idx <= end_frame:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break
                    stats["frames_checked"] = int(stats["frames_checked"]) + 1
                    pts = frame_idx / max(fps, 1.0)
                    wall_ts = (clip_start_ts + pts) if clip_start_ts is not None else None
                    frame_bbox = norm_bbox
                    if wall_ts is not None:
                        gap = self._path_nearest_gap_sec(matched, float(wall_ts))
                        if gap is not None and gap > RED_LIGHT_PATH_BBOX_MAX_GAP_SEC:
                            # Frigate track has points but none near this frame —
                            # a stale box would land beside the vehicle. Skip it.
                            next_frame = frame_idx + step
                            cap.set(cv2.CAP_PROP_POS_FRAMES, next_frame)
                            frame_idx = next_frame
                            continue
                        frame_bbox = self._bbox_from_path_at_time(matched, float(wall_ts)) or norm_bbox
                    if self._frame_light_state(frame, poly) == "red":
                        stats["red_frames"] = int(stats["red_frames"]) + 1
                        if bbox_region_has_content(frame, frame_bbox):
                            stats["content_frames"] = int(stats["content_frames"]) + 1
                            scene_jpeg, subject_jpeg, _ = capture_images_from_policy(
                                frame, frame_bbox, images_spec, JPEG_QUALITY, draw_bbox=True,
                            )
                            texture = subject_jpeg_texture(subject_jpeg)
                            if scene_jpeg and subject_jpeg and texture is not None:
                                prev = stats.get("best_texture")
                                stats["best_texture"] = max(float(prev or 0.0), float(texture))
                                temporal = abs(pts - target_pts) if target_pts is not None else pts
                                texture_ok_rank = 0 if texture >= RED_LIGHT_SUBJECT_MIN_TEXTURE else 1
                                score = (texture_ok_rank, temporal, -float(texture))
                                plate_crop = self._plate_rear_crop_jpeg(frame, frame_bbox, images_spec)
                                capture_ts = (clip_start_ts + pts) if clip_start_ts is not None else None
                                cand = (score, scene_jpeg, subject_jpeg, plate_crop, pts, capture_ts, frame_bbox)
                                if best is None or cand[0] < best[0]:
                                    best = cand
                    # Advance by a stable wall-clock step without decoding every frame forever.
                    next_frame = frame_idx + step
                    cap.set(cv2.CAP_PROP_POS_FRAMES, next_frame)
                    frame_idx = next_frame

            if target_pts is None:
                scan_range(0.0, duration)
            else:
                scan_range(
                    max(0.0, target_pts - RED_LIGHT_FRAME_WINDOW_SEC),
                    min(duration, target_pts + RED_LIGHT_FRAME_WINDOW_SEC),
                )
                if best is None:
                    start_f = align_debug.get("start_time")
                    end_f = align_debug.get("end_time")
                    clip_start_f = align_debug.get("clip_start_ts")
                    if isinstance(start_f, (int, float)) and isinstance(end_f, (int, float)) and isinstance(clip_start_f, (int, float)):
                        scan_range(max(0.0, float(start_f) - float(clip_start_f)), min(duration, float(end_f) - float(clip_start_f)))
                    if best is None:
                        scan_range(0.0, duration)

            cap.release()
            self._last_red_light_frame_debug = {**align_debug, **stats}
            if best is None:
                return None
            _, scene_jpeg, subject_jpeg, plate_crop, pts, capture_ts, out_bbox = best
            texture = subject_jpeg_texture(subject_jpeg)
            if texture is None or texture < RED_LIGHT_SUBJECT_MIN_TEXTURE:
                # Clip frames near the anchor often have a blurred/dark vehicle crop
                # while Frigate snapshot.jpg stays sharp — defer to snapshot proof.
                return None
            return scene_jpeg, subject_jpeg, plate_crop, out_bbox, capture_ts, pts
        except Exception:
            logger.exception("frigate_track: red_light anchored frame failed cam=%s", camera_id[:8])
            return None
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _resolve_scene_light(
        scene_bytes: bytes | None,
        clip_bytes: bytes | None,
        evt: dict[str, Any],
        *,
        current: str | None = None,
    ) -> str | None:
        """Proof scene HSV → clip red frame; never call proof red from emission alone."""
        from_scene = current
        if scene_bytes and from_scene != "red":
            from_scene = FrigateTrackEvidence._scene_light_state(scene_bytes, evt)
        # Preuve contredit l'émission : feu vert visible sur l'image archivée.
        if from_scene == "green":
            return "green"
        if from_scene == "red":
            return "red"
        if clip_bytes and FrigateTrackEvidence._red_frame_jpeg_from_clip(clip_bytes, evt) is not None:
            return "red"
        emission = FrigateTrackEvidence._emission_light_state(evt)
        if emission in ("green", "yellow"):
            return emission
        return from_scene

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

        # demo_loop_guard §3.1: absolute window before soft-accept / bound trust.
        # Bridge-sourced events already carry Frigate-native bbox_ts (or track id);
        # skip loop guard — same policy as _compose_from_matched.
        accept_max = self._hard_align_max_sec(event_type)
        meta_early = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        bridge_sourced = str(meta_early.get("bridge_source") or "").lower() == "frigate"
        if (
            self._demo_loop_guard_active()
            and not bridge_sourced
            and not self._demo_loop_pair_ok(
                anchor_for_loop, matched, float(align_delta), event_type,
            )
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
        # Bound id still must pass the hard align gate above (non-bridge); then trust.
        # Speeding / red_light must not short-circuit on YOLO binder alone (stale box).
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
        # Bridge-sourced speeding/red_light: track id is authoritative — accept.
        if bridge_sourced and event_type in ("red_light_violation", "speeding") and bound_id:
            return True
        if (
            settings.demo_relaxed_evidence()
            and settings.frigate_demo_timeline_align
            and event_type not in ("red_light_violation", "speeding")
        ):
            return True
        # Soft fallback: IoU soft-accept only — align already enforced.
        if soft_pre and event_type == "red_light_violation" and settings.demo_relaxed_evidence():
            if _feu_strict_red(event_type):
                logger.warning(
                    "frigate_track: reject soft-pre red_light — FEU_1HIT_STRICT cam=%s",
                    camera_id[:8],
                )
                return False
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
                    if _feu_strict_red(event_type):
                        logger.warning(
                            "frigate_track: reject demo soft-accept iou=%.3f — FEU_1HIT_STRICT cam=%s",
                            iou, camera_id[:8],
                        )
                        abort_stats.record_probe_reject(
                            abort_stats.ABORT_IOU_REJECT,
                            camera_id=camera_id,
                            event_type=event_type,
                            extra={"iou": round(float(iou), 4), "feu_1hit_strict": True},
                        )
                        return False
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
        bridge_sourced = str(meta.get("bridge_source") or "").lower() == "frigate"
        # Road rules: avoid Frigate burned-in bbox — except Frigate→Gemini bridge
        # events whose bbox already comes from MQTT (must stay bbox_source=frigate_mqtt).
        force_ia_road = (
            event_type in ("red_light_violation", "speeding") and not bridge_sourced
        )
        if _feu_strict_red(event_type):
            soft_ia = False
            force_ia_road = False

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
                    if _feu_strict_red(event_type):
                        logger.warning(
                            "frigate_track: reject IA bbox fallback — FEU_1HIT_STRICT cam=%s event=%s",
                            camera_id[:8], event_id[:24],
                        )
                        return None, None, False, False, None
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
        try:
            from citevision_ai.observability.rule_blockers import blockers
            blockers.inc("frigate_list_calls")
        except Exception:
            pass
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

    @staticmethod
    def _demo_mode() -> bool:
        return str(os.environ.get("DEMO_MODE", "")).strip().lower() in ("1", "true", "yes")

    def _wait_for_event_media(self, event_id: str) -> dict[str, Any]:
        # Demo hyper-reactive: cap the media wait so the go2rtc live pull kicks
        # in well inside the evidence window instead of after 25s+ of polling.
        wait_sec = float(settings.frigate_event_media_wait_sec)
        if self._demo_mode():
            wait_sec = min(wait_sec, 6.0)
        deadline = time.time() + wait_sec
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
        try:
            from citevision_ai.observability.rule_blockers import blockers
            blockers.inc("frigate_clip_http")
        except Exception:
            pass
        demo = self._demo_mode()
        if meta.get("has_clip") is False and not demo:
            time.sleep(settings.frigate_clip_wait_if_missing)
        url = f"{self._base}/api/events/{event_id}/clip.mp4"
        # Young events frequently return HTTP 400 until the segment is sealed —
        # retry longer than the generic snapshot path. Demo: fail fast so the
        # go2rtc live pull (reliable, ~5s) runs inside the evidence window.
        if demo:
            attempts = 2
            delay = 0.8
            timeout = 6
        else:
            attempts = max(12, int(settings.frigate_clip_retries) * 2)
            delay = max(1.0, float(settings.frigate_clip_retry_delay))
            timeout = 20
        data = self._read_bytes_retry(
            url,
            attempts=attempts,
            delay=delay,
            timeout=timeout,
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
                attempts=2 if demo else 6,
                delay=delay,
                timeout=8 if demo else 20,
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

    def _download_go2rtc_clip(
        self,
        *,
        camera_id: str,
        meta: dict[str, Any],
        seconds: float,
    ) -> bytes | None:
        """Last-resort MP4 from go2rtc when Frigate segments are missing."""
        import subprocess

        # Prefer a short clip first — long pulls often time out under load.
        seconds = max(2.0, min(6.0, float(seconds or CLIP_DURATION_SEC)))
        candidates: list[str] = []
        # Prefer explicit go2rtc stream name from camera metadata / frigate path.
        for key in ("go2rtc_src", "go2rtc_stream", "demo_stream"):
            v = meta.get(key)
            if isinstance(v, str) and v.strip():
                candidates.append(v.strip())
                break
        path = str(meta.get("ffmpeg_path") or meta.get("rtsp") or "")
        if "/demo-" in path or path.startswith("rtsp://"):
            leaf = path.rstrip("/").split("/")[-1]
            if leaf and leaf not in candidates:
                candidates.append(leaf)
        # Resolve RTSP/go2rtc name from live Frigate camera config.
        try:
            fid = self.frigate_camera_id(camera_id)
            with urllib.request.urlopen(f"{self._base}/api/config", timeout=8) as resp:
                cfg = json.loads(resp.read().decode())
            entry = (cfg.get("cameras") or {}).get(fid) or {}
            inputs = ((entry.get("ffmpeg") or {}).get("inputs") or [])
            for inp in inputs:
                p = str((inp or {}).get("path") or "")
                if p:
                    leaf = p.rstrip("/").split("/")[-1]
                    if leaf and leaf not in candidates:
                        candidates.insert(0, leaf)
        except Exception:
            pass
        host = str(getattr(settings, "go2rtc_rtsp_host", None) or "127.0.0.1")
        api = f"http://{host}:1984"
        try:
            with urllib.request.urlopen(f"{api}/api/streams", timeout=5) as resp:
                streams = json.loads(resp.read().decode())
            if isinstance(streams, dict):
                for name in streams.keys():
                    if camera_id[:8] in str(name) and name not in candidates:
                        candidates.insert(0, str(name))
                # Demo fallback: any live demo-* stream (video switch may lag go2rtc registry).
                for name in streams.keys():
                    n = str(name)
                    if n.startswith("demo-") and n not in candidates:
                        candidates.append(n)
        except Exception:
            pass
        if not candidates:
            logger.warning(
                "frigate_track: go2rtc no candidates yet camera=%s meta_keys=%s — probing streams",
                (camera_id or "")[:8], list(meta.keys())[:12],
            )
        # Always probe go2rtc streams API as last resort.
        try:
            with urllib.request.urlopen(f"{api}/api/streams", timeout=5) as resp:
                streams = json.loads(resp.read().decode())
            if isinstance(streams, dict):
                for name in streams.keys():
                    n = str(name)
                    if n not in candidates:
                        if camera_id and camera_id[:8] in n:
                            candidates.insert(0, n)
                        elif n.startswith("demo-") or n.startswith("cam-"):
                            candidates.append(n)
        except Exception as exc:
            logger.warning("frigate_track: go2rtc streams probe fail: %s", exc)
        # Demo video id → deterministic stream name
        for key in ("demo_video_id", "active_video_id", "video_id"):
            vid = str(meta.get(key) or "").strip()
            if vid and "-" in vid:
                # demo-<org_first_segment>-<video_uuid>
                org = str(meta.get("org_id") or "74d51ead-97a7-4e41-a488-503a9b90c466")
                name = f"demo-{org.split('-')[0]}-{vid}"
                if name not in candidates:
                    candidates.insert(0, name)
                name2 = f"demo-{org.split('-')[0]}-{vid.split('-')[0]}"
                if name2 not in candidates:
                    candidates.insert(0, name2)
                break
        if not candidates:
            logger.warning("frigate_track: go2rtc clip unavailable camera=%s candidates=[]", (camera_id or "")[:8])
            return None
        ffmpeg = "ffmpeg"
        min_b = min(256, int(getattr(settings, "frigate_clip_min_bytes", 512) or 512))
        for name in candidates[:6]:
            # Prefer ffmpeg RTSP first — go2rtc HTTP stream.mp4 often times out under load.
            rtsp = f"rtsp://{host}:8554/{name}"
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    out = os.path.join(tmp, "clip.mp4")
                    cmd = [
                        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                        "-rtsp_transport", "tcp",
                        "-i", rtsp, "-t", f"{min(3.0, float(seconds)):.1f}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                        "-an", "-movflags", "+faststart", out,
                    ]
                    proc = subprocess.run(
                        cmd, capture_output=True, timeout=max(35, int(seconds) + 25),
                    )
                    if proc.returncode == 0 and os.path.isfile(out):
                        raw = open(out, "rb").read()
                        if len(raw) >= min_b:
                            logger.info(
                                "frigate_track: go2rtc ffmpeg clip ok src=%s bytes=%d",
                                name[:40], len(raw),
                            )
                            return raw
                    logger.warning(
                        "go2rtc ffmpeg clip fail src=%s rc=%s err=%s",
                        name[:24], proc.returncode, (proc.stderr or b"")[-240:],
                    )
            except Exception as exc:
                logger.warning("go2rtc ffmpeg clip fail src=%s: %s", name[:24], exc)
            # HTTP fallback (can be slow; allow longer timeout)
            url = f"{api}/api/stream.mp4?src={urllib.parse.quote(name)}&duration={int(min(3, seconds))}"
            data = self._read_bytes(url, timeout=max(45, int(seconds) + 30))
            if data and len(data) >= min_b:
                logger.info(
                    "frigate_track: go2rtc clip ok src=%s bytes=%d",
                    name[:40], len(data),
                )
                return data
        logger.warning(
            "frigate_track: go2rtc clip unavailable camera=%s candidates=%s",
            camera_id[:8], candidates[:4],
        )
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
        if plate_bbox:
            jpeg = encode_subject_jpeg(
                frame, plate_bbox, JPEG_QUALITY,
                padding_pct=padding, zoom=zoom, crop="bbox", fallback_full=False,
            )
            if jpeg:
                return jpeg
        if norm_bbox:
            jpeg = encode_subject_jpeg(
                frame, norm_bbox, JPEG_QUALITY,
                padding_pct=4, zoom=4.0, crop="bbox", fallback_full=False,
            )
            if jpeg:
                return jpeg
            return encode_subject_jpeg(
                frame, norm_bbox, JPEG_QUALITY,
                padding_pct=0, zoom=2.5, crop="bbox", fallback_full=True,
            )
        return None

    def _ocr_plate(
        self,
        plate_crop: bytes | None,
        evt: dict[str, Any],
    ) -> tuple[bytes | None, str | None, float | None, str]:
        """Return plate JPEG + best OCR reading for the evidence slot.

        Readings are fused from Gemini + PaddleOCR (and Fast-ALPR when its
        service is configured); only composition-matching candidates are kept,
        then the highest-confidence valid text wins. Text is best-effort: when
        nothing readable, still attach the crop as visual plate proof — never
        fabricate a plate (R.2).
        """
        if not plate_crop:
            return None, evt.get("plate_number"), evt.get("plate_confidence"), "none"
        from citevision_ai.identity.plate_fusion import (
            filter_plate_candidates,
            reading_from_gemini_verdict,
            resolve_zone_plate_pattern,
            run_paddle_on_jpeg,
        )

        pattern_re = resolve_zone_plate_pattern(evt if isinstance(evt, dict) else None)
        raw_readings: list[tuple[str, float, str]] = []
        # PaddleOCR (local, always available when models loaded).
        try:
            paddle = run_paddle_on_jpeg(plate_crop, pattern_re)
            if paddle:
                raw_readings.append((paddle.text, float(paddle.confidence), "paddle"))
        except Exception:
            logger.debug("plate paddle read failed", exc_info=True)
        # Gemini one-shot OCR (one call per violation event — events are rare).
        # Demo: skip — Gemini is rate-limited (429) and each call can hold the
        # composer up to 20s, blowing the evidence window.
        if (
            not self._demo_mode()
            and settings.gemini_enabled
            and (settings.gemini_api_key or "").strip()
        ):
            try:
                from citevision_ai.vlm.gemini_client import GeminiClient
                client = GeminiClient(
                    settings.gemini_api_key,
                    model=settings.gemini_model,
                    timeout=min(float(settings.gemini_timeout or 20.0), 20.0),
                )
                verdict = client.judge_jpeg(plate_crop, rule="plate_ocr")
                gem = reading_from_gemini_verdict(verdict, pattern_re)
                if gem:
                    raw_readings.append((gem.text, float(gem.confidence), "gemini"))
            except Exception:
                logger.debug("plate gemini read failed", exc_info=True)
        # Fast-ALPR HTTP service (legacy slot reader) as extra candidate.
        if settings.ocr_url:
            try:
                plate, conf, _src = recognize_plate_jpeg(
                    plate_crop, settings.ocr_url, timeout=settings.ocr_timeout,
                )
                if plate and conf >= settings.plate_min_conf:
                    raw_readings.append((plate, float(conf), "fast_alpr"))
            except Exception:
                logger.debug("plate fast_alpr read failed", exc_info=True)
        readings = filter_plate_candidates(raw_readings, pattern_re)
        if readings:
            # Agreement between two engines boosts confidence over either alone.
            by_text: dict[str, list[tuple[str, float, str]]] = {}
            for r in readings:
                by_text.setdefault(r[0], []).append(r)
            best_text, group = max(
                by_text.items(),
                key=lambda kv: (len(kv[1]), max(r[1] for r in kv[1])),
            )
            conf = max(r[1] for r in group)
            source = "+".join(sorted({r[2] for r in group}))
            logger.info(
                "plate_fusion text=%s conf=%.2f source=%s candidates=%d",
                best_text, conf, source, len(readings),
            )
            return plate_crop, best_text, conf, source
        # Drop prior plate_number if it no longer matches composition.
        prior = evt.get("plate_number")
        if prior and filter_plate_candidates([(str(prior), 1.0, "prior")], pattern_re):
            return plate_crop, prior, evt.get("plate_confidence"), "unreadable"
        return plate_crop, None, None, "unreadable"

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
