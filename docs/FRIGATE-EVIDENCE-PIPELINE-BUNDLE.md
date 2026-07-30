# Bundle pipeline Frigate / preuves CitéVision

> Généré le 2026-07-21 10:36:52 UTC  
> Workspace: `C:\\Users\\gheno\\citevision`  
> Runtime de vérité: WSL `~/citevision-v2` (launcher `Start-CiteVision.ps1`)

Ce document regroupe le code, la config, le schéma et les tests demandés pour
préparer le correctif binder + alignement temporel démo (feu / vitesse).

## Table des matières

1. [Cœur détection / preuve](#1-cœur-du-pipeline-détectionpreuve)
2. [Alignement temporel démo](#2-alignement-temporel-démo)
3. [Modules métier](#3-modules-métier-spécifiques)
4. [Backend Frigate Go](#4-intégration-frigate-côté-backend-go)
5. [Modèle de données](#5-modèle-de-données)
6. [Tests existants](#6-tests-existants)
7. [Logs / données réelles](#7-logsdonnées-réelles-récentes)
8. [Carte des responsabilités](#8-carte-des-responsabilités-rappel-correctif)

---

## Notes importantes avant lecture

| Fait | Détail |
|------|--------|
| `_bound_usable_for_road` | **N’existe pas encore** — à créer dans le correctif |
| `aligned_anchor` / `learn_clock_offset` / `_demo_clock_offset` | `frigate_timeline.py` + état sur `FrigateTrackEvidence` — **pas** dans le binder |
| `match_track_to_event` / `_maybe_learn_offset` | Sur `FrigateTrackEvidence` |
| Soft keys `frigate_red_light_soft_iou` / `frigate_speed_soft_iou` | Métadonnées runtime event — **pas** des settings |
| Skip inject feu/vitesse | `pipeline.py` ~L1009-1013 **et** ignore bound dans `_capture_impl` |

---

## 1. Cœur du pipeline détection/preuve

### 1.1 `pipeline.py` (fichier complet)

- Path: `ai-engine/src/citevision_ai/pipeline.py`
- Lines: 1371

```python
from __future__ import annotations

import copy
import ctypes
import gc
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from citevision_ai.analytics.abandoned import AbandonedObjectDetector
from citevision_ai.analytics.calibration import CalibrationEngine
from citevision_ai.analytics.scene import SceneAnalyzer
from citevision_ai.analytics.correlation import CorrelationEngine
from citevision_ai.analytics.scene_correlation import SceneCorrelationEngine
from citevision_ai.analytics.state import StateEngine
from citevision_ai.evidence.config import EVIDENCE_WORTHY_TYPES
from citevision_ai.evidence.gate import default_evidence_policy
from citevision_ai.evidence.capture import (
    bbox_valid,
    normalize_bbox,
    pick_best_bbox_with_ts,
    resolve_emission_track_bbox,
)
from citevision_ai.behavior.heuristics import BEHAVIOR_EVENT_TYPES, BehaviorHeuristics
from citevision_ai.budget.resource_budget import ResourceBudgetManager
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
from citevision_ai.events.generator import EventGenerator
from citevision_ai.evidence.segment_replay_cache import SegmentReplayCache
from citevision_ai.evidence.service import EvidenceCaptureService
from citevision_ai.identity.face import FaceIdentityEngine
from citevision_ai.identity.plate import PlateIdentityEngine
from citevision_ai.road_enforcement.detector import RoadEnforcementEngine
from citevision_ai.road_enforcement.traffic_light import TrafficLightEngine
from citevision_ai.secondary.inference import SecondaryInferenceEngine
from citevision_ai.analytics.zone_speed import ZoneSpeedEngine
from citevision_ai.config import settings
from citevision_ai.evidence.segment_align import (
    read_segment_frame_bgr,
    read_segment_frame_by_index,
    segment_pts_from_bbox_ts,
    segment_pts_from_frame_index,
)
from citevision_ai.ingest.timeline import FrameTimeline, SegmentCaptureContext
from citevision_ai.live.burn_in import draw_overlay_boxes
from citevision_ai.models.schemas import BBox, Detection, DetectionFrame
from citevision_ai.mqtt.publisher import MqttPublisher
from citevision_ai.tracking.bytetrack import ByteTracker

OVERLAY_MIN_CONF = 0.5
OVERLAY_MIN_AREA_FRAC = 0.00035
OVERLAY_MAX_TRACKS = 16


def build_overlay_detections(
    track_dicts: list[dict[str, Any]], width: int, height: int, *, max_coast: int = 0,
) -> list[dict[str, Any]]:
    """Active tracks for live UI overlay; optional brief coasting between inference frames."""
    area_frame = max(1, width * height)
    candidates: list[dict[str, Any]] = []
    for td in track_dicts:
        if int(td.get("time_since_update", 0)) > max_coast:
            continue
        if float(td.get("confidence", 0)) < OVERLAY_MIN_CONF:
            continue
        bb = td.get("bbox") or {}
        area = float(bb.get("width", 0)) * float(bb.get("height", 0))
        if area / area_frame < OVERLAY_MIN_AREA_FRAC:
            continue
        candidates.append({
            "track_id": td["track_id"],
            "class_id": td.get("class_id", 0),
            "class_name": td.get("class_name", "object"),
            "confidence": td["confidence"],
            "bbox": dict(bb),
            "metadata": td.get("metadata") or {},
        })
    candidates.sort(key=lambda d: float(d["confidence"]), reverse=True)
    return candidates[:OVERLAY_MAX_TRACKS]

logger = logging.getLogger(__name__)

# Fixed processing rate for priority zones (speed measurement, traffic light state
# machines) — these need a steady per-tick cadence to time dwell/crossings
# accurately, but must NOT scale down to "every ingested frame" as more cameras
# are added: at 16 concurrent cameras, several priority zones each demanding
# their full configured ai_fps would oversaturate the shared GPU regardless of
# batching. This cap is independent of ResourceBudgetManager's camera-count-based
# profile — priority zones always get this fixed budget, no more, no less.
PRIORITY_ZONE_TARGET_HZ = float(os.environ.get("PRIORITY_ZONE_TARGET_HZ", "8.0"))


def priority_zone_skip(source_fps: float) -> int:
    """Effective frame-skip for priority zones (speed/traffic-light).

    Replaces the old unconditional skip=1 ("process every ingested frame")
    with a fixed Hz target that stays constant regardless of active camera
    count. Priority zones intentionally bypass the camera-count-based resource
    budget (they need a steady per-tick cadence for accurate dwell/crossing
    timing) — but "every tick" must mean a bounded rate, not an unbounded one
    that scales with however many priority-zone cameras happen to be active.
    """
    if source_fps <= 0:
        return 1
    return max(1, round(source_fps / PRIORITY_ZONE_TARGET_HZ))


class PipelineService:
    """Orchestrates detection, tracking, analytics, and MQTT publishing."""

    def __init__(
        self,
        detector: YoloOnnxDetector,
        budget: ResourceBudgetManager,
        mqtt: MqttPublisher,
        face_engine: FaceIdentityEngine | None = None,
        plate_engine: PlateIdentityEngine | None = None,
    ) -> None:
        self.detector = detector
        self.budget = budget
        self.mqtt = mqtt
        self.event_generator = EventGenerator()
        self.state_engine = StateEngine()
        self.behavior = BehaviorHeuristics()
        self.scene = SceneAnalyzer()
        self.abandoned = AbandonedObjectDetector()
        self.scene_correlation = SceneCorrelationEngine()
        self.correlation = CorrelationEngine()
        self.face_engine = face_engine or FaceIdentityEngine()
        self.plate_engine = plate_engine or PlateIdentityEngine()
        self.road_enforcement = RoadEnforcementEngine()
        self.traffic_light = TrafficLightEngine()
        self.zone_speed = ZoneSpeedEngine()
        self.secondary = SecondaryInferenceEngine(device=os.environ.get("YOLO_DEVICE", "cuda"))
        self.secondary.load()
        self.evidence = EvidenceCaptureService()
        self._segment_replay_cache = SegmentReplayCache()
        self.evidence.set_segment_replay_cache(self._segment_replay_cache)
        self._calibrations: dict[str, CalibrationEngine] = {}
        self._trackers: dict[str, ByteTracker] = {}
        self._frame_counters: dict[str, int] = {}
        self._track_history: dict[tuple[str, int], list[tuple[float, float]]] = {}
        self._bbox_history: dict[tuple[str, int], list[dict]] = {}
        self._rules: list[dict] = []
        self._spatial_configs: dict[str, dict[str, Any]] = {}
        self._runtime_config: dict[str, dict[str, Any]] = {}
        self._line_configs: dict[str, dict[str, dict[str, Any]]] = {}
        self._timestamps: dict[str, float] = {}
        self._org_ids: dict[str, str] = {}
        self._capability_profiles: dict[str, list[dict[str, Any]]] = {}
        self._spatial_behavior_fp: dict[str, str] = {}
        self._frame_shape: dict[str, tuple[int, int]] = {}
        self._blur_streak: dict[str, int] = {}
        self._latest_detection_payload: dict[str, dict[str, Any]] = {}
        self._detection_broadcaster: Any | None = None
        self._tracker_lock = threading.RLock()
        self._burn_in_enabled: dict[str, bool] = {}

    def set_burn_in_enabled(self, camera_id: str, enabled: bool) -> None:
        self._burn_in_enabled[camera_id] = enabled

    def is_burn_in_enabled(self, camera_id: str) -> bool:
        if camera_id in self._burn_in_enabled:
            return self._burn_in_enabled[camera_id]
        return settings.burn_in_overlay

    def burn_in_frame(self, camera_id: str, frame: np.ndarray) -> np.ndarray:
        if not settings.burn_in_overlay or not self.is_burn_in_enabled(camera_id):
            return frame
        with self._tracker_lock:
            tracker = self._trackers.get(camera_id)
            if tracker is None:
                return frame
            h, w = frame.shape[:2]
            tracks = tracker.overlay_snapshot(max_coast=1, predict_steps=0.0)
            dets = build_overlay_detections(tracks, w, h, max_coast=1)
        return draw_overlay_boxes(frame, dets)

    def set_detection_broadcaster(self, broadcaster: Any | None) -> None:
        self._detection_broadcaster = broadcaster

    def register_camera(self, camera_id: str, spatial_config: dict[str, Any] | None = None) -> None:
        if camera_id not in self._trackers:
            self.budget.register_camera(camera_id)
            self._trackers[camera_id] = ByteTracker(min_hits=1)
            self._frame_counters[camera_id] = 0
        if spatial_config:
            if org := spatial_config.get("org_id"):
                self._org_ids[camera_id] = str(org)
            self.set_spatial_config(camera_id, spatial_config)
        if os.environ.get("E2E_MODE") == "1":
            self._apply_e2e_sensitivity()

    def _apply_e2e_sensitivity(self) -> None:
        """Seuils assouplis pour validation E2E sur flux Benedicte (marche, loitering, véhicules)."""
        self.behavior.speed_threshold = min(self.behavior.speed_threshold, 1.5)
        self.behavior.fight_overlap_ratio = min(self.behavior.fight_overlap_ratio, 0.05)
        self.state_engine.dwell_threshold_sec = min(self.state_engine.dwell_threshold_sec, 5.0)
        self.state_engine.stop_threshold_px = max(self.state_engine.stop_threshold_px, 25.0)
        self.scene.vehicle_threshold = 1
        self.scene.crowd_threshold = min(self.scene.crowd_threshold, 2)

    def set_org_id(self, camera_id: str, org_id: str) -> None:
        if org_id:
            self._org_ids[camera_id] = org_id

    def set_evidence_capture_rules(self, camera_id: str, rules: list[dict[str, Any]] | None) -> None:
        self.evidence.set_capture_rules(camera_id, rules)

    def set_capability_profiles(self, camera_id: str, profiles: list[dict[str, Any]] | None) -> None:
        self._capability_profiles[camera_id] = list(profiles or [])

    def get_latest_detections(self, camera_id: str) -> dict[str, Any]:
        """Last MQTT detection payload for live UI overlay — no extra inference."""
        cached = self._latest_detection_payload.get(camera_id)
        if cached:
            return cached
        w, h = self._frame_shape.get(camera_id, (0, 0))
        return {
            "camera_id": camera_id,
            "timestamp": None,
            "frame_id": 0,
            "resolution": {"width": w, "height": h} if w and h else None,
            "detections": [],
        }

    def _profile_has_capability(self, profile: dict[str, Any], capability: str) -> bool:
        caps = profile.get("capabilities")
        if isinstance(caps, list):
            if capability in caps:
                return True
            if not caps:
                return True
        stages = profile.get("stages") or []
        for stage in stages:
            if isinstance(stage, dict) and stage.get("capability") == capability:
                return True
        if not caps and not stages:
            return True
        return False

    def _track_in_capability_zone(self, camera_id: str, track: dict[str, Any], capability: str) -> bool:
        profiles = self._capability_profiles.get(camera_id, [])
        if not profiles:
            return True
        class_name = str(track.get("class_name", ""))
        bbox = track.get("bbox") or {}
        fw, fh = self._frame_shape.get(camera_id, (1920, 1080))
        x = float(bbox.get("x", 0))
        y = float(bbox.get("y", 0))
        bw = float(bbox.get("width", 0))
        bh = float(bbox.get("height", 0))
        if bw <= 0 or bh <= 0:
            return False
        if x <= 1 and y <= 1 and bw <= 1 and bh <= 1:
            cx, cy = x + bw / 2, y + bh / 2
        else:
            cx = (x + bw / 2) / max(fw, 1)
            cy = (y + bh / 2) / max(fh, 1)
        spatial = self._spatial_configs.get(camera_id, {})
        zone_map = {z.get("zone_id", z.get("name", "")): z for z in spatial.get("zones", [])}
        for pr in profiles:
            if not self._profile_has_capability(pr, capability):
                continue
            cf = str(pr.get("class_filter", "any"))
            if cf not in ("any", "", "*") and class_name and class_name != cf:
                continue
            zone_id = str(pr.get("zone_id", ""))
            if not zone_id:
                return True
            zone = zone_map.get(zone_id)
            if not zone:
                continue
            polygon = zone.get("polygon") or []
            if not polygon:
                return True
            if self._polygon_is_normalized(polygon):
                if self._point_in_polygon(cx, cy, polygon):
                    return True
            elif self._point_in_polygon(cx * fw, cy * fh, polygon):
                return True
        return False

    @staticmethod
    def _point_in_polygon(x: float, y: float, polygon: list[dict]) -> bool:
        if len(polygon) < 3:
            return False
        inside = False
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = float(polygon[i].get("x", 0)), float(polygon[i].get("y", 0))
            xj, yj = float(polygon[j].get("x", 0)), float(polygon[j].get("y", 0))
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside
            j = i
        return inside

    def unregister_camera(self, camera_id: str) -> None:
        self.budget.unregister_camera(camera_id)
        self._trackers.pop(camera_id, None)
        self._frame_counters.pop(camera_id, None)
        self._spatial_configs.pop(camera_id, None)
        self._calibrations.pop(camera_id, None)
        self._runtime_config.pop(camera_id, None)
        self._line_configs.pop(camera_id, None)
        self._org_ids.pop(camera_id, None)
        self._capability_profiles.pop(camera_id, None)
        # Preserve the ring buffer so the rules-engine can still capture evidence
        # for events that fired just before the camera was stopped (e.g. the next
        # rule's preflight stops parasitic cameras while evidence retries are in
        # flight).  Only clear the capture-gate rules, not the frame data.
        self.evidence.clear_camera_rules_only(camera_id)
        self.plate_engine.reset_camera(camera_id)

    def begin_segment_replay(self, camera_id: str) -> None:
        """Fresh tracker + zone-speed state for each offline segment replay."""
        self._segment_replay_cache.clear_camera(camera_id)
        self._trackers.pop(camera_id, None)
        self._frame_counters[camera_id] = 0
        self.zone_speed.reset_camera(camera_id)
        self.plate_engine.reset_camera(camera_id)
        to_drop = [k for k in self._bbox_history if k[0] == camera_id]
        for k in to_drop:
            self._bbox_history.pop(k, None)
        to_drop_h = [k for k in self._track_history if k[0] == camera_id]
        for k in to_drop_h:
            self._track_history.pop(k, None)

    def apply_runtime_config(self, camera_id: str, config: dict[str, Any]) -> None:
        self._runtime_config[camera_id] = dict(config)
        if duration := config.get("duration_seconds"):
            self.state_engine.dwell_threshold_sec = float(duration)
        if speed := config.get("speed_kmh"):
            self.behavior.speed_threshold = float(speed)
        if crowd := config.get("crowd_threshold"):
            self.scene.crowd_threshold = int(crowd)
        if vehicles := config.get("vehicle_threshold"):
            self.scene.vehicle_threshold = int(vehicles)
        if density := config.get("density_threshold"):
            self.scene.density_threshold = float(density)
        if fight := config.get("fight_overlap_ratio"):
            self.behavior.fight_overlap_ratio = float(fight)

    def _runtime_for(self, camera_id: str) -> dict[str, Any]:
        return self._runtime_config.get(camera_id, {})

    @staticmethod
    def _behavior_fingerprint(config: dict[str, Any]) -> str:
        zones = config.get("zones") or []
        parts: list[tuple[str, str, str]] = []
        for z in zones:
            bcfg = z.get("behavior_config") or {}
            parts.append(
                (
                    str(z.get("name", "")),
                    str(z.get("behavior", "")),
                    json.dumps(bcfg, sort_keys=True, default=str),
                )
            )
        return json.dumps(sorted(parts))

    spatial_behavior_fingerprint = _behavior_fingerprint

    def set_rules(self, rules: list[dict]) -> None:
        self._rules = rules

    def reload_secondary_models(self) -> dict[str, bool]:
        self.secondary.reload()
        return self.secondary.health()

    def set_spatial_config(self, camera_id: str, config: dict[str, Any]) -> None:
        fp = self._behavior_fingerprint(config)
        if self._spatial_behavior_fp.get(camera_id) != fp:
            self.traffic_light.reset_camera(camera_id)
            self.zone_speed.reset_camera(camera_id)
            self.plate_engine.reset_camera(camera_id)
            self._trackers.pop(camera_id, None)
            self._track_history = {
                k: v for k, v in self._track_history.items() if k[0] != camera_id
            }
            self._bbox_history = {
                k: v for k, v in self._bbox_history.items() if k[0] != camera_id
            }
            self._spatial_behavior_fp[camera_id] = fp
        self._spatial_configs[camera_id] = config
        calib = CalibrationEngine(config.get("calibration"))
        self._calibrations[camera_id] = calib
        line_map: dict[str, dict[str, Any]] = {}
        for line in config.get("lines") or []:
            line_id = line.get("line_id", line.get("name", "line"))
            line_map[line_id] = line
            self.behavior.set_line_config(
                camera_id,
                line_id,
                line.get("start", line.get("start_point", {})),
                line.get("end", line.get("end_point", {})),
                str(line.get("direction", "unknown")),
            )
        self._line_configs[camera_id] = line_map
        rules = self._build_spatial_rules(camera_id, config)
        if rules:
            self._rules = [r for r in self._rules if r.get("camera_id") != camera_id] + rules

    def set_watchlist(self, entries: list[dict[str, Any]]) -> None:
        self.face_engine.set_watchlist(entries)

    def set_plates(self, entries: list[dict[str, Any]]) -> None:
        self.plate_engine.set_plates(entries)

    # Zone behaviors that must never spawn parasitic loitering / dwell rules.
    _LOITERING_SKIP_BEHAVIORS = frozenset({
        "speed_measurement", "traffic_light", "red_light", "phone_use",
        "seatbelt", "driver_cabin", "vehicle_count", "line_crossing",
    })

    # Non-speed MQTT noise suppressed on speed-only cameras.
    _SPEED_ONLY_SKIP_EVENTS = frozenset({
        "loitering", "loitering_near_entrance", "dwell_time_exceeded",
        "crowd_gathering", "crowd_count_threshold", "fight_detected", "fighting",
        "sudden_stop", "vehicle_stopped", "person_stopped", "abandoned_object",
        "crowd_dispersal", "group_gathering", "zone_enter", "zone_exit",
        "line_cross", "behavior_anomaly", "presence_detected", "absence_detected",
        "vehicle_count_threshold", "running",
    })

    @classmethod
    def _zone_behaviors(cls, config: dict[str, Any]) -> set[str]:
        out: set[str] = set()
        for zone in config.get("zones") or []:
            b = str(zone.get("behavior") or zone.get("zone_kind") or "").strip()
            if b:
                out.add(b)
        return out

    def _is_speed_only_camera(self, camera_id: str) -> bool:
        """True when every configured zone behavior is speed_measurement.

        Cameras that also have count/crossing lines are not speed-only: skipping
        EventGenerator would suppress line_cross and freeze observation counters.
        """
        cfg = self._spatial_configs.get(camera_id) or {}
        if cfg.get("lines"):
            return False
        behaviors = self._zone_behaviors(cfg)
        return bool(behaviors) and behaviors <= {"speed_measurement"}

    def _build_spatial_rules(self, camera_id: str, config: dict[str, Any]) -> list[dict]:
        rules: list[dict] = []
        for zone in config.get("zones") or []:
            zone_id = zone.get("zone_id", zone.get("name", "zone"))
            polygon = zone.get("polygon", [])
            behavior = str(zone.get("behavior", zone.get("zone_kind", "")) or "")
            bcfg = zone.get("behavior_config") or {}
            loiter_sec = float(zone.get("loiter_threshold", 30))
            if behavior == "loitering" and bcfg.get("duration_seconds"):
                loiter_sec = float(bcfg["duration_seconds"])
            if os.environ.get("E2E_MODE") == "1":
                loiter_sec = min(loiter_sec, 5.0)
            rules.append({
                "camera_id": camera_id,
                "rule_type": "zone",
                "enabled": True,
                "zone": {
                    "zone_id": zone_id,
                    "polygon": polygon,
                    "zone_kind": zone.get("zone_kind", ""),
                    "behavior": behavior,
                    "behavior_config": bcfg,
                    "name": zone.get("name", zone_id),
                },
            })
            # Speed / traffic-light / cabin zones use dedicated engines — a generic
            # loitering rule on the same polygon floods MQTT and starves YOLO.
            if behavior not in self._LOITERING_SKIP_BEHAVIORS:
                rules.append({
                    "camera_id": camera_id,
                    "rule_type": "loitering",
                    "enabled": True,
                    "loitering": {
                        "zone_id": zone_id,
                        "threshold_seconds": loiter_sec,
                    },
                    "zone": {"polygon": polygon},
                })
            # A "presence" behavior adds an explicit zone_presence rule honoring its config.
            if behavior == "presence":
                rules.append({
                    "camera_id": camera_id,
                    "rule_type": "zone_presence",
                    "enabled": True,
                    "presence_seconds": float(bcfg.get("duration_seconds", 5)),
                    "class_filter": str(bcfg.get("class_filter", "any")),
                    "zone": {"zone_id": zone_id, "polygon": polygon},
                })
        for pr in config.get("presence_rules") or []:
            zone_id = pr.get("zone_id", "zone")
            polygon = pr.get("polygon", [])
            rules.append({
                "camera_id": camera_id,
                "rule_type": "zone_presence",
                "enabled": True,
                "presence_seconds": float(pr.get("presence_seconds", 5)),
                "class_filter": pr.get("class_filter", "any"),
                "zone": {"zone_id": zone_id, "polygon": polygon},
            })
        for line in config.get("lines") or []:
            rules.append({
                "camera_id": camera_id,
                "rule_type": "line",
                "enabled": True,
                "line": {
                    "line_id": line.get("line_id", line.get("name", "line")),
                    "start": line.get("start", line.get("start_point", {})),
                    "end": line.get("end", line.get("end_point", {})),
                    "direction_filter": line.get("direction", "unknown"),
                },
            })
        return rules

    @staticmethod
    def _polygon_is_normalized(polygon: list[dict]) -> bool:
        if not polygon:
            return False
        try:
            return all(0 <= float(p.get("x", 2)) <= 1.0 and 0 <= float(p.get("y", 2)) <= 1.0 for p in polygon)
        except (TypeError, ValueError):
            return False

    def _scale_rules_to_frame(self, rules: list[dict], width: int, height: int) -> list[dict]:
        """Convert normalized (0–1) zone/line geometry from the UI to frame pixels."""
        scaled: list[dict] = []
        for rule in rules:
            r = copy.deepcopy(rule)
            zone = r.get("zone")
            if zone and zone.get("polygon") and self._polygon_is_normalized(zone["polygon"]):
                zone["polygon"] = [
                    {"x": float(p["x"]) * width, "y": float(p["y"]) * height}
                    for p in zone["polygon"]
                ]
            line = r.get("line")
            if line:
                for key in ("start", "end"):
                    pt = line.get(key)
                    if not pt:
                        continue
                    try:
                        x, y = float(pt.get("x", 2)), float(pt.get("y", 2))
                        if 0 <= x <= 1.0 and 0 <= y <= 1.0:
                            line[key] = {"x": x * width, "y": y * height}
                    except (TypeError, ValueError):
                        continue
            scaled.append(r)
        return scaled

    _MALLOC_TRIM_INTERVAL = 500  # frames between malloc_trim calls per camera

    @staticmethod
    def _trim_malloc() -> None:
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        source_fps: float = 30.0,
        *,
        timeline: FrameTimeline | None = None,
        segment_ctx: SegmentCaptureContext | None = None,
        capture_wall_ts: float | None = None,
        publish_frame_index: int | None = None,
    ) -> DetectionFrame:
        frame_id = self._frame_counters.get(camera_id, 0)
        self._frame_counters[camera_id] = frame_id + 1
        if frame_id % self._MALLOC_TRIM_INTERVAL == 0 and frame_id > 0:
            gc.collect()
            self._trim_malloc()
        self.state_engine.set_fps(source_fps)
        now_ts = timeline.monotonic if timeline else time.monotonic()
        frame_wall_ts = timeline.wall if timeline else (capture_wall_ts or time.time())
        self._timestamps[camera_id] = now_ts
        if segment_ctx is not None:
            self._segment_replay_cache.store(
                camera_id, segment_ctx.cycle_id, segment_ctx.frame_index, frame,
            )
        if camera_id not in settings.parsed_segment_mode_camera_ids():
            self.evidence.push_frame(camera_id, frame)
        rt = self._runtime_for(camera_id)
        if rt.get("duration_seconds"):
            self.state_engine.dwell_threshold_sec = float(rt["duration_seconds"])
        if rt.get("speed_kmh"):
            self.behavior.speed_threshold = float(rt["speed_kmh"])

        zones_cfg = (self._spatial_configs.get(camera_id) or {}).get("zones") or []
        tl_active = self.traffic_light.camera_has_behavior(zones_cfg)
        zs_active = self.zone_speed.camera_has_behavior(zones_cfg)
        skip = self.budget.frame_skip_interval(source_fps)
        # State machines (traffic light, zone speed) need a steady per-tick cadence,
        # but capped at a fixed Hz — not "every ingested frame" — so priority zones
        # don't scale their GPU demand with the ingest rate as camera count grows.
        if tl_active or zs_active:
            skip = priority_zone_skip(source_fps)

        if frame_id % skip != 0:
            pre_events: list[dict[str, Any]] = []
            if tl_active:
                ts0 = datetime.now(timezone.utc).isoformat()
                pre_events.extend(
                    self.traffic_light.process_frame(camera_id, frame, [], ts0, zones_cfg)
                )
            for evt in pre_events:
                if self._org_ids.get(camera_id):
                    evt["org_id"] = self._org_ids[camera_id]
                self.mqtt.publish_event(camera_id, evt)
            h, w = frame.shape[:2]
            self._frame_shape[camera_id] = (w, h)
            self._publish_overlay_predict(
                camera_id, frame_id, w, h, capture_wall_ts, frame_wall_ts, skip,
                publish_frame_index=publish_frame_index,
            )
            return DetectionFrame(
                camera_id=camera_id,
                timestamp=datetime.fromtimestamp(frame_wall_ts, tz=timezone.utc).isoformat(),
                frame_id=frame_id,
                width=w,
                height=h,
                detections=[],
            )

        profile = self.budget.get_profile()
        resized = cv2.resize(frame, (profile.width, profile.height))
        raw_dets = self.detector.detect(resized)
        scale_x = frame.shape[1] / profile.width
        scale_y = frame.shape[0] / profile.height
        for d in raw_dets:
            b = d["bbox"]
            b["x"] *= scale_x
            b["y"] *= scale_y
            b["width"] *= scale_x
            b["height"] *= scale_y

        tracker = self._trackers.setdefault(camera_id, ByteTracker(min_hits=1))
        with self._tracker_lock:
            tracks = tracker.update(raw_dets)
        track_dicts = []
        calib = self._calibrations.get(camera_id, CalibrationEngine())
        h, w = frame.shape[:2]
        self._frame_shape[camera_id] = (w, h)
        ts = (
            timeline.iso_timestamp
            if timeline and timeline.iso_timestamp
            else datetime.fromtimestamp(frame_wall_ts, tz=timezone.utc).isoformat()
        )

        for t in tracks:
            td = {
                "track_id": t.track_id,
                "class_id": t.class_id,
                "class_name": t.class_name,
                "confidence": t.confidence,
                "bbox": t.bbox,
            }
            bbox = t.bbox
            cx = bbox["x"] + bbox["width"] / 2
            cy = bbox["y"] + bbox["height"] / 2
            key = (camera_id, t.track_id)
            hist = self._track_history.setdefault(key, [])
            hist.append((cx, cy))
            if len(hist) > 12:
                hist.pop(0)
            bbox_hist = self._bbox_history.setdefault(key, [])
            bbox_hist.append({"bbox": dict(t.bbox), "ts": frame_wall_ts})
            if len(bbox_hist) > 12:
                bbox_hist.pop(0)

            speed_info = calib.update_track(camera_id, t.track_id, cx, cy, now_ts, t.class_name)
            td["metadata"] = {"speed_kmh": speed_info.get("speed_kmh", 0.0)}
            td["time_since_update"] = t.time_since_update
            track_dicts.append(td)

        detections = [
            Detection(
                track_id=t["track_id"],
                class_id=t["class_id"],
                class_name=t["class_name"],
                confidence=t["confidence"],
                bbox=BBox(**t["bbox"]),
            )
            for t in track_dicts
        ]

        frame_result = DetectionFrame(
            camera_id=camera_id,
            timestamp=ts,
            frame_id=frame_id,
            width=w,
            height=h,
            detections=detections,
        )

        # Filter out ghost tracks: tracks whose bbox is outside the frame (with 30% slack)
        # or have degenerate size (< 4px). These accumulate when a looping demo video
        # causes ByteTrack to keep Kalman-extrapolated predictions far outside frame bounds.
        # We keep them in track_dicts for zone_speed (which handles lost-track cleanup),
        # but exclude them from all heavy behavioral analytics to avoid CPU saturation.
        def _bbox_in_frame(bbox: dict, fw: int, fh: int) -> bool:
            bx = float(bbox.get("x", 0))
            by = float(bbox.get("y", 0))
            bw = float(bbox.get("width", 0))
            bh = float(bbox.get("height", 0))
            if bw < 4 or bh < 4:
                return False
            slack_x = 0.30 * fw
            slack_y = 0.30 * fh
            if bx + bw < -slack_x or bx > fw + slack_x:
                return False
            if by + bh < -slack_y or by > fh + slack_y:
                return False
            return True

        track_dicts_inframe = [
            t for t in track_dicts
            if _bbox_in_frame(t.get("bbox") or {}, w, h)
        ]

        all_events: list[dict[str, Any]] = []
        speed_only = self._is_speed_only_camera(camera_id)
        zone_dwell: dict[str, float] = {}

        if not speed_only:
            camera_rules = [
                r for r in self._rules
                if not r.get("camera_id") or r.get("camera_id") == camera_id
            ]
            scaled_rules = self._scale_rules_to_frame(camera_rules, w, h)
            all_events.extend(self.event_generator.process_frame(camera_id, track_dicts_inframe, scaled_rules, ts))

            for evt in all_events:
                if evt.get("event_type") != "line_cross":
                    continue
                line_id = evt.get("line_id")
                track_id = evt.get("track_id")
                if line_id is None or track_id is None:
                    continue
                line_cfg = self._line_configs.get(camera_id, {}).get(str(line_id))
                key = (camera_id, track_id)
                hist = self._track_history.get(key, [])
                if line_cfg and len(hist) >= 2:
                    direction = self.behavior.crossing_direction(
                        hist[-2], hist[-1],
                        line_cfg.get("start", line_cfg.get("start_point", {})),
                        line_cfg.get("end", line_cfg.get("end_point", {})),
                    )
                else:
                    direction = str(evt.get("direction", "unknown"))
                self.behavior.record_line_cross(camera_id, str(line_id), track_id, direction, now_ts)

            for sig in self.behavior.evaluate_line_behaviors(camera_id, now_ts):
                evt_type = BEHAVIOR_EVENT_TYPES.get(sig.label, "behavior_anomaly")
                all_events.append(self.event_generator.emit_behavior_event(
                    camera_id, sig.track_id, evt_type, sig.confidence,
                    {"behavior": sig.label.value, **sig.details}, ts,
                ))

            for evt in all_events:
                if evt.get("event_type") == "zone_enter" and evt.get("zone_id"):
                    self.state_engine.set_zone(camera_id, evt["track_id"], evt["zone_id"], True)
                elif evt.get("event_type") == "zone_exit" and evt.get("zone_id"):
                    self.state_engine.set_zone(camera_id, evt["track_id"], evt["zone_id"], False)

            _, state_events, zone_dwell = self.state_engine.update(camera_id, frame_id, track_dicts_inframe, ts)
            all_events.extend(state_events)

            frame_histories = {
                t["track_id"]: self._track_history.get((camera_id, t["track_id"]), [])
                for t in track_dicts_inframe
            }
            frame_bbox_histories = {
                t["track_id"]: [
                    h["bbox"] for h in self._bbox_history.get((camera_id, t["track_id"]), [])
                ]
                for t in track_dicts_inframe
            }
            behavior_signals = self.behavior.evaluate_frame(
                track_dicts_inframe, frame_histories, frame_bbox_histories
            )
            all_events.extend(
                self.event_generator.emit_behavior_signals(camera_id, behavior_signals, ts)
            )

            speeds = [t.get("metadata", {}).get("speed_kmh", 0) for t in track_dicts_inframe]
            avg_speed = sum(speeds) / max(len(speeds), 1)
            scene_kw: dict[str, Any] = {}
            if rt.get("density_threshold") is not None:
                scene_kw["density_threshold"] = float(rt["density_threshold"])
            if rt.get("crowd_threshold") is not None:
                scene_kw["crowd_threshold"] = int(rt["crowd_threshold"])
            if rt.get("vehicle_threshold") is not None:
                scene_kw["vehicle_threshold"] = int(rt["vehicle_threshold"])
            _, scene_events = self.scene.analyze(
                camera_id, track_dicts_inframe, float(w * h), avg_speed, **scene_kw,
            )
            all_events.extend(scene_events)

            vehicle_count = len([
                t for t in track_dicts_inframe
                if t.get("class_name") in ("car", "truck", "bus", "motorcycle")
            ])

            for t in track_dicts_inframe:
                calib_result = calib.update_track(
                    camera_id, t["track_id"],
                    t["bbox"]["x"] + t["bbox"]["width"] / 2,
                    t["bbox"]["y"] + t["bbox"]["height"] / 2,
                    now_ts, t["class_name"],
                )
                speed_evt = calib_result.get("speed_event")
                if speed_evt:
                    meta: dict[str, Any] = {"speed_kmh": t.get("metadata", {}).get("speed_kmh", 0)}
                    if speed_evt == "sudden_stop":
                        meta["vehicle_count"] = vehicle_count
                        if calib_result.get("prior_speed_kmh") is not None:
                            meta["prior_speed_kmh"] = calib_result["prior_speed_kmh"]
                    all_events.append(self.event_generator.emit_behavior_event(
                        camera_id, t["track_id"], speed_evt, 0.8,
                        meta, ts, "warning",
                    ))

            persons = [t for t in track_dicts_inframe if t.get("class_name") == "person"]
            all_events.extend(self.abandoned.process(camera_id, track_dicts_inframe, persons, ts))
            all_events.extend(self.scene_correlation.analyze(camera_id, track_dicts_inframe, zone_dwell, ts))
            all_events.extend(self._correlation_events(camera_id, all_events, track_dicts_inframe, ts))

            quality_events = self._check_video_quality(camera_id, frame, ts)
            all_events.extend(quality_events)

            all_events.extend(self.face_engine.process_frame(camera_id, frame, ts))

            gated_tracks = [t for t in track_dicts if self._track_in_capability_zone(camera_id, t, "plate_ocr")]
            if gated_tracks:
                all_events.extend(self.plate_engine.process_frame(camera_id, frame, gated_tracks, ts))

        # Dedicated, zone-driven red-light pipeline (color classification + synergy).
        if tl_active:
            all_events.extend(
                self.traffic_light.process_frame(camera_id, frame, track_dicts, ts, zones_cfg)
            )
        # Dedicated secondary ONNX models for cabin violations (phone, seatbelt).
        zone_behaviors = {str(z.get("behavior", "")) for z in zones_cfg}
        cabin_active = "driver_cabin" in zone_behaviors or "phone_use" in zone_behaviors or "seatbelt" in zone_behaviors
        if not speed_only:
            if self.secondary.camera_has_behavior(zones_cfg):
                all_events.extend(
                    self.secondary.process_frame(camera_id, frame, track_dicts, zones_cfg, ts)
                )
            # Legacy heuristics only as fallback on driver-cabin cameras (never on feux/ligne/décompte).
            all_events.extend(
                self.road_enforcement.process_frame(
                    camera_id, frame, track_dicts, ts, zones_cfg,
                    disable_red_light=tl_active,
                    disable_phone=not cabin_active,
                    disable_seatbelt=not cabin_active,
                )
            )
        # Zone-distance speed measurement (real metres → km/h).
        # Cabin cameras (phone_use / seatbelt) are mutually exclusive with
        # speed-measurement: running zone_speed on a driver-cabin feed wastes
        # GPU/CPU cycles and can be caused by a misconfigured zone in the DB.
        if not cabin_active and self.zone_speed.camera_has_behavior(zones_cfg):
            all_events.extend(
                self.zone_speed.process_frame(
                    camera_id, track_dicts, zones_cfg, w, h, now_ts, ts,
                    frame_wall_ts=frame_wall_ts,
                    segment_frame_index=segment_ctx.frame_index if segment_ctx else None,
                )
            )

        # Plate ↔ vehicle linking: enrich violation events with the plate read on
        # the same vehicle track this frame (red light, speeding, phone, seatbelt).
        self._link_plates_to_violations(camera_id, all_events)

        if settings.frigate_evidence and settings.frigate_track_binding_enabled:
            self.evidence.update_frigate_bindings(
                camera_id, track_dicts, frame_w=w, frame_h=h, wall_ts=frame_wall_ts,
            )

        for t in track_dicts:
            if not self._track_in_capability_zone(camera_id, t, "speed_estimate"):
                continue
            spd = t.get("metadata", {}).get("speed_kmh")
            plate = next(
                (e.get("plate_number") for e in all_events if e.get("track_id") == t.get("track_id") and e.get("plate_number")),
                None,
            )
            zone_id = next(
                (e.get("zone_id") for e in all_events if e.get("track_id") == t.get("track_id") and e.get("zone_id")),
                None,
            )
            if spd is not None and float(spd) > 0:
                all_events.append({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "vehicle_corridor",
                    "event": "vehicle_corridor",
                    "timestamp": ts,
                    "track_id": t.get("track_id"),
                    "class_name": t.get("class_name"),
                    "zone_id": zone_id,
                    "plate_number": plate,
                    "speed_kmh": spd,
                    "bbox": t.get("bbox"),
                    "confidence": t.get("confidence", 0.8),
                    "severity": "info",
                })

        for evt in all_events:
            if self._org_ids.get(camera_id):
                evt["org_id"] = self._org_ids[camera_id]
            evt.setdefault("event", evt.get("event_type"))
            tid = evt.get("track_id")
            fh, fw = frame.shape[:2]

            def _evt_bbox_invalid() -> bool:
                bb = evt.get("bbox")
                if bb is None:
                    return True
                if isinstance(bb, dict) and not bb:
                    return True
                return not bbox_valid(bb, min_frac=0.02)

            if tid is not None and segment_ctx is None:
                hist = self._bbox_history.get((camera_id, int(tid)), [])
                last_fb = hist[-1] if hist else None
                best, best_ts, bbox_src = resolve_emission_track_bbox(
                    evt, track_dicts, fw, fh, frame_wall_ts, last_bbox_fallback=last_fb,
                )
                if best:
                    evt["bbox"] = best
                    evt["bbox_ts"] = best_ts if best_ts is not None else frame_wall_ts
                    evt["bbox_source"] = bbox_src
                    meta = evt.setdefault("metadata", {})
                    if isinstance(meta, dict):
                        meta["bbox_source"] = bbox_src
                elif not _evt_bbox_invalid():
                    evt.setdefault("bbox_source", "event_fallback")
                    evt["bbox_ts"] = frame_wall_ts
                    meta = evt.setdefault("metadata", {})
                    if isinstance(meta, dict):
                        meta.setdefault("bbox_source", "event_fallback")
                elif _evt_bbox_invalid():
                    for t in track_dicts:
                        if t.get("track_id") == tid and t.get("bbox"):
                            bb = normalize_bbox(t["bbox"], fw, fh)
                            if bbox_valid(bb, min_frac=0.02):
                                evt["bbox"] = bb
                                evt["bbox_ts"] = frame_wall_ts
                                evt["bbox_source"] = "emission_track"
                                break
            elif tid is not None and segment_ctx is not None and _evt_bbox_invalid():
                for t in track_dicts:
                    if t.get("track_id") == tid and t.get("bbox"):
                        bb = normalize_bbox(t["bbox"], fw, fh)
                        if bbox_valid(bb, min_frac=0.02):
                            evt["bbox"] = bb
                            evt["bbox_ts"] = frame_wall_ts
                            evt.setdefault("segment_bbox_frame_index", segment_ctx.frame_index)
                            break
            evt.setdefault("bbox_ts", frame_wall_ts)
            evidence_frame = frame
            if segment_ctx is not None:
                evt.setdefault("segment_cycle_id", segment_ctx.cycle_id)
                evt.setdefault("segment_frame_index", segment_ctx.frame_index)
                evt.setdefault("segment_frame_pts", segment_ctx.frame_pts)
                evt.setdefault("segment_path", segment_ctx.segment_path)
                evt.setdefault("segment_start_wall", segment_ctx.segment_start_wall)
                bbox_idx = evt.get("segment_bbox_frame_index")
                bbox_pts = segment_pts_from_frame_index(bbox_idx, segment_ctx.ingest_fps)
                if bbox_pts is None:
                    bbox_pts = segment_pts_from_bbox_ts(
                        evt.get("bbox_ts"), segment_ctx.segment_start_wall,
                    )
                if bbox_pts is None:
                    bbox_pts = segment_ctx.frame_pts
                evt["segment_bbox_pts"] = bbox_pts
                if bbox_idx is not None:
                    try:
                        want_idx = int(bbox_idx)
                        if want_idx != segment_ctx.frame_index:
                            cached = self._segment_replay_cache.get_bgr(
                                camera_id, segment_ctx.cycle_id, want_idx,
                            )
                            if cached is not None:
                                evidence_frame = cached
                            else:
                                evidence_frame = read_segment_frame_by_index(
                                    segment_ctx.segment_path, want_idx, fw, fh,
                                )
                    except (TypeError, ValueError):
                        pass
            if settings.frigate_evidence and settings.frigate_track_binding_enabled:
                # Red-light re-correlates at capture time — binder ids are often stale
                # (box behind the vehicle on the Frigate snapshot).
                if str(evt.get("event_type") or "") not in ("red_light_violation", "speeding"):
                    self.evidence.inject_frigate_binding(camera_id, evt)
            self._publish_event_with_evidence(
                camera_id, evt, evidence_frame, track_dicts, frame_wall_ts, segment_ctx,
            )

        payload = frame_result.to_mqtt_payload()
        for i, det in enumerate(payload.get("detections", [])):
            if i < len(track_dicts):
                det["metadata"] = track_dicts[i].get("metadata", {})
        self._emit_detection_payload(
            camera_id, payload, track_dicts, w, h, capture_wall_ts, frame_wall_ts,
            overlay_coast=0, overlay_only=False,
            publish_frame_index=publish_frame_index,
        )
        return frame_result

    def _publish_overlay_predict(
        self,
        camera_id: str,
        frame_id: int,
        width: int,
        height: int,
        capture_wall_ts: float | None,
        frame_wall_ts: float,
        skip: int,
        publish_frame_index: int | None = None,
    ) -> None:
        tracker = self._trackers.get(camera_id)
        if tracker is None:
            return
        steps = max(1.0, float(skip)) * 2.0
        with self._tracker_lock:
            track_dicts = tracker.overlay_snapshot(max_coast=2, predict_steps=steps)
        if not track_dicts:
            return
        cached = self._latest_detection_payload.get(camera_id) or {}
        payload = {
            "camera_id": camera_id,
            "timestamp": cached.get("timestamp"),
            "frame_id": frame_id,
            "resolution": {"width": width, "height": height},
            "detections": cached.get("detections") or [],
            "overlay_only": True,
        }
        self._emit_detection_payload(
            camera_id, payload, track_dicts, width, height,
            capture_wall_ts, frame_wall_ts, overlay_coast=2, overlay_only=True,
            publish_frame_index=publish_frame_index,
        )

    def _emit_detection_payload(
        self,
        camera_id: str,
        payload: dict[str, Any],
        track_dicts: list[dict[str, Any]],
        width: int,
        height: int,
        capture_wall_ts: float | None,
        frame_wall_ts: float,
        *,
        overlay_coast: int,
        overlay_only: bool,
        publish_frame_index: int | None = None,
    ) -> None:
        infer_wall = time.time()
        capture_src = capture_wall_ts if capture_wall_ts is not None else frame_wall_ts
        payload["capture_ts"] = datetime.fromtimestamp(capture_src, tz=timezone.utc).isoformat()
        payload["infer_ts"] = datetime.fromtimestamp(infer_wall, tz=timezone.utc).isoformat()
        queue_ms = round(max(0.0, (infer_wall - capture_src) * 1000), 1)
        payload["queue_latency_ms"] = queue_ms
        payload["pipeline_mode"] = (
            "frigate"
            if settings.frigate_enabled and settings.frigate_live
            else (
                "burn_in"
                if settings.go2rtc_publish_enabled and settings.burn_in_overlay and settings.unified_pipeline
                else ("pull" if settings.unified_pipeline else "legacy")
            )
        )
        payload["publish_frame_index"] = publish_frame_index or payload.get("frame_id", 0)
        if settings.go2rtc_publish_enabled and settings.unified_pipeline:
            payload["video_lead_ms"] = 120.0
        else:
            payload["video_lead_ms"] = round(850.0 + queue_ms * 0.4, 1)
        tracker = self._trackers.get(camera_id)
        if tracker and overlay_coast == 0:
            with self._tracker_lock:
                overlay_src = tracker.overlay_snapshot(max_coast=0, predict_steps=0.0)
        else:
            overlay_src = track_dicts
        payload["overlay_detections"] = build_overlay_detections(
            overlay_src, width, height, max_coast=overlay_coast,
        )
        payload["overlay_only"] = overlay_only
        self._latest_detection_payload[camera_id] = payload
        if self._detection_broadcaster is not None:
            self._detection_broadcaster.publish(camera_id, payload)
        if not overlay_only:
            self.mqtt.publish_detection(camera_id, payload)

    def _publish_event_with_evidence(
        self,
        camera_id: str,
        evt: dict[str, Any],
        frame: np.ndarray,
        track_dicts: list[dict[str, Any]],
        frame_wall_ts: float,
        segment_ctx: SegmentCaptureContext | None,
    ) -> None:
        org_id = self._org_ids.get(camera_id, "")
        if not org_id:
            self.mqtt.publish_event(camera_id, evt)
            return
        et = str(evt.get("event_type") or evt.get("event") or "")
        if et in ("vehicle_corridor", "vehicle_count_threshold"):
            return
        if self._is_speed_only_camera(camera_id) and et in self._SPEED_ONLY_SKIP_EVENTS:
            return
        policy = self.evidence._gate.match_policy(camera_id, evt)
        should_capture = policy is not None or et in self._PLATE_LINKED_EVENTS
        if should_capture:
            force = policy is None and et in self._PLATE_LINKED_EVENTS
            pol = policy if policy is not None else (default_evidence_policy() if force else None)
            if pol is not None:
                if segment_ctx is not None:
                    # Synchronous capture: segment MP4 is deleted after replay.
                    capture_pts = evt.get("segment_bbox_pts", segment_ctx.frame_pts)
                    try:
                        capture_pts = float(capture_pts)
                    except (TypeError, ValueError):
                        capture_pts = segment_ctx.frame_pts
                    cap_idx = evt.get("segment_bbox_frame_index")
                    try:
                        cap_frame_index = int(cap_idx) if cap_idx is not None else segment_ctx.frame_index
                    except (TypeError, ValueError):
                        cap_frame_index = segment_ctx.frame_index
                    self.evidence.capture_from_segment(
                        org_id,
                        camera_id,
                        evt,
                        frame.copy(),
                        segment_ctx.segment_path,
                        capture_pts,
                        pol,
                        cycle_id=segment_ctx.cycle_id,
                        frame_index=cap_frame_index,
                    )
                else:
                    # Never block the RTSP infer thread on Frigate clip downloads.
                    self.evidence.attach_evidence(
                        camera_id, org_id, evt, frame.copy(), policy=pol,
                        frame_ts=frame_wall_ts, async_upload=True,
                    )
        if et in self._EVIDENCE_MANDATORY and not self._event_has_package(evt):
            evt.setdefault("evidence_status", "pending")
        self.mqtt.publish_event(camera_id, evt)

    def process_segment_eof(
        self,
        camera_id: str,
        timeline: FrameTimeline,
        segment_ctx: SegmentCaptureContext,
        source_fps: float = 25.0,
    ) -> None:
        """Finalize zone-speed crossings still open at end of a recorded segment."""
        zones_cfg = (self._spatial_configs.get(camera_id) or {}).get("zones") or []
        if not self.zone_speed.camera_has_behavior(zones_cfg):
            return
        w, h = self._frame_shape.get(camera_id, (1920, 1080))
        ts = timeline.iso_timestamp or datetime.now(timezone.utc).isoformat()
        all_events = self.zone_speed.process_frame(
            camera_id,
            [],
            zones_cfg,
            w,
            h,
            timeline.monotonic,
            ts,
            frame_wall_ts=timeline.wall,
        )
        self._link_plates_to_violations(camera_id, all_events)
        segment_start_wall = segment_ctx.segment_start_wall
        max_pts = segment_ctx.frame_pts
        for evt in all_events:
            if self._org_ids.get(camera_id):
                evt["org_id"] = self._org_ids[camera_id]
            evt.setdefault("event", evt.get("event_type"))
            frame_idx = evt.get("segment_bbox_frame_index")
            bbox_pts = segment_pts_from_frame_index(frame_idx, segment_ctx.ingest_fps)
            if bbox_pts is None:
                bbox_pts = segment_pts_from_bbox_ts(evt.get("bbox_ts"), segment_start_wall)
            if bbox_pts is None:
                bbox_pts = max_pts
            else:
                bbox_pts = min(bbox_pts, max_pts)
            evt["segment_cycle_id"] = segment_ctx.cycle_id
            evt["segment_frame_index"] = segment_ctx.frame_index
            evt["segment_frame_pts"] = segment_ctx.frame_pts
            evt["segment_path"] = segment_ctx.segment_path
            evt["segment_start_wall"] = segment_start_wall
            evt["segment_bbox_pts"] = bbox_pts
            if frame_idx is not None:
                try:
                    want_idx = int(frame_idx)
                    cached = self._segment_replay_cache.get_bgr(
                        camera_id, segment_ctx.cycle_id, want_idx,
                    )
                    evidence_frame = cached if cached is not None else read_segment_frame_by_index(
                        segment_ctx.segment_path, want_idx, w, h,
                    )
                except (TypeError, ValueError):
                    evidence_frame = read_segment_frame_bgr(
                        segment_ctx.segment_path, bbox_pts, w, h,
                    )
            else:
                evidence_frame = read_segment_frame_bgr(
                    segment_ctx.segment_path, bbox_pts, w, h,
                )
            aligned_ctx = SegmentCaptureContext(
                segment_path=segment_ctx.segment_path,
                cycle_id=segment_ctx.cycle_id,
                frame_index=int(frame_idx) if frame_idx is not None else segment_ctx.frame_index,
                frame_pts=bbox_pts,
                segment_start_wall=segment_start_wall,
                ingest_fps=segment_ctx.ingest_fps,
            )
            self._publish_event_with_evidence(
                camera_id,
                evt,
                evidence_frame,
                [],
                timeline.wall,
                aligned_ctx,
            )

    @staticmethod
    def _read_segment_frame(
        segment_path: str, frame_pts: float, width: int, height: int,
    ) -> np.ndarray:
        """Load a BGR frame from a segment MP4 for EOF evidence crops."""
        return read_segment_frame_bgr(segment_path, frame_pts, width, height)

    # Violation events that benefit from a linked plate number.
    _PLATE_LINKED_EVENTS = {
        "red_light_violation",
        "speeding",
        "phone_use_violation",
        "seatbelt_violation",
        "vehicle_corridor",
        "wrong_way",
    }
    _EVIDENCE_MANDATORY = {
        "red_light_violation",
        "speeding",
        "phone_use_violation",
        "seatbelt_violation",
    }

    @staticmethod
    def _event_has_package(evt: dict[str, Any]) -> bool:
        pkg = evt.get("package")
        if isinstance(pkg, dict) and (pkg.get("clip") or pkg.get("images")):
            return True
        ev = evt.get("evidence")
        if isinstance(ev, dict):
            inner = ev.get("package")
            if isinstance(inner, dict) and (inner.get("clip") or inner.get("images")):
                return True
        return False

    def _link_plates_to_violations(self, camera_id: str, events: list[dict[str, Any]]) -> None:
        """Copy plate reads onto violation events (same frame, then per-track cache)."""
        plate_by_track: dict[Any, tuple[str, float]] = {}
        for e in events:
            tid = e.get("track_id")
            plate = e.get("plate_number")
            if tid is None or int(tid) < 0 or not plate:
                continue
            conf = float(e.get("plate_confidence", 0) or 0)
            prev = plate_by_track.get(tid)
            if prev is None or conf > prev[1]:
                plate_by_track[tid] = (plate, conf)
        for e in events:
            et = e.get("event_type") or e.get("event")
            if et not in PipelineService._PLATE_LINKED_EVENTS:
                continue
            if e.get("plate_number"):
                continue
            tid = e.get("track_id")
            linked = plate_by_track.get(tid) if tid is not None else None
            if not linked and tid is not None and int(tid) >= 0:
                linked = self.plate_engine.get_last_plate(camera_id, int(tid))
            if linked:
                e["plate_number"] = linked[0]
                e["plate_confidence"] = linked[1]
                meta = e.setdefault("metadata", {})
                meta["plate_number"] = linked[0]
                meta["plate_confidence"] = linked[1]

    def _correlation_events(
        self,
        camera_id: str,
        events: list[dict[str, Any]],
        track_dicts: list[dict[str, Any]],
        ts: str,
    ) -> list[dict[str, Any]]:
        """Emit multi-camera identity correlation events from zone crossings."""
        class_by_track = {t["track_id"]: t.get("class_name", "person") for t in track_dicts}
        correlated: list[dict[str, Any]] = []

        for evt in events:
            et = evt.get("event_type") or evt.get("event")
            track_id = evt.get("track_id", -1)
            if track_id is None or int(track_id) < 0:
                continue
            class_name = evt.get("class_name") or class_by_track.get(int(track_id), "person")

            if et == "zone_exit":
                self.correlation.record_exit(camera_id, int(track_id), str(class_name), ts)
            elif et == "zone_enter":
                correlated.extend(
                    self.correlation.correlate_entry(camera_id, int(track_id), str(class_name), ts)
                )

        return correlated

    def _check_video_quality(self, camera_id: str, frame: np.ndarray, ts: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if brightness < 30:
            events.append({
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": "video_darkness",
                "timestamp": ts,
                "severity": "warning",
                "track_id": -1,
                "metadata": {"brightness": brightness},
            })
        # J.86 stub: require consecutive blurry frames before emitting video_blur.
        min_blur_frames = 2
        if blur_score < 50:
            streak = self._blur_streak.get(camera_id, 0) + 1
            self._blur_streak[camera_id] = streak
            if streak >= min_blur_frames:
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id,
                    "event_type": "video_blur",
                    "timestamp": ts,
                    "severity": "info",
                    "track_id": -1,
                    "metadata": {"blur_score": blur_score, "frame_streak": streak},
                })
        else:
            self._blur_streak[camera_id] = 0
        return events
```

### 1.2 `frigate_track_evidence.py` (fichier complet)

- Path: `ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py`
- Lines: 1775

```python
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
        meta0 = evt.get("metadata") if isinstance(evt.get("metadata"), dict) else {}
        soft_ia_used = (
            meta0.get("frigate_red_light_soft_iou") is not None
            or meta0.get("frigate_speed_soft_iou") is not None
        )
        ia_norm_meta = normalize_bbox(ia_bbox, 1920, 1080) if ia_bbox else None
        using_ia_bbox = soft_ia_used or (
            ia_norm_meta
            and norm_bbox
            and not frigate_bbox_embedded
            and all(
                abs(float(norm_bbox.get(k, 0)) - float(ia_norm_meta.get(k, 0))) < 0.02
                for k in ("x", "y", "w", "h")
            )
        )
        if frigate_bbox_embedded or (event_id and norm_bbox and not using_ia_bbox):
            bbox_source = "frigate_mqtt"
        elif using_ia_bbox:
            bbox_source = "ia_overlay"
        else:
            bbox_source = "emission_track"
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
        frigate_norm_bbox = norm_bbox  # from _frigate_box_from_event(matched) — preserve origin
        ia_fallback = False
        frigate_bbox_drawn = False

        # Demo soft-accept only (IoU mismatch): overlay IA offender — never default road rules.
        soft_frame = clean_frame
        soft_bytes = clean_bytes
        if soft_ia and soft_frame is None and scene_bytes:
            soft_frame = cv2.imdecode(np.frombuffer(scene_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            soft_bytes = scene_bytes
        if soft_ia and soft_frame is not None and ia_norm and bbox_region_has_content(soft_frame, ia_norm):
            if clean_bytes and clean_frame is not None and bbox_region_has_content(clean_frame, ia_norm):
                scene_out = clean_bytes
                soft_frame = clean_frame
            else:
                scene_out = soft_bytes
            norm_bbox = ia_norm
            frigate_bbox_embedded = False
            ia_fallback = True
            bbox_quality_ok = True
            images_spec = policy.get("images") or default_evidence_policy()["images"]
            drawn_scene, subject_bytes, _ = capture_images_from_policy(
                soft_frame, ia_norm, images_spec, JPEG_QUALITY, draw_bbox=True,
            )
            if drawn_scene:
                scene_out = drawn_scene
            logger.info(
                "frigate_track: soft-accept IA bbox cam=%s event=%s",
                camera_id[:8], event_id[:24],
            )
            return scene_out, norm_bbox, frigate_bbox_embedded, bbox_quality_ok, subject_bytes

        # Prefer native Frigate snapshot (bbox burned in) when scene is the bbox=1 JPEG.
        if scene_out and clean_bytes and scene_out == scene_bytes and norm_bbox:
            check_frame = clean_frame
            if check_frame is not None and bbox_region_has_content(check_frame, norm_bbox):
                frigate_bbox_embedded = True
                bbox_quality_ok = True
                return scene_out, norm_bbox, frigate_bbox_embedded, bbox_quality_ok, subject_bytes

        # Frigate coords valid on clean/scene — draw Frigate box (not IA) on the scene frame.
        scene_frame = None
        if scene_out:
            scene_frame = cv2.imdecode(np.frombuffer(scene_out, dtype=np.uint8), cv2.IMREAD_COLOR)
        validate_frame = clean_frame if clean_frame is not None else scene_frame
        if (
            validate_frame is not None
            and norm_bbox
            and bbox_region_has_content(validate_frame, norm_bbox)
        ):
            if scene_frame is not None and not frigate_bbox_embedded:
                images_spec = policy.get("images") or default_evidence_policy()["images"]
                drawn_scene, subject_bytes, _ = capture_images_from_policy(
                    scene_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=True,
                )
                if drawn_scene:
                    scene_out = drawn_scene
                    frigate_bbox_drawn = True
            frigate_bbox_embedded = frigate_bbox_embedded or False
            bbox_quality_ok = True
            logger.info(
                "frigate_track: Frigate bbox on scene cam=%s event=%s embedded=%s drawn=%s",
                camera_id[:8], event_id[:24], frigate_bbox_embedded, frigate_bbox_drawn,
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
```

### 1.3 `frigate_track_binder.py` (fichier complet)

- Path: `ai-engine/src/citevision_ai/evidence/frigate_track_binder.py`
- Lines: 131

```python
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
```

### 1.4 `evidence/service.py` (wrappers update/inject)

- Path: `ai-engine/src/citevision_ai/evidence/service.py`
- Lines: 1378

```python
from __future__ import annotations

import ctypes
import cv2
import gc
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from typing import Any

# Force glibc to return freed arenas to the OS after each clip encode.
# Without this, Python's numpy/ffmpeg decompression of 144 frames × 25 MB (4K)
# fragments the heap. Over hundreds of captures the RSS silently grows to 25 GB.
def _trim_malloc() -> None:
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

from citevision_ai.evidence.buffer import FrameRingBuffer
from citevision_ai.evidence.capture import (
    bbox_from_event,
    bbox_region_has_content,
    capture_images_from_policy,
    normalize_bbox,
    subject_jpeg_texture,
)
from citevision_ai.evidence.config import (
    CLIP_DURATION_SEC,
    FRAME_ALIGN_TOLERANCE_SEC,
    JPEG_QUALITY,
    RING_FPS,
    RING_SECONDS,
)
from citevision_ai.evidence.frigate_backend import FrigateEvidenceBackend
from citevision_ai.evidence.frigate_track_binder import FrigateTrackBinder
from citevision_ai.evidence.gate import EvidenceCaptureGate, default_evidence_policy
from citevision_ai.evidence.uploader import EvidenceUploader
from citevision_ai.config import settings
from citevision_ai.evidence.segment_align import resolve_segment_capture_frame, segment_pts_from_bbox_ts
from citevision_ai.evidence.segment_replay_cache import SegmentReplayCache

logger = logging.getLogger(__name__)

SUBJECT_MIN_TEXTURE = 50.0
_EMISSION_BBOX_SOURCES = frozenset({"emission_track", "last_known", "event_fallback"})


def probe_media_duration(path: str) -> float | None:
    """Return media duration in seconds via ffprobe, or None."""
    if not os.path.isfile(path):
        return None
    ffprobe = shutil.which("ffprobe") or "/usr/bin/ffprobe"
    if not os.path.isfile(ffprobe):
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if proc.returncode != 0:
            return None
        val = float(proc.stdout.strip())
        return val if val > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def extract_subclip_mp4(segment_path: str, center_pts: float, duration_sec: float) -> bytes | None:
    """Cut a sub-clip from a segment MP4 centred on ``center_pts`` (seconds)."""
    if not shutil.which("ffmpeg") or not os.path.isfile(segment_path):
        return None
    media_dur = probe_media_duration(segment_path)
    if media_dur is not None and media_dur > 0:
        center_pts = min(max(0.0, center_pts), max(0.0, media_dur - 0.05))
        duration_sec = min(duration_sec, media_dur)
    half = duration_sec / 2.0
    start = max(0.0, center_pts - half)
    if media_dur is not None:
        start = min(start, max(0.0, media_dur - duration_sec))
        duration_sec = min(duration_sec, max(0.1, media_dur - start))
    tmp = tempfile.mkdtemp(prefix="cv_seg_clip_")
    out_path = os.path.join(tmp, "clip.mp4")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", segment_path,
            "-ss", f"{start:.3f}",
            "-t", f"{duration_sec:.3f}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-preset", "veryfast",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
        if result.returncode != 0:
            logger.warning("segment subclip ffmpeg failed: %s", result.stderr[-400:])
            return None
        with open(out_path, "rb") as f:
            data = f.read()
        if len(data) < 1000:
            return None
        nf = probe_frame_count(out_path)
        if nf is None or nf < 2:
            return None
        return data
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("segment subclip error: %s", exc)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_frame_count(path: str) -> int | None:
    ffprobe = shutil.which("ffprobe") or "/usr/bin/ffprobe"
    if not os.path.isfile(ffprobe):
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-count_frames", "-show_entries", "stream=nb_read_frames",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if proc.returncode != 0:
            return None
        return int(proc.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


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
    # Limit concurrent clip-encoding threads to prevent OOM.
    # Two separate semaphores prevent background-attachment threads from starving the
    # retroactive HTTP path (rules-engine evidence requests).
    #
    # Background threads (attach_evidence_async / attach_segment_evidence_async):
    #   These fire at event time, are not retried, and are best-effort.  Limit to 2.
    # Retroactive HTTP (capture_retroactive):
    #   Called repeatedly by the rules-engine (up to 8 retries); must succeed for alerts.
    #   Allow up to 4 concurrent captures — each uses ~200 MB (post inline-downscale),
    #   so 4 × 200 MB ≈ 800 MB peak, well within the 28 GB system budget.
    # Background attachment: increased to 8 so evidence is cached quickly before
    # the rules-engine first retry (8s). 8 × ~200 MB (post inline-downscale) ≈ 1.6 GB peak.
    _ENCODE_SEM = threading.BoundedSemaphore(8)
    # Retroactive HTTP: 4 concurrent, but with a SHORT timeout (5s) so the HTTP
    # call returns quickly and the rules-engine retries at 8s intervals. By then
    # the background thread has already populated the cache for most events.
    _RETRO_SEM = threading.BoundedSemaphore(4)
    _CACHE_MAX = 500                               # max entries in evidence cache
    # Speeding fires many MQTT events per track; one Frigate capture per track
    # within this window prevents encode-semaphore stampede (100 clips → drops).
    _SPEED_EVIDENCE_DEDUPE_SEC = 90.0

    def __init__(self) -> None:
        self._buffers: dict[str, FrameRingBuffer] = {}
        self._gate = EvidenceCaptureGate()
        # event_id → uploaded evidence package (populated by background capture).
        # capture_retroactive checks this first so the rules-engine gets the already-
        # uploaded package without re-capturing, eliminating semaphore contention.
        self._evidence_cache: dict[str, dict] = {}
        self._uploader = EvidenceUploader()
        self._segment_replay_cache: SegmentReplayCache | None = None
        self._frigate = FrigateEvidenceBackend()
        self._frigate_binder = FrigateTrackBinder(self._frigate_track)
        # Speeding: one Frigate capture per (camera, track) within the window.
        # Never gate the whole camera — that reuses one scene for every alert.
        self._speed_evidence_dedupe: dict[tuple[str, str], float] = {}
        self._speed_evidence_inflight: set[tuple[str, str]] = set()
        self._speed_evidence_ok: dict[tuple[str, str], float] = {}
        self._speed_evidence_last: dict[tuple[str, str], dict[str, Any]] = {}
        self._speed_evidence_lock = threading.Lock()
        # Demo loop clock: wall epoch at last demo activate / first buffer push.
        self._demo_loop_epoch: dict[str, float] = {}

    def update_frigate_bindings(
        self,
        camera_id: str,
        tracks: list[dict[str, Any]],
        *,
        frame_w: int,
        frame_h: int,
        wall_ts: float,
    ) -> None:
        self._frigate_binder.update_tracks(
            camera_id, tracks, frame_w=frame_w, frame_h=frame_h, wall_ts=wall_ts,
        )

    def inject_frigate_binding(self, camera_id: str, evt: dict[str, Any]) -> None:
        self._frigate_binder.inject_event(camera_id, evt)

    def _evidence_backend_mode(self) -> str:
        if settings.demo_mode:
            mode = (settings.demo_evidence_backend or "").strip().lower()
            if mode:
                return mode
        return (settings.evidence_backend or "ring_buffer").strip().lower()

    @property
    def _frigate_track(self):
        return self._frigate._track

    def reset_demo_activate(self, camera_id: str, previous_camera_id: str | None = None) -> None:
        """Reset Frigate timeline offsets and analytics state after demo source switch."""
        self._frigate_track.reset_demo_offset(camera_id)
        self._frigate_binder.clear_camera(camera_id)
        self._demo_loop_epoch[camera_id] = time.time()
        if previous_camera_id and previous_camera_id != camera_id:
            self._frigate_track.reset_demo_offset(previous_camera_id)
            self._frigate_binder.clear_camera(previous_camera_id)
            self._demo_loop_epoch.pop(previous_camera_id, None)

    # Cabin-camera event types: Frigate only tracks vehicles/persons passing a scene,
    # not driver-cabin close-ups. Attempting Frigate downloads for these event types
    # always fails with IncompleteRead (Frigate returns a corrupt/empty clip), and each
    # failed attempt holds its partial bytes in memory — causing multi-GB OOM when
    # many events are processed concurrently. Skip Frigate entirely for cabin events.
    _CABIN_EVENT_TYPES: frozenset[str] = frozenset({
        "seatbelt_violation",
        "seatbelt",
        "phone_use_violation",
        "phone_driving",
        "driver_phone",
        "driver_cabin",
    })

    def _try_frigate_capture(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        policy: dict[str, Any],
        images_spec: list[dict[str, Any]],
        return_upload: bool,
        *,
        live_frame=None,
        frame_ts: float | None = None,
    ) -> dict[str, Any] | None:
        mode = self._evidence_backend_mode()
        if mode not in ("frigate", "hybrid", "strict_frigate") or not self._frigate_track.enabled():
            return None
        # Skip Frigate for cabin events — see _CABIN_EVENT_TYPES docstring.
        event_type = str(evt.get("event_type") or "")
        if event_type in self._CABIN_EVENT_TYPES:
            return None
        try:
            fg = self._frigate_track.capture(
                policy, evt, org_id=org_id, camera_id=camera_id,
            )
        except Exception as exc:
            # Network/decode errors from Frigate are non-fatal in hybrid mode —
            # fall through to the ring-buffer path so the alert is never lost.
            logger.warning(
                "frigate capture exception camera=%s event=%s: %s",
                camera_id[:8], evt.get("event_id", "?"), exc,
            )
            if mode == "hybrid":
                return None
            return self._mark_frigate_failed(evt, return_upload)
        if not fg:
            return None if mode == "hybrid" else self._mark_frigate_failed(evt, return_upload)
        # Sprint 1 — structured missing (Décision 2): never upload fabricated assets.
        if str(fg.get("status") or "") == "missing" or str(
            (fg.get("meta") or {}).get("evidence_status") or ""
        ) == "missing":
            reason = str((fg.get("meta") or {}).get("abort_reason") or "missing")
            evt["evidence_status"] = "missing"
            evt["evidence_abort_reason"] = reason
            meta = fg.get("meta") if isinstance(fg.get("meta"), dict) else {}
            if meta:
                evt.setdefault("evidence_meta", meta)
            logger.info(
                "frigate capture missing camera=%s event=%s reason=%s",
                camera_id[:8], evt.get("event_id", "?"), reason,
            )
            if return_upload:
                return {"evidence_status": "missing", "abort_reason": reason, "meta": meta}
            return None
        return self._upload_capture_result(
            org_id, camera_id, str(evt.get("event_id", "")), evt, fg, images_spec, return_upload,
        )

    def _mark_frigate_failed(
        self, evt: dict[str, Any], return_upload: bool,
    ) -> dict[str, Any] | None:
        evt["evidence_status"] = "failed"
        return None if not return_upload else {"evidence_status": "failed"}

    def _upload_capture_result(
        self,
        org_id: str,
        camera_id: str,
        event_id: str,
        evt: dict[str, Any],
        captured: dict[str, Any],
        images_spec: list[dict[str, Any]],
        return_upload: bool,
    ) -> dict[str, Any] | None:
        scene = captured.get("scene")
        subject = captured.get("subject")
        clip_bytes = captured.get("clip_bytes")
        plate_jpeg = captured.get("plate_jpeg")
        extra_frames = captured.get("extra_images") or []
        meta = dict(captured.get("meta") or {})
        image_labels: dict[str, str] = {}
        for spec in images_spec:
            role = str(spec.get("role", ""))
            label = spec.get("label")
            if role and label:
                image_labels[role] = str(label)
        meta["image_labels"] = image_labels
        status = str(meta.get("evidence_status") or captured.get("status") or "partial")
        uploaded = self._uploader.upload(
            org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
            plate_jpeg=plate_jpeg, extra_frames=extra_frames,
        )
        if not uploaded:
            uploaded = self._uploader.upload(
                org_id, camera_id, event_id, scene, subject, clip_bytes, meta,
                plate_jpeg=plate_jpeg, extra_frames=extra_frames,
            )
        if uploaded:
            evt["evidence"] = uploaded
            if pkg := uploaded.get("package"):
                evt["package"] = pkg
            evt["evidence_status"] = status
            uploaded["evidence_status"] = status
            if meta.get("capture_source") == "frigate_track" and meta.get("bbox"):
                evt["bbox"] = meta["bbox"]
                evt["bbox_source"] = meta.get("bbox_source") or "frigate_mqtt"
            if meta.get("plate_number"):
                evt["plate_number"] = meta["plate_number"]
            if meta.get("plate_confidence") is not None:
                evt["plate_confidence"] = meta["plate_confidence"]
            if event_id:
                if len(self._evidence_cache) >= self._CACHE_MAX:
                    try:
                        oldest = next(iter(self._evidence_cache))
                        del self._evidence_cache[oldest]
                    except StopIteration:
                        pass
                self._evidence_cache[event_id] = uploaded
        else:
            evt["evidence_status"] = "failed"
            status = "failed"
        if return_upload:
            return uploaded
        return None

    def set_segment_replay_cache(self, cache: SegmentReplayCache) -> None:
        self._segment_replay_cache = cache

    def _resolve_segment_evidence_frame(
        self,
        camera_id: str,
        cycle_id: str,
        evt: dict[str, Any],
        frame,
        segment_path: str,
        capture_pts: float,
        frame_index: int,
        bbox: dict[str, Any] | None,
    ):
        width = frame.shape[1] if frame is not None and getattr(frame, "shape", None) else 1920
        height = frame.shape[0] if frame is not None and getattr(frame, "shape", None) else 1080
        norm_bbox = normalize_bbox(bbox, width, height) if bbox else None
        want_idx = evt.get("segment_bbox_frame_index")
        cache = self._segment_replay_cache
        if cache is not None and cycle_id and want_idx is not None:
            try:
                base = int(want_idx)
            except (TypeError, ValueError):
                base = None
            if base is not None:
                for idx in (base, base - 1, base + 1, base - 2, base + 2, base - 3, base + 3):
                    if idx < 0:
                        continue
                    cached = cache.get_bgr(camera_id, cycle_id, idx)
                    if cached is None:
                        continue
                    if norm_bbox and not bbox_region_has_content(cached, norm_bbox):
                        continue
                    evt["segment_bbox_frame_index"] = idx
                    return cached

        resolved = resolve_segment_capture_frame(
            frame,
            segment_path if segment_path and os.path.isfile(segment_path) else None,
            evt,
            capture_pts,
            width,
            height,
            current_frame_index=frame_index,
        )
        if resolved is not None and getattr(resolved, "size", 0):
            if norm_bbox and not bbox_region_has_content(resolved, norm_bbox):
                logger.warning(
                    "segment evidence bbox region empty cam=%s cycle=%s idx=%s pts=%.2f",
                    camera_id[:8], cycle_id, want_idx, capture_pts,
                )
            return resolved
        return frame

    def set_capture_rules(self, camera_id: str, rules: list[dict[str, Any]] | None) -> None:
        self._gate.set_rules(camera_id, rules)

    def _allows_ring_buffer_fallback(self, evt: dict[str, Any]) -> bool:
        """Ring-buffer allowed for hybrid/legacy, or cabin events in strict demo.

        Road rules (red_light / speeding) are fail-closed Frigate in strict_frigate:
        never silently ship demo_ring_buffer as a complete proof.
        """
        mode = self._evidence_backend_mode()
        if mode in ("ring_buffer", "hybrid", ""):
            return True
        et = str(evt.get("event_type") or "")
        if mode == "strict_frigate":
            if et in self._CABIN_EVENT_TYPES:
                return True
        return False

    def _demo_loop_meta(self, camera_id: str, bbox_ts: float | None) -> dict[str, Any]:
        """Position in the looping MP4 relative to last demo activate / first push."""
        loop_sec = float(getattr(settings, "demo_red_light_loop_sec", 352.52) or 352.52)
        epoch = self._demo_loop_epoch.get(camera_id)
        if epoch is None:
            epoch = time.time()
            self._demo_loop_epoch[camera_id] = epoch
        anchor = float(bbox_ts) if isinstance(bbox_ts, (int, float)) else time.time()
        # Wall-clock demo timeline: position = elapsed since epoch mod loop.
        pos = (anchor - epoch) % loop_sec if loop_sec > 0 else 0.0
        if pos < 0:
            pos += loop_sec
        return {
            "demo_loop_duration_sec": round(loop_sec, 3),
            "demo_loop_epoch": epoch,
            "demo_loop_position_sec": round(float(pos), 3),
        }

    def _ring_buffer_active(self) -> bool:
        mode = self._evidence_backend_mode()
        # strict_frigate keeps the buffer warm for cabin-only fallback (seatbelt/phone).
        if mode == "strict_frigate":
            return True
        return mode in ("ring_buffer", "hybrid", "")

    def _aligned_buffer_frame(self, camera_id: str, evt: dict[str, Any]):
        bbox_ts = evt.get("bbox_ts")
        buf = self._buffers.get(camera_id)
        if buf is not None and isinstance(bbox_ts, (int, float)):
            return buf.get_frame_at_ts(float(bbox_ts))
        return None

    def push_frame(self, camera_id: str, frame) -> None:
        if not self._ring_buffer_active():
            return
        buf = self._buffers.get(camera_id)
        if buf is None:
            buf = FrameRingBuffer(max_seconds=RING_SECONDS, fps=RING_FPS, jpeg_quality=JPEG_QUALITY)
            self._buffers[camera_id] = buf
        buf.maybe_push(frame)

    def _is_speeding_event(self, evt: dict[str, Any]) -> bool:
        return str(evt.get("event_type") or "") == "speeding"

    def _speed_track_key(self, camera_id: str, evt: dict[str, Any]) -> tuple[str, str] | None:
        """Stable per-track key; None when track_id missing (no camera-wide gate)."""
        track_id = evt.get("track_id")
        if track_id is None or track_id == "":
            return None
        return (camera_id, str(track_id))

    def _purge_speed_dedupe(self, now: float) -> None:
        expired = [k for k, ts in self._speed_evidence_dedupe.items() if now - ts > self._SPEED_EVIDENCE_DEDUPE_SEC]
        for k in expired:
            del self._speed_evidence_dedupe[k]
        expired_ok = [k for k, ts in self._speed_evidence_ok.items() if now - ts > self._SPEED_EVIDENCE_DEDUPE_SEC]
        for k in expired_ok:
            del self._speed_evidence_ok[k]

    def _should_skip_speed_evidence(self, camera_id: str, evt: dict[str, Any]) -> bool:
        """True when this track already has an in-flight or recent successful capture."""
        if not self._is_speeding_event(evt):
            return False
        key = self._speed_track_key(camera_id, evt)
        if key is None:
            return False
        now = time.time()
        with self._speed_evidence_lock:
            self._purge_speed_dedupe(now)
            if key in self._speed_evidence_ok or key in self._speed_evidence_inflight:
                return True
            prev = self._speed_evidence_dedupe.get(key)
            return prev is not None and now - prev < self._SPEED_EVIDENCE_DEDUPE_SEC

    def _begin_speed_evidence(self, camera_id: str, evt: dict[str, Any]) -> bool:
        """Reserve a speeding capture slot for this track. False ⇒ caller must skip."""
        if not self._is_speeding_event(evt):
            return True
        key = self._speed_track_key(camera_id, evt)
        # No track_id → allow capture (cannot safely dedupe); avoid camera-wide lock.
        if key is None:
            return True
        now = time.time()
        with self._speed_evidence_lock:
            self._purge_speed_dedupe(now)
            if key in self._speed_evidence_ok or key in self._speed_evidence_inflight:
                return False
            prev = self._speed_evidence_dedupe.get(key)
            if prev is not None and now - prev < self._SPEED_EVIDENCE_DEDUPE_SEC:
                return False
            self._speed_evidence_inflight.add(key)
            return True

    def _finish_speed_evidence(
        self,
        camera_id: str,
        evt: dict[str, Any],
        *,
        success: bool,
        uploaded: dict[str, Any] | None = None,
    ) -> None:
        if not self._is_speeding_event(evt):
            return
        key = self._speed_track_key(camera_id, evt)
        with self._speed_evidence_lock:
            if key is not None:
                self._speed_evidence_inflight.discard(key)
                if success:
                    self._speed_evidence_ok[key] = time.time()
                    self._speed_evidence_dedupe[key] = time.time()
                    if uploaded:
                        self._speed_evidence_last[key] = uploaded

    def _reuse_speed_evidence(self, camera_id: str, evt: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Return last good package for THIS track only (never another vehicle's scene)."""
        key = self._speed_track_key(camera_id, evt or {})
        if key is None:
            return None
        deadline = time.time() + 20.0
        while time.time() < deadline:
            with self._speed_evidence_lock:
                last = self._speed_evidence_last.get(key)
                inflight = key in self._speed_evidence_inflight
            if last is not None:
                logger.info(
                    "speed evidence dedupe reuse camera=%s track=%s",
                    camera_id[:8], key[1],
                )
                return last
            if not inflight:
                return None
            time.sleep(0.4)
        with self._speed_evidence_lock:
            return self._speed_evidence_last.get(key)

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
        if not force and not self._begin_speed_evidence(camera_id, evt):
            logger.info(
                "speed evidence dedupe skip camera=%s track=%s event=%s",
                camera_id[:8], evt.get("track_id"), str(evt.get("event_id") or "")[:8],
            )
            return
        speed_slot = self._is_speeding_event(evt) and not force
        try:
            if policy is None:
                if force:
                    policy = default_evidence_policy()
                else:
                    policy = self._gate.match_policy(camera_id, evt)
            if policy is None:
                if speed_slot:
                    self._finish_speed_evidence(camera_id, evt, success=False)
                return
            if async_upload:
                self.attach_evidence_async(
                    camera_id, org_id, evt, frame, policy=policy, frame_ts=frame_ts,
                    speed_slot=speed_slot,
                )
                return
            try:
                self._capture_and_attach(camera_id, org_id, evt, frame, policy, frame_ts=frame_ts)
                if speed_slot:
                    ok = str(evt.get("evidence_status") or "") in ("complete", "partial")
                    self._finish_speed_evidence(
                        camera_id, evt, success=ok, uploaded=evt.get("evidence") if ok else None,
                    )
            except Exception:
                if speed_slot:
                    self._finish_speed_evidence(camera_id, evt, success=False)
                raise
        except Exception:
            if speed_slot:
                self._finish_speed_evidence(camera_id, evt, success=False)
            raise

    def resolve_aligned_frame(
        self,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        frame_ts: float | None = None,
    ) -> tuple[Any, bool]:
        """Pick the capture frame; co-emission live events use the inference frame as-is."""
        bbox_src = evt.get("bbox_source")
        if bbox_src in _EMISSION_BBOX_SOURCES:
            if frame is None:
                return frame, False
            raw_bbox = bbox_from_event(evt)
            if raw_bbox is None:
                return frame, True
            fh, fw = frame.shape[:2]
            norm = normalize_bbox(raw_bbox, fw, fh)
            if not norm or bbox_region_has_content(frame, norm):
                return frame, True
            logger.warning(
                "emission bbox region empty camera=%s event=%s source=%s",
                camera_id[:8], evt.get("event_id"), bbox_src,
            )
            return frame, False

        capture_frame = self._resolve_capture_frame(camera_id, evt, frame, frame_ts)
        raw_bbox = bbox_from_event(evt)
        if raw_bbox is None or capture_frame is None:
            return capture_frame, True
        fh, fw = capture_frame.shape[:2]
        norm = normalize_bbox(raw_bbox, fw, fh)
        if not norm:
            return capture_frame, True
        if bbox_region_has_content(capture_frame, norm):
            return capture_frame, True
        bbox_ts = evt.get("bbox_ts")
        buf = self._buffers.get(camera_id)
        if buf is not None and isinstance(bbox_ts, (int, float)):
            for cand, cand_ts in buf.get_frames_near_ts(float(bbox_ts), max_frames=6):
                if bbox_region_has_content(cand, norm):
                    logger.info(
                        "evidence frame realigned camera=%s event=%s dt=%.3fs",
                        camera_id[:8], evt.get("event_id"), cand_ts - float(bbox_ts),
                    )
                    return cand, True
        logger.warning(
            "evidence bbox region empty camera=%s event=%s bbox_ts=%s",
            camera_id[:8], evt.get("event_id"), bbox_ts,
        )
        return capture_frame, False

    def attach_evidence_async(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        frame,
        *,
        policy: dict[str, Any],
        frame_ts: float | None = None,
        speed_slot: bool = False,
    ) -> None:
        """Frame selection happens synchronously (ring buffer still holds the
        bbox-instant frame); crops, clip export and backend upload run in a
        background thread so ingest never blocks on ffmpeg or HTTP."""
        try:
            resolved_frame, quality_ok = self.resolve_aligned_frame(
                camera_id, evt, frame, frame_ts,
            )
        except Exception:
            logger.exception(
                "frame alignment failed camera=%s event=%s",
                camera_id, evt.get("event_id"),
            )
            resolved_frame, quality_ok = frame, False

        def _run() -> None:
            acquired = self._ENCODE_SEM.acquire(blocking=True, timeout=120)
            if not acquired:
                logger.warning(
                    "evidence semaphore timeout — dropping capture camera=%s event=%s",
                    camera_id[:8], evt.get("event_id", ""),
                )
                if speed_slot:
                    self._finish_speed_evidence(camera_id, evt, success=False)
                return
            try:
                self._capture_and_attach(
                    camera_id, org_id, evt, resolved_frame, policy,
                    frame_ts=frame_ts, resolved=True, bbox_quality_ok=quality_ok,
                )
                if speed_slot:
                    ok = str(evt.get("evidence_status") or "") in ("complete", "partial")
                    self._finish_speed_evidence(
                        camera_id, evt, success=ok, uploaded=evt.get("evidence") if ok else None,
                    )
            except Exception:
                logger.exception(
                    "async evidence failed camera=%s event=%s",
                    camera_id,
                    evt.get("event_id"),
                )
                if speed_slot:
                    self._finish_speed_evidence(camera_id, evt, success=False)
            finally:
                self._ENCODE_SEM.release()
                gc.collect()
                _trim_malloc()

        threading.Thread(
            target=_run,
            daemon=True,
            name=f"evidence-{evt.get('event_id', 'evt')}",
        ).start()

    def attach_segment_evidence_async(
        self,
        org_id: str,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        segment_path: str,
        frame_pts: float,
        policy: dict[str, Any],
        *,
        cycle_id: str = "",
        frame_index: int = 0,
    ) -> None:
        def _run() -> None:
            acquired = self._ENCODE_SEM.acquire(blocking=True, timeout=120)
            if not acquired:
                logger.warning(
                    "segment evidence semaphore timeout — dropping capture camera=%s event=%s",
                    camera_id[:8], evt.get("event_id", ""),
                )
                return
            try:
                self.capture_from_segment(
                    org_id,
                    camera_id,
                    evt,
                    frame,
                    segment_path,
                    frame_pts,
                    policy,
                    cycle_id=cycle_id,
                    frame_index=frame_index,
                )
            except Exception:
                logger.exception(
                    "segment evidence failed camera=%s event=%s",
                    camera_id,
                    evt.get("event_id"),
                )
            finally:
                self._ENCODE_SEM.release()
                gc.collect()
                _trim_malloc()

        threading.Thread(
            target=_run,
            daemon=True,
            name=f"seg-evidence-{evt.get('event_id', 'evt')}",
        ).start()

    def capture_from_segment(
        self,
        org_id: str,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        segment_path: str,
        frame_pts: float,
        policy: dict[str, Any],
        *,
        cycle_id: str = "",
        frame_index: int = 0,
    ) -> dict[str, Any] | None:
        """Evidence from the recorded segment — frame and clip are time-aligned."""
        clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
        event_id = str(evt.get("event_id", ""))
        raw_bbox = bbox_from_event(evt)
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        draw_bbox = policy.get("draw_bbox", True) is not False

        capture_pts = frame_pts
        bbox_pts = evt.get("segment_bbox_pts")
        if bbox_pts is not None:
            try:
                capture_pts = float(bbox_pts)
            except (TypeError, ValueError):
                pass
        else:
            derived = segment_pts_from_bbox_ts(evt.get("bbox_ts"), evt.get("segment_start_wall", 0.0))
            if derived is not None:
                capture_pts = derived

        capture_frame = self._resolve_segment_evidence_frame(
            camera_id,
            cycle_id,
            evt,
            frame,
            segment_path,
            capture_pts,
            frame_index,
            raw_bbox,
        )

        fh, fw = capture_frame.shape[:2]
        norm_bbox = normalize_bbox(raw_bbox, fw, fh) if raw_bbox else None
        scene, subject, extras = capture_images_from_policy(
            capture_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=draw_bbox,
        )
        clip_bytes = extract_subclip_mp4(segment_path, capture_pts, clip_sec)
        if not clip_bytes:
            logger.warning(
                "segment clip extraction failed cam=%s cycle=%s pts=%.2f path=%s",
                camera_id[:8], cycle_id, capture_pts, segment_path,
            )
        media_dur = probe_media_duration(segment_path)
        effective = min(clip_sec, media_dur) if media_dur else clip_sec
        clip_duration = effective if clip_bytes else 0.0
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
            "bbox_ts": evt.get("bbox_ts"),
            "capture_frame_ts": capture_pts,
            "capture_source": "segment",
            "segment_cycle_id": cycle_id,
            "segment_frame_index": evt.get("segment_bbox_frame_index", frame_index),
            "segment_bbox_frame_index": evt.get("segment_bbox_frame_index"),
            "segment_frame_pts": capture_pts,
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
        return uploaded

    def capture_retroactive(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        # Speeding: one Frigate attempt per track — rules-engine storms
        # /evidence/capture for every pending event and must not stampede Frigate.
        speed_slot = False
        if self._is_speeding_event(evt):
            if not self._begin_speed_evidence(camera_id, evt):
                reused = self._reuse_speed_evidence(camera_id, evt)
                if reused is not None:
                    return reused
                logger.info(
                    "speed evidence dedupe skip (retro) camera=%s track=%s event=%s",
                    camera_id[:8], evt.get("track_id"), str(evt.get("event_id") or "")[:8],
                )
                return None
            speed_slot = True
        # Use the dedicated retroactive semaphore (_RETRO_SEM, limit=4) so these HTTP
        # requests don't compete with the background attachment threads (_ENCODE_SEM,
        # limit=2).  Without separation, 100 concurrent events saturate both pools and
        # the majority of retries time-out before getting a slot.
        #
        # CRITICAL: if the semaphore is not acquired within the timeout, return None
        # immediately — do NOT fall through to _capture_retroactive_inner without the
        # semaphore, which would re-introduce unbounded memory usage.
        # Short timeout: if the 4 slots are busy, return None quickly so the
        # rules-engine retries after 8s.  By then the background thread has likely
        # populated the evidence cache, turning the next retry into a cache hit.
        acquired = self._RETRO_SEM.acquire(blocking=True, timeout=5)
        if not acquired:
            logger.info(
                "retroactive semaphore busy — deferring camera=%s event=%s",
                camera_id[:8], str(evt.get("event_id") or "")[:8],
            )
            if speed_slot:
                self._finish_speed_evidence(camera_id, evt, success=False)
            return None
        try:
            uploaded = self._capture_retroactive_inner(camera_id, org_id, evt, policy)
            if speed_slot:
                ok = bool(uploaded) and str(
                    (uploaded or {}).get("evidence_status")
                    or evt.get("evidence_status")
                    or ""
                ) in ("complete", "partial")
                # Also accept packages with frigate_track capture_source.
                if not ok and isinstance(uploaded, dict):
                    pkg = uploaded.get("package") or {}
                    meta = pkg.get("metadata") if isinstance(pkg, dict) else {}
                    if isinstance(meta, dict) and meta.get("capture_source") == "frigate_track":
                        ok = True
                self._finish_speed_evidence(
                    camera_id, evt, success=ok, uploaded=uploaded if ok else None,
                )
            return uploaded
        except Exception:
            if speed_slot:
                self._finish_speed_evidence(camera_id, evt, success=False)
            raise
        finally:
            self._RETRO_SEM.release()
            gc.collect()
            _trim_malloc()

    def _capture_retroactive_inner(
        self,
        camera_id: str,
        org_id: str,
        evt: dict[str, Any],
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        # Fast path: return the package already captured by the background thread.
        # This avoids re-decompressing the ring buffer and re-uploading — which is
        # the main cause of semaphore saturation when 100+ events fire simultaneously.
        event_id = str(evt.get("event_id") or "")
        if event_id and event_id in self._evidence_cache:
            logger.debug("retroactive evidence cache hit event=%s", event_id[:8])
            return self._evidence_cache[event_id]
        seg_path = evt.get("segment_path")
        frame_pts = evt.get("segment_frame_pts")
        if (
            isinstance(seg_path, str)
            and seg_path
            and os.path.isfile(seg_path)
            and isinstance(frame_pts, (int, float))
        ):
            pol = policy or default_evidence_policy()
            buf = self._buffers.get(camera_id)
            frame = None
            if buf:
                frame = buf.get_last_frame()
            if frame is None:
                cap = cv2.VideoCapture(seg_path)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_POS_MSEC, float(frame_pts) * 1000.0)
                    ok, frame = cap.read()
                    cap.release()
                if frame is None:
                    logger.warning("segment retro capture: no frame at pts=%s", frame_pts)
                    return None
            return self.capture_from_segment(
                org_id,
                camera_id,
                evt,
                frame,
                seg_path,
                float(frame_pts),
                pol,
                cycle_id=str(evt.get("segment_cycle_id") or ""),
                frame_index=int(evt.get("segment_frame_index") or 0),
            )
        if camera_id in settings.parsed_segment_mode_camera_ids():
            logger.warning(
                "segment retro capture unavailable camera=%s (segment file gone)",
                camera_id,
            )
            return None
        pol = policy or default_evidence_policy()
        images_spec = pol.get("images") or default_evidence_policy()["images"]
        if self._evidence_backend_mode() in ("frigate", "hybrid", "strict_frigate") and self._frigate_track.enabled():
            fg = self._try_frigate_capture(
                camera_id, org_id, evt, pol, images_spec, return_upload=True,
            )
            if fg is not None:
                return fg
            if self._evidence_backend_mode() in ("frigate", "strict_frigate"):
                if not (
                    self._evidence_backend_mode() == "strict_frigate"
                    and self._allows_ring_buffer_fallback(evt)
                ):
                    return self._mark_frigate_failed(evt, return_upload=True)
        if not self._allows_ring_buffer_fallback(evt):
            return self._mark_frigate_failed(evt, return_upload=True)
        buf = self._buffers.get(camera_id)
        bbox_ts = evt.get("bbox_ts")
        event_ts = _parse_event_ts(evt)
        lookup_ts: float | None = None
        if isinstance(bbox_ts, (int, float)):
            lookup_ts = float(bbox_ts)
        elif event_ts is not None:
            lookup_ts = float(event_ts)
        else:
            lookup_ts = time.time()
        frame = None
        frame_ts: float | None = None
        if buf and lookup_ts is not None:
            frame = buf.get_frame_at_ts(lookup_ts)
            if frame is not None:
                frame_ts = lookup_ts
        if frame is None and buf:
            frame = buf.get_last_frame()
        if frame is None:
            logger.warning("retro capture unavailable camera=%s (no buffer frame)", camera_id)
            return None
        return self._capture_and_attach(
            camera_id, org_id, evt, frame, pol, return_upload=True, frame_ts=frame_ts,
        )

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
        resolved: bool = False,
        bbox_quality_ok: bool = True,
        no_clip: bool = False,
    ) -> dict[str, Any] | None:
        clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
        event_id = str(evt.get("event_id", ""))
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        event_type = str(evt.get("event_type") or evt.get("event") or "")

        # Road rules: Frigate-only in strict demo — no early ring freeze/fallback that
        # used to ship demo_ring_buffer + emission_track bbox as "complete".
        if not no_clip:
            frigate_upload = self._try_frigate_capture(
                camera_id, org_id, evt, policy, images_spec, return_upload,
                live_frame=frame, frame_ts=frame_ts,
            )
            if frigate_upload is not None:
                return frigate_upload
            if self._evidence_backend_mode() in ("frigate", "strict_frigate"):
                if not (
                    self._evidence_backend_mode() == "strict_frigate"
                    and self._allows_ring_buffer_fallback(evt)
                ):
                    return self._mark_frigate_failed(evt, return_upload)
        if not self._allows_ring_buffer_fallback(evt):
            return self._mark_frigate_failed(evt, return_upload)
        if resolved:
            capture_frame = frame
        else:
            capture_frame, bbox_quality_ok = self.resolve_aligned_frame(
                camera_id, evt, frame, frame_ts,
            )
        raw_bbox = bbox_from_event(evt)
        images_spec = policy.get("images") or default_evidence_policy()["images"]
        draw_bbox = policy.get("draw_bbox", True) is not False
        fh, fw = capture_frame.shape[:2]
        norm_bbox = normalize_bbox(raw_bbox, fw, fh) if raw_bbox else None
        scene, subject, extras = capture_images_from_policy(
            capture_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=draw_bbox,
        )
        subject_texture = subject_jpeg_texture(subject)
        if subject is None:
            subject_quality_ok = False
        else:
            subject_quality_ok = (
                subject_texture is not None and subject_texture >= SUBJECT_MIN_TEXTURE
            )
        if subject is not None and not subject_quality_ok:
            bbox_quality_ok = False
        buf = self._buffers.get(camera_id)
        clip_bytes: bytes | None = None
        clip_duration = 0.0
        if buf and not no_clip:
            if evt.get("bbox_source") in _EMISSION_BBOX_SOURCES and frame_ts is not None:
                anchor_ts = float(frame_ts)
            else:
                anchor_ts = evt.get("bbox_ts")
                if not isinstance(anchor_ts, (int, float)):
                    anchor_ts = _parse_event_ts(evt)
            exported = buf.export_clip_mp4(
                clip_sec,
                RING_FPS,
                center_ts=float(anchor_ts) if anchor_ts is not None else None,
            )
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
        # Plate is identification-only (Tâche 4) — do not fail violation completeness.
        if not bbox_quality_ok:
            complete = False
        if subject is not None and not subject_quality_ok:
            complete = False
        status = "complete" if complete else "partial"
        capture_source = (
            "demo_ring_buffer"
            if event_type == "red_light_violation" and settings.demo_relaxed_evidence()
            else "live"
        )
        meta = {
            "bbox": norm_bbox,
            "bbox_ts": evt.get("bbox_ts"),
            "bbox_source": evt.get("bbox_source"),
            "bbox_quality_ok": bbox_quality_ok,
            "subject_texture": round(subject_texture, 1) if subject_texture is not None else None,
            "subject_quality_ok": subject_quality_ok,
            "capture_frame_ts": frame_ts,
            "capture_source": capture_source,
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
        if capture_source == "demo_ring_buffer":
            meta.update(self._demo_loop_meta(camera_id, evt.get("bbox_ts")))
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
            # Cache the result so capture_retroactive can return it instantly
            # when the rules-engine requests evidence for the same event.
            if event_id:
                if len(self._evidence_cache) >= self._CACHE_MAX:
                    try:
                        oldest = next(iter(self._evidence_cache))
                        del self._evidence_cache[oldest]
                    except StopIteration:
                        pass
                self._evidence_cache[event_id] = uploaded
        else:
            evt["evidence_status"] = "failed"
        if return_upload:
            return uploaded
        return None

    def _export_demo_ring_capture(
        self,
        camera_id: str,
        evt: dict[str, Any],
        frame,
        policy: dict[str, Any],
        images_spec: list[dict[str, Any]],
        *,
        frame_ts: float | None,
        resolved: bool,
        bbox_quality_ok: bool,
    ) -> dict[str, Any] | None:
        """Freeze ring-buffer scene/subject/clip immediately (before Frigate waits)."""
        try:
            if resolved:
                capture_frame = frame
            else:
                capture_frame, bbox_quality_ok = self.resolve_aligned_frame(
                    camera_id, evt, frame, frame_ts,
                )
            if capture_frame is None:
                return None
            clip_sec = float(policy.get("clip_seconds") or CLIP_DURATION_SEC)
            raw_bbox = bbox_from_event(evt)
            draw_bbox = policy.get("draw_bbox", True) is not False
            fh, fw = capture_frame.shape[:2]
            norm_bbox = normalize_bbox(raw_bbox, fw, fh) if raw_bbox else None
            scene, subject, extras = capture_images_from_policy(
                capture_frame, norm_bbox, images_spec, JPEG_QUALITY, draw_bbox=draw_bbox,
            )
            subject_texture = subject_jpeg_texture(subject)
            subject_quality_ok = bool(
                subject is not None
                and subject_texture is not None
                and subject_texture >= SUBJECT_MIN_TEXTURE
            )
            if subject is not None and not subject_quality_ok:
                bbox_quality_ok = False
            buf = self._buffers.get(camera_id)
            clip_bytes: bytes | None = None
            clip_duration = 0.0
            if buf:
                if evt.get("bbox_source") in _EMISSION_BBOX_SOURCES and frame_ts is not None:
                    anchor_ts = float(frame_ts)
                else:
                    anchor_ts = evt.get("bbox_ts")
                    if not isinstance(anchor_ts, (int, float)):
                        anchor_ts = _parse_event_ts(evt)
                exported = buf.export_clip_mp4(
                    clip_sec,
                    RING_FPS,
                    center_ts=float(anchor_ts) if anchor_ts is not None else None,
                )
                if exported:
                    clip_bytes = exported.data
                    clip_duration = exported.duration_sec
            if not (scene and subject and clip_bytes):
                logger.info(
                    "demo_ring_buffer incomplete cam=%s scene=%s subject=%s clip=%s",
                    camera_id[:8], bool(scene), bool(subject), bool(clip_bytes),
                )
                return None
            want_plate = any(s.get("role") == "plate" for s in images_spec)
            plate_jpeg = extras[0] if extras else None
            missing_roles = ["plate"] if want_plate and not plate_jpeg else []
            status = "complete" if bbox_quality_ok and subject_quality_ok else "partial"
            meta = {
                "bbox": norm_bbox,
                "bbox_ts": evt.get("bbox_ts"),
                "bbox_source": evt.get("bbox_source"),
                "bbox_quality_ok": bbox_quality_ok,
                "subject_texture": round(subject_texture, 1) if subject_texture is not None else None,
                "subject_quality_ok": subject_quality_ok,
                "capture_frame_ts": frame_ts,
                "capture_source": "demo_ring_buffer",
                "confidence": evt.get("confidence"),
                "class_name": evt.get("class_name"),
                "zone_id": evt.get("zone_id"),
                "track_id": evt.get("track_id"),
                "event_type": evt.get("event_type") or evt.get("event"),
                "clip_duration_sec": clip_duration,
                "plate_number": evt.get("plate_number"),
                "plate_confidence": evt.get("plate_confidence"),
                "missing_roles": missing_roles,
                "evidence_status": status,
            }
            meta.update(self._demo_loop_meta(camera_id, evt.get("bbox_ts")))
            return {
                "status": status,
                "scene": scene,
                "subject": subject,
                "clip_bytes": clip_bytes,
                "plate_jpeg": plate_jpeg,
                "extra_images": [],
                "meta": meta,
            }
        except Exception as exc:
            logger.warning(
                "demo_ring_buffer export failed cam=%s: %s", camera_id[:8], exc,
            )
            return None

    def clear_camera(self, camera_id: str) -> None:
        self._buffers.pop(camera_id, None)
        self._gate.clear_camera(camera_id)

    def clear_camera_rules_only(self, camera_id: str) -> None:
        """Clear capture rules but preserve the ring buffer.

        Called when a camera is stopped so that any in-flight rules-engine evidence
        retries (which may arrive seconds after the camera stops) can still succeed.
        The ring buffer is replaced automatically when the camera restarts.
        """
        self._gate.clear_camera(camera_id)
```

### 1.5 Clarification API (où est quoi)

| Symbole | Fichier réel |
|---------|--------------|
| `update_frigate_bindings` | `evidence/service.py` → `FrigateTrackBinder.update_tracks` |
| `inject_frigate_binding` | `evidence/service.py` → `FrigateTrackBinder.inject_event` |
| `match_track_to_event` | `frigate_track_evidence.py` |
| `_demo_clock_offset` | instance `FrigateTrackEvidence` |
| `_maybe_learn_offset` | `frigate_track_evidence.py` |
| `aligned_anchor` / `learn_clock_offset` | `frigate_timeline.py` |
| `_demo_latest_vehicle_event` | `frigate_track_evidence.py` |
| `_bound_usable_for_road` | **absent** (à créer) |

Extraits critiques `pipeline.py` (émission):

```python
# ~891-894 : maj bindings tous tracks
self.evidence.update_frigate_bindings(
    camera_id, track_dicts, frame_w=w, frame_h=h, wall_ts=frame_wall_ts,
)

# ~1009-1013 : inject SAUF red_light / speeding
if str(evt.get("event_type") or "") not in ("red_light_violation", "speeding"):
    self.evidence.inject_frigate_binding(camera_id, evt)
```

---
## 2. Alignement temporel démo

### 2.1 `frigate_timeline.py` (fichier complet)

- Path: `ai-engine/src/citevision_ai/evidence/frigate_timeline.py`
- Lines: 128

```python
"""Timeline alignment between IA wall clock and Frigate event timestamps (demo go2rtc loops)."""

from __future__ import annotations

from typing import Any

# Frigate on looped go2rtc often exposes stream-relative seconds; wall clock is ~1.7e9+.
_STREAM_CLOCK_MAX = 1_000_000_000.0


def demo_loop_absolute_align_ok(align_delta_sec: float, max_align_sec: float) -> bool:
    """Hard time gate — never bypassed by soft-accept / bound-id trust (demo_loop_guard)."""
    try:
        return float(align_delta_sec) <= float(max_align_sec)
    except (TypeError, ValueError):
        return False


def same_demo_loop_cycle(
    ia_ts: float,
    frigate_ts: float,
    loop_sec: float,
    *,
    boundary_slack_sec: float = 2.0,
) -> bool:
    """True when IA and Frigate timestamps fall in the same demo-loop iteration.

    Rejects pairings separated by ~k full loops (k≥1) even if modulo positions
    look similar — the classic stale Frigate event reuse on looping go2rtc.

    Important: a small wall-clock delta that straddles a ``floor(ts/loop)``
    boundary is still the same capture moment — do **not** reject via floor
    equality (that falsely aborted ~1s-aligned pairs during T1).
    """
    try:
        loop = float(loop_sec)
        a = float(ia_ts)
        b = float(frigate_ts)
    except (TypeError, ValueError):
        return True
    if loop <= 1.0:
        return True
    delta = abs(a - b)
    # Nearly one full loop or more ⇒ different iteration.
    if delta >= max(loop - max(0.0, boundary_slack_sec), loop * 0.95):
        return False
    return True


def best_frigate_ts(ev: dict[str, Any]) -> float | None:
    """Prefer start_time / frame_time for loop-cycle comparison."""
    for key in ("frame_time", "start_time", "end_time"):
        v = ev.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    cands = frigate_event_time_candidates(ev)
    return cands[0] if cands else None


def frigate_event_time_candidates(ev: dict[str, Any]) -> list[float]:
    """Collect comparable timestamps from a Frigate event."""
    out: list[float] = []
    for key in ("frame_time", "start_time", "end_time"):
        v = ev.get(key)
        if isinstance(v, (int, float)):
            out.append(float(v))
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    for pt in data.get("path_data") or []:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        ts = pt[1]
        if isinstance(ts, (int, float)):
            out.append(float(ts))
    return out


def min_time_delta(anchor: float, ev: dict[str, Any]) -> float:
    candidates = frigate_event_time_candidates(ev)
    if not candidates:
        return 1e18
    return min(abs(t - anchor) for t in candidates)


def learn_clock_offset(
    offsets: dict[str, float],
    camera_id: str,
    ia_anchor: float,
    frigate_ts: float,
    *,
    ema_alpha: float = 0.35,
) -> float:
    """Estimate IA_wall - Frigate_ts for looped demo streams; returns learned offset."""
    sample = float(ia_anchor) - float(frigate_ts)
    prev = offsets.get(camera_id)
    if prev is None:
        offsets[camera_id] = sample
    else:
        offsets[camera_id] = prev * (1.0 - ema_alpha) + sample * ema_alpha
    return offsets[camera_id]


def aligned_anchor(offsets: dict[str, float], camera_id: str, anchor: float) -> float:
    off = offsets.get(camera_id)
    if off is None:
        return anchor
    return float(anchor) - float(off)


def frigate_times_look_stream_relative(events: list[dict[str, Any]]) -> bool:
    """True when Frigate event times look like go2rtc loop positions, not unix epoch."""
    samples: list[float] = []
    for ev in events[:12]:
        samples.extend(frigate_event_time_candidates(ev))
    if not samples:
        return False
    return max(samples) < _STREAM_CLOCK_MAX


def wall_clock_skewed_from_frigate(anchor: float, events: list[dict[str, Any]]) -> bool:
    """True when IA wall anchor cannot match Frigate times within loose window."""
    if not events:
        return False
    samples: list[float] = []
    for ev in events[:8]:
        samples.extend(frigate_event_time_candidates(ev))
    if not samples:
        return False
    return min(abs(anchor - t) for t in samples) > 3600.0
```

### 2.2 `config.py` (fichier complet — settings IA)

- Path: `ai-engine/src/citevision_ai/config.py`
- Lines: 292

```python
from pathlib import Path
from urllib.parse import urlparse
import os
import logging

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_AI_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _AI_ROOT.parent  # citevision-v2/
_log = logging.getLogger("citevision_ai.config")


def _env_files() -> list[str]:
    """
    Retourne la liste ordonnée des fichiers .env à charger.
    generated.env (produit par apply-hardware-profile.py) est chargé EN PREMIER
    pour que ses valeurs soient visibles, mais .env peut les surcharger.
    L'ordre pydantic-settings: le dernier fichier a la priorité.
    On place donc generated.env avant .env pour que .env puisse override.
    """
    files: list[str] = []
    generated = _REPO_ROOT / "generated.env"
    if generated.exists():
        files.append(str(generated))
    # .env can be repo-root or ai-engine/.env
    for candidate in (_REPO_ROOT / ".env", _AI_ROOT / ".env"):
        if candidate.exists():
            files.append(str(candidate))
    # Always include relative ".env" as fallback for backward compat
    if not files:
        files = [".env"]
    return files


def _parse_env_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    v = raw.strip().strip('"').strip("'").lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off", ""):
        return False
    return None


def _read_key_from_env_files(key: str) -> str | None:
    """Parse KEY=value from repo .env files (last file wins). Independent of process environ."""
    found: str | None = None
    for path in _env_files():
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, val = s.partition("=")
            if k.strip() == key:
                found = val.strip()
    return found


def resolve_demo_mode() -> tuple[bool, str]:
    """
    Resolve DEMO_MODE without relying on the shell having sourced .env.

    Priority:
      1. Process environ DEMO_MODE / CITEVISION_DEMO_MODE
      2. Explicit key in repo .env / generated.env / ai-engine/.env
      3. Default False (strict / production)
    """
    for env_key in ("DEMO_MODE", "CITEVISION_DEMO_MODE"):
        parsed = _parse_env_bool(os.environ.get(env_key))
        if parsed is not None:
            return parsed, f"environ:{env_key}"
    for file_key in ("DEMO_MODE", "CITEVISION_DEMO_MODE"):
        parsed = _parse_env_bool(_read_key_from_env_files(file_key))
        if parsed is not None:
            return parsed, f"env_file:{file_key}"
    return False, "default:false"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ai_engine_host: str = "0.0.0.0"
    ai_engine_port: int = 8001
    yolo_model_path: str = "models/yolov8n.onnx"
    yolo_device: str = "cuda"
    max_cameras: int = 12
    yolo_confidence: float = 0.25
    yolo_iou: float = 0.45
    yolo_min_fps: float = 10.0

    # GPU Elasticity — modifié dynamiquement par hardware_profile.apply()
    # "auto" = détection automatique au démarrage
    hardware_tier: str = "auto"
    batch_size: int = 4

    # Aliases produits par generated.env (apply-hardware-profile.py)
    # Ces variables prennent effet si generated.env est présent et .env ne les override pas.
    # pydantic-settings les lit via les noms de champ (case-insensitive).
    cv_gpu_tier: str = ""           # ex: "ultra" — copié dans hardware_tier par apply()
    cv_max_cameras: int = 0         # override de max_cameras si > 0
    cv_yolo_model: str = ""         # override de yolo_model_path si non vide
    cv_batch_size: int = 0          # override de batch_size si > 0
    cv_target_fps: float = 0.0      # info FPS cible
    cv_inference_backend: str = ""  # "cuda" ou "cpu" — override de yolo_device si non vide

    mqtt_broker: str = "localhost"
    mqtt_port: int = 1884
    mqtt_user: str = ""
    mqtt_password: str = ""

    insightface_model_path: str = ""
    paddleocr_model_dir: str = ""
    ai_require_all_models: bool = True

    # Segment cycle mode (Phase A — disabled): empty = all cameras use live RTSP.
    # Comma-separated camera UUIDs to opt-in to record→replay cycles (not recommended).
    # Archived Sprint 4 — keep empty. Non-empty raises at camera start.
    segment_mode_camera_ids: str = ""
    segment_record_sec: float = 10.0
    segment_process_budget_sec: float = 5.0
    segment_ingest_fps: float = 12.0

    # Unified pipeline: AI reads camera RTSP for analytics. Live preview uses go2rtc pull
    # (ffmpeg RTSP publish to go2rtc :8554 is unreliable on go2rtc 1.9.x).
    unified_pipeline: bool = True
    go2rtc_publish_enabled: bool = False
    burn_in_overlay: bool = True
    go2rtc_rtsp_host: str = "127.0.0.1"
    go2rtc_rtsp_port: int = 8554
    go2rtc_publish_max_width: int = 1280
    go2rtc_publish_fps: float = 15.0

    # Frigate media plane (off by default — see docs/FRIGATE-INTEGRATION.md)
    frigate_enabled: bool = False
    frigate_live: bool = False
    frigate_evidence: bool = False
    frigate_url: str = "http://127.0.0.1:5000"
    frigate_plate_ocr: bool = True
    evidence_backend: str = "ring_buffer"  # ring_buffer | frigate | hybrid
    # Resolved again in model_post_init via resolve_demo_mode() so soft-accept
    # never depends on the restart shell having sourced .env.
    demo_mode: bool = Field(default=False, validation_alias=AliasChoices("DEMO_MODE", "CITEVISION_DEMO_MODE"))
    demo_mode_source: str = "default:false"
    demo_evidence_backend: str = "strict_frigate"  # strict_frigate | frigate | hybrid | ring_buffer
    demo_resolution: str = "1080p"  # 1080p | source
    # Demo go2rtc loop length for red_light Feux video (ffprobe stream duration).
    demo_red_light_loop_sec: float = 352.52
    # Demo-only: hard |bbox_ts−Frigate| gate + same-loop-cycle check (stale capture H1).
    # Live cameras have no loop boundary — leave False outside DEMO_MODE.
    demo_loop_guard: bool = True

    # Frigate track evidence (ported from citevision_videoverbalisation)
    frigate_event_match_sec: float = 12.0
    # Demo go2rtc loops: Frigate start_time is stream-relative; IA uses wall clock.
    frigate_demo_timeline_align: bool = True
    # Demo go2rtc: max |IA anchor − Frigate event| — stale loop events rejected above this.
    # 10s tolerates binder/queue delay while still rejecting hour-old loop events.
    frigate_demo_max_align_sec: float = 10.0
    frigate_demo_loose_match_sec: float = 10.0
    frigate_demo_bootstrap_max_sec: float = 18.0
    frigate_demo_min_bbox_iou: float = 0.12
    # Evidence accept gate: reject correlated events beyond this |IA−Frigate| skew.
    # Soft-accept may relax IoU inside this window — never enlarge the window itself.
    frigate_demo_accept_max_align_sec: float = 30.0
    # Minimum IoU between IA emission bbox and Frigate event box to accept evidence.
    # Demo go2rtc skips IoU in _accept_correlation (ByteTrack vs Frigate boxes diverge).
    frigate_accept_min_bbox_iou: float = 0.15
    frigate_demo_time_only_max_sec: float = 15.0
    frigate_demo_time_only_min_iou: float = 0.12
    frigate_demo_events_limit: int = 80
    frigate_snapshot_retries: int = 8
    frigate_snapshot_retry_delay: float = 0.45
    frigate_snapshot_quality: int = 98
    frigate_clip_retries: int = 8
    frigate_clip_retry_delay: float = 0.8
    frigate_clip_wait_if_missing: float = 1.2
    frigate_clip_min_bytes: int = 512
    frigate_clip_pad_before: float = 0.4
    frigate_clip_pad_after: float = 0.8
    frigate_event_media_wait_sec: float = 25.0
    frigate_event_media_poll_sec: float = 0.5
    # Poll Frigate events until correlated (demo go2rtc often lags IA by several seconds).
    frigate_correlate_wait_sec: float = 12.0
    # Sprint 1 — red_light deferred compose: wait for end_time before clip download.
    frigate_red_light_end_time_wait_sec: float = 30.0
    frigate_red_light_end_time_backoff_initial: float = 2.0
    frigate_red_light_end_time_backoff_max: float = 8.0
    frigate_evidence_frame_count: int = 6
    frigate_clip_frame_jpeg_q: int = 2
    # Proactive track → Frigate event binding (IoU while track is live).
    frigate_track_binding_enabled: bool = True
    frigate_bind_every_n_frames: int = 2
    frigate_bind_min_iou: float = 0.12

    # Fast-ALPR OCR service (evidence plate recognition)
    ocr_url: str = Field(
        default="",
        validation_alias=AliasChoices("ocr_url", "OCR_URL", "CITEVISION_OCR_URL"),
    )
    ocr_timeout: float = 8.0
    plate_max_frames: int = 6
    plate_stop_conf: float = 0.88
    plate_min_conf: float = 0.35

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    redis_host: str = "localhost"
    redis_port: int = 6380

    def model_post_init(self, __context: object) -> None:
        """
        Applique les variables CV_* de generated.env si elles sont définies
        et si les valeurs correspondantes n'ont pas été explicitement surchargées
        par les variables standard dans .env.
        Force DEMO_MODE from environ or .env files so soft-accept gates are never silent.
        """
        if self.cv_gpu_tier and self.hardware_tier == "auto":
            object.__setattr__(self, "hardware_tier", self.cv_gpu_tier)
        if self.cv_max_cameras > 0:
            object.__setattr__(self, "max_cameras", self.cv_max_cameras)
        if self.cv_yolo_model:
            object.__setattr__(self, "yolo_model_path", f"models/{self.cv_yolo_model}")
        if self.cv_batch_size > 0:
            object.__setattr__(self, "batch_size", self.cv_batch_size)
        if self.cv_inference_backend:
            object.__setattr__(self, "yolo_device", self.cv_inference_backend)

        # Always re-resolve DEMO_MODE from environ + on-disk .env (last write wins over
        # pydantic defaults when the process was started without a sourced shell env).
        demo, source = resolve_demo_mode()
        object.__setattr__(self, "demo_mode", demo)
        object.__setattr__(self, "demo_mode_source", source)
        _log.info("DEMO_MODE=%s source=%s", demo, source)

    def demo_relaxed_evidence(self) -> bool:
        """True when demo soft-accept / timeline-relaxed Frigate paths are allowed."""
        return bool(self.demo_mode)

    def parsed_segment_mode_camera_ids(self) -> frozenset[str]:
        raw = self.segment_mode_camera_ids.strip()
        if not raw:
            return frozenset()
        return frozenset(x.strip() for x in raw.split(",") if x.strip())

    def resolved_yolo_path(self) -> Path:
        p = Path(self.yolo_model_path)
        if p.is_absolute():
            return p
        # .env may use repo-relative "ai-engine/models/..." while _AI_ROOT is already ai-engine/
        parts = p.parts
        if parts and parts[0] == "ai-engine":
            p = Path(*parts[1:])
        return (_AI_ROOT / p).resolve()

    def resolved_insightface_root(self) -> Path:
        if self.insightface_model_path.strip():
            p = Path(self.insightface_model_path)
            if p.is_absolute():
                return p
            parts = p.parts
            if parts and parts[0] == "ai-engine":
                p = Path(*parts[1:])
            return (_AI_ROOT / p).resolve()
        return (_AI_ROOT / "models" / "insightface").resolve()

    def resolved_mqtt_host(self) -> str:
        broker = self.mqtt_broker.strip()
        if broker.startswith("tcp://") or broker.startswith("mqtt://"):
            parsed = urlparse(broker)
            return parsed.hostname or "localhost"
        return broker

    def resolved_mqtt_port(self) -> int:
        broker = self.mqtt_broker.strip()
        if broker.startswith("tcp://") or broker.startswith("mqtt://"):
            parsed = urlparse(broker)
            if parsed.port:
                return parsed.port
        return self.mqtt_port


settings = Settings()
```

### 2.3 Table des settings Frigate / démo (valeurs défaut actuelles)

| Setting | Défaut | Rôle |
|---------|--------|------|
| `demo_mode` | False (+ resolve env) | Active soft-accept / paths démo |
| `demo_evidence_backend` | `strict_frigate` | Backend preuves démo |
| `demo_red_light_loop_sec` | 352.52 | Durée boucle Feux |
| `demo_loop_guard` | True | Gate abs + même cycle boucle |
| `frigate_demo_timeline_align` | True | Offset horloge démo |
| `frigate_demo_max_align_sec` | 10.0 | Max \|IA−Frigate\| correlate |
| `frigate_demo_accept_max_align_sec` | 30.0 | Max accept (red_light clampé plus bas) |
| `frigate_demo_min_bbox_iou` | 0.12 | IoU min démo pick |
| `frigate_accept_min_bbox_iou` | 0.15 | IoU min accept evidence |
| `frigate_bind_min_iou` | 0.12 | IoU min binder |
| `frigate_bind_every_n_frames` | 2 | Fréquence maj binder |
| `frigate_track_binding_enabled` | True | Master binder |
| `frigate_correlate_wait_sec` | 12.0 | Poll correlate |
| `frigate_red_light_soft_iou` | — | **Pas un setting** : clé meta event |
| `frigate_speed_soft_iou` | — | **Pas un setting** : clé meta event |

---
## 3. Modules métier spécifiques

### 3.1 `zone_speed.py` (fichier complet)

- Path: `ai-engine/src/citevision_ai/analytics/zone_speed.py`
- Lines: 655

```python
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
from citevision_ai.evidence.capture import bbox_evidence_score, bbox_valid, pick_best_bbox_with_ts

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

    @staticmethod
    def _maybe_update_best_bbox(
        store: dict[tuple[str, str, int], dict],
        key: tuple[str, str, int],
        bbox: dict,
        frame_wall_ts: float,
        frame_w: int,
        frame_h: int,
        segment_frame_index: int | None,
    ) -> None:
        prev = store.get(key)
        prev_bbox = prev.get("bbox") if prev else None
        prev_score = bbox_evidence_score(prev_bbox, frame_w, frame_h, min_frac=0.01) if prev_bbox else 0.0
        new_score = bbox_evidence_score(bbox, frame_w, frame_h, min_frac=0.01)
        if new_score <= 0:
            return
        if prev_bbox is None or new_score > prev_score:
            entry: dict = {"bbox": dict(bbox), "ts": frame_wall_ts}
            if segment_frame_index is not None:
                entry["frame_index"] = int(segment_frame_index)
            store[key] = entry

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
        segment_frame_index: int | None = None,
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

                if edge_pair is not None and entry_mid is not None and exit_mid is not None:
                    cx, cy = _track_anchor_norm(bbox, frame_w, frame_h, anchor="bottom")
                    at_entry = _near_norm_point(cx, cy, entry_mid[0], entry_mid[1])
                    if at_entry:
                        if key not in self._entry_time:
                            self._entry_time[key] = now_ts
                            self._entry_xy[key] = (cx, cy)
                        self._inside[key] = True
                    # Best bbox only while the crossing is active (in-zone), and
                    # never as an elif that would shadow exit detection.
                    if (
                        (at_entry or self._inside.get(key))
                        and bbox_valid(bbox, min_frac=0.01)
                    ):
                        self._maybe_update_best_bbox(
                            self._best_bbox, key, bbox, frame_wall_ts,
                            frame_w, frame_h, segment_frame_index,
                        )
                    if (
                        not at_entry
                        and key in self._entry_time
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
                    if bbox_valid(bbox, min_frac=0.01):
                        self._maybe_update_best_bbox(
                            self._best_bbox, key, bbox, frame_wall_ts,
                            frame_w, frame_h, segment_frame_index,
                        )
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
        last_entry = self._last_bbox.get(key)
        # Evidence bbox = YOLO/ByteTrack on the finalize frame (co-emission).
        # Do not inject _best_bbox from an earlier in-zone instant.
        if track_lost and last_entry and last_entry.get("bbox"):
            track = {**track, "bbox": dict(last_entry["bbox"])}
        elif not bbox_valid(track.get("bbox") or {}, min_frac=0.02):
            if last_entry and last_entry.get("bbox"):
                track = {**track, "bbox": dict(last_entry["bbox"])}
            else:
                self._last_bbox.pop(key, None)
                self._best_bbox.pop(key, None)
                self._last_class.pop(key, None)
                return []
        self._last_bbox.pop(key, None)
        self._best_bbox.pop(key, None)
        self._last_class.pop(key, None)
        best_bbox_ts = frame_wall_ts if frame_wall_ts is not None else now_ts
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
            segment_bbox_frame_index=None,
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
        segment_bbox_frame_index: int | None = None,
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
            "segment_bbox_frame_index": segment_bbox_frame_index,
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
```

### 3.2 `traffic_light.py` (fichier complet)

- Path: `ai-engine/src/citevision_ai/road_enforcement/traffic_light.py`
- Lines: 324

```python
"""Traffic-light color classification per zone + red-light violation synergy.

This module implements the truthful red-light pipeline described in the demo plan:

  * A zone with behavior ``traffic_light_color`` defines the ROI of the traffic
    light. Its color (red / green / amber) is classified by HSV thresholds and
    smoothed over N frames to avoid flicker. A ``traffic_light_state`` event is
    emitted whenever the stable state changes.
  * A zone with behavior ``red_light_observation`` is the intersection/stop area.
    When the camera's stable light state is ``red`` AND a vehicle is *moving*
    inside this zone, a ``red_light_violation`` event is emitted for that
    specific vehicle (so ANPR / plate linking can target the offender).

All polygons received here are expected normalized (0..1) like the rest of the
spatial config; they are scaled to frame pixels internally.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from typing import Any

import cv2
import numpy as np

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

logger = logging.getLogger(__name__)

TRAFFIC_LIGHT_BEHAVIOR = "traffic_light_color"
OBSERVATION_BEHAVIOR = "red_light_observation"


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


def _polygon_pixel_bbox(polygon: list[dict], w: int, h: int) -> tuple[int, int, int, int] | None:
    if not polygon:
        return None
    xs = [float(p.get("x", 0)) for p in polygon]
    ys = [float(p.get("y", 0)) for p in polygon]
    normalized = all(0 <= v <= 1.0 for v in xs + ys)
    sx, sy = (w, h) if normalized else (1, 1)
    x1 = max(0, int(min(xs) * sx))
    y1 = max(0, int(min(ys) * sy))
    x2 = min(w, int(max(xs) * sx))
    y2 = min(h, int(max(ys) * sy))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def classify_light_color(roi: np.ndarray) -> tuple[str, dict[str, float]]:
    """Classify a traffic-light ROI as red / green / amber / unknown via HSV ratios."""
    if roi is None or roi.size == 0:
        return "unknown", {}
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    total = max(hsv.shape[0] * hsv.shape[1], 1)

    red = cv2.inRange(hsv, np.array([0, 90, 90]), np.array([10, 255, 255])) | cv2.inRange(
        hsv, np.array([160, 90, 90]), np.array([180, 255, 255])
    )
    amber = cv2.inRange(hsv, np.array([11, 90, 90]), np.array([28, 255, 255]))
    green = cv2.inRange(hsv, np.array([40, 70, 70]), np.array([90, 255, 255]))

    ratios = {
        "red": float(np.count_nonzero(red)) / total,
        "amber": float(np.count_nonzero(amber)) / total,
        "green": float(np.count_nonzero(green)) / total,
    }
    # Minimum illuminated ratio for any colour to count.
    min_ratio = 0.008
    state = max(ratios, key=ratios.get)
    if ratios[state] < min_ratio:
        return "unknown", ratios
    # No "prefer red" bias: if green/amber truly dominate the ROI, trust them.
    # Only reject a max==red when another colour is strictly stronger.
    if state == "red":
        if ratios["green"] > ratios["red"]:
            return ("green" if ratios["green"] >= ratios["amber"] else "amber"), ratios
        if ratios["amber"] > ratios["red"]:
            return "amber", ratios
    return state, ratios


class TrafficLightEngine:
    """Per-camera traffic-light state + red-light violation synergy."""

    def __init__(self) -> None:
        # Smoothed state machine per camera.
        self._state_history: dict[str, deque[str]] = {}
        self._stable_state: dict[str, str] = {}
        # Previous centroids to estimate per-track motion (pixels/frame).
        self._prev_centroid: dict[tuple[str, int], tuple[float, float]] = {}
        self._cooldown: dict[tuple[str, int], int] = {}
        # Consecutive frames a track spent inside an observation zone (motion gate).
        self._obs_streak: dict[tuple[str, int], int] = {}
        self._frame_counter = 0
        self._cooldown_frames = 45

    def reset_camera(self, camera_id: str) -> None:
        """Clear smoothed state when spatial config is hot-reloaded."""
        self._state_history.pop(camera_id, None)
        self._stable_state.pop(camera_id, None)
        drop = [k for k in self._prev_centroid if k[0] == camera_id]
        for k in drop:
            self._prev_centroid.pop(k, None)
            self._cooldown.pop(k, None)
            self._obs_streak.pop(k, None)

    def camera_has_behavior(self, zones: list[dict] | None) -> bool:
        if not zones:
            return False
        return any(
            str(z.get("behavior", "")) in (TRAFFIC_LIGHT_BEHAVIOR, OBSERVATION_BEHAVIOR)
            for z in zones
        )

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        tracks: list[dict],
        timestamp: str,
        zones: list[dict] | None,
    ) -> list[dict[str, Any]]:
        self._frame_counter += 1
        if frame is None or frame.size == 0 or not zones:
            return []
        light_zones = [z for z in zones if str(z.get("behavior", "")) == TRAFFIC_LIGHT_BEHAVIOR]
        obs_zones = [z for z in zones if str(z.get("behavior", "")) == OBSERVATION_BEHAVIOR]
        if not light_zones and not obs_zones:
            return []

        h, w = frame.shape[:2]
        events: list[dict[str, Any]] = []

        # 1) Classify the traffic-light color from the dedicated zone(s).
        stable_window = 3
        cooldown = self._cooldown_frames
        new_state = self._stable_state.get(camera_id, "unknown")
        raw_state = "unknown"
        hsv_ratios: dict[str, float] = {}
        light_polygon: list[dict] = []
        for lz in light_zones:
            cfg = lz.get("behavior_config") or {}
            try:
                stable_window = max(1, int(cfg.get("stable_frames", 3)))
            except (TypeError, ValueError):
                stable_window = 3
            cooldown = 8 if stable_window <= 1 else self._cooldown_frames
            light_polygon = list(lz.get("polygon") or [])
            box = _polygon_pixel_bbox(light_polygon, w, h)
            if not box:
                continue
            x1, y1, x2, y2 = box
            raw_state, hsv_ratios = classify_light_color(frame[y1:y2, x1:x2])
            hist = self._state_history.setdefault(camera_id, deque(maxlen=max(stable_window, 1)))
            hist.append(raw_state)
            if len(hist) >= hist.maxlen:
                # Majority vote — more tolerant of brief HSV flicker in live video.
                counts: dict[str, int] = {}
                for s in hist:
                    counts[s] = counts.get(s, 0) + 1
                new_state = max(counts, key=counts.get)
            else:
                new_state = raw_state
            break  # one traffic-light zone per camera is the supported case

        prev_stable = self._stable_state.get(camera_id)
        if new_state != prev_stable:
            self._stable_state[camera_id] = new_state
            events.append(
                self._make_state_event(camera_id, new_state, timestamp)
            )

        # 2) Red-light synergy: moving vehicle in observation zone while red.
        # Require BOTH stable history and current-frame raw classification as red
        # so sticky "red" after the lamp turned green cannot keep firing.
        tracks_in_obs: set[tuple[str, int]] = set()
        light_is_red = (
            self._stable_state.get(camera_id) == "red"
            and raw_state == "red"
        )
        if light_is_red and obs_zones:
            for oz in obs_zones:
                cfg = oz.get("behavior_config") or {}
                class_filter = str(cfg.get("class_filter", "car"))
                try:
                    min_motion = float(cfg.get("min_speed_px", 2))
                except (TypeError, ValueError):
                    min_motion = 2.0
                poly = oz.get("polygon") or []
                for track in tracks:
                    cls = str(track.get("class_name", ""))
                    if class_filter not in ("any", "") and cls != class_filter and cls not in VEHICLE_CLASSES:
                        continue
                    bbox = track.get("bbox") or {}
                    cx = (float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2)
                    # Use a point near the bottom of the bbox (wheels / road contact).
                    cy = float(bbox.get("y", 0)) + float(bbox.get("height", 0)) * 0.85
                    ncx, ncy = cx / max(w, 1), cy / max(h, 1)
                    if poly and not _point_in_polygon(ncx, ncy, poly):
                        continue
                    tid = int(track.get("track_id", -1))
                    key = (camera_id, tid)
                    tracks_in_obs.add(key)
                    streak = self._obs_streak.get(key, 0) + 1
                    self._obs_streak[key] = streak
                    motion = self._motion_px(camera_id, tid, cx, cy)
                    # First frame in zone has motion=0; allow after 2 consecutive frames.
                    if motion < min_motion and streak < 2:
                        continue
                    if not self._allow_emit(camera_id, tid, cooldown):
                        continue
                    events.append(
                        self._make_violation_event(
                            camera_id, track, timestamp, motion,
                            hsv_ratios=hsv_ratios,
                            light_state=raw_state,
                            light_zone_polygon=light_polygon,
                            frame_w=w,
                            frame_h=h,
                        )
                    )
        for key in list(self._obs_streak):
            if key[0] == camera_id and key not in tracks_in_obs:
                self._obs_streak.pop(key, None)

        # Always refresh centroid cache for motion estimation.
        for track in tracks:
            bbox = track.get("bbox") or {}
            cx = float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2
            cy = float(bbox.get("y", 0)) + float(bbox.get("height", 0)) / 2
            self._prev_centroid[(camera_id, int(track.get("track_id", -1)))] = (cx, cy)

        if events:
            logger.info(
                "traffic_light camera=%s events=%s",
                camera_id[:8],
                [e.get("event_type") for e in events],
            )
        return events

    def _motion_px(self, camera_id: str, track_id: int, cx: float, cy: float) -> float:
        prev = self._prev_centroid.get((camera_id, track_id))
        if not prev:
            return 0.0
        return float(((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) ** 0.5)

    def _allow_emit(self, camera_id: str, track_id: int, cooldown_frames: int | None = None) -> bool:
        key = (camera_id, track_id)
        last = self._cooldown.get(key, -9999)
        frames = self._cooldown_frames if cooldown_frames is None else cooldown_frames
        if self._frame_counter - last < frames:
            return False
        self._cooldown[key] = self._frame_counter
        return True

    @staticmethod
    def _make_state_event(camera_id: str, state: str, timestamp: str) -> dict[str, Any]:
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": "traffic_light_state",
            "event": "traffic_light_state",
            "timestamp": timestamp,
            "track_id": -1,
            "severity": "info",
            "metadata": {"state": state, "detection_method": "hsv_zone_classifier"},
        }

    @staticmethod
    def _make_violation_event(
        camera_id: str,
        track: dict,
        timestamp: str,
        motion_px: float,
        *,
        hsv_ratios: dict[str, float] | None = None,
        light_state: str = "red",
        light_zone_polygon: list[dict] | None = None,
        frame_w: int = 0,
        frame_h: int = 0,
    ) -> dict[str, Any]:
        bbox = track.get("bbox") or {}
        return {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "event_type": "red_light_violation",
            "event": "red_light_violation",
            "timestamp": timestamp,
            "track_id": track.get("track_id"),
            "class_name": track.get("class_name"),
            "bbox": bbox,
            "confidence": 0.85,
            "severity": "high",
            "frame_width": frame_w or None,
            "frame_height": frame_h or None,
            "metadata": {
                "red_signal_active": True,
                "light_state": light_state,
                "hsv_ratios": hsv_ratios or {},
                "light_zone_polygon": light_zone_polygon or [],
                "motion_px": round(motion_px, 2),
                "detection_method": "zone_traffic_light_synergy",
            },
        }
```

## 4. Intégration Frigate côté backend Go

### 4.1 `compiler.go` (fichier complet)

- Path: `backend/internal/frigate/compiler.go`
- Lines: 308

```go
package frigate

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"go.yaml.in/yaml/v3"

	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

// errConfigUnchanged means the generated YAML matches disk — skip Frigate reload.
var errConfigUnchanged = errors.New("frigate config unchanged")

// CameraEntry is the Frigate camera config block for one CitéVision camera.
type CameraEntry struct {
	FFmpeg struct {
		Inputs []struct {
			Path      string   `yaml:"path"`
			InputArgs string   `yaml:"input_args,omitempty"`
			Roles     []string `yaml:"roles"`
		} `yaml:"inputs"`
	} `yaml:"ffmpeg"`
	Detect struct {
		Enabled bool `yaml:"enabled"`
		Width   int  `yaml:"width,omitempty"`
		Height  int  `yaml:"height,omitempty"`
		FPS     int  `yaml:"fps,omitempty"`
	} `yaml:"detect"`
	Record struct {
		Enabled bool `yaml:"enabled"`
	} `yaml:"record"`
	Snapshots struct {
		Enabled bool `yaml:"enabled"`
	} `yaml:"snapshots"`
	LPR struct {
		Enabled bool `yaml:"enabled"`
	} `yaml:"lpr"`
	Objects struct {
		Track []string `yaml:"track,omitempty"`
	} `yaml:"objects,omitempty"`
	Live struct {
		Streams map[string]string `yaml:"streams,omitempty"`
	} `yaml:"live,omitempty"`
	Zones map[string]ZoneEntry `yaml:"zones,omitempty"`
}

type ZoneEntry struct {
	Coordinates string `yaml:"coordinates"`
	Filters     struct {
		MinArea float64 `yaml:"min_area,omitempty"`
	} `yaml:"filters,omitempty"`
}

// EvidenceAggregate drives record/snapshots/lpr per camera from active rules.
type EvidenceAggregate struct {
	RecordEnabled    bool
	SnapshotsEnabled bool
	LPREnabled       bool
}

// Compiler builds frigate.generated.yml from DB state.
type Compiler struct {
	cfg Config
}

func NewCompiler(cfg Config) *Compiler {
	return &Compiler{cfg: cfg}
}

func (c *Compiler) BuildConfig(
	cameras []CompiledCamera,
) ([]byte, error) {
	base, err := c.loadBase()
	if err != nil {
		return nil, err
	}
	camMap := map[string]CameraEntry{}
	go2rtcStreams := map[string][]string{}
	for _, cam := range cameras {
		camMap[cam.FrigateID] = cam.Entry
		go2rtcStreams[cam.FrigateID] = []string{
			cam.UpstreamURL,
			fmt.Sprintf("ffmpeg:%s#audio=opus", cam.FrigateID),
		}
	}
	base["cameras"] = camMap
	go2rtc, _ := base["go2rtc"].(map[string]interface{})
	if go2rtc == nil {
		go2rtc = map[string]interface{}{}
	}
	go2rtc["streams"] = go2rtcStreams
	base["go2rtc"] = go2rtc
	// Frigate 0.17+ requires global lpr.enabled when any camera has lpr.enabled.
	for _, entry := range camMap {
		if entry.LPR.Enabled {
			base["lpr"] = map[string]interface{}{"enabled": true}
			break
		}
	}
	return yaml.Marshal(base)
}

func (c *Compiler) WriteGenerated(data []byte) error {
	dir := c.cfg.GeneratedDir
	if dir == "" {
		dir = filepath.Dir(c.cfg.ConfigPath)
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	target := c.cfg.ConfigPath
	if target == "" {
		target = filepath.Join(dir, "frigate.generated.yml")
	}
	if prev, err := os.ReadFile(target); err == nil && bytes.Equal(prev, data) {
		return errConfigUnchanged
	}
	tmp := target + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, target)
}

func (c *Compiler) loadBase() (map[string]interface{}, error) {
	path := c.cfg.BaseYAML
	if path == "" {
		path = "infra/frigate.base.yaml"
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read base yaml: %w", err)
	}
	var base map[string]interface{}
	if err := yaml.Unmarshal(raw, &base); err != nil {
		return nil, fmt.Errorf("parse base yaml: %w", err)
	}
	if base == nil {
		base = map[string]interface{}{}
	}
	return base, nil
}

// CompiledCamera pairs a Frigate camera id with its config entry.
type CompiledCamera struct {
	FrigateID   string
	CameraID    string
	OrgID       string
	UpstreamURL string
	Entry       CameraEntry
}

// UpsertCamera builds a Frigate camera entry from CitéVision camera + RTSP URL.
func UpsertCamera(cam *models.Camera, rtspURL string, stats *camera.StreamStats, agg EvidenceAggregate, zones []models.Zone) CompiledCamera {
	fid := CameraID(cam.ID.String())
	entry := CameraEntry{}
	entry.Detect.Enabled = true
	entry.Detect.FPS = 10
	if stats != nil && stats.Width > 0 && stats.Height > 0 {
		entry.Detect.Width = stats.Width
		entry.Detect.Height = stats.Height
	} else {
		entry.Detect.Width = 1280
		entry.Detect.Height = 720
	}
	entry.Objects.Track = []string{"car", "truck", "motorcycle", "bus", "van"}
	entry.Record.Enabled = agg.RecordEnabled
	entry.Snapshots.Enabled = agg.SnapshotsEnabled
	entry.LPR.Enabled = agg.LPREnabled
	cfg := ConfigFromEnv()
	if cfg.Evidence && !cfg.DemoMode {
		entry.Snapshots.Enabled = true
		entry.Record.Enabled = true
	} else if cfg.Evidence && cfg.DemoMode {
		// Demo: snapshots on events only; record follows rule aggregate (event clips).
		entry.Snapshots.Enabled = agg.SnapshotsEnabled || agg.RecordEnabled
		// strict_frigate demo must keep record+snapshots even while other demo rules
		// are toggled off during 1-hit validation — otherwise Frigate stops emitting
		// clip events and evidence capture fails closed.
		if strings.EqualFold(strings.TrimSpace(os.Getenv("DEMO_EVIDENCE_BACKEND")), "strict_frigate") {
			entry.Record.Enabled = true
			entry.Snapshots.Enabled = true
		}
	}
	// Phase A Tâche 6: demo go2rtc cameras always keep record+snapshots permanent
	// so toggling rules never drops Frigate media (and avoids rebuild storms).
	if isDemoGo2rtcCamera(cam.Metadata) {
		entry.Record.Enabled = true
		entry.Snapshots.Enabled = true
	}
	upstream := frigateUpstreamPath(cam.ID.String(), rtspURL, cam.Metadata)
	roles := []string{"detect"}
	if entry.Record.Enabled {
		roles = append(roles, "record")
	}
	ffmpegPath := upstream
	inputArgs := ""
	if cfg.InputViaGo2RTC {
		ffmpegPath = frigateRestreamPath(fid)
		inputArgs = "preset-rtsp-restream"
	}
	entry.FFmpeg.Inputs = []struct {
		Path      string   `yaml:"path"`
		InputArgs string   `yaml:"input_args,omitempty"`
		Roles     []string `yaml:"roles"`
	}{
		{
			Path:      ffmpegPath,
			InputArgs: inputArgs,
			Roles:     roles,
		},
	}
	entry.Live.Streams = map[string]string{"Live": fid}
	if len(zones) > 0 {
		entry.Zones = map[string]ZoneEntry{}
		for _, z := range zones {
			if z.CameraID == nil || *z.CameraID != cam.ID {
				continue
			}
			coords := polygonToFrigateCoords(z.Polygon)
			if coords == "" {
				continue
			}
			entry.Zones[ZoneID(z.ID.String())] = ZoneEntry{Coordinates: coords}
		}
	}
	return CompiledCamera{
		FrigateID:   fid,
		CameraID:    cam.ID.String(),
		OrgID:       cam.OrgID.String(),
		UpstreamURL: upstream,
		Entry:       entry,
	}
}

func frigateRestreamPath(frigateID string) string {
	return fmt.Sprintf("rtsp://127.0.0.1:8554/%s", frigateID)
}

// frigateUpstreamPath is the external source registered in go2rtc.streams (Docker-safe relay by default).
func frigateUpstreamPath(cameraUUID, rtspURL string, meta json.RawMessage) string {
	cfg := ConfigFromEnv()
	if demo := demoGo2rtcStreamName(meta, rtspURL); demo != "" {
		return fmt.Sprintf("rtsp://%s:%d/%s", cfg.Go2RTCHost, cfg.Go2RTCPort, demo)
	}
	if cfg.InputViaGo2RTC {
		return fmt.Sprintf("rtsp://%s:%d/cam-%s", cfg.Go2RTCHost, cfg.Go2RTCPort, cameraUUID)
	}
	return rtspURL
}

// demoGo2rtcStreamName resolves the looped demo file stream (demo-{org}-{video}) for Frigate/go2rtc.
func demoGo2rtcStreamName(meta json.RawMessage, rtspURL string) string {
	var m map[string]interface{}
	_ = json.Unmarshal(meta, &m)
	if m != nil {
		if src, _ := m["go2rtc_src"].(string); strings.TrimSpace(src) != "" {
			return strings.TrimSpace(src)
		}
	}
	path := rtspURL
	if i := strings.Index(path, "://"); i >= 0 {
		if j := strings.Index(path[i+3:], "/"); j >= 0 {
			path = path[i+3+j:]
		}
	}
	name := strings.TrimPrefix(path, "/")
	if strings.HasPrefix(name, "demo-") {
		return name
	}
	return ""
}

func polygonToFrigateCoords(polygon json.RawMessage) string {
	if len(polygon) == 0 {
		return ""
	}
	var pts []map[string]float64
	if err := json.Unmarshal(polygon, &pts); err != nil {
		var alt [][]float64
		if err2 := json.Unmarshal(polygon, &alt); err2 != nil {
			return ""
		}
		var parts []string
		for _, p := range alt {
			if len(p) >= 2 {
				parts = append(parts, fmt.Sprintf("%.4f,%.4f", p[0], p[1]))
			}
		}
		return strings.Join(parts, ",")
	}
	var parts []string
	for _, p := range pts {
		x, okX := p["x"]
		y, okY := p["y"]
		if okX && okY {
			parts = append(parts, fmt.Sprintf("%.4f,%.4f", x, y))
		}
	}
	return strings.Join(parts, ",")
}
```

### 4.2 `FRIGATE-INTEGRATION.md` (fichier complet)

- Path: `docs/FRIGATE-INTEGRATION.md`
- Lines: 59

```markdown
# Frigate integration — CitéVision v2

## Invariant

**zone → IA → règle → preuve** — Frigate is a **media plane** only. Business logic stays in CitéVision DB, rules-engine, and ai-engine analytics.

## ID conventions

| Entity | CitéVision | Frigate |
|--------|------------|---------|
| Camera | UUID | `cv_{uuid}` |
| Zone | UUID | `cv_zone_{uuid}` |

## Camera metadata (JSON)

After sync:

```json
{
  "frigate_camera_id": "cv_d2eb7076-...",
  "frigate_synced_at": "2026-07-09T15:00:00Z",
  "frigate_error": null
}
```

## Feature flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `FRIGATE_ENABLED` | `0` | Master switch |
| `FRIGATE_CONFIG_SYNC` | `0` | DB → generated config |
| `FRIGATE_LIVE` | `0` | Frigate player on `/live` |
| `FRIGATE_EVIDENCE` | `0` | Evidence via Frigate recordings |
| `FRIGATE_EVENTS` | `0` | MQTT adapter (debug only) |
| `FRIGATE_URL` | `http://127.0.0.1:5000` | API base |
| `EVIDENCE_BACKEND` | `ring_buffer` | `ring_buffer` \| `frigate` \| `hybrid` |

## Evidence contract

Input: `EvidencePolicy` from `rule.definition.evidence` (matched by `EvidenceCaptureGate`).

Output: `EvidencePackage` per [shared/schemas/evidence.json](../shared/schemas/evidence.json).

Plate slot (`role=plate`): crop from Frigate snapshot + **PaddleOCR** (ai-engine). Frigate LPR is **live zoom only**.

## Config compiler

Single writer: `backend/internal/frigate` → `infra/frigate-config/config.yml`.

Never edit Frigate YAML by hand in production.

## Baseline (cam 108)

Run before/after integration:

```bash
python3 scripts/audit_evidence_quality.py --limit 20
python3 scripts/frigate_baseline.py
```
```

## 5. Modèle de données

### 5.1 ORM Go — Zone / Line / Event / Rule / Alert

```go
type Zone struct {
	ID        uuid.UUID       `json:"id"`
	OrgID     uuid.UUID       `json:"org_id"`
	SiteID    uuid.UUID       `json:"site_id"`
	CameraID  *uuid.UUID      `json:"camera_id,omitempty"`
	Name      string          `json:"name"`
	Polygon   json.RawMessage `json:"polygon"`
	Color     string          `json:"color"`
	ZoneKind  string          `json:"zone_kind,omitempty"`
	// BehaviorConfig holds the rich per-zone AI behavior: {"behavior":"<id>","config":{...}}.
	// Supersedes ZoneKind when a behavior is set. See shared/zone-behaviors.json.
	BehaviorConfig json.RawMessage `json:"behavior_config,omitempty"`
	IsActive       bool            `json:"is_active"`
	CreatedAt time.Time       `json:"created_at"`
	UpdatedAt time.Time       `json:"updated_at"`
}

type Line struct {
	ID         uuid.UUID       `json:"id"`
	OrgID      uuid.UUID       `json:"org_id"`
	SiteID     uuid.UUID       `json:"site_id"`
	CameraID   *uuid.UUID      `json:"camera_id,omitempty"`
	Name       string          `json:"name"`
	StartPoint json.RawMessage `json:"start_point"`
	EndPoint   json.RawMessage `json:"end_point"`
	Direction  *string         `json:"direction,omitempty"`
	// BehaviorConfig mirrors zones: {"behavior":"line_cross","config":{"class_filter":"...","direction":"..."}}.
	BehaviorConfig json.RawMessage `json:"behavior_config,omitempty"`
	IsActive       bool            `json:"is_active"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
}

type Event struct {
	ID               uuid.UUID       `json:"id"`
	OrgID            uuid.UUID       `json:"org_id"`
	SiteID           *uuid.UUID      `json:"site_id,omitempty"`
	CameraID         *uuid.UUID      `json:"camera_id,omitempty"`
	EventType        string          `json:"event_type"`
	Severity         string          `json:"severity"`
	Payload          json.RawMessage `json:"payload"`
	EvidenceSnapshot json.RawMessage `json:"evidence_snapshot,omitempty"`
	OccurredAt       time.Time       `json:"occurred_at"`
	IngestedAt       time.Time       `json:"ingested_at"`
}

type Rule struct {
	ID          uuid.UUID       `json:"id"`
	OrgID       uuid.UUID       `json:"org_id"`
	SiteID      *uuid.UUID      `json:"site_id,omitempty"`
	Name        string          `json:"name"`
	Description *string         `json:"description,omitempty"`
	Definition  json.RawMessage `json:"definition"`
	IsEnabled   bool            `json:"is_enabled"`
	Priority    int             `json:"priority"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

type Alert struct {
	ID        uuid.UUID       `json:"id"`
	OrgID     uuid.UUID       `json:"org_id"`
	SiteID    *uuid.UUID      `json:"site_id,omitempty"`
	RuleID    *uuid.UUID      `json:"rule_id,omitempty"`
	EventID   *uuid.UUID      `json:"event_id,omitempty"`
	Title     string          `json:"title"`
	Message   *string         `json:"message,omitempty"`
	Severity  string          `json:"severity"`
	Status    string          `json:"status"`
	Metadata  json.RawMessage `json:"metadata"`
	CreatedAt time.Time       `json:"created_at"`
	UpdatedAt time.Time       `json:"updated_at"`
}
```
### 5.2 Migration zones/lines

- Path: `backend/migrations/000006_zones_lines.up.sql`
- Lines: 29

```sql
CREATE TABLE zones (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    camera_id   UUID REFERENCES cameras(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    polygon     JSONB NOT NULL,
    color       TEXT NOT NULL DEFAULT '#FF5733',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE lines (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    camera_id   UUID REFERENCES cameras(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    start_point JSONB NOT NULL,
    end_point   JSONB NOT NULL,
    direction   TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_zones_site ON zones (site_id);
CREATE INDEX idx_lines_site ON lines (site_id);
```

### 5.3 Migration events/rules

- Path: `backend/migrations/000007_events_rules.up.sql`
- Lines: 31

```sql
CREATE TYPE event_severity AS ENUM ('info', 'low', 'medium', 'high', 'critical');

CREATE TABLE events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id         UUID REFERENCES sites(id) ON DELETE SET NULL,
    camera_id       UUID REFERENCES cameras(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,
    severity        event_severity NOT NULL DEFAULT 'info',
    payload         JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id     UUID REFERENCES sites(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    description TEXT,
    definition  JSONB NOT NULL,
    is_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    priority    INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_org_time ON events (org_id, occurred_at DESC);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_rules_org ON rules (org_id);
CREATE INDEX idx_rules_org_enabled ON rules (org_id, is_enabled) WHERE is_enabled = TRUE;
```

### 5.4 Migration zone_kind

- Path: `backend/migrations/000016_zone_kind.up.sql`
- Lines: 1

```sql
ALTER TABLE zones ADD COLUMN IF NOT EXISTS zone_kind TEXT NOT NULL DEFAULT '';
```

### 5.5 Migration behavior_config zones

- Path: `backend/migrations/000019_zone_behaviors.up.sql`
- Lines: 11

```sql
-- Rich, extensible AI behavior configuration per zone.
-- behavior_config holds: { "behavior": "<id>", "config": { ... } }
-- where <id> is one of the entries in shared/zone-behaviors.json.
-- zone_kind is kept for backward compatibility; behavior supersedes it when set.
ALTER TABLE zones ADD COLUMN IF NOT EXISTS behavior_config JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Backfill behavior_config from legacy zone_kind so existing zones keep working.
UPDATE zones
SET behavior_config = jsonb_build_object('behavior', zone_kind)
WHERE (behavior_config = '{}'::jsonb OR behavior_config IS NULL)
  AND zone_kind <> '';
```

### 5.6 Migration line_counters

- Path: `backend/migrations/000020_line_counters.up.sql`
- Lines: 18

```sql
-- Persistent per-line crossing counters, incremented on every line_cross event.
-- line_id stores the line NAME (the identifier carried in AI events), with the
-- line UUID kept when resolvable for joins.
CREATE TABLE IF NOT EXISTS line_counters (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    camera_id   UUID REFERENCES cameras(id) ON DELETE CASCADE,
    line_id     TEXT NOT NULL,
    count_in    BIGINT NOT NULL DEFAULT 0,
    count_out   BIGINT NOT NULL DEFAULT 0,
    count_total BIGINT NOT NULL DEFAULT 0,
    last_class  TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, camera_id, line_id)
);

CREATE INDEX IF NOT EXISTS idx_line_counters_org_cam ON line_counters (org_id, camera_id);
```

### 5.7 Migration behavior_config lines

- Path: `backend/migrations/000021_line_behaviors.up.sql`
- Lines: 15

```sql
-- Rich, extensible AI behavior configuration per line (mirrors zones.behavior_config).
-- behavior_config holds: { "behavior": "<id>", "config": { "class_filter": "...", ... } }
-- Lets a counting line own its class_filter / direction as the single source of truth ([C.27]/[C.30]).
ALTER TABLE lines ADD COLUMN IF NOT EXISTS behavior_config JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Backfill: existing lines are counting lines. Keep any configured direction.
UPDATE lines
SET behavior_config = jsonb_build_object(
        'behavior', 'line_cross',
        'config', jsonb_build_object(
            'class_filter', 'any',
            'direction', COALESCE(direction, 'both')
        )
    )
WHERE behavior_config = '{}'::jsonb OR behavior_config IS NULL;
```

### 5.8 Extrait représentatif `shared/ai-capabilities.json`

- Templates totaux: 90
- `supported: true`: 81
- `supported: false`: 9

```json
{
  "templates_sample": {
    "tpl-speeding-premium": {
      "supported": true,
      "capability_id": "speeding",
      "human_description": "Excès de vitesse (routier national).",
      "prerequisites": [
        "Calibration caméra"
      ],
      "configSchema": {
        "fields": [
          {
            "key": "camera_id",
            "type": "camera",
            "label": "Caméra",
            "required": true
          },
          {
            "key": "speed_kmh",
            "type": "number",
            "label": "Limite (km/h)",
            "required": true,
            "default": 50
          }
        ]
      },
      "role_summary_fr": "Alerte vitesse avancée avec calcul homographique précis et capture de la plaque."
    },
    "tpl-red-light": {
      "supported": true,
      "capability_id": "red_light_violation",
      "human_description": "Franchissement feu rouge (HSV + zone).",
      "tutorial": "Détection HSV rouge sur ROI feu + véhicule en zone. Preuve Frigate ou ring-buffer selon capture_source.",
      "prerequisites": [
        "Modèle YOLO actif",
        "Zone intersection",
        "Calibrage ROI feu"
      ],
      "configSchema": {
        "fields": [
          {
            "key": "camera_id",
            "type": "camera",
            "label": "Caméra",
            "required": true
          },
          {
            "key": "zone_name",
            "type": "zone",
            "label": "Zone feu",
            "required": true
          }
        ]
      },
      "role_summary_fr": "Passage au rouge via HSV — calibrage requis ; vérifier capture_source (frigate_track vs demo_ring_buffer)."
    },
    "tpl-phone-driving": {
      "supported": true,
      "capability_id": "phone_use_violation",
      "human_description": "Téléphone au volant (modèle secondaire ONNX phone_use).",
      "tutorial": "Zone habitacle + modèle driver_phone. Event émis: phone_use_violation (pas phone_driving heuristique).",
      "prerequisites": [
        "Modèle YOLO actif",
        "Modèle secondaire driver_phone"
      ],
      "configSchema": {
        "fields": [
          {
            "key": "camera_id",
            "type": "camera",
            "label": "Caméra",
            "required": true
          }
        ]
      },
      "role_summary_fr": "Détecte l'utilisation d'un téléphone au volant via modèle ONNX — event_type phone_use_violation."
    },
    "tpl-seatbelt": {
      "supported": true,
      "capability_id": "seatbelt_violation",
      "human_description": "Ceinture non portée (modèle secondaire ONNX seatbelt).",
      "tutorial": "Zone habitacle + modèle seatbelt. Preuves cabine ring/live (pas Frigate track).",
      "prerequisites": [
        "Modèle YOLO actif",
        "Modèle secondaire seatbelt"
      ],
      "configSchema": {
        "fields": [
          {
            "key": "camera_id",
            "type": "camera",
            "label": "Caméra",
            "required": true
          }
        ]
      },
      "role_summary_fr": "Détecte l'absence de ceinture via modèle ONNX — preuves cabine ring/live."
    },
    "tpl-line-cross": {
      "supported": true,
      "capability_id": "line_cross",
      "human_description": "Détecte le franchissement d'une ligne de comptage.",
      "configSchema": {
        "fields": [
          {
            "key": "camera_id",
            "type": "camera",
            "label": "Caméra",
            "required": true
          },
          {
            "key": "line_name",
            "type": "line",
            "label": "Ligne",
            "required": true
          },
          {
            "key": "class_filter",
            "type": "class_filter",
            "label": "Objet surveillé",
            "required": true
          },
          {
            "key": "direction",
            "type": "enum",
            "label": "Direction",
            "required": false,
            "options": [
              {
                "value": "both",
                "label": "Les deux sens"
              },
              {
                "value": "in",
                "label": "Entrée seulement"
              },
              {
                "value": "out",
                "label": "Sortie seulement"
              }
            ],
            "default": "both"
          }
        ]
      },
      "role_summary_fr": "Alerte dès qu'un objet franchit la ligne de comptage, dans n'importe quel sens."
    },
    "tpl-scene-occupancy": {
      "supported": false,
      "capability_id": "crowd_count_threshold",
      "human_description": "Nombre total de personnes dans la scène dépassant le seuil.",
      "tutorial": "Définissez le nombre maximal de personnes toléré dans le champ caméra.",
      "prerequisites": [
        "Modèle YOLO actif"
      ],
      "configSchema": {
        "fields": [
          {
            "key": "camera_id",
            "type": "camera",
            "label": "Caméra",
            "required": true
          },
          {
            "key": "crowd_threshold",
            "type": "number",
            "label": "Seuil personnes",
            "required": true,
            "min": 1,
            "max": 500,
            "default": 10
          }
        ]
      }
    },
    "tpl-vandalism": {
      "supported": false,
      "capability_id": "crowd_gathering",
      "human_description": "Vandalisme suspect : groupe + activité rapide.",
      "tutorial": "Seuil foule + détection running/rapid_activity (métadonnée behavior).",
      "prerequisites": [
        "Modèle YOLO actif"
      ],
      "configSchema": {
        "fields": [
          {
            "key": "camera_id",
            "type": "camera",
            "label": "Caméra",
            "required": true
          },
          {
            "key": "crowd_threshold",
            "type": "number",
            "label": "Seuil personnes",
            "required": true,
            "default": 2
          }
        ]
      },
      "role_summary_fr": "Détecte les comportements de dégradation : présence longue + mouvement erratique."
    }
  }
}
```

---

## 6. Tests existants

### 6.1 `test_demo_loop_guard.py`

- Path: `ai-engine/tests/test_demo_loop_guard.py`
- Lines: 111

```python
"""demo_loop_guard — reject stale Frigate events across demo loop iterations."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from citevision_ai.evidence.frigate_timeline import (
    demo_loop_absolute_align_ok,
    same_demo_loop_cycle,
)
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence


def test_absolute_align_ok():
    assert demo_loop_absolute_align_ok(0.4, 30.0) is True
    assert demo_loop_absolute_align_ok(720.444, 30.0) is False


def test_same_demo_loop_cycle_rejects_full_loop_gap():
    loop = 352.52
    t0 = 1_700_000_000.0
    assert same_demo_loop_cycle(t0, t0 + 5.0, loop) is True
    assert same_demo_loop_cycle(t0, t0 + loop, loop) is False
    assert same_demo_loop_cycle(t0, t0 + 2 * loop, loop) is False


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_accept_rejects_720s_delta_under_demo_loop_guard(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.demo_red_light_loop_sec = 352.52
    mock_settings.frigate_demo_accept_max_align_sec = 30.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12

    engine = FrigateTrackEvidence()
    anchor = 1_784_483_713.0 + 720.444
    evt = {
        "event_type": "speeding",
        "bbox_ts": anchor,
        "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        "frigate_event_id": "1784483713.108543-spihzy",  # bound trust must NOT bypass
        "class_name": "car",
    }
    matched = {
        "id": "1784483713.108543-spihzy",
        "label": "car",
        "start_time": 1_784_483_713.108543,
        "data": {"box": [0.2, 0.3, 0.2, 0.2]},
    }
    assert engine._accept_correlation(evt, matched, 720.444, "cam-speed") is False


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_accept_allows_tight_delta_under_demo_loop_guard(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.demo_red_light_loop_sec = 352.52
    mock_settings.frigate_demo_accept_max_align_sec = 30.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12

    engine = FrigateTrackEvidence()
    t0 = 1_784_483_713.0
    evt = {
        "event_type": "speeding",
        "bbox_ts": t0 + 0.5,
        "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        "class_name": "car",
    }
    matched = {
        "id": "fresh-ev",
        "label": "car",
        "start_time": t0,
        "data": {"box": [0.2, 0.3, 0.2, 0.2]},
    }
    assert engine._accept_correlation(evt, matched, 0.5, "cam-speed") is True


@patch("citevision_ai.evidence.frigate_track_evidence.settings")
def test_soft_red_does_not_widen_align_window(mock_settings: MagicMock):
    mock_settings.demo_loop_guard = True
    mock_settings.demo_mode = True
    mock_settings.demo_relaxed_evidence = lambda: True
    mock_settings.demo_red_light_loop_sec = 352.52
    mock_settings.frigate_demo_accept_max_align_sec = 30.0
    mock_settings.frigate_accept_min_bbox_iou = 0.15
    mock_settings.frigate_demo_timeline_align = True
    mock_settings.frigate_bind_min_iou = 0.12
    mock_settings.demo_mode_source = "test"

    engine = FrigateTrackEvidence()
    t0 = 1_784_483_713.0
    evt = {
        "event_type": "red_light_violation",
        "bbox_ts": t0 + 90.0,
        "bbox": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        "metadata": {"frigate_red_light_soft_iou": -1.0},
        "class_name": "car",
    }
    matched = {
        "id": "stale-red",
        "label": "car",
        "start_time": t0,
        "data": {"box": [0.2, 0.3, 0.2, 0.2]},
    }
    # 90s > RED_LIGHT_MAX_ALIGN_SEC (8) and > would-be soft bypass
    assert engine._accept_correlation(evt, matched, 90.0, "cam-feux") is False
```

### 6.2 `test_frigate_track_binder.py`

- Path: `ai-engine/tests/test_frigate_track_binder.py`
- Lines: 72

```python
#!/usr/bin/env python3
"""Tests for proactive Frigate track binding."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from citevision_ai.evidence.frigate_track_binder import FrigateTrackBinder


class FrigateTrackBinderTests(unittest.TestCase):
    def test_inject_event_sets_frigate_event_id(self) -> None:
        track = MagicMock()
        track.enabled.return_value = True
        binder = FrigateTrackBinder(track)
        binder._bindings[("cam-1", 7)] = type("B", (), {
            "frigate_event_id": "1783942846.01981-b55uqn",
            "align_delta": 0.4,
            "iou": 0.55,
            "bound_at": 1.0,
        })()
        evt: dict = {"track_id": 7, "event_type": "speeding", "metadata": {}}
        binder.inject_event("cam-1", evt)
        self.assertEqual(evt["frigate_event_id"], "1783942846.01981-b55uqn")
        self.assertAlmostEqual(evt["metadata"]["frigate_bind_iou"], 0.55)

    @patch("citevision_ai.evidence.frigate_track_binder.settings")
    def test_update_tracks_skips_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_track_binding_enabled = False
        track = MagicMock()
        track.enabled.return_value = True
        binder = FrigateTrackBinder(track)
        binder.update_tracks(
            "cam-1",
            [{"track_id": 1, "class_name": "car", "bbox": {"x": 10, "y": 10, "width": 50, "height": 40}}],
            frame_w=640,
            frame_h=480,
            wall_ts=1000.0,
        )
        track.list_events_for_camera.assert_not_called()

    @patch("citevision_ai.evidence.frigate_track_binder.settings")
    def test_update_tracks_reserves_on_iou_match(self, mock_settings: MagicMock) -> None:
        mock_settings.frigate_track_binding_enabled = True
        mock_settings.frigate_bind_every_n_frames = 1
        mock_settings.frigate_bind_min_iou = 0.12
        track = MagicMock()
        track.enabled.return_value = True
        track.frigate_camera_id.return_value = "cv_cam-1"
        track.list_events_for_camera.return_value = [{"id": "ev-1", "label": "car"}]
        track.match_track_to_event.return_value = (
            {"id": "ev-1", "label": "car"},
            0.5,
            0.42,
        )
        binder = FrigateTrackBinder(track)
        binder.update_tracks(
            "cam-1",
            [{"track_id": 3, "class_name": "car", "bbox": {"x": 100, "y": 80, "width": 120, "height": 90}}],
            frame_w=640,
            frame_h=480,
            wall_ts=1783944000.0,
        )
        got = binder.get("cam-1", 3)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.frigate_event_id, "ev-1")
        self.assertAlmostEqual(got.iou, 0.42)


if __name__ == "__main__":
    unittest.main()
```

### 6.3 Couverture actuelle vs correctif proposé

| Scénario | Couvert ? |
|----------|-----------|
| Reject delta 720s sous demo_loop_guard | Oui |
| Accept delta serré | Oui |
| Soft red ne élargit pas la fenêtre | Oui |
| inject_event pose frigate_event_id | Oui |
| update_tracks skip si disabled | Oui |
| update_tracks réserve sur IoU | Oui |
| Bound frais + IoU OK pour speeding | **Non** (à ajouter) |
| Bound vieux (>max_age) → re-correlate | **Non** |
| IoU 0 → missing (pas soft) | **Non** |
| ignore_time_filter=False en démo | **Non** |

---
## 7. Logs/données réelles récentes

### 7.0 Synthèse pour calibrer `max_age_sec` / seuils

D’après le log runtime WSL au moment de la génération du bundle :

| Observation | Implication correctif |
|-------------|----------------------|
| Boucle dominante : `demo vehicle fallback` → `demo_loop_guard reject` avec `align_delta_sec` **~308–753 s** | Le fallback « dernier véhicule » est **hors cycle** ; à supprimer pour road rules |
| `offset=none` sur `no correlated event` | L’EMA `_demo_clock_offset` **n’est pas apprise** (ou reset) avant correlate feu |
| Rejet `via=demo_loop_guard_fallback` (count 199→214+) | Le guard temporel marche ; le soft path ne devrait même pas être tenté |
| `bound_at` **absent** des logs / snapshots | Impossible de figer `max_age_sec` empiriquement tant qu’on n’instrumente pas l’inject |
| Audit API alertes PARTIAL | Backend API down (`Connection refused`) au moment du dump — relancer stack puis `python3 scripts/_tmp_audit_evidence_provenance.py` |
| Suggestion provisoire `max_age_sec` | **2.0–3.0 s** (binder every 2 frames @ ~10 FPS detect ≈ 0.2 s ; marge capture async ~2 s). À confirmer après log `frigate_bind age=` |

- Source log: `/home/gheno/citevision-v2/logs/ai-engine.log`

Lignes filtrées (dernières 80 / 105617 match):

```text
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=308.9s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 199, 'align_delta_sec': 308.855, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624217.903 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 170, 'count_for_event_type': 217, 'anchor_ts': 1784624217.902991}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=752.7s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 200, 'align_delta_sec': 752.708, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784623143.808 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 171, 'count_for_event_type': 218, 'anchor_ts': 1784623143.8075664}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=349.4s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 201, 'align_delta_sec': 349.38, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624258.428 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 172, 'count_for_event_type': 219, 'anchor_ts': 1784624258.4275355}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=349.4s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 202, 'align_delta_sec': 349.38, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624258.428 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 173, 'count_for_event_type': 220, 'anchor_ts': 1784624258.4275355}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=349.4s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 203, 'align_delta_sec': 349.38, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624258.428 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 174, 'count_for_event_type': 221, 'anchor_ts': 1784624258.4275355}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=349.4s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 204, 'align_delta_sec': 349.38, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624258.428 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 175, 'count_for_event_type': 222, 'anchor_ts': 1784624258.4275355}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=354.1s
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 205, 'align_delta_sec': 354.138, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624263.186 offset=none
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=354.1s
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 176, 'count_for_event_type': 223, 'anchor_ts': 1784624263.1855474}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 206, 'align_delta_sec': 354.138, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=354.1s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 207, 'align_delta_sec': 354.138, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624263.186 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 177, 'count_for_event_type': 224, 'anchor_ts': 1784624263.1855474}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624263.186 offset=none
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=354.1s
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 178, 'count_for_event_type': 225, 'anchor_ts': 1784624263.1855474}
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 208, 'align_delta_sec': 354.138, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624263.186 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 179, 'count_for_event_type': 226, 'anchor_ts': 1784624263.1855474}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=752.7s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 209, 'align_delta_sec': 752.708, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784623143.808 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 180, 'count_for_event_type': 227, 'anchor_ts': 1784623143.8075664}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=355.8s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 210, 'align_delta_sec': 355.776, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624264.824 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 181, 'count_for_event_type': 228, 'anchor_ts': 1784624264.8239145}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=355.8s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 211, 'align_delta_sec': 355.776, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624264.824 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 182, 'count_for_event_type': 229, 'anchor_ts': 1784624264.8239145}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=355.8s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 212, 'align_delta_sec': 355.776, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624264.824 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 183, 'count_for_event_type': 230, 'anchor_ts': 1784624264.8239145}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=355.8s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 213, 'align_delta_sec': 355.776, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624264.824 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 184, 'count_for_event_type': 231, 'anchor_ts': 1784624264.8239145}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: red_light_violation demo vehicle fallback cam=8ed20433 (IA bbox on Frigate media) DEMO_MODE=True source=environ:DEMO_MODE
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: demo_loop_guard reject fallback cam=8ed20433 event=1784623896.515994-8c4c8o delta=364.9s
WARNING:citevision_ai.evidence.abort_stats:evidence_probe_reject {'probe_reject': 'align_reject', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'count_for_reason': 214, 'align_delta_sec': 364.943, 'via': 'demo_loop_guard_fallback'}
WARNING:citevision_ai.evidence.frigate_track_evidence:frigate_track: no correlated event cam=8ed20433 anchor=1784624273.990 offset=none
WARNING:citevision_ai.evidence.abort_stats:evidence_abort {'abort_reason': 'no_correlation', 'camera_id': '8ed20433', 'event_type': 'red_light_violation', 'event_id': '', 'count_for_reason': 185, 'count_for_event_type': 232, 'anchor_ts': 1784624273.9900925}
```

### Audit provenance alertes (script)

```text
Traceback (most recent call last):
  File "/usr/lib/python3.12/urllib/request.py", line 1344, in do_open
    h.request(req.get_method(), req.selector, req.data, headers,
  File "/usr/lib/python3.12/http/client.py", line 1365, in request
    self._send_request(method, url, body, headers, encode_chunked)
  File "/usr/lib/python3.12/http/client.py", line 1411, in _send_request
    self.endheaders(body, encode_chunked=encode_chunked)
  File "/usr/lib/python3.12/http/client.py", line 1360, in endheaders
    self._send_output(message_body, encode_chunked=encode_chunked)
  File "/usr/lib/python3.12/http/client.py", line 1120, in _send_output
    self.send(msg)
  File "/usr/lib/python3.12/http/client.py", line 1064, in send
    self.connect()
  File "/usr/lib/python3.12/http/client.py", line 1030, in connect
    self.sock = self._create_connection(
                ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/socket.py", line 852, in create_connection
    raise exceptions[0]
  File "/usr/lib/python3.12/socket.py", line 837, in create_connection
    sock.connect(sa)
ConnectionRefusedError: [Errno 111] Connection refused

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/mnt/c/Users/gheno/citevision/scripts/_tmp_audit_evidence_provenance.py", line 124, in <module>
    main()
  File "/mnt/c/Users/gheno/citevision/scripts/_tmp_audit_evidence_provenance.py", line 27, in main
    login = post(f"{API}/api/v1/auth/login", {"email": email, "password": password})
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/mnt/c/Users/gheno/citevision/scripts/_tmp_audit_evidence_provenance.py", line 16, in post
    with urllib.request.urlopen(req, timeout=20) as r:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/urllib/request.py", line 215, in urlopen
    return opener.open(url, data, timeout)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/urllib/request.py", line 515, in open
    response = self._open(req, data)
               ^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/urllib/request.py", line 532, in _open
    result = self._call_chain(self.handle_open, protocol, protocol +
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/urllib/request.py", line 492, in _call_chain
    result = func(*args)
             ^^^^^^^^^^^
  File "/usr/lib/python3.12/urllib/request.py", line 1373, in http_open
    return self.do_open(http.client.HTTPConnection, req)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/urllib/request.py", line 1347, in do_open
    raise URLError(err)
urllib.error.URLError: <urlopen error [Errno 111] Connection refused>
```

### Note sur `bound_at`

`bound_at` est un champ **in-memory** du dataclass `FrigateTrackBinding` (binder). Il n’est **pas** persisté dans `evidence_snapshot` aujourd’hui. Pour calibrer `max_age_sec`, ajouter un log `frigate_bind ... age=%.2fs` à l’inject, ou écrire `metadata.frigate_bind_age_sec` au moment de l’émission.

---

## 8. Carte des responsabilités (rappel correctif)

```
pipeline.py
  update_frigate_bindings()  --> FrigateTrackBinder.update_tracks()
       |                              |
       |                              v
       |                     FrigateTrackEvidence.match_track_to_event()
       |                              |  (today: ignore_time_filter=True)
       |                              v
       |                     learn_clock_offset / _demo_clock_offset
       |
       v
  emit event (bbox_ts, track_id, bbox IA)
       |
       +-- inject_frigate_binding  [SKIP red_light/speeding today]
       |
       v
  FrigateTrackEvidence.capture / _capture_impl
       |
       +-- ignore bound_id for red_light/speeding  [today]
       +-- _correlate_event (+ timeline align)
       +-- soft-accept IoU / demo vehicle fallback  [remove for honesty]
       +-- _compose_from_matched --> evidence package
```

Correctif cible (résumé):

1. Durcir binder (temps + loop cycle + IoU)
2. Réinjecter bind feu/vitesse si frais (`max_age_sec` à calibrer via logs §7)
3. Trust bound road seulement si `_bound_usable_for_road` (à créer)
4. Couper soft-accept + `_demo_latest_vehicle_event` pour road rules

---

*Fin du bundle.*
