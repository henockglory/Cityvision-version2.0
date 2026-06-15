from __future__ import annotations

import copy
import logging
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
from citevision_ai.behavior.heuristics import BEHAVIOR_EVENT_TYPES, BehaviorHeuristics
from citevision_ai.budget.resource_budget import ResourceBudgetManager
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
from citevision_ai.events.generator import EventGenerator
from citevision_ai.evidence.service import EvidenceCaptureService
from citevision_ai.identity.face import FaceIdentityEngine
from citevision_ai.identity.plate import PlateIdentityEngine
from citevision_ai.models.schemas import BBox, Detection, DetectionFrame
from citevision_ai.mqtt.publisher import MqttPublisher
from citevision_ai.tracking.bytetrack import ByteTracker

logger = logging.getLogger(__name__)

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
        self.evidence = EvidenceCaptureService()
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

    def register_camera(self, camera_id: str, spatial_config: dict[str, Any] | None = None) -> None:
        self.budget.register_camera(camera_id)
        self._trackers[camera_id] = ByteTracker(min_hits=1)
        self._frame_counters[camera_id] = 0
        if spatial_config:
            if org := spatial_config.get("org_id"):
                self._org_ids[camera_id] = str(org)
            self.set_spatial_config(camera_id, spatial_config)

    def set_org_id(self, camera_id: str, org_id: str) -> None:
        if org_id:
            self._org_ids[camera_id] = org_id

    def unregister_camera(self, camera_id: str) -> None:
        self.budget.unregister_camera(camera_id)
        self._trackers.pop(camera_id, None)
        self._frame_counters.pop(camera_id, None)
        self._spatial_configs.pop(camera_id, None)
        self._calibrations.pop(camera_id, None)
        self._runtime_config.pop(camera_id, None)
        self._line_configs.pop(camera_id, None)
        self._org_ids.pop(camera_id, None)
        self.evidence.clear_camera(camera_id)

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

    def _runtime_for(self, camera_id: str) -> dict[str, Any]:
        return self._runtime_config.get(camera_id, {})

    def set_rules(self, rules: list[dict]) -> None:
        self._rules = rules

    def set_spatial_config(self, camera_id: str, config: dict[str, Any]) -> None:
        self._spatial_configs[camera_id] = config
        calib = CalibrationEngine(config.get("calibration"))
        self._calibrations[camera_id] = calib
        line_map: dict[str, dict[str, Any]] = {}
        for line in config.get("lines", []):
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

    def _build_spatial_rules(self, camera_id: str, config: dict[str, Any]) -> list[dict]:
        rules: list[dict] = []
        for zone in config.get("zones", []):
            zone_id = zone.get("zone_id", zone.get("name", "zone"))
            polygon = zone.get("polygon", [])
            rules.append({
                "camera_id": camera_id,
                "rule_type": "zone",
                "enabled": True,
                "zone": {
                    "zone_id": zone_id,
                    "polygon": polygon,
                },
            })
            rules.append({
                "camera_id": camera_id,
                "rule_type": "loitering",
                "enabled": True,
                "loitering": {
                    "zone_id": zone_id,
                    "threshold_seconds": zone.get("loiter_threshold", 30),
                },
                "zone": {"polygon": polygon},
            })
        for pr in config.get("presence_rules", []):
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
        for line in config.get("lines", []):
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

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        source_fps: float = 30.0,
    ) -> DetectionFrame:
        frame_id = self._frame_counters.get(camera_id, 0)
        self._frame_counters[camera_id] = frame_id + 1
        self.state_engine.set_fps(source_fps)
        now_ts = time.monotonic()
        self._timestamps[camera_id] = now_ts
        self.evidence.push_frame(camera_id, frame)
        rt = self._runtime_for(camera_id)
        if rt.get("duration_seconds"):
            self.state_engine.dwell_threshold_sec = float(rt["duration_seconds"])
        if rt.get("speed_kmh"):
            self.behavior.speed_threshold = float(rt["speed_kmh"])

        skip = self.budget.frame_skip_interval(source_fps)
        if frame_id % skip != 0:
            h, w = frame.shape[:2]
            return DetectionFrame(
                camera_id=camera_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
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
        tracks = tracker.update(raw_dets)
        track_dicts = []
        calib = self._calibrations.get(camera_id, CalibrationEngine())
        h, w = frame.shape[:2]
        ts = datetime.now(timezone.utc).isoformat()

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
            bbox_hist.append(dict(t.bbox))
            if len(bbox_hist) > 12:
                bbox_hist.pop(0)

            speed_info = calib.update_track(camera_id, t.track_id, cx, cy, now_ts, t.class_name)
            td["metadata"] = {"speed_kmh": speed_info.get("speed_kmh", 0.0)}
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

        all_events: list[dict[str, Any]] = []
        camera_rules = [
            r for r in self._rules
            if not r.get("camera_id") or r.get("camera_id") == camera_id
        ]
        scaled_rules = self._scale_rules_to_frame(camera_rules, w, h)
        all_events.extend(self.event_generator.process_frame(camera_id, track_dicts, scaled_rules, ts))

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

        _, state_events, zone_dwell = self.state_engine.update(camera_id, frame_id, track_dicts, ts)
        all_events.extend(state_events)

        frame_histories = {
            t["track_id"]: self._track_history.get((camera_id, t["track_id"]), [])
            for t in track_dicts
        }
        frame_bbox_histories = {
            t["track_id"]: self._bbox_history.get((camera_id, t["track_id"]), [])
            for t in track_dicts
        }
        behavior_signals = self.behavior.evaluate_frame(
            track_dicts, frame_histories, frame_bbox_histories
        )
        all_events.extend(
            self.event_generator.emit_behavior_signals(camera_id, behavior_signals, ts)
        )

        speeds = [t.get("metadata", {}).get("speed_kmh", 0) for t in track_dicts]
        avg_speed = sum(speeds) / max(len(speeds), 1)
        scene_kw: dict[str, Any] = {}
        if rt.get("density_threshold") is not None:
            scene_kw["density_threshold"] = float(rt["density_threshold"])
        if rt.get("crowd_threshold") is not None:
            scene_kw["crowd_threshold"] = int(rt["crowd_threshold"])
        if rt.get("vehicle_threshold") is not None:
            scene_kw["vehicle_threshold"] = int(rt["vehicle_threshold"])
        _, scene_events = self.scene.analyze(
            camera_id, track_dicts, float(w * h), avg_speed, **scene_kw,
        )
        all_events.extend(scene_events)

        for t in track_dicts:
            speed_evt = calib.update_track(
                camera_id, t["track_id"],
                t["bbox"]["x"] + t["bbox"]["width"] / 2,
                t["bbox"]["y"] + t["bbox"]["height"] / 2,
                now_ts, t["class_name"],
            ).get("speed_event")
            if speed_evt:
                all_events.append(self.event_generator.emit_behavior_event(
                    camera_id, t["track_id"], speed_evt, 0.8,
                    {"speed_kmh": t.get("metadata", {}).get("speed_kmh", 0)}, ts, "warning",
                ))

        persons = [t for t in track_dicts if t.get("class_name") == "person"]
        all_events.extend(self.abandoned.process(camera_id, track_dicts, persons, ts))
        all_events.extend(self.scene_correlation.analyze(camera_id, track_dicts, zone_dwell, ts))
        all_events.extend(self._correlation_events(camera_id, all_events, track_dicts, ts))

        quality_events = self._check_video_quality(camera_id, frame, ts)
        all_events.extend(quality_events)

        all_events.extend(self.face_engine.process_frame(camera_id, frame, ts))
        all_events.extend(self.plate_engine.process_frame(camera_id, frame, track_dicts, ts))

        for evt in all_events:
            if self._org_ids.get(camera_id):
                evt["org_id"] = self._org_ids[camera_id]
            evt.setdefault("event", evt.get("event_type"))
            tid = evt.get("track_id")
            if tid is not None and evt.get("bbox") is None:
                for t in track_dicts:
                    if t.get("track_id") == tid and t.get("bbox"):
                        bb = t["bbox"]
                        fh, fw = frame.shape[:2]
                        evt["bbox"] = {
                            "x": bb["x"] / fw,
                            "y": bb["y"] / fh,
                            "width": bb["width"] / fw,
                            "height": bb["height"] / fh,
                        }
                        break
            org_id = self._org_ids.get(camera_id, "")
            if org_id:
                self.evidence.attach_evidence(camera_id, org_id, evt, frame)
            self.mqtt.publish_event(camera_id, evt)

        payload = frame_result.to_mqtt_payload()
        for i, det in enumerate(payload.get("detections", [])):
            if i < len(track_dicts):
                det["metadata"] = track_dicts[i].get("metadata", {})
        self.mqtt.publish_detection(camera_id, payload)
        return frame_result

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
        if blur_score < 50:
            events.append({
                "event_id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "event_type": "video_blur",
                "timestamp": ts,
                "severity": "info",
                "track_id": -1,
                "metadata": {"blur_score": blur_score},
            })
        return events
