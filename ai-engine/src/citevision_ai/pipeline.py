from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np

from citevision_ai.analytics.behavior import BehaviorHeuristics as AnalyticsBehavior
from citevision_ai.analytics.correlation import CorrelationEngine
from citevision_ai.analytics.state import StateEngine
from citevision_ai.budget.resource_budget import ResourceBudgetManager
from citevision_ai.detection.yolo_onnx import YoloOnnxDetector
from citevision_ai.events.generator import EventGenerator
from citevision_ai.models.schemas import BBox, Detection, DetectionFrame
from citevision_ai.mqtt.publisher import MqttPublisher
from citevision_ai.tracking.bytetrack import ByteTracker

logger = logging.getLogger(__name__)


class PipelineService:
    """Orchestrates detection, tracking, events, and MQTT publishing."""

    def __init__(
        self,
        detector: YoloOnnxDetector,
        budget: ResourceBudgetManager,
        mqtt: MqttPublisher,
    ) -> None:
        self.detector = detector
        self.budget = budget
        self.mqtt = mqtt
        self.event_generator = EventGenerator()
        self.state_engine = StateEngine()
        self.behavior = AnalyticsBehavior()
        self.correlation = CorrelationEngine()
        self._trackers: dict[str, ByteTracker] = {}
        self._frame_counters: dict[str, int] = {}
        self._rules: list[dict] = []

    def register_camera(self, camera_id: str) -> None:
        self.budget.register_camera(camera_id)
        self._trackers[camera_id] = ByteTracker(min_hits=1)
        self._frame_counters[camera_id] = 0

    def unregister_camera(self, camera_id: str) -> None:
        self.budget.unregister_camera(camera_id)
        self._trackers.pop(camera_id, None)
        self._frame_counters.pop(camera_id, None)

    def set_rules(self, rules: list[dict]) -> None:
        self._rules = rules

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        source_fps: float = 30.0,
    ) -> DetectionFrame:
        frame_id = self._frame_counters.get(camera_id, 0)
        self._frame_counters[camera_id] = frame_id + 1

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
        import cv2

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

        detections = [
            Detection(
                track_id=t.track_id,
                class_id=t.class_id,
                class_name=t.class_name,
                confidence=t.confidence,
                bbox=BBox(
                    x=t.bbox["x"],
                    y=t.bbox["y"],
                    width=t.bbox["width"],
                    height=t.bbox["height"],
                ),
            )
            for t in tracks
        ]

        h, w = frame.shape[:2]
        ts = datetime.now(timezone.utc).isoformat()
        frame_result = DetectionFrame(
            camera_id=camera_id,
            timestamp=ts,
            frame_id=frame_id,
            width=w,
            height=h,
            detections=detections,
        )

        track_dicts = [d.to_dict() for d in detections]
        self.state_engine.update(camera_id, frame_id, track_dicts)
        events = self.event_generator.process_frame(camera_id, track_dicts, self._rules, ts)

        for evt in events:
            self.mqtt.publish_event(camera_id, evt)

        self.mqtt.publish_detection(camera_id, frame_result.to_mqtt_payload())
        return frame_result
