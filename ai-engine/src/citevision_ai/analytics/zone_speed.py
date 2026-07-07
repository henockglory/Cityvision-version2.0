"""Zone-based speed measurement with per-edge real-world calibration.

Each polygon vertex may declare ``distance_to_next_m`` (metres to the next
vertex). From calibrated edges we derive a ground scale and measure speed as:

    speed_kmh = path_distance_m / elapsed_seconds * 3.6

Speed is measured once per zone crossing (entry → exit). Spatial dedup prevents
the same physical vehicle from re-firing when ByteTrack reassigns track_id.
"""

from __future__ import annotations

import logging
import math
import os
import time
import uuid
from typing import Any

from citevision_ai.analytics.zone_geometry import edge_midpoint, resolve_speed_distance_m
from citevision_ai.evidence.capture import bbox_valid, pick_best_bbox_with_ts

SPEED_BEHAVIOR = "speed_measurement"
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}
MIN_DWELL_SEC = 0.35
DEFAULT_COOLDOWN_SEC = 20.0
MAX_PLAUSIBLE_SPEED_KMH = 160.0
SPATIAL_DEDUP_SEC = 8.0
SPATIAL_DEDUP_DIST = 0.05
MIN_EXIT_PROGRESS_NORM = 0.015
# B.18: start/finalize timer when track anchor passes calibrated edge midpoints.
EDGE_PAIR_PROXIMITY_NORM = 0.04
# Explicit demo-dense mode ([E.52]/[D.45]): reduced cooldown + relaxed spatial
# dedup so closely-spaced vehicles each raise an alert during a live demo.
# Opt-in only (behavior_config.demo_dense or CV_DEMO_DENSE=1) — never a prod default.
DENSE_COOLDOWN_SEC = 5.0
DENSE_SPATIAL_DEDUP_SEC = 3.0
LIVE_COOLDOWN_SEC = 2.0
LIVE_SPATIAL_DEDUP_SEC = 4.0
LIVE_SPATIAL_DEDUP_DIST = 0.04


def _edge_pair_indices(cfg: dict) -> tuple[int, int] | None:
    """Return (entry_edge_index, exit_edge_index) when both are configured."""
    try:
        entry = cfg.get("entry_edge_index")
        exit_ = cfg.get("exit_edge_index")
        if entry is not None and exit_ is not None:
            return int(entry), int(exit_)
    except (TypeError, ValueError):
        pass
    return None


def _near_norm_point(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    threshold: float = EDGE_PAIR_PROXIMITY_NORM,
) -> bool:
    return math.hypot(ax - bx, ay - by) <= threshold


def _demo_dense_enabled(cfg: dict) -> bool:
    """Explicit dense-demo toggle, decoupled from the speed limit value."""
    if cfg.get("demo_dense"):
        return True
    return os.getenv("CV_DEMO_DENSE", "").strip().lower() in ("1", "true", "yes", "on")


def _live_traffic_enabled(cfg: dict) -> bool:
    if cfg.get("live_traffic"):
        return True
    return str(cfg.get("traffic_profile", "")).strip().lower() == "live_traffic"


def _point_in_polygon(px: float, py: float, polygon: list[dict]) -> bool:
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(polygon[i].get("x", 0)), float(polygon[i].get("y", 0))
        xj, yj = float(polygon[j].get("x", 0)), float(polygon[j].get("y", 0))
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


def _bbox_area_px(bbox: dict) -> float:
    w = float(bbox.get("width", 0))
    h = float(bbox.get("height", 0))
    if w <= 0 or h <= 0:
        return 0.0
    if w <= 1 and h <= 1:
        return w * h
    return w * h


def _track_anchor_norm(
    bbox: dict,
    frame_w: int,
    frame_h: int,
    *,
    anchor: str = "bottom",
) -> tuple[float, float]:
    """Normalised (0–1) anchor on the bbox — bottom centre matches road contact for speed zones."""
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    w = float(bbox.get("width", 0))
    h = float(bbox.get("height", 0))
    cx = (x + w / 2) / max(frame_w, 1)
    cy = (y + h) / max(frame_h, 1) if anchor == "bottom" else (y + h / 2) / max(frame_h, 1)
    return cx, cy


def _track_in_zone(bbox: dict, polygon: list[dict], frame_w: int, frame_h: int) -> tuple[bool, tuple[float, float]]:
    """True when bottom-centre or bbox centre lies inside the speed polygon."""
    bottom = _track_anchor_norm(bbox, frame_w, frame_h, anchor="bottom")
    center = _track_anchor_norm(bbox, frame_w, frame_h, anchor="center")
    if _point_in_polygon(*bottom, polygon):
        return True, bottom
    if _point_in_polygon(*center, polygon):
        return True, center
    return False, bottom


class ZoneSpeedEngine:
    """Measures vehicle speed from zone entry/exit timing and calibrated edges."""

    def __init__(self) -> None:
        self._entry_time: dict[tuple[str, str, int], float] = {}
        self._entry_xy: dict[tuple[str, str, int], tuple[float, float]] = {}
        self._inside: dict[tuple[str, str, int], bool] = {}
        self._cooldown: dict[tuple[str, str, int], float] = {}
        self._recent_spatial: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
        self._last_bbox: dict[tuple[str, str, int], dict] = {}
        self._best_bbox: dict[tuple[str, str, int], dict] = {}
        self._last_class: dict[tuple[str, str, int], str] = {}

    def reset_camera(self, camera_id: str) -> None:
        for key in list(self._entry_time):
            if key[0] == camera_id:
                self._entry_time.pop(key, None)
                self._entry_xy.pop(key, None)
                self._inside.pop(key, None)
                self._last_bbox.pop(key, None)
                self._best_bbox.pop(key, None)
                self._last_class.pop(key, None)
        for key in list(self._recent_spatial):
            if key[0] == camera_id:
                self._recent_spatial.pop(key, None)
        for key in list(self._cooldown):
            if key[0] == camera_id:
                self._cooldown.pop(key, None)

    def camera_has_behavior(self, zones: list[dict] | None) -> bool:
        if not zones:
            return False
        return any(str(z.get("behavior", "")) == SPEED_BEHAVIOR for z in zones)

    def _prune_spatial(self, camera_id: str, zone_id: str, now_ts: float, window_sec: float) -> list[tuple[float, float, float]]:
        zkey = (camera_id, zone_id)
        kept = [
            (t, x, y)
            for t, x, y in self._recent_spatial.get(zkey, [])
            if now_ts - t < window_sec
        ]
        self._recent_spatial[zkey] = kept
        return kept

    def _spatial_duplicate(
        self,
        camera_id: str,
        zone_id: str,
        cx: float,
        cy: float,
        now_ts: float,
        window_sec: float,
        dist_thresh: float,
    ) -> bool:
        for t, x, y in self._prune_spatial(camera_id, zone_id, now_ts, window_sec):
            if math.hypot(cx - x, cy - y) < dist_thresh:
                return True
        return False

    def _record_spatial_emit(
        self,
        camera_id: str,
        zone_id: str,
        cx: float,
        cy: float,
        now_ts: float,
        window_sec: float,
    ) -> None:
        zkey = (camera_id, zone_id)
        hist = self._prune_spatial(camera_id, zone_id, now_ts, window_sec)
        hist.append((now_ts, cx, cy))
        self._recent_spatial[zkey] = hist

    def process_frame(
        self,
        camera_id: str,
        tracks: list[dict],
        zones: list[dict] | None,
        frame_w: int,
        frame_h: int,
        now_ts: float,
        iso_ts: str,
        frame_wall_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        if frame_wall_ts is None:
            frame_wall_ts = time.time()
        if not zones:
            return []
        speed_zones = [z for z in zones if str(z.get("behavior", "")) == SPEED_BEHAVIOR]
        if not speed_zones:
            return []

        events: list[dict[str, Any]] = []
        for sz in speed_zones:
            cfg = sz.get("behavior_config") or {}
            try:
                limit = float(cfg.get("speed_limit_kmh", 0) or 0)
            except (TypeError, ValueError):
                limit = 0.0
            class_filter = str(cfg.get("class_filter", "car"))
            zone_id = str(sz.get("zone_id", sz.get("name", "zone")))
            poly = sz.get("polygon") or []
            if not poly:
                continue
            try:
                cooldown_sec = float(cfg.get("cooldown_sec", DEFAULT_COOLDOWN_SEC) or DEFAULT_COOLDOWN_SEC)
            except (TypeError, ValueError):
                cooldown_sec = DEFAULT_COOLDOWN_SEC
            try:
                spatial_window = float(cfg.get("spatial_dedup_sec", SPATIAL_DEDUP_SEC) or SPATIAL_DEDUP_SEC)
            except (TypeError, ValueError):
                spatial_window = SPATIAL_DEDUP_SEC
            spatial_dist = SPATIAL_DEDUP_DIST
            live_traffic = _live_traffic_enabled(cfg)
            if live_traffic:
                try:
                    cooldown_sec = float(cfg.get("cooldown_sec", LIVE_COOLDOWN_SEC) or LIVE_COOLDOWN_SEC)
                except (TypeError, ValueError):
                    cooldown_sec = LIVE_COOLDOWN_SEC
                try:
                    spatial_window = float(cfg.get("spatial_dedup_sec", LIVE_SPATIAL_DEDUP_SEC) or LIVE_SPATIAL_DEDUP_SEC)
                except (TypeError, ValueError):
                    spatial_window = LIVE_SPATIAL_DEDUP_SEC
                try:
                    spatial_dist = float(cfg.get("spatial_dedup_dist", LIVE_SPATIAL_DEDUP_DIST) or LIVE_SPATIAL_DEDUP_DIST)
                except (TypeError, ValueError):
                    spatial_dist = LIVE_SPATIAL_DEDUP_DIST
            # Dense demo mode: explicit opt-in only (never auto from speed limit).
            demo_dense = _demo_dense_enabled(cfg)
            if demo_dense:
                cooldown_sec = min(cooldown_sec, DENSE_COOLDOWN_SEC)
                spatial_window = min(spatial_window, DENSE_SPATIAL_DEDUP_SEC)
                spatial_dist = DENSE_SPATIAL_DEDUP_DIST
            cooldown_sec = max(cooldown_sec, MIN_DWELL_SEC)

            edge_pair = _edge_pair_indices(cfg)
            entry_mid: tuple[float, float] | None = None
            exit_mid: tuple[float, float] | None = None
            if edge_pair is not None:
                entry_mid = edge_midpoint(poly, edge_pair[0])
                exit_mid = edge_midpoint(poly, edge_pair[1])
                if entry_mid is None or exit_mid is None:
                    edge_pair = None

            active_tids = {
                int(t.get("track_id", -1))
                for t in tracks
                if int(t.get("track_id", -1)) >= 0
            }
            # Debug: log tracks once per 10s to diagnose no-detection issues
            _dbg_log = logging.getLogger(__name__)
            _debug_key = f"_dbg_{camera_id}_{zone_id}"
            _now_dbg = time.monotonic()
            _last_dbg = getattr(ZoneSpeedEngine, _debug_key, 0)
            if _now_dbg - _last_dbg > 10:
                setattr(ZoneSpeedEngine, _debug_key, _now_dbg)
                vehicle_tracks = [t for t in tracks if str(t.get("class_name","")) in VEHICLE_CLASSES or class_filter in ("any","")]
                _dbg_log.warning(
                    "[zone_speed_debug] cam=%s zone=%s tracks_total=%d vehicle_tracks=%d "
                    "poly_y=[%.2f-%.2f] frame=%dx%d",
                    camera_id[:8], zone_id, len(tracks), len(vehicle_tracks),
                    min((p.get("y",0) for p in poly), default=0),
                    max((p.get("y",0) for p in poly), default=0),
                    frame_w, frame_h,
                )
                for t in vehicle_tracks[:3]:
                    bbox = t.get("bbox") or {}
                    bottom = _track_anchor_norm(bbox, frame_w, frame_h, anchor="bottom")
                    center = _track_anchor_norm(bbox, frame_w, frame_h, anchor="center")
                    in_z, _ = _track_in_zone(bbox, poly, frame_w, frame_h)
                    _dbg_log.warning(
                        "  track_id=%s cls=%s bbox_px=(%.0f,%.0f,%.0f,%.0f) "
                        "norm_bottom=(%.3f,%.3f) norm_center=(%.3f,%.3f) in_zone=%s",
                        t.get("track_id"), t.get("class_name"),
                        bbox.get("x",0), bbox.get("y",0), bbox.get("width",0), bbox.get("height",0),
                        bottom[0], bottom[1], center[0], center[1], in_z,
                    )
            for track in tracks:
                cls = str(track.get("class_name", ""))
                if class_filter not in ("any", "") and cls != class_filter and cls not in VEHICLE_CLASSES:
                    continue
                tid = int(track.get("track_id", -1))
                if tid < 0:
                    continue
                bbox = track.get("bbox") or {}
                key = (camera_id, zone_id, tid)
                if bbox_valid(bbox, min_frac=0.01):
                    self._last_bbox[key] = {"bbox": dict(bbox), "ts": frame_wall_ts}
                    self._last_class[key] = cls
                    prev = self._best_bbox.get(key)
                    prev_bbox = prev.get("bbox") if prev else None
                    if prev_bbox is None or _bbox_area_px(bbox) > _bbox_area_px(prev_bbox):
                        self._best_bbox[key] = {"bbox": dict(bbox), "ts": frame_wall_ts}

                if edge_pair is not None and entry_mid is not None and exit_mid is not None:
                    cx, cy = _track_anchor_norm(bbox, frame_w, frame_h, anchor="bottom")
                    if _near_norm_point(cx, cy, entry_mid[0], entry_mid[1]):
                        if key not in self._entry_time:
                            self._entry_time[key] = now_ts
                            self._entry_xy[key] = (cx, cy)
                        self._inside[key] = True
                    elif (
                        key in self._entry_time
                        and self._inside.get(key)
                        and _near_norm_point(cx, cy, exit_mid[0], exit_mid[1])
                    ):
                        events.extend(
                            self._finalize_crossing(
                                camera_id,
                                zone_id,
                                tid,
                                track,
                                key,
                                entry_xy=self._entry_xy.get(key),
                                exit_xy=(cx, cy),
                                entry=self._entry_time.get(key),
                                now_ts=now_ts,
                                iso_ts=iso_ts,
                                poly=poly,
                                cfg=cfg,
                                limit=limit,
                                cooldown_sec=cooldown_sec,
                                spatial_window=spatial_window,
                                spatial_dist=spatial_dist,
                                frame_w=frame_w,
                                frame_h=frame_h,
                                track_lost=False,
                                demo_dense=demo_dense,
                                edge_pair_mode=True,
                                frame_wall_ts=frame_wall_ts,
                            )
                        )
                    continue

                inside, (cx, cy) = _track_in_zone(bbox, poly, frame_w, frame_h)
                if inside:
                    if key not in self._entry_time:
                        self._entry_time[key] = now_ts
                        self._entry_xy[key] = (cx, cy)
                    self._inside[key] = True
                    continue

                if not self._inside.get(key):
                    continue
                events.extend(
                    self._finalize_crossing(
                        camera_id,
                        zone_id,
                        tid,
                        track,
                        key,
                        entry_xy=self._entry_xy.get(key),
                        exit_xy=(cx, cy),
                        entry=self._entry_time.get(key),
                        now_ts=now_ts,
                        iso_ts=iso_ts,
                        poly=poly,
                        cfg=cfg,
                        limit=limit,
                        cooldown_sec=cooldown_sec,
                        spatial_window=spatial_window,
                        spatial_dist=spatial_dist,
                        frame_w=frame_w,
                        frame_h=frame_h,
                        track_lost=False,
                        demo_dense=demo_dense,
                        edge_pair_mode=False,
                        frame_wall_ts=frame_wall_ts,
                    )
                )

            # Track lost while still inside zone → measure on last known entry (common with ByteTrack).
            for key in list(self._inside.keys()):
                if key[0] != camera_id or key[1] != zone_id or not self._inside.get(key):
                    continue
                tid = key[2]
                if tid in active_tids:
                    continue
                entry = self._entry_time.get(key)
                entry_xy = self._entry_xy.get(key)
                if entry is None or entry_xy is None:
                    self._inside.pop(key, None)
                    continue
                lost_entry = self._best_bbox.get(key) or self._last_bbox.get(key) or {}
                lost_bbox = lost_entry.get("bbox", {})
                lost_cls = self._last_class.get(key, "car")
                lost_track = {"track_id": tid, "class_name": lost_cls, "bbox": lost_bbox}
                if not bbox_valid(lost_bbox, min_frac=0.01):
                    self._inside.pop(key, None)
                    self._last_bbox.pop(key, None)
                    self._best_bbox.pop(key, None)
                    self._last_class.pop(key, None)
                    continue
                events.extend(
                    self._finalize_crossing(
                        camera_id,
                        zone_id,
                        tid,
                        lost_track,
                        key,
                        entry_xy=entry_xy,
                        exit_xy=entry_xy,
                        entry=entry,
                        now_ts=now_ts,
                        iso_ts=iso_ts,
                        poly=poly,
                        cfg=cfg,
                        limit=limit,
                        cooldown_sec=cooldown_sec,
                        spatial_window=spatial_window,
                        spatial_dist=spatial_dist,
                        frame_w=frame_w,
                        frame_h=frame_h,
                        track_lost=True,
                        demo_dense=demo_dense,
                        edge_pair_mode=edge_pair is not None,
                        frame_wall_ts=lost_entry.get("ts", frame_wall_ts),
                    )
                )
        return events

    def _finalize_crossing(
        self,
        camera_id: str,
        zone_id: str,
        tid: int,
        track: dict,
        key: tuple[str, str, int],
        *,
        entry_xy: tuple[float, float] | None,
        exit_xy: tuple[float, float] | None,
        entry: float | None,
        now_ts: float,
        iso_ts: str,
        poly: list[dict],
        cfg: dict,
        limit: float,
        cooldown_sec: float,
        spatial_window: float,
        spatial_dist: float,
        frame_w: int,
        frame_h: int,
        track_lost: bool,
        demo_dense: bool = False,
        edge_pair_mode: bool = False,
        frame_wall_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        self._inside[key] = False
        self._entry_time.pop(key, None)
        self._entry_xy.pop(key, None)
        best_entry = self._best_bbox.get(key)
        last_entry = self._last_bbox.get(key)
        best_track_bbox, best_bbox_ts = pick_best_bbox_with_ts(
            [
                (track.get("bbox"), frame_wall_ts),
                (best_entry.get("bbox") if best_entry else None, best_entry.get("ts") if best_entry else None),
                (last_entry.get("bbox") if last_entry else None, last_entry.get("ts") if last_entry else None),
            ],
            frame_w,
            frame_h,
            min_frac=0.02,
        )
        self._last_bbox.pop(key, None)
        self._best_bbox.pop(key, None)
        self._last_class.pop(key, None)
        if best_track_bbox:
            track = {**track, "bbox": best_track_bbox}
        elif not bbox_valid(track.get("bbox") or {}, min_frac=0.02):
            return []
        else:
            best_bbox_ts = frame_wall_ts
        if entry is None or entry_xy is None:
            return []

        elapsed = max(now_ts - entry, MIN_DWELL_SEC)
        if not track_lost and exit_xy is not None:
            if not edge_pair_mode:
                progress = math.hypot(exit_xy[0] - entry_xy[0], exit_xy[1] - entry_xy[1])
                if progress < MIN_EXIT_PROGRESS_NORM:
                    return []
            distance_m, method = resolve_speed_distance_m(poly, cfg, entry_xy, exit_xy)
        else:
            distance_m, method = resolve_speed_distance_m(poly, cfg, entry_xy, None)
        if distance_m is None or distance_m <= 0:
            return []

        speed_kmh = distance_m / elapsed * 3.6
        demo_force = limit > 0 and limit <= 1.0
        if speed_kmh > MAX_PLAUSIBLE_SPEED_KMH:
            return []
        if demo_force:
            # Demo: sub-1 km/h limits force alerts; slow ingest inflates dwell → under-counted speed.
            if speed_kmh <= 0:
                return []
            if speed_kmh <= limit:
                speed_kmh = limit + 1.0
        elif speed_kmh <= limit:
            return []

        emit_x = entry_xy[0]
        emit_y = entry_xy[1]
        if exit_xy is not None and not track_lost:
            emit_x = (entry_xy[0] + exit_xy[0]) / 2
            emit_y = (entry_xy[1] + exit_xy[1]) / 2
        spatial_dist = spatial_dist if spatial_dist > 0 else (DENSE_SPATIAL_DEDUP_DIST if demo_dense else SPATIAL_DEDUP_DIST)
        if self._spatial_duplicate(
            camera_id, zone_id, emit_x, emit_y, now_ts, spatial_window, spatial_dist,
        ):
            return []

        track_key = (camera_id, zone_id, tid)
        last = self._cooldown.get(track_key, -9999.0)
        if (now_ts - last) < cooldown_sec:
            return []

        self._cooldown[track_key] = now_ts
        self._record_spatial_emit(camera_id, zone_id, emit_x, emit_y, now_ts, spatial_window)
        ev = self._make_speeding_event(
            camera_id,
            track,
            zone_id,
            speed_kmh,
            limit,
            distance_m,
            elapsed,
            iso_ts,
            method or ("track_lost_timing" if track_lost else "edge_path_timing"),
            frame_w,
            frame_h,
            bbox_ts=best_bbox_ts,
        )
        if not ev:
            return []
        return [ev]

    @staticmethod
    def _make_speeding_event(
        camera_id: str,
        track: dict,
        zone_id: str,
        speed_kmh: float,
        limit: float,
        distance_m: float,
        elapsed_s: float,
        iso_ts: str,
        method: str,
        frame_w: int = 1920,
        frame_h: int = 1080,
        bbox_ts: float | None = None,
    ) -> dict[str, Any]:
        raw = track.get("bbox") or {}
        x, y = float(raw.get("x", 0)), float(raw.get("y", 0))
        bw, bh = float(raw.get("width", 0)), float(raw.get("height", 0))
        fw, fh = max(frame_w, 1), max(frame_h, 1)
        if bw > 0 and bh > 0 and not (x <= 1 and y <= 1 and bw <= 1 and bh <= 1):
            bbox = {
                "x": max(0.0, min(1.0, x / fw)),
                "y": max(0.0, min(1.0, y / fh)),
                "width": max(0.0, min(1.0, bw / fw)),
                "height": max(0.0, min(1.0, bh / fh)),
            }
        elif bbox_valid(raw, min_frac=0.02):
            bbox = raw
        else:
            return {}
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": "speeding",
            "event": "speeding",
            "timestamp": iso_ts,
            "track_id": track.get("track_id"),
            "class_name": track.get("class_name"),
            "zone_id": zone_id,
            "bbox": bbox,
            "bbox_ts": bbox_ts,
            "speed_kmh": round(speed_kmh, 1),
            "confidence": 0.85,
            "severity": "high",
            "metadata": {
                "speed_kmh": round(speed_kmh, 1),
                "speed_limit_kmh": limit,
                "distance_m": round(distance_m, 2),
                "elapsed_s": round(elapsed_s, 2),
                "detection_method": method,
            },
        }
